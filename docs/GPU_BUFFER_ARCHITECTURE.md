# GPU Buffer Architecture

How the v1.0 native renderer holds visible-sector points in a way
that makes the future jump to a real GPU vertex buffer a one-file
change. v1.0 already ships the architecture; the GPU upload path
is a virtual hook that v1.1 will populate with Maxon's
`BaseDraw::DrawArrayWithVertexBuffer`.

For the surrounding milestone scope see
[`V1_0_GPU_RENDERER.md`](V1_0_GPU_RENDERER.md).

---

## 1. Two layers, three classes

```
+----------------------------+
|     UnavRenderer           |  shader-style config + draw loop
+----------------------------+
              |
              v  setGpuBuffer(...)
+----------------------------+
|     UnavGpuBuffer          |  packed CPU shadow + GPU upload hook
+----------------------------+
              |
              v  buildFromCpu(buf)
+----------------------------+
|     UnavPointBuffer        |  on-disk records, sector_origin,
|                            |  accel grid, picking
+----------------------------+
```

Three classes, three concerns:

* **`UnavPointBuffer`** owns the records loaded from the binary
  file. Double-precision positions, full v2 metadata, accel grid
  for picking. SDK-free.
* **`UnavGpuBuffer`** owns a packed CPU shadow of the per-vertex
  attributes the renderer needs (`GpuVertex`, 40 bytes packed),
  plus an opaque GPU handle that an SDK-aware subclass populates.
  SDK-free at the base class.
* **`UnavRenderer`** owns the artist-facing shader config
  (`RenderConfig`) and the draw loop. SDK-free at the base class;
  the SDK subclass overrides `drawImpl` with a real
  `BaseDraw::DrawPoint` (v1.0) / `DrawArrayWithVertexBuffer`
  (v1.1+) call.

The plugin shell instantiates one `SdkGpuBuffer` + one
`SdkRenderer` per process (subclasses of the base classes that
add Maxon's draw helpers); the base classes are what the unit
tests cover.

---

## 2. `GpuVertex` — 40 bytes packed

```cpp
#pragma pack(push, 1)
struct GpuVertex {
  float x, y, z;          // 12 bytes — world-space, post relative-coords
  float size;             //  4 bytes
  float r, g, b;          // 12 bytes
  uint64 uid_hash;        //  8 bytes
  uint32 source_id;       //  4 bytes
};
#pragma pack(pop)
```

Total: 40 bytes. Static asserted to keep the renderer / tests in
sync with the layout. Compared to the on-disk `UnavPoint` (52
bytes), the GPU shadow strips the double-precision positions
(positions become float after the camera-relative subtract).
Tests cover both layouts so a future packing tweak is caught at
compile time.

The trim from 52 → 40 is deliberate: 200k points × 12 bytes saved
= 2.4 MB less GPU traffic per upload.

---

## 3. CPU fallback (the v1.0 default)

`UnavGpuBuffer::buildFromCpu` always builds the CPU shadow. It
then asks `uploadImpl()` to push to the GPU; the base class
returns false ("no GPU available") and `isUploaded()` stays
`false`. The renderer's draw loop walks the CPU shadow in that
case — slower than a real VBO call but correct, and the path
unit-tested in any C++17 host.

The SDK subclass `SdkGpuBuffer` (in `unav_native_plugin.cpp`)
v1.0 still returns false from `uploadImpl` because Maxon's
`DrawArrayWithVertexBuffer` requires a host context the editor
owns; the plugin uses `BaseDraw::DrawPoint` per-vertex. v1.1
flips the implementation: `uploadImpl` calls the SDK's
buffer-allocator, copies `vertices_.data()` over, and reports the
GPU bytes consumed via `recordUploadOk(...)`.

When the upload succeeds, `isUploaded() == true` and the renderer
calls the SDK's array-draw entry point. When it fails (driver
reload, allocation failure, host shutting down), the next draw
falls back to the CPU shadow automatically — the renderer's
`drawImpl` never crashes on a missing GPU resource.

---

## 4. `RenderConfig` — shader-style knobs

```cpp
struct RenderConfig {
  float point_size_scale  = 1.0f;
  float brightness_scale  = 1.0f;
  float fade_distance     = 0.0f;   // 0 = no fade
  bool  antialiased_points = true;
  double camera_origin[3]  = {0, 0, 0};
  bool  debug_draw         = false;
};
```

Five artist-level parameters (size scale, brightness, distance
fade, AA hint, debug recolour) plus the `camera_origin` the
floating-origin pattern uses. `RenderConfig` is plain data; the
SDK subclass copies it into a uniform / push-constant when the
v1.1 shader path lands.

The CPU-side `shadeVertex` and `effectivePointSize` helpers in
`unav_renderer.cpp` are the reference implementation. The shader
in v1.1 will be byte-equivalent to these helpers; tests assert
the math behaves the same on both sides.

---

## 5. Lifecycle

```
PluginStart
  └─ UnavStarfield::Init                ← gRenderer.setGpuBuffer(&gGpuBuffer)
                                          (renderer + buffer share process state)

UnavReloadCommand::Execute
  ├─ LoadFromRequestFile(gNativeBuffer, …)
  ├─ gGpuBuffer.buildFromCpu(gNativeBuffer)   ← CPU shadow rebuilt; upload attempted
  └─ EventAdd()

UnavStarfield::Draw  (per redraw)
  ├─ if (gGpuBuffer.empty())
  │    gGpuBuffer.buildFromCpu(gNativeBuffer)  ← lazy first-frame init
  ├─ gRenderer.bindHostDraw(bd)
  └─ gRenderer.draw()                         ← walks shadow / VBO

UnavStarfield::Free
  └─ gRenderer.shutdown()                     ← releases GPU handle, clears buffer

PluginEnd
  └─ WriteStatusFile(...) "engine: gone"
  └─ gNativeBuffer.clear()
```

The Reload command rebuilds the buffer atomically: a Sync from
Python writes the binary file, posts the request, and the next
Reload click (or the v1.1 SceneHook auto-poll) triggers
`buildFromCpu` which atomically replaces the CPU shadow and
re-attempts the GPU upload.

---

## 6. Memory budget

The dialog's status strip surfaces three numbers:

* **CPU bytes** = `vertex_count × 40`. Always the live cost.
* **GPU bytes** = `vertex_count × 40` when uploaded, else `0`.
* **Estimated GPU bytes** (from `LoadStats::estimated_gpu_bytes`)
  = budget the safety advisory should reserve regardless of
  whether the upload succeeded yet.

The Python `NativeStatus` carries all three; the `detailed_lines()`
method formats them for the panel.

---

## 7. Safety

* **Hard upper bound on point count.** `UnavPointBuffer` rejects
  files with `point_count > kAbsurdPointCount` (50 M) before
  any allocation. The error is recorded in the status file's
  `error` field; Python surfaces it in the dialog log.
* **Per-load cap.** The Python load request can lower
  `maxPoints` per load. v1.0 keeps the default at 5 M (the C++
  default) — a clear ceiling well above the editor's realistic
  draw budget.
* **Allocation failure.** `uploadImpl` returning `false` is the
  fallback signal: the buffer keeps the CPU shadow and the
  renderer walks it. No exception, no half-state.
* **Shutdown.** `gNativeBuffer.clear()` runs in `PluginEnd`;
  `UnavRenderer::shutdown` calls `freeImpl` and clears the
  shadow. The bridge writes a final
  ``engine_available=false`` status before quitting.

---

## 8. Future tightening

* **Real GPU upload.** v1.1 swaps the SDK subclass's
  `uploadImpl` for a Maxon vertex-buffer call, with
  `MSG_DEVICECHANGE` re-upload handling.
* **Delta updates.** The bridge already carries
  `last_request_id`; a future format extension can ship
  add/remove deltas instead of full snapshots so the GPU
  upload is incremental.
* **Multiple buffers.** Today the plugin keeps one buffer per
  process. A future per-`UnavStarfield` buffer lets the artist
  load multiple visible sectors simultaneously (different
  navigators in the same scene).
* **Compressed vertices.** Half-float positions, packed RGB
  (8-bit per channel), or a deferred normal-from-mesh path are
  all options once the v1.1 GPU upload lands.
