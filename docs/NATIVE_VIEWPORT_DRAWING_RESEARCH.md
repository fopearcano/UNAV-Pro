# Native Viewport Drawing — Research Notes

What Cinema 4D's C++ SDK offers for "draw a packed array of points
in one call" and how UNAV Pro's native plugin will use it. This
document is a research record from the v0.8 spike; v0.9 implements
against it.

For the SDK plugin-type breakdown see
[`MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md`](MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md).
For the binary format the draw callback consumes see
[`BINARY_VISIBLE_SECTOR_FORMAT.md`](BINARY_VISIBLE_SECTOR_FORMAT.md).
For the scaling targets see
[`FUTURE_GPU_POINT_RENDERER.md`](FUTURE_GPU_POINT_RENDERER.md).

---

## 1. What we need from the editor viewport

UNAV Pro's render goal: 200 k – 2 M visible points, redrawn at
≥ 30 fps as the artist orbits / pans / zooms. Each point carries
position, colour, size, and a uid hash; the colour and size are
already baked into the binary visible-sector file by the v0.8
exporter, so the renderer only has to push them through.

Concrete requirements:

1. **One draw call per frame.** Per-primitive draws (one GL call
   per point) cap viewport throughput around 50 k objects on
   modern hardware. UNAV needs the SDK's array-draw path.
2. **GPU-resident buffer.** Re-uploading the buffer per frame
   wastes bandwidth and stalls the host. The buffer must persist
   across draws and re-upload only when the file on disk
   changes.
3. **Point sprite size mode.** Each point renders as a screen-
   space sprite with per-vertex size. Cinema 4D's editor
   supports point sprites in its native draw path (the
   `DRAWPATH` flag set varies per SDK release; v0.9 records the
   exact constant).
4. **Z-tested but unlit.** The point sprite is a constant-colour
   billboard; the editor's lighting / shading is a no-op.
5. **Hookable selection.** Click on a point in the viewport →
   yield the point's `uid_hash` so the dialog's metadata
   inspector can resolve it.

---

## 2. SDK paths, surveyed

### 2.1 `BaseDraw::DrawPoint(const Vector& p)`

Per-primitive helper. Issues one immediate-mode draw per call.
Intended for "small numbers of helper indicators" — debug cones,
manipulator handles, that kind of thing.

* **Where used in UNAV today:** the v0.1 `UNAV_DebugCone` is
  drawn via the equivalent path (`PRIM_CONE_*` parameters on a
  `c4d.Ocone` is sufficient because cones are one primitive per
  navigator). Native code keeps using this for the debug cone.
* **Where rejected:** the visible-sector hot path. 200 k calls
  per frame is unworkable.

### 2.2 `BaseDraw::DrawArray(...)`

The Maxon SDK's "vertex array" draw entry point. Takes:

* a vertex pointer + count,
* a primitive type (points / lines / triangles),
* optional per-vertex colour pointer,
* optional per-vertex normal pointer (unused for points),
* a Maxon `DRAWPATH` flag set ("editor / shaded / wireframe").

For point clouds we configure points-only with per-vertex colour;
size comes through Maxon's "point size" attribute set per draw
call.

* **Where used in UNAV (v0.9+):** the visible-sector renderer.
  One `DrawArray(POINTS, count=N, vertices=ptr, colours=ptr)`
  per editor pass.
* **Limitations:**
  * The vertex pointer must outlive the call; UNAV's
    `UnavPointBuffer` owns the storage so this is automatic.
  * `Vector` in Maxon's SDK is float-precision in viewport
    contexts; UNAV stores `double` and converts at the boundary
    using floating-origin (subtract the navigator pose before
    cast). Avoids float32 jitter at parsec scale.
  * Per-vertex sprite size: SDK exposes a global "point size"
    per draw call but not per-vertex sizes for the simple
    `DrawArray` overload. v0.9 starts with uniform size; v0.10+
    moves to a custom shader (see §2.4).

### 2.3 `BaseDraw::DrawArrayWithVertexBuffer(...)`

The 2023+ generation of the array-draw call. Same shape as 2.2
but with a Maxon-managed vertex-buffer object (VBO) lifetime.
The plugin pre-uploads the buffer once; subsequent draws are
"bind + issue".

* **Where used in UNAV (v0.10+):** the GPU-resident buffer
  path. v0.9 still uses 2.2 for simplicity; the v0.10 milestone
  switches when per-frame upload overhead becomes the limit.

### 2.4 Raw GL / Metal / DX (the escape hatch)

Inside a plugin's `Draw` callback the SDK exposes the platform
context. A plugin can issue raw `glDrawArraysInstanced(...)`,
`[id<MTLRenderCommandEncoder> drawPrimitives:...]`, or DX11
`Draw` calls.

* **Where considered:** v0.10+ for per-vertex sprite sizes and
  custom point-sprite shaders.
* **Cost:** per-platform code paths. Each UNAV release has to
  ship and test three of them (Win/macOS/[deprecated Linux]).
* **Constraint:** the plugin must NOT retain GPU resources
  across SDK boundaries. Maxon owns the device / queue;
  per-buffer handles are per-context. The SDK's
  `MSG_DEVICECHANGE` notifies the plugin when the GPU context
  cycles (driver reload, swapchain rebuild) — UNAV listens and
  re-uploads.

### 2.5 SceneHook redraw triggers

`SceneHookData::Execute` runs every redraw cycle. The hook
itself does not draw, but it is the canonical place to mark
the `UnavStarfield` dirty when the navigator pose changes,
which then triggers the host to re-call the ObjectData's
`Draw`.

---

## 3. Floating-origin and float32

Cinema 4D's viewport stack is float32. At parsec scale, that's
already lossy (1 pc ≈ 3.086 × 10¹⁶ m; float32 mantissa runs out
around the 1 m level for stars 10 pc out). The mitigation pattern
is **floating origin**:

* Keep all positions in `double` on the CPU side (the binary
  format already does — `UnavPoint::x/y/z` are `double`).
* Subtract the navigator's current world-space origin from every
  point at draw time, then cast to `float`.
* Update the navigator's "rebase origin" every time the artist
  flies a long distance.

The C++ Draw callback does the subtract-and-cast inline:

```cpp
const Vector navOrigin = navigator.GetMg().off;  // double precision
for (size_t i = 0; i < buf.size(); ++i) {
  Vector32 v = static_cast<Vector32>(buf[i].xyz - navOrigin);
  // push v into the per-frame upload
}
```

Maxon's SDK has a `Vector32` typedef; v0.9 uses it directly. The
upload is `count × (vec3<f32> + vec4<u8>) = count × 16` bytes per
frame, which is bandwidth-cheap even for 1 M points.

---

## 4. Selection / picking

Two paths considered:

### 4.1 SDK pick: `BaseDraw::PickObject`

Maxon's SDK exposes a `PickObject(BaseDocument*, BaseDraw*, x, y,
PickObjectFlags, ...)` that returns the topmost selectable
primitive at a screen-space coordinate. Plugins can opt into the
pick by overriding their `Draw` callback's "pick mode" branch
and emitting per-primitive IDs.

* **Used in UNAV (v0.10+):** the depth-pick selection bridge.
* **Limitations:** per-primitive ID is a single 32-bit int. UNAV
  encodes the point index (the array slot) directly; the
  metadata sidecar maps `slot → uid` for the inspector.
  ~4 billion slots is plenty.

### 4.2 Search-based fallback

Already implemented for v0.7 Point Cloud Mode (see
[`SEARCH_AND_TARGET_LOCK.md`](SEARCH_AND_TARGET_LOCK.md)). The
artist types a name / uid into the Search tab, gets a result,
clicks Focus. The native renderer doesn't have to participate —
the v0.6 Python panel resolves everything.

* **Used in UNAV today (and forever):** the always-on path, even
  after pick lands.

---

## 5. Threading model

* `Draw` runs on the editor main thread. The buffer must be
  read-only during the call. Mutations happen elsewhere (in
  the SceneHook's `Execute` or the diagnostic command's
  invocation), and they re-upload to the GPU as the next step.
* Maxon exposes `GeListNode::Message(MSG_THREAD_JOB)` for
  background work. v0.10's GPU-compute filter uses this; v0.9
  doesn't need it.

---

## 6. Lifetime

The native plugin's resource ownership cascade:

```
UnavStarfield (ObjectData instance)
└── unav::UnavPointBuffer (member)
    ├── std::vector<UnavPoint>   ← CPU
    └── (v0.10+) gpu_handle_t    ← GPU, freed in dtor

UnavSceneHook (SceneHookData instance) ← passive observer; no own data
UnavEngineDiagnostic (CommandData)     ← stateless query path
```

When the artist deletes the starfield, the `ObjectData::Free`
runs, the `UnavPointBuffer` destructor frees both halves. When
the host shuts down, `PluginEnd` (in `unav_native_plugin.cpp`)
unregisters the three classes.

---

## 7. SDK release pinning

Maxon publishes a "Cinema 4D SDK Release Notes" page per major
release. The relevant constraints v0.9 will pin against:

* C++17 minimum (some 2024.x SDKs require C++20; v0.9 targets
  the lowest-common-denominator).
* `BaseDraw::DrawArray` shape stable since R20; the
  `DrawArrayWithVertexBuffer` shape stable since R23.
* Plugin ID range stable since R10; PluginCafe registration
  required.
* `.c4d` file-format compatibility: the `Read`/`Write` calls
  serialise plugin state; the format itself is owned by the
  host and survives plugin migrations.

---

## 8. The v0.9 implementation order

1. Implement `UnavPointBuffer::loadFromFile(...)` against the
   v0.8 binary format. Pure CPU; no SDK calls. **Smoke test
   without C4D loaded.**
2. Wire `UnavStarfield::Init/Free` to allocate / release the
   buffer.
3. Wire `UnavStarfield::Draw` to `DrawArray`. Single call.
   **First in-viewport visualization.**
4. Wire the diagnostic command to surface "engine: native".
5. Update the Python diagnostics dialog to read the command.

After v0.9 ships, v0.10+ adds the GPU buffer, the depth-pick,
and the SceneHook-driven Auto Sync.

---

## 9. What we deliberately do not research yet

* Final-frame renderer integration (Standard / Physical /
  Redshift / Octane / Cycles). Phase G of the long roadmap;
  out of v0.8 / v0.9 scope.
* Cross-renderer instancing.
* Shader-based per-vertex sprite sizes.
* Custom material interfaces.
* Time-varying point clouds (animation timelines).
* Real-time per-frame catalog re-fetch (would require
  reworking the v0.2 streaming layer).

These all post-date the v0.9 milestone. The point of the spike
is to make sure the path **to** v0.9 is unblocked, not to
pre-design every future phase.
