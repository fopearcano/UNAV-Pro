# UNAV Pro — v3.0 Scalability & Streaming

The v3.0 milestone is about **handling very large
astronomical datasets in a stable, production-oriented way
inside Cinema 4D**. Not rendering. Not new authoring
surfaces. The runtime feature set is the v2.5 contract; v3.0
adds the scaffolding that makes it survive 10 M-row catalogs
and a working artist's iterate-fast loop.

This document is the milestone overview. For deep dives see:

* [`LARGE_DATA_WORKFLOWS.md`](LARGE_DATA_WORKFLOWS.md) —
  artist-facing patterns for working with multi-million-row
  catalogs.
* [`SAFE_TASK_QUEUE_MODEL.md`](SAFE_TASK_QUEUE_MODEL.md) —
  the cooperative single-threaded queue model that replaces
  ad-hoc long-running calls.
* [`QUERY_OPTIMIZATION.md`](QUERY_OPTIMIZATION.md) — the
  v3.0 changes to `db/spatial_query.py`, the chunk-reuse
  cache, and the timing log.

---

## 1. What changed at a glance

| Surface | v2.5 | v3.0 |
| --- | --- | --- |
| Cone query SQL cap | hard-coded 4× max_visible | `QueryCaps` (configurable, default 6×) |
| Repeated identical queries | re-run each time | `ChunkReuseCache` LRU |
| Query timing | logged once | bounded ring buffer (`GLOBAL_QUERY_TIMING_LOG`) |
| Visible-sector pagination | none | `iter_paged_cone` |
| Unchanged sectors | full diff + backend round-trip | `SyncDiff.is_unchanged` short-circuit |
| Overlay rebuild | always full | `plan_overlay_rebuild` |
| Science-layer rebuild | always full | `plan_science_rebuild` |
| Mission preview rebuild | always full | `plan_mission_update` |
| Long ops | run synchronously | optional `TaskQueue` cooperative scheduling |
| Diagnostics | health check | dataset memory + visible-sector estimate + cache + timing |

Every change is **opt-in**. v2.5 call sites continue to
work unmodified; the v3.0 wrappers light up when callers
pass the new keyword arguments or wire the new modules in.

## 2. New modules

* `unav_pro/db/streaming.py` — paged loading, chunk reuse
  cache, repeated-query detector. Pure stdlib; no Cinema 4D.
* `unav_pro/core/task_queue.py` — lightweight cooperative
  task queue with progress + cancellation. **No threads.**
  C4D-API contracts are honoured (main-thread only).
* `unav_pro/core/diagnostics.py` — pure helpers for the
  diagnostics panel: dataset memory estimate, visible-sector
  estimate, long-operation classifier, cache + timing
  renderers, overlay/science layer counts.

## 3. Extended modules

* `unav_pro/db/spatial_query.py` gains `QueryCaps`,
  `QueryTimingLog`, and `GLOBAL_QUERY_TIMING_LOG`.
  `query_cone` and `query_cone_for_navigator` now accept
  `caps=`, `timing_log=`, `timing_note=` keyword arguments.
* `unav_pro/core/scene_sync.py` gains
  `SyncDiff.is_unchanged`, `plan_overlay_rebuild`,
  `plan_science_rebuild`, and `plan_mission_update` —
  pure helpers the C4D builders read to skip unnecessary
  rebuilds.

## 4. Acceptance criteria

* [x] **Large datasets remain manageable.** Cone queries
  derive a SQL-level row cap from `max_visible_objects`
  even when the caller doesn't pass one explicitly. The
  cap is configurable per project via `QueryCaps`.
* [x] **Repeated navigation is more responsive.** When the
  artist re-syncs at the same pose (within the cache
  quantum), the cone result is served from
  `ChunkReuseCache` rather than re-querying.
* [x] **Unnecessary rebuilds are reduced.**
  `SyncDiff.is_unchanged` short-circuits the backend
  round-trip when the visible set didn't change. The
  rebuild planners do the same for overlays / science
  layers / mission previews.
* [x] **UI remains usable during heavier operations.**
  The `TaskQueue` is a cooperative single-threaded model
  the dialog drains step-by-step; long operations report
  progress and honour cancellation between steps.
* [x] **Dataset diagnostics are understandable.** The
  diagnostics panel renders dataset memory estimate,
  visible-sector estimate, cache usage, query-timing
  history, and active overlay / science-layer counts in
  plain text.
* [x] **No renderer assumptions.** Nothing in v3.0 produces
  pixels. The plugin still populates the C4D scene; C4D's
  renderers (Standard / Redshift / Octane / Arnold) draw
  it.
* [x] **No unsafe threading.** The task queue is explicitly
  single-threaded. C4D API touches stay on the main
  thread.

## 5. What v3.0 is **not**

* Not a render engine. (Same as every milestone since v0.1.)
* Not a RelativityRender bridge. (Same.)
* Not a network protocol / IPC / socket bridge. (Same.)
* Not an `asyncio` framework. (The task queue is FIFO and
  synchronous; `run_next()` returns when the task returns.)
* Not a multi-process worker pool. (One process; one
  Cinema 4D document at a time.)
* Not a replacement for the v1.x sector-streaming layer.
  `core/sector_streaming.py` continues to drive
  per-dataset cone queries; v3.0 wraps and accelerates it.

## 6. Rollout

v3.0 ships as a **drop-in v2.5 upgrade**:

1. The dialog can keep its existing Sync / Overlay /
   Science / Mission code paths and gain v3.0 speedups
   simply by passing the new modules in (e.g. wiring
   a `ChunkReuseCache` into `mock_actions.do_sync`).
2. New diagnostics panel rows appear automatically once
   the panel reads `build_diagnostics_report(...)`.
3. The task queue is opt-in per-operation; existing
   one-shot calls continue to work as before.

## 7. Where to read next

* Artist-facing patterns →
  [`LARGE_DATA_WORKFLOWS.md`](LARGE_DATA_WORKFLOWS.md).
* Task-queue model + cancellation →
  [`SAFE_TASK_QUEUE_MODEL.md`](SAFE_TASK_QUEUE_MODEL.md).
* Cone-query internals + cache key construction →
  [`QUERY_OPTIMIZATION.md`](QUERY_OPTIMIZATION.md).
