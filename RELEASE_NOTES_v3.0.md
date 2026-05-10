# UNAV Pro v3.0 — Large-Scale Workflow Optimization

Release date: 2026-05-10
Codename: *Large-Scale Workflow Optimization*

v3.0 is the **scalability and streaming** milestone. The
goal: make UNAV capable of handling very large
astronomical datasets in a stable, production-oriented way
inside Cinema 4D.

This is **not** rendering. This is scalability, navigation
responsiveness, dataset streaming, and workflow efficiency.
The runtime feature surface is unchanged from v2.5; v3.0
adds the scaffolding that makes the existing surface
survive 10 M-row catalogs and a working artist's
iterate-fast loop.

---

## Highlights

* **Chunk-reuse cache.** New
  `unav_pro/db/streaming.py::ChunkReuseCache` — an LRU
  keyed by quantised pose + cone parameters + filter
  sets + epoch. When the artist re-syncs at the same
  pose, the result is served from cache. Hit ratio is
  surfaced in the diagnostics panel.
* **Paged loading.** `iter_paged_cone(...)` streams a
  cone-query result page-by-page (default 5 000 rows
  per page) so a 250 K-row sector can dispatch through
  the task queue without ever materialising the whole
  list.
* **Cone-query caps.** `QueryCaps` centralises bbox
  row caps + multipliers + hard ceilings. The default
  multiplier was bumped from 4× (v1.7) to 6× to give
  the cone refine more slack on anisotropic catalogs.
* **Query timing log.**
  `db.spatial_query.GLOBAL_QUERY_TIMING_LOG` records
  every cone query's bbox / refine / total elapsed in
  a bounded ring buffer. Surfaced in the diagnostics
  panel as "recent" + "slowest" + "mean".
* **Partial-rebuild planning.** `core/scene_sync.py`
  gains `SyncDiff.is_unchanged`,
  `plan_overlay_rebuild`, `plan_science_rebuild`, and
  `plan_mission_update`. The C4D builders read these
  to skip backend round-trips when nothing changed.
* **Lightweight task queue.** New
  `unav_pro/core/task_queue.py` — a cooperative
  single-threaded queue with progress + cancellation.
  **No threads.** C4D API calls stay on the main
  thread. Long-running operations report progress
  between steps and honour cancellation cooperatively.
* **Diagnostics.** New
  `unav_pro/core/diagnostics.py` — pure helpers for the
  diagnostics panel: dataset memory estimate,
  visible-sector estimate, long-operation classifier,
  cache + timing renderers, overlay/science layer
  counts.

## What's new in detail

### Modules

* `unav_pro/db/streaming.py` (new) — pagination, chunk
  reuse cache, cache invalidation, repeated-query
  detector.
* `unav_pro/core/task_queue.py` (new) — `Task`,
  `TaskQueue`, `TaskStatus`, `make_chunked_task`,
  `GLOBAL_TASK_QUEUE`.
* `unav_pro/core/diagnostics.py` (new) — pure helpers
  for the diagnostics panel.

### Module extensions

* `unav_pro/db/spatial_query.py` — `QueryCaps`,
  `QueryTimingLog`, `GLOBAL_QUERY_TIMING_LOG`. The
  `query_cone` and `query_cone_for_navigator`
  functions accept `caps=`, `timing_log=`,
  `timing_note=` kwargs.
* `unav_pro/core/scene_sync.py` —
  `SyncDiff.is_unchanged`, `OverlayRebuildPlan`,
  `ScienceRebuildPlan`, `MissionUpdatePlan`,
  `plan_overlay_rebuild`, `plan_science_rebuild`,
  `plan_mission_update`.

### Documentation

* `docs/V3_0_SCALABILITY_AND_STREAMING.md` —
  milestone overview.
* `docs/LARGE_DATA_WORKFLOWS.md` — artist-facing
  patterns for working with multi-million-row
  catalogs.
* `docs/SAFE_TASK_QUEUE_MODEL.md` — the cooperative
  scheduling model and runner contract.
* `docs/QUERY_OPTIMIZATION.md` — `db/spatial_query.py`
  + cache + timing log internals.

### Release engineering

* `PLUGIN_VERSION` 2.5.0 → 3.0.0; codename
  *Large-Scale Workflow Optimization*.
* `RELEASE_NOTES_v3.0.md` (this file).
* CHANGELOG entry.
* Packaging script ships the four new docs +
  release notes; `REQUIRED_FILES` updated.

## What didn't change

* No new on-disk schemas. Mission JSON, Route JSON,
  Camera Path JSON, Export Manifest, DB schema,
  binary format are all v2.5 byte-identical.
* No new runtime dependencies. Stdlib-only at runtime.
* No rendering, no IPC, no RelativityRender bridge.
* No threading. The task queue is explicitly
  single-threaded; C4D API contracts are honoured.
* No replacement of core architecture. v0.1 → v2.5
  authoring surfaces continue to work unmodified.

## Migration

* **Drop-in v2.5 upgrade.** v2.5 saves load cleanly in
  v3.0. No format change.
* The new modules are **opt-in**: existing call sites
  continue to work; the v3.0 wrappers light up when
  callers wire them in (e.g. passing a
  `ChunkReuseCache` to `do_sync` or routing a long
  operation through the `TaskQueue`).
* The `query_cone` / `query_cone_for_navigator` calls
  now accept new optional kwargs (`caps`,
  `timing_log`, `timing_note`); existing calls
  continue to work without them.

## Acceptance

* [x] Large datasets remain manageable (SQL-level
  bbox cap derived from `max_visible_objects`).
* [x] Repeated navigation is more responsive (cache
  hit ratio surfaces in diagnostics).
* [x] Unnecessary rebuilds are reduced
  (`SyncDiff.is_unchanged` short-circuit + rebuild
  planners).
* [x] UI remains usable during heavier operations
  (cooperative task queue with progress +
  cancellation).
* [x] Dataset diagnostics are understandable
  (`build_diagnostics_report` renders plain text).
* [x] No renderer assumptions.
* [x] No unsafe threading (queue is single-threaded;
  C4D API calls stay main-thread).

## Testing

* Full suite passes: **1895 tests** (1777 v2.5 baseline
  + 118 new v3.0 tests).
* New v3.0 test files:
  * `test_v30_streaming.py` — pagination, cache
    reuse, invalidation, key quantisation.
  * `test_v30_query_caps.py` — `QueryCaps` decision
    logic, timing-log ring buffer.
  * `test_v30_partial_sync.py` — `SyncDiff`, overlay
    / science / mission rebuild plans.
  * `test_v30_task_queue.py` — task lifecycle,
    cancellation, runner-error containment,
    `make_chunked_task` builder.
  * `test_v30_diagnostics.py` — memory + sector
    estimates, classifier, renderers, layer counts.

## Boundary, restated

UNAV Pro v3.0 is an **astronomical navigation + voyage /
camera-animation tool for Cinema 4D**, scaled to handle
multi-million-row catalogs. Rendering, IPC, real-time
scientific simulation, online services, and render-engine
bridges remain explicitly out of scope.

If a future milestone changes this boundary, it will:
update `docs/ROADMAP.md` first, document the new identity
in `docs/USER_MANUAL.md`, and ship in a major-version
release with a migration path for v2.x / v3.x state.

For the long-form view of the boundary see
[`docs/ROADMAP.md`](docs/ROADMAP.md) §4–§5.
