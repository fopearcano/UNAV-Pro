# Camera-Relative Rendering

How the v1.0 binary v2 format and the v1.0 native renderer keep
visible sectors precise even when the absolute scene coordinates
are millions of float32 ULPs from the C4D origin. This is the
floating-origin pattern formalised at the file-format and
renderer level.

For the binary-format spec see
[`BINARY_VISIBLE_SECTOR_FORMAT.md`](BINARY_VISIBLE_SECTOR_FORMAT.md) §9.5.
For the renderer architecture see
[`GPU_BUFFER_ARCHITECTURE.md`](GPU_BUFFER_ARCHITECTURE.md).

---

## 1. The problem

Cinema 4D's viewport stack is float32. A star at 1000 pc from
the C4D origin has roughly 25-bit absolute precision; small
positional changes (sub-AU jitter from a drag-resync) start to
quantise visibly. At 100 kpc — a galactic-scale fly-through —
the precision drops to whole parsecs.

The fix is well-known: pick a local origin near the camera, store
positions relative to it, and rebase when the camera moves "far
enough". UNAV Pro applies this pattern at three layers:

1. **The data layer (v1.0).** The v2 binary format carries
   `sector_origin` in its extra header and an opt-in flag
   (`RENDERER_FLAG_POINTS_RELATIVE_TO_SECTOR_ORIGIN`) that says
   "the per-point xyz are offsets, not absolutes."
2. **The native loader.** When the flag is set, the C++ buffer's
   `worldPosition(index, ...)` re-adds `sector_origin` so any
   downstream code (picking, GPU-shadow build, debug draw) sees
   absolute world-space.
3. **The renderer.** The shader's `camera_origin` is subtracted
   from every vertex right before the float cast, so the GPU
   stage receives small floats regardless of how far the cluster
   is from the C4D origin.

---

## 2. The flag and the math

When ``RENDERER_FLAG_POINTS_RELATIVE_TO_SECTOR_ORIGIN`` is set:

```
world_position(i) = file_xyz(i) + sector_origin
```

When the flag is clear (the v0.8 / v0.9 default), the file's xyz
*is* the world position:

```
world_position(i) = file_xyz(i)
```

Either way, the renderer applies the floating-origin shift at
draw time:

```
gpu_position(i) = float32(world_position(i) - camera_origin)
```

The combined effect: even if the cluster is at parsec-scale
absolute coordinates, the GPU sees offsets in the metres /
sub-AU range and float32 jitter is invisible.

---

## 3. The Python side

`unav_pro/data/binary_export.py` exposes:

* `make_v2_extras(points, sector_origin=None, ...)` — builds the
  v2 extra-header block. `sector_origin=None` falls back to the
  bounding-sphere centre (the centroid of the points) so the
  default origin sits inside the cluster.
* `make_relative_points(points, sector_origin)` — returns a new
  list with each point's xyz expressed relative to the origin.
* `export_objects(..., camera_relative=True, sector_origin=...)`
  — convenience wrapper that does both: computes extras, sets
  the flag, rewrites the points, and writes the file.

The `NativeViewerBackend` defaults to `camera_relative=True` in
v1.0, so every Sync click under Native Viewer Mode produces a
floating-origin-friendly file.

---

## 4. The C++ side

`UnavPointBuffer::loadFromFile` parses the v2 extras into the
internal `extras_` slot. Every helper that reads point positions
goes through `worldPosition(index, &x, &y, &z)`:

```cpp
void UnavPointBuffer::worldPosition(
    size_t index, double* outX, double* outY, double* outZ) const {
  ...
  if (extras_.pointsAreRelative()) {
    x += extras_.sector_origin[0];
    y += extras_.sector_origin[1];
    z += extras_.sector_origin[2];
  }
  ...
}
```

The picking layer (`queryNearestPointToPosition`,
`queryNearestPointToRay`, `pickByRayAndScreenRadius`) all
consult `worldPosition` so their math is in absolute space —
the relative-storage flag is invisible to the picker.

The accel grid is also built in absolute space so picks against
camera-relative files behave identically to absolute files.

---

## 5. The renderer side

`RenderConfig::camera_origin` is a `double[3]` — the renderer
keeps it in double, subtracts at the boundary, and casts to
float32 just before the SDK call:

```cpp
const float gx = static_cast<float>(world_x - cfg.camera_origin[0]);
const float gy = static_cast<float>(world_y - cfg.camera_origin[1]);
const float gz = static_cast<float>(world_z - cfg.camera_origin[2]);
```

The CPU shadow stored in `UnavGpuBuffer` already has positions
in absolute float32 (after the relative-coords reconstruction);
the renderer applies the camera-origin subtract per draw call.
v1.1's GPU upload path may move this subtract into the shader
once Maxon's API for uniform doubles stabilises.

---

## 6. When to set `sector_origin`

The default (`make_v2_extras` without `sector_origin`) puts the
origin at the cluster centroid. Three patterns:

* **Stellar-scale clusters (≤ 100 pc).** Centroid origin is
  fine. The float32 precision after subtract is at the
  AU-or-finer level.
* **Galactic-scale clouds (1 kpc – 1 Mpc).** Set
  `sector_origin` to the navigator's pose (the C4D camera's
  world position) for best precision near the camera. Far-side
  points still suffer float32 jitter, but the visible region
  near the navigator is precise.
* **Multi-cluster scenes.** One file per cluster is the v1.0
  recommendation; multi-buffer rendering (one Native Point
  Viewer node per cluster) is a v1.1+ feature.

The dialog hides this knob in v1.0 — the backend always uses
the centroid. A future "Set Origin Manually" UI lets the artist
override it for the galactic-scale case.

---

## 7. Limits

* **Absolute precision is still float32 in C4D's viewport.** The
  floating-origin pattern moves the precision floor to the
  camera; it does not eliminate it. A galaxy 10 kpc away from
  the camera still has parsec-scale jitter.
* **Multiple sectors share one camera.** With one renderer per
  process, the camera origin is global. v1.1 per-`UnavStarfield`
  buffers will let separate navigators carry separate origins.
* **Origin updates require a re-export.** The binary file's
  `sector_origin` is fixed at write time. To change it, the
  artist re-clicks Sync (or Reload Native Viewer + a fresh
  request).
* **Renderer's `camera_origin` is updated per draw call.** The
  v1.0 renderer applies the subtract on the CPU; v1.1 may
  hoist it into the shader.

---

## 8. Tests

Python:

* `tests/test_binary_export_v2.py::test_make_relative_points_subtracts_origin`
* `tests/test_binary_export_v2.py::test_v2_camera_relative_round_trip_via_export_objects`

C++:

* `tests/test_unav_point_buffer.cpp::test_v2_load_camera_relative` —
  loads a v2 file with the flag set, verifies
  `worldPosition` reconstructs the absolute coordinates.
* `tests/test_unav_point_buffer.cpp::test_v2_load_absolute` —
  same but with the flag clear.

The two C++ tests are byte-bit identical fixtures except for
the flag bit and the per-point xyz; the loader must produce the
same `worldPosition` output for both.
