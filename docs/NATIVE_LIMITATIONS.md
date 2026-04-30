# Native Point Viewer — Limitations (v0.9 prototype)

The v0.9 milestone is a **working end-to-end proof**, not a
production renderer. This document is the honest list of what
the prototype does **not** do today, so artists pick the right
mode and v0.10+ implementers know exactly what to ship next.

For the prototype's scope see
[`V0_9_NATIVE_VIEWER_PROTOTYPE.md`](V0_9_NATIVE_VIEWER_PROTOTYPE.md).
For the bridge protocol see
[`BINARY_BRIDGE_WORKFLOW.md`](BINARY_BRIDGE_WORKFLOW.md).
For the future GPU path see
[`FUTURE_GPU_POINT_RENDERER.md`](FUTURE_GPU_POINT_RENDERER.md).

---

## 1. Drawing

* **Per-point `BaseDraw::DrawPoint`.** Each visible point is one
  SDK call inside the plugin's `Draw` callback. Fine for a few
  thousand points to demonstrate the pipeline; unworkable past
  ~10 k.
* **No `DrawArray` or `DrawArrayWithVertexBuffer`.** v0.10
  swaps in the single-call array path documented in
  [`NATIVE_VIEWPORT_DRAWING_RESEARCH.md`](NATIVE_VIEWPORT_DRAWING_RESEARCH.md)
  §2.2. The buffer is already laid out for it; only the draw
  call changes.
* **No GPU buffer.** The point array lives on the CPU and is
  walked every frame. v0.10 uploads to a vertex buffer object;
  the plugin re-uploads only when the request file's mtime
  changes.
* **No point sprites / shaders.** Each point is a constant-size
  pixel-sprite the SDK provides. No size-by-magnitude on the
  GPU side, no per-vertex sizes, no custom shading.
* **No floating origin.** Positions are passed in world space
  every frame. At parsec scale, float32 jitter is visible past
  ~100 pc from the origin. v0.10 subtracts the navigator pose
  before the cast-to-float.

## 2. Selection / picking

* **Manual selection only via the search panel.** v0.9's
  `UnavStarfield::Draw` does **not** implement a per-frame
  pick path; the v0.6 search-based fallback is the
  recommended workflow.
* **Reserved selection bridge.** The bridge protocol
  ([`BINARY_BRIDGE_WORKFLOW.md`](BINARY_BRIDGE_WORKFLOW.md) §2.3)
  defines `native_selection.json`; the C++ side has the
  `queryNearestPointToRay` / `queryNearestPointToPosition`
  hit-tests; the plugin shell exposes
  `WriteSelectionFile`. v0.9 does not register a click
  callback on the `BaseDraw` — that lands in v0.10's
  `BaseDraw::PickObject` integration.
* **No depth-buffer pick.** Even the v0.10 plan falls short of
  pixel-accurate pick at 60 fps; that's reserved for v0.11+
  alongside the GPU pipeline.

## 3. Visual encoding

* **Baked at export time.** The Python exporter pipes every
  visible row through `core.visual_encoding.encode(...)`,
  bakes the (RGB, size) tuple into the binary, and the C++
  side reads the baked values. v0.9 does **not** apply any
  visual encoding on the native side.
* **No live encoding switch.** Changing the Render Mode
  combo's colour mode while in Native Viewer Mode requires
  another Sync click (or the explicit `Export Visible Sector
  (Binary)` button) to re-export.
* **No level-of-detail.** Every visible point draws every
  frame regardless of distance.

## 4. Animation

* **No per-frame ephemeris.** The v0.4 JPL Horizons spike
  shipped as a one-epoch snapshot; v0.9 keeps the same
  snapshot model. The buffer is rebuilt on the next Sync
  click, never per frame.
* **No interpolation.** Switching mode / re-syncing produces
  an instant cut, not a fly-through.

## 5. Auto Sync

* **No file-watcher.** v0.9's reload is **manual** —
  `UnavReloadCommand` registers a Cinema 4D command the
  artist invokes from the menu (or the dialog's *Reload
  Native Viewer* button writes a fresh request).
* **No SceneHook.** The v0.10 SceneHook polls the request
  file per-redraw and re-loads automatically; v0.9 does not.
* **No live navigator follow.** Per-frame re-sync as the
  artist drags the navigator is a v0.11 GPU-compute
  feature; v0.9 expects an explicit Sync click.

## 6. Render-pass parity

* **Editor only.** Like every other render backend in v0.7+,
  the Native Point Viewer paints into the C4D editor
  viewport, not into final-frame renderers.
* **No Standard / Physical / Redshift / Octane / Cycles
  integration.** Phase G of the long roadmap; out of v0.9
  scope.

## 7. Threading

* **Main-thread only.** All loads run inline on the host's
  main thread (the plugin's command callback). Big files
  (≥ 100 k points) will stall the editor for the load
  duration. v0.10's GPU upload runs the same way; v0.11
  moves the reads to a background thread.

## 8. Schema and version

* **Binary format v1.** Locked in v0.8. Bumping the format
  version requires both Python (`unav_pro/data/binary_export.py`)
  and C++ (`native/src/unav_point_buffer.cpp`) coordinated
  changes. The Python writer + C++ reader fail closed on
  unknown versions today.
* **Bridge schema v1.** Same: bump invalidates older clients.
* **Plugin IDs are placeholders.** The native plugin
  registers under PluginIDs `1000001` / `1000002` /
  `1000003`. v0.10 replaces these with PluginCafe-issued
  IDs before the plugin can ship publicly.

## 9. Selection guarantees

* **Hash collisions theoretically possible.** `uid_hash` is
  64-bit BLAKE2b. The birthday-paradox collision probability
  at 1 M points is ≈ 2.7 × 10⁻⁸ — vanishingly small but
  non-zero. The Python resolver returns the first match in
  the candidate list; if a future format keeps both the hash
  *and* the original uid in the binary file, the resolver
  becomes exact.
* **No multi-select.** A single click yields a single uid;
  rubber-band selection in the viewport is not implemented.

## 10. UX rough edges

* **The placeholder null.** When Native Viewer Mode is
  active, a single `UNAV_NativeViewerPlaceholder` null
  appears under `UNAV_VisibleSector` so the editor knows
  the cloud exists. Without it, the artist would see no
  scene-graph indication of an active visible sector at
  all.
* **Mode switches don't migrate state.** Flipping from
  Instances to Native Viewer requires a fresh Sync click.
* **Status strip is request-driven, not auto-refreshed.**
  The dialog's native-status label only updates when the
  artist clicks one of the three Native bridge buttons.

---

## 11. What v0.9 is not

* **Production C++ plugin.** It is a feasibility prototype
  with the v0.8 surface filled in.
* **Replacement for the Python prototype.** Every existing
  v0.1 – v0.7 contract still works; the native viewer is
  one of four render-mode options.
* **Public API.** The plugin IDs, the SDK glue, and the
  bridge protocol are all internal to the v0.9 prototype.
  Public API stabilisation lands when v0.10's GPU buffer
  + selection bridge ship together.

When v0.10 lands, this document grows a "what changed"
section and the items above migrate into "shipped" /
"deferred to v0.11+" buckets. Until then, v0.9 is the
honest end-to-end proof: Python writes a file, C++ loads
it, points appear in the viewport.
