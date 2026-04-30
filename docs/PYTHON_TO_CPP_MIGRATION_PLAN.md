# Python → C++ Migration Plan

How UNAV Pro moves from the v0.7 Python prototype to the v0.9+
native plugin without breaking any existing scene, dialog
contract, or test. This is the sequencing doc; the design rationale
for each step lives in the linked references.

For the v0.8 spike summary see
[`V0_8_NATIVE_CPP_FEASIBILITY.md`](V0_8_NATIVE_CPP_FEASIBILITY.md).
For the existing long-form roadmap (which v0.9 starts executing
on) see
[`ROADMAP_CPP_GPU_VERSION.md`](ROADMAP_CPP_GPU_VERSION.md).

---

## 1. Guiding rules

1. **The Python plugin keeps working at every step.** Every
   release of the native plugin is *opt-in*: the dialog detects
   the native engine at startup; if it isn't present, the
   Python backends from v0.7 still run.
2. **The on-disk formats stay stable.** JSONL catalogs, the
   chunked spatial index, the project-state sidecars, the
   bookmarks file — none of them change in this migration. The
   v0.8 binary visible-sector file is *additive*.
3. **The dialog stays Python.** GeDialog UIs are the right
   surface for the data / search / route / nav-controller
   interactions.
4. **Tests are the oracle.** Every C++ behaviour that has a
   Python counterpart must agree with the Python tests on the
   small inputs those tests cover.

---

## 2. Phase ledger

| Phase | What ships                                                       | UNAV release |
|-------|------------------------------------------------------------------|--------------|
| 0     | v0.7 Python performance layer (already shipping)                 | v0.7         |
| 1     | C++ skeleton + binary export (this milestone)                    | v0.8         |
| 2     | Native CMake + `UnavPointBuffer::loadFromFile` + minimal `BaseDraw` | v0.9         |
| 3     | GPU-resident buffer + SceneHook + depth-pick                     | v0.10        |
| 4     | GPU compute filter + per-frame Auto Sync                         | v0.11        |
| 5     | Real-time sector streaming (read-ahead / LRU)                    | v0.12        |
| 6     | Per-renderer integrations (Standard / Physical / Redshift / Octane / Cycles) | v0.13+ |

The phases align with the "Phase A–G" naming in
[`ROADMAP_CPP_GPU_VERSION.md`](ROADMAP_CPP_GPU_VERSION.md): v0.9
= Phase C entry, v0.10 = Phase D entry, v0.11 = Phase D
completion, v0.12 = Phase E, v0.13+ = Phase G.

---

## 3. Phase 1 (v0.8) — done

This milestone. Concretely:

* `unav_pro/data/binary_export.py` — Python writer + reader.
* `tools/export_visible_sector_binary.py` — CLI.
* `unav_pro/tests/test_binary_export.py` — 32 tests.
* `native/` — skeleton folder with placeholder C++.
* Four feasibility / research docs (this file is one of them).
* No native build is wired; v0.8 ships zero compiled bytes.

Exit criteria (all met by this milestone):

* Python tests stay 100 % green (808 + 32 = 840).
* Binary file round-trip works at every supported size
  (empty / 3 / many).
* Corrupt-file rejection works for bad magic, bad version, bad
  CRC, truncated content, lying point counts.
* Native skeleton compiles in principle (header-only static
  asserts; CPP files are stubs).

---

## 4. Phase 2 (v0.9) — entry into native code

**Headline:** the native plugin loads, draws a static buffer, and
the Diagnostics dialog says "engine: native".

### 4.1 Build harness

* `native/CMakeLists.txt` flips `UNAV_NATIVE_BUILD` to a real
  target.
* Maxon SDK located via `MAXON_SDK_DIR`.
* CI runs CMake configure on at least one platform. Full builds
  require a Maxon SDK install which CI may or may not have;
  failure to find the SDK is a clear "skipped" status, not a
  broken build.

### 4.2 Implement `UnavPointBuffer::loadFromFile`

* Open the v0.8 binary file.
* Parse the header.
* Validate the CRC.
* Populate `points_` and `sources_` directly from the on-disk
  layout (the C++ struct matches under `#pragma pack(push, 1)`,
  so a `memcpy` plus an endianness check suffices on
  little-endian hosts).
* Return point count on success, set `errorOut` on failure.

This is **the** interop test: the same file the Python
`write_visible_sector` produces must parse to the same point
count and the same `uid_hash` values on the C++ side. v0.9 ships
a tiny C++ test executable (`test_unav_point_buffer.cpp`)
exercising this against the same test fixtures the Python tests
use.

### 4.3 Register `UnavStarfield` ObjectData

* `Init` allocates a `UnavPointBuffer`.
* `Free` releases it.
* `Read` / `Write` serialise the binary file's path into the
  document.
* `Draw` issues a single `BaseDraw::DrawArray(POINTS, ...)`
  call against the loaded buffer.

The class registers under the placeholder PluginID
`kPluginIdUnavStarfield = 1000001` until Maxon's PluginCafe
issues a real ID.

### 4.4 Register `UnavEngineDiagnostic` CommandData

* Returns `EngineStatus { available=true, version="0.9.0",
  description="UNAV native engine — single-pass DrawArray" }`.
* The Python Diagnostics dialog polls this on startup and
  shows the result.

### 4.5 Python side

* Add a `core/native_engine.py` (Python) module that uses
  `ctypes` (or whichever bridge v0.9 picks) to invoke the
  diagnostic command and read the status.
* `core/scene_sync.py` gains an opt-in path: when the native
  engine reports `available=true`, the dialog can ask it to
  load the binary file in addition to (or instead of) the
  current Python backends.
* The Render Mode combo gains a fourth entry **Native (read-
  only)** that points at the v0.9 path. The first three modes
  keep working unchanged.

### 4.6 Exit criteria

* The same binary file produced by Python loads in C++ on
  Windows + macOS, surfaces the documented point count, and
  draws as a static field of dots in the editor viewport.
* The Diagnostics dialog reports "engine: native v0.9.0" when
  the .xdl/.cdl is installed and "engine: python (fallback)"
  otherwise.
* Every existing Python test stays green.
* No GPU code yet; `BaseDraw::DrawArray` is the entire renderer.

---

## 5. Phase 3 (v0.10) — performance + selection

**Headline:** the native renderer holds the buffer GPU-side,
and clicking a point yields the uid.

* Switch from `DrawArray` to `DrawArrayWithVertexBuffer` (or
  the platform raw-GL/Metal/DX path under a host-platform
  switch). The buffer uploads once and stays GPU-resident.
* Implement `UnavPointBuffer::queryNearestPoint(...)` against
  the depth buffer. Maxon's `BaseDraw::PickObject` is the
  entry point; per-primitive IDs are the point's array index;
  the metadata sidecar resolves index → uid → metadata.
* Register `UnavSceneHook` to listen for navigator-pose
  changes (it sets a "buffer dirty wrt floating origin" flag
  the next `Draw` consumes).
* The Python dialog grows a "Use Native Selection" checkbox
  that when on routes Inspect Selected Object through the
  native pick path; when off, the v0.6 search-based fallback
  remains.

Exit criteria:

* 200 k points draw at ≥ 60 fps on a modern integrated GPU.
* Click-pick in the viewport yields a uid the inspector
  resolves.
* Auto Sync still a placeholder checkbox (it lands in v0.11).

---

## 6. Phase 4 (v0.11) — GPU compute filter + Auto Sync

**Headline:** the navigator drags, the visible sector follows
at framerate.

* Port the cone filter to a GPU compute kernel (CUDA / Metal /
  Vulkan compute) running over the catalog's full
  cartesian-pc array.
* Per-frame: the SceneHook detects the navigator move, kicks
  the compute kernel, the kernel writes a survivor mask, the
  ObjectData rebinds the point buffer, the next draw shows
  the new sector.
* Auto Sync becomes a real feature — the checkbox now flips a
  flag the SceneHook reads.

Exit criteria:

* 1 M-row catalog filters at ≥ 30 Hz against a single GPU.
* Auto Sync drives the visible sector live as the artist
  drags the navigator.
* The Python sector-streaming layer (v0.2) stays the
  authoritative path for the offline cache; the GPU filter
  works *within* a loaded chunk.

---

## 7. Phase 5 (v0.12) — real-time sector streaming

**Headline:** infinite-catalog navigation, cache-bound.

* The native side caches loaded chunks; the host-side cone
  filter prefetches the cells the cone is about to enter.
* LRU-evict the cells leaving the cone.
* The on-disk index format does not change (the spatial-index
  layer's contract is the same).

Exit criteria:

* Catalogs the size of full Gaia DR3 (1.8 B sources) navigate
  at framerate on a single workstation given enough disk
  bandwidth.

---

## 8. Phase 6 (v0.13+) — renderer integrations

Each final-frame renderer (Standard / Physical / Redshift /
Octane / Cycles) gets its own integration. Out of v0.8 / v0.9 /
v0.10 / v0.11 / v0.12 scope; tracked in
[`ROADMAP_CPP_GPU_VERSION.md`](ROADMAP_CPP_GPU_VERSION.md) §3
Phase G.

---

## 9. Backout plan

If at any phase the native build is too unstable or the SDK
constraint set tightens unexpectedly, the migration backs out
without losing user-facing functionality:

* The Python prototype still runs at v0.7 capacity.
* The dialog hides the "Native" Render Mode entry when the
  engine is unavailable.
* The binary format remains useful as a *cache* artifact —
  v0.7 Python can read it, even though it won't draw it any
  faster than the JSONL path.
* All v0.6 UX features (search / target lock / bookmarks /
  route / step) keep working.

The migration is therefore *uniformly reversible* until the
native side becomes the *only* renderer (which is not on the
roadmap — Python remains the always-available fallback).

---

## 10. Risk register

| Risk                                                   | Phase   | Mitigation                                                 |
|--------------------------------------------------------|---------|------------------------------------------------------------|
| Maxon SDK ABI changes between releases                | 2       | Pin the lowest-common SDK that supports C4D 2023+; document compiler version. |
| PluginCafe ID assignment delay                         | 2       | Ship behind PluginCafe-issued IDs only; placeholder IDs in the skeleton are dev-only. |
| GPU driver-specific point-sprite quirks                | 3       | Stay in Maxon's `DrawArray` family until per-platform code is necessary. |
| `MSG_DEVICECHANGE` not firing on every host           | 3       | Treat the SceneHook's redraw as a re-upload trigger as a fallback. |
| Per-frame compute saturating shared memory bandwidth  | 4       | Combine with the v0.2 sector-streaming prefilter so the GPU never sees more than the cone-touched cells. |
| Cosmology / animation timeline pressure                | 5+      | Out of scope; tracked separately in the data-layer roadmap. |

---

## 11. Communications surface

Throughout all phases the user-visible surface stays:

* **Dialog buttons.** Same names, same logs.
* **Render Mode strip.** Gains "Native" in v0.9; Debug Objects
  / Instances / Point Cloud all keep working.
* **Diagnostics dialog.** New "Engine" line: native version /
  python fallback.
* **CLIs.** Unchanged.

The artist who never reads any docs sees only an extra Render
Mode option and a faster scene at high object counts.
