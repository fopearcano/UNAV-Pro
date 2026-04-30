# UNAV Pro v0.8 — Native (C++) Feasibility Spike

The v0.7 performance layer (Debug Objects / Instances / Point
Cloud backends, see
[`V0_7_PERFORMANCE_LAYER.md`](V0_7_PERFORMANCE_LAYER.md))
took the Python plugin to its scaling ceiling for individual
scene nodes. v0.8 is a deliberate **spike**: lock the shape of
the future C++ Cinema 4D plugin, document what the Maxon SDK
allows, and ship the binary bridge the native side will read —
without claiming any native viewport rendering is complete.

This document is the entry point. The four siblings cover the
specifics:

* [`MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md`](MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md)
* [`NATIVE_VIEWPORT_DRAWING_RESEARCH.md`](NATIVE_VIEWPORT_DRAWING_RESEARCH.md)
* [`PYTHON_TO_CPP_MIGRATION_PLAN.md`](PYTHON_TO_CPP_MIGRATION_PLAN.md)
* [`BINARY_VISIBLE_SECTOR_FORMAT.md`](BINARY_VISIBLE_SECTOR_FORMAT.md)

Plus the new on-disk skeleton at
[`../native/`](../native/) — placeholders, not a build target.

---

## 1. The brief

Goal: determine the **safest** path from the Python prototype to
a native Cinema 4D plugin that draws large astronomical point
fields efficiently.

* **Python = data, index, cache.** The CLIs (`tools/fetch_*.py`,
  `tools/build_spatial_index.py`,
  `tools/export_visible_sector_binary.py`), the schema
  (`unav_pro/data/schema.py`), the spatial-index layer
  (`unav_pro/core/spatial_index.py`), the safety policies
  (`unav_pro/core/safety.py`), the dialog UI, the search /
  bookmarks / route / nav-controller modules all stay Python.
* **C++ = rendering, selection, scene hooks.** The C++ plugin
  takes over the visible-sector materialisation, the viewport
  draw, the picking bridge, and the live "Auto Sync" path.
* **The bridge is a file.** v0.8 ships the binary
  visible-sector format Python writes and C++ will read; there
  is no embedded ABI / pybind / shared memory in v0.8.

---

## 2. What v0.8 deliberately is and is not

### 2.1 Is

* A documentation pack: this file plus the four siblings.
* A C++ skeleton at `native/` with placeholder headers + stubs
  that pin the eventual C++ surface.
* A real Python binary exporter
  (`unav_pro/data/binary_export.py`) plus a CLI
  (`tools/export_visible_sector_binary.py`) that produces files
  the future native plugin will load.
* Tests covering the binary format's header / source-table /
  point round-trip / corruption rejection / source-id
  bookkeeping (32 new tests).

### 2.2 Is not

* A built native plugin. The CMakeLists.txt is a
  no-op-when-`UNAV_NATIVE_BUILD=OFF` placeholder.
* A loaded GPU renderer. `UnavPointBuffer::uploadPlaceholder`
  and `drawPlaceholder` are intentionally named so a casual
  reader cannot mistake them for shipping code.
* A Python ↔ C++ embedding. There is no pybind11 / ctypes /
  Maxon `MAXON.PYTHON` glue here. v0.9 will ship that bridge
  on top of the v0.8 surface.
* A replacement for the Python prototype. Every existing
  v0.1 – v0.7 contract still works; the v0.8 binary export is
  *additive*.

---

## 3. Audit — what stays in Python, what leaves

### 3.1 Stays in Python (forever or for a long time)

| Subsystem                                   | Why it stays Python                                               |
|---------------------------------------------|-------------------------------------------------------------------|
| `tools/fetch_*.py` (Gaia, JPL, SDSS, DESI)  | HTTP, CSV/JSONL parsing, archive-specific quirks. Stdlib-friendly; no perf benefit from native. |
| `unav_pro/data/schema.py`                   | The canonical row model. Pure CPython; the C++ side mirrors structs by hand. |
| `unav_pro/data/catalog_io.py`               | Local JSONL/CSV I/O. Fast enough; the binary path is for hot-loaded data only. |
| `unav_pro/data/connectors/*`                | Stdlib HTTP + CSV + the redshift proxy. No reason to leave.       |
| `unav_pro/core/spatial_index.py`            | Offline tooling; ran once per dataset. Native acceleration buys nothing here. |
| `unav_pro/core/safety.py`                   | Policy-driven; defining safety in C++ would be premature.         |
| `unav_pro/core/search.py`                   | In-memory lookup over a few thousand rows; trivially fast.        |
| `unav_pro/core/bookmarks.py`                | Persistent state; tiny.                                           |
| `unav_pro/core/navigation_controller.py`    | Math on three floats per step.                                    |
| `unav_pro/core/route.py`                    | Per-waypoint logic; trivially fast.                               |
| `unav_pro/ui/*`                             | The GeDialog stack. Maxon's Python API is the right tool here.    |
| `unav_pro/tests/*`                          | Pure-Python tests are the reference oracle for the C++ behaviour. |

### 3.2 Moves to C++ (in v0.9+)

| Subsystem                                    | Why it must leave Python                                           |
|----------------------------------------------|---------------------------------------------------------------------|
| `c4d_objects/point_cloud_builder.build_point_object` | One `BaseObject` allocation per row through the GIL. Caps at ~10 k. |
| `c4d_objects/render_backend.PointCloudBackend` (current placeholder) | Needs the Maxon `BaseDraw` extension to push a packed buffer. |
| `c4d_objects/instance_builder.InstanceBackend` | Helps to ~200 k; native instance arrays + GPU buffers go further. |
| Selection / picking from the viewport        | Can't be done correctly from Python at scale; needs depth-buffer access. |
| Live "Auto Sync" (per-frame)                 | Python hits the GIL on every frame; must be C++ + GPU compute.    |
| Floating-origin scene rebasing               | Per-object `SetAbsPos` from Python is the same per-row bottleneck.|

### 3.3 Hybrid — the bridge

| Subsystem                              | Where it lives                                                      |
|----------------------------------------|----------------------------------------------------------------------|
| Visible-sector cone filter             | Python today; v0.9 adds an optional C++ accelerator that takes the same input and produces the same output. |
| Visible-sector binary export           | Python (`unav_pro/data/binary_export.py`); C++ reads the same format. |
| Metadata sidecar                       | Python writes; both sides read.                                    |
| Diagnostics                            | Python dialog; queries C++ availability via the v0.9 extern "C".   |

---

## 4. The contract that v0.8 freezes

When v0.9 starts, three things are already locked:

1. **The on-disk binary format.** Documented in
   [`BINARY_VISIBLE_SECTOR_FORMAT.md`](BINARY_VISIBLE_SECTOR_FORMAT.md).
   The Python writer is the reference; the C++ reader is
   constrained to match.
2. **The C++ surface.** `native/include/unav_point_buffer.h`
   declares `UnavPoint`, `UnavPointBuffer`, `UnavSourceEntry`
   exactly as v0.9 will use them. Static-asserts in the header
   guard struct sizes against drift.
3. **The plugin-type plan.** Documented in
   [`MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md`](MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md).
   The v0.9 implementer registers exactly what the doc names —
   no more, no less.

Anything else (CMake details, GPU backend choice per platform,
exact `BaseDraw` registration call) is allowed to evolve.

---

## 5. The v0.9 milestone

v0.9 (the next milestone) ships the **first half** of the
native bridge:

* CMake glue against the Maxon SDK.
* `UnavPointBuffer::loadFromFile(...)` implemented; reads the
  v0.8 binary file produced by Python.
* A trivial `BaseDraw` callback drawing the loaded buffer as
  GL points (no instancing yet).
* Diagnostics dialog reports "engine: native loaded".

The Python plugin still owns generation; the native side is
read-only. v0.9 is when "is this whole thing actually
buildable" becomes a yes-or-no question, not a research
question.

v0.10+ then layers GPU instancing, depth-buffer picking, and
the per-frame Auto Sync path on top.

---

## 6. Risks the spike surfaces

* **Maxon SDK platform variation.** Cinema 4D 2023+ ships on
  Windows / macOS / (deprecated) Linux. Each has its own draw
  API expectation (DX11 / Metal / OpenGL). Mitigation: the
  `BaseDraw` abstraction Maxon provides ought to flatten these
  for the editor viewport; the spike doc records this assumption
  with citations.
* **Plugin ID collisions.** Plugin IDs must be registered with
  Maxon's PluginCafe, never invented. The skeleton uses
  placeholder IDs (1000001, 1000002, 1000003) that the v0.9
  implementer will replace. Mitigation: the doc flags this; the
  CMakeLists fail-closed unless `UNAV_NATIVE_BUILD=ON` is
  explicitly set.
* **C++17 ↔ Maxon SDK compiler ABI.** Maxon publishes the
  expected toolchain per SDK release. Mitigation: the spike's
  CMakeLists.txt notes this and v0.9 pins the toolchain there.
* **Float32 viewport precision.** The native renderer can keep
  positions in `double` on the CPU side but the GPU pipeline is
  float32. Mitigation: the floating-origin pattern documented in
  `UNAV_PRO_ARCHITECTURE.md §3.6` becomes mandatory at scale;
  the v0.9 plan records this.
* **Selection from a bare buffer.** Without per-object
  `BaseObject` nodes, "click to select" requires the depth-buffer
  pick path. Mitigation: the v0.6 search-based fallback (already
  shipping) covers users while the pick path matures.

---

## 7. Pointers

* C++ skeleton: [`../native/`](../native/)
* Binary format spec: [`BINARY_VISIBLE_SECTOR_FORMAT.md`](BINARY_VISIBLE_SECTOR_FORMAT.md)
* Plugin-type research: [`MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md`](MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md)
* Viewport-drawing research:
  [`NATIVE_VIEWPORT_DRAWING_RESEARCH.md`](NATIVE_VIEWPORT_DRAWING_RESEARCH.md)
* Migration plan:
  [`PYTHON_TO_CPP_MIGRATION_PLAN.md`](PYTHON_TO_CPP_MIGRATION_PLAN.md)
* The v0.7 layer that v0.8 builds on:
  [`V0_7_PERFORMANCE_LAYER.md`](V0_7_PERFORMANCE_LAYER.md)
* The longer-term ceiling discussion:
  [`ROADMAP_CPP_GPU_VERSION.md`](ROADMAP_CPP_GPU_VERSION.md)
* The future GPU renderer (where Point Cloud Mode ends up):
  [`FUTURE_GPU_POINT_RENDERER.md`](FUTURE_GPU_POINT_RENDERER.md)
