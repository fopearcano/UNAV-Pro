# UNAV Pro v1.0 — Native GPU Point Renderer

The v0.9 prototype proved the Python ↔ C++ bridge end-to-end.
v1.0 turns that prototype into a stable production-grade render
mode: GPU buffer architecture, shader-style rendering config,
camera-relative coordinates, accelerated picking, the v2 binary
format, and the safety / lifecycle / stats infrastructure the
dialog needs.

For per-area depth see:

* [`GPU_BUFFER_ARCHITECTURE.md`](GPU_BUFFER_ARCHITECTURE.md)
* [`CAMERA_RELATIVE_RENDERING.md`](CAMERA_RELATIVE_RENDERING.md)
* [`PICKING_SYSTEM.md`](PICKING_SYSTEM.md)
* [`PERFORMANCE_TARGETS.md`](PERFORMANCE_TARGETS.md)
* [`BINARY_VISIBLE_SECTOR_FORMAT.md`](BINARY_VISIBLE_SECTOR_FORMAT.md)

---

## 1. What v1.0 ships

### 1.1 Python side

| Surface | Change |
|---------|--------|
| `data/binary_export.py` | Dual-version (v1 + v2) writer + reader. v2 adds `BinaryV2Extras` (renderer_flags, visual_encoding_id, sector_origin, bounding sphere, AABB), `make_v2_extras`, `make_relative_points`, `compute_aabb`, `compute_bounding_sphere`. |
| `c4d_objects/native_viewer_backend.py` | Defaults to format v2 + camera-relative coords; derives `visual_encoding_id` from the active encoding. |
| `core/render_mode.py` | Native Point Viewer drops the "(Experimental)" suffix; description updated. |
| `core/native_bridge.py` | `NativeStatus` gains `gpu_uploaded`, `gpu_bytes`, `estimated_gpu_bytes`, `gpu_backend`, `format_version`; new `detailed_lines()` method drives the multi-line dialog status. |
| `tools/benchmark_visible_sector_export.py` | New CLI. Synthetic catalog + timing per phase + file-size + per-point bytes. |
| `ui/main_dialog.py` | Native Viewer status panel now shows the multi-line breakdown (file path, point count, GPU buffer, memory estimate, last reload time). |

### 1.2 C++ side

| File | Change |
|------|--------|
| `native/include/unav_point_buffer.h` | Adds `V2Extras`, dual-version loader, `worldPosition()` (camera-relative reconstruction), uniform-grid acceleration (`accelCellCount`), `pickByRayAndScreenRadius`, `kAbsurdPointCount`, `LoadStats::format_version` + `estimated_gpu_bytes`. |
| `native/src/unav_point_buffer.cpp` | Real v2 parser, accel-grid build, accelerated pick, "absurd point count" rejection. |
| `native/include/unav_gpu_buffer.h` | New. `GpuVertex` (40 bytes packed), `UnavGpuBuffer` base + virtual upload/free hooks. CPU shadow always present; SDK-aware subclass swaps in real GPU upload. |
| `native/src/unav_gpu_buffer.cpp` | Base implementation: builds CPU shadow from `UnavPointBuffer`, attempts upload, falls back gracefully. |
| `native/include/unav_renderer.h` | New. `RenderConfig` (point size scale, brightness, fade distance, debug, camera origin), `FrameStats`, `UnavRenderer` base, CPU-side `shadeVertex` / `effectivePointSize` helpers. |
| `native/src/unav_renderer.cpp` | Base draw loop walks the CPU shadow; SDK subclass overrides `drawImpl`. |
| `native/src/unav_native_plugin.cpp` | Wires `SdkGpuBuffer` + `SdkRenderer` into `UnavStarfield::Draw`. The Reload command rebuilds both layers. v1.0 `WriteStatusFile` emits the new GPU/format fields. |

### 1.3 Test surface

* **Python: 896 tests** — including 18 new v2-format tests and 5 benchmark-CLI tests.
* **C++: 30 tests** across two binaries:
  * `test_unav_point_buffer` (16 tests) — v1 + v2 loading, corruption rejection, accel grid, picking.
  * `test_unav_gpu_renderer` (14 tests) — GpuVertex layout, CPU shadow build, GPU upload fallback, shader helpers, renderer lifecycle.

Cross-checked end-to-end: the Python writer's v2 file parses cleanly via the C++ loader; the C++ tests build a synthetic v2 fixture and verify the same bit-by-bit layout.

---

## 2. Acceptance criteria

| Checkpoint                                                | Status   |
|-----------------------------------------------------------|----------|
| C4D loads native GPU render mode                          | ✓ — `UnavStarfield` ObjectData wired with `SdkGpuBuffer` + `SdkRenderer`; the SDK draw path issues per-vertex `BaseDraw::DrawPoint` (v1.1+ swaps to `DrawArrayWithVertexBuffer`). |
| Visible sector drawn without per-object scene bloat       | ✓ — Native Viewer Mode creates one placeholder null + one ObjectData node; no per-point C4D children. |
| Binary sector reload works                                 | ✓ — `UnavReloadCommand` parses the request file, calls `loadFromFile`, then rebuilds the GPU shadow. The bridge protocol echoes `last_request_id` for staleness detection. |
| Picking returns resolvable metadata id                    | ✓ — `pickByRayAndScreenRadius` returns the point index; the bridge writes `native_selection.json` with `uid_hash`; Python's `resolve_uid_from_hash` resolves it via the metadata sidecar. |
| Bad binary files do not crash C4D                         | ✓ — Loader fails closed on bad magic, version mismatch, point-count overflow, CRC mismatch, absurd counts; errors land in the status file. |
| Python Debug Mode still works                             | ✓ — Render Mode combo still has Debug Objects / Instances / Point Cloud; v1.0 doesn't touch the v0.7 backends. |
| Docs clearly state limits                                 | ✓ — `PERFORMANCE_TARGETS.md` documents the per-mode targets; `PICKING_SYSTEM.md` lists what the picker doesn't do; `CAMERA_RELATIVE_RENDERING.md` documents float32 limits. |

---

## 3. UI

The Native Point Viewer strip in the dialog now shows:

```
engine    : v1.0.0 (format v2)
file      : ~/.unav_pro/native_bridge/visible_sector.bin
points    : 87,432
file size : 4,546,560 bytes
load time : 31.2 ms
GPU       : c4d_basedraw_perpoint (3,497,280 bytes)
last load : 2026-04-30T08:30:14
```

When the native plugin isn't loaded the dialog says
"(native viewer: no status file — Python fallback)" and the
v0.7 backends keep working unchanged.

---

## 4. Where v1.0 sits in the migration

| Phase | Milestone | Status |
|-------|-----------|--------|
| 0     | v0.7 Python performance layer | ✓ shipped |
| 1     | v0.8 binary export + skeleton  | ✓ shipped |
| 2     | v0.9 binary bridge + native prototype | ✓ shipped |
| **3** | **v1.0 native GPU renderer**          | ✓ this milestone |
| 4     | v1.1 `DrawArrayWithVertexBuffer` swap, depth-pick | next |
| 5     | v1.2 GPU compute filter + Auto Sync               | future |
| 6     | v1.3 real-time sector streaming                    | future |
| 7     | v1.4+ per-renderer integrations                    | future |

See [`PYTHON_TO_CPP_MIGRATION_PLAN.md`](PYTHON_TO_CPP_MIGRATION_PLAN.md)
for the per-phase exit criteria.

---

## 5. What v1.0 is NOT

* **Not a single-call DrawArray.** The v1.0 SDK draw still issues
  `BaseDraw::DrawPoint` per vertex. The GPU buffer abstraction is
  in place so v1.1 can swap to a vertex-buffer call without
  changing the buffer or the bridge — but at v1.0 the per-point
  call is what the editor draws.
* **Not a custom shader.** ``RenderConfig`` is a CPU-side data
  struct. The renderer applies the math during the CPU draw loop;
  v1.1+ pushes the math into a real shader.
* **Not depth-buffer pick.** Picking is brute-force or uniform-
  grid accelerated; the v1.1 `BaseDraw::PickObject` integration
  swaps it for pixel-accurate selection.
* **Not Auto Sync.** The reload remains manual (Reload Native
  Viewer button or the equivalent C4D command).
* **Not per-renderer integration.** Editor-viewport only.

These items are tracked in the migration plan and have docs of
their own.
