# UNAV Pro — Large-Data Workflows

The artist-facing companion to
[`V3_0_SCALABILITY_AND_STREAMING.md`](V3_0_SCALABILITY_AND_STREAMING.md).
Six concrete patterns for working with multi-million-row
catalogs inside Cinema 4D without blowing through memory or
losing UI responsiveness.

This is a **field guide**, not a feature list. Every
recommendation maps to existing v0.x → v3.0 surfaces; no new
authoring concepts.

---

## 1. Always build a spatial index before sync

For every dataset above ~100 K rows, build the spatial
index (`Dataset Manager → Build Index`) before syncing the
visible sector. The streamed path is dramatically faster
than the full-load fallback and uses bounded memory:
chunks the navigator's cone touches reach the plugin;
everything else stays on disk.

The streaming layer (`core/sector_streaming.py`) refuses
outright to full-load above 5 M rows. Below the ceiling it
warns. Build the index — it's a one-time per-dataset cost.

## 2. Keep `max_visible_objects` honest

`max_visible_objects` is the navigator's safety cap. v3.0
derives a SQL-level bbox cap from it (default 6× the
visible-objects cap) so the bounding-box prefilter never
fetches more than `6 × max_visible` rows into Python.

If you need more visible objects, raise `max_visible_objects`
on the navigator's user data. Don't try to bypass the cap
with very wide cones — the bbox prefilter will still trim
to the configured ratio.

For the very-large-cap case, set explicit `QueryCaps` (see
[`QUERY_OPTIMIZATION.md`](QUERY_OPTIMIZATION.md) §3) per
project.

## 3. Re-sync at the same pose is free

The v3.0 chunk-reuse cache (`db/streaming.py::ChunkReuseCache`)
remembers cone-query results keyed by the navigator's pose +
cone parameters + filter sets + epoch. When the artist
nudges the navigator a hair and re-syncs, the cache serves
the previous result instead of re-querying.

The cache holds at most 16 entries (configurable) of up to
250 K objects each (configurable) and evicts least-recently-
used. A scrubbing cinematic that loops through 5–10 poses
will hit the cache repeatedly and feel snappy.

The cache invalidates automatically when:

* the active dataset changes (`invalidate_for_dataset`);
* the time-navigator epoch advances (`invalidate_for_epoch`);
* the user clicks "Reset cache" or saves the project
  (`invalidate_all`).

## 4. Unchanged sectors don't re-render

When the artist nudges the navigator within the same sector
and the visible set is identical, the v3.0 sync layer
short-circuits. `SyncDiff.is_unchanged` is True; the C4D
backend round-trip is skipped; the status line says
`"unchanged (12,003 visible)"`.

This means scrubbing a 30-second timeline that crosses two
visible sectors will trigger one backend rebuild per
**sector boundary**, not per **frame**.

## 5. Long operations: use the task queue

For one-off operations bigger than ~100 K objects (e.g. a
multi-page sync, a long timeline bake, a multi-dataset
export), use the v3.0 task queue
(`core/task_queue.py::TaskQueue`).

The queue is **cooperative single-threaded** (no preemption,
no race conditions in C4D). Long-running operations report
progress between steps and honour `task.is_cancelled()` —
the dialog's cancel button flips that flag.

See [`SAFE_TASK_QUEUE_MODEL.md`](SAFE_TASK_QUEUE_MODEL.md)
for the wiring + cancellation contract.

Quick recipe:

```python
from core.task_queue import GLOBAL_TASK_QUEUE, make_chunked_task
from db.streaming import iter_paged_cone

pages = list(iter_paged_cone(cone_result, page_size=5_000))

def step(page, task):
    apply_page_to_scene(page)

runner = make_chunked_task(
    kind="sync_paged",
    label="Sync visible sector (paged)",
    units=pages,
    step=step,
)
GLOBAL_TASK_QUEUE.enqueue(runner, kind="sync_paged", label="Sync (paged)")
```

The dialog's tick handler calls `GLOBAL_TASK_QUEUE.run_next()`
to drain the queue between Cinema 4D message-loop iterations.

## 6. Watch the diagnostics panel

The v3.0 diagnostics panel reports five things that matter
for large-data workflows:

1. **Per-dataset memory estimate** — rows / on-disk MB / in-
   memory MB. Confirms the dataset fits before syncing.
2. **Visible-sector estimate** — coarse uniform-distribution
   proxy; useful for "this sync will be ~200 K objects".
3. **Cone cache** — entries / row footprint / hit ratio.
   A high hit ratio means the artist's workflow is making
   good use of the cache.
4. **Query-timing history** — last few cone queries +
   slowest. Catches regressions from filter changes.
5. **Active overlays + science layers** — counts so the
   artist can tell at a glance whether they have layers on
   that they don't need.

`build_diagnostics_report(...)` in
`unav_pro/core/diagnostics.py` is the single entry point.

---

## Anti-patterns

* **Don't loop sync in Python.** Cinema 4D's main thread
  doesn't yield during a long sync; spinning sync across
  10 poses in a row will block the UI for tens of seconds.
  Use the task queue.
* **Don't disable `max_visible_objects` to "see everything"**
  on a multi-million-row catalog. The plugin will refuse
  to materialise more than the cap × bbox-multiplier; even
  if it didn't, Cinema 4D's editor viewport doesn't render
  millions of distinct nulls efficiently. Raise the cap to
  what the host can handle (typically tens of thousands)
  and use the procedural overlays (v2.0) for far context.
* **Don't bake a frame-aware sync.** v2.2 sync markers run
  at marker boundaries, not per frame. Per-frame
  regeneration is explicitly out of scope.
* **Don't keep stale caches.** When you swap datasets or
  change the time navigator, call
  `cache.invalidate_for_dataset(...)` or
  `cache.invalidate_for_epoch(...)`. The dialog wires this
  automatically; manual scripts must remember.

## Cross-reference

* [`USER_MANUAL.md`](USER_MANUAL.md) §5 — Dataset workflow.
* [`USER_MANUAL.md`](USER_MANUAL.md) §6 — Navigator workflow.
* [`TD_GUIDE.md`](TD_GUIDE.md) §6 — Performance limits.
* [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) — Known
  performance edges.
