# UNAV Pro — Query Optimization (v3.0)

Reference for the v3.0 changes to `unav_pro/db/spatial_query.py`
and the new `unav_pro/db/streaming.py` cache layer. Read
this when you're tuning a project that runs many cone
queries against very large catalogs.

For the architectural overview see
[`V3_0_SCALABILITY_AND_STREAMING.md`](V3_0_SCALABILITY_AND_STREAMING.md).
For the artist's view see
[`LARGE_DATA_WORKFLOWS.md`](LARGE_DATA_WORKFLOWS.md).

---

## 1. The two-step query

The cone-query strategy hasn't changed since v1.1:

1. **Bounding-box prefilter (SQL).** Compute a conservative
   AABB containing the cone; run `WHERE cartesian_x BETWEEN
   ? AND ? AND cartesian_y BETWEEN ? AND ? AND cartesian_z
   BETWEEN ? AND ?` against the indexed columns.
2. **Exact cone refine (Python).** Hand the survivors to
   `core/spatial_filter.apply_filter`, which honours
   `near_clip`, `far_clip`, half-angle, source filters,
   and `max_visible_objects`.

v3.0 keeps both steps. What changes is the **caps that
control how big each step is allowed to grow**, and a
new **cache** that skips the whole pipeline when the
artist re-asks for the same result.

## 2. `QueryCaps`

Single config object that lives in `db/spatial_query.py`:

```python
@dataclass(frozen=True)
class QueryCaps:
    bbox_max_rows: Optional[int] = None
    bbox_cap_multiplier: Optional[int] = None
    candidate_hard_ceiling: Optional[int] = None
    lazy_metadata: bool = False
```

Every field is optional; `None` means "use the v1.x
default behaviour."

* `bbox_max_rows` — explicit `LIMIT` for the SQL
  prefilter. Overrides the multiplier when set.
* `bbox_cap_multiplier` — multiplier on
  `max_visible_objects` to derive the SQL `LIMIT` when
  no explicit cap is supplied. **Default 6×** in v3.0
  (was 4× in v1.7). Higher gives the cone refine more
  slack on anisotropic catalogs; lower bounds memory
  more aggressively.
* `candidate_hard_ceiling` — defensive trim on the
  Python-side candidates list. Catches the case where
  the SQL cap was missed (e.g. an in-memory DB without
  index hints).
* `lazy_metadata` — placeholder for a future column-
  pruning prefilter. v3.0 implementation reserves the
  flag; it has no behavioural effect yet.

`QueryCaps.effective_bbox_cap(max_visible)` computes the
final cap value the SQL `LIMIT` uses.

Pass `caps=QueryCaps(...)` to `query_cone(...)` or
`query_cone_for_navigator(...)` to override per-call.

## 3. `QueryTimingLog`

A bounded ring buffer of recent cone-query timings. Every
call to `query_cone(...)` records one entry by default
into `GLOBAL_QUERY_TIMING_LOG`; tests construct a local
instance.

Fields per entry:

```python
QueryTimingEntry(
    stamp=...,
    candidate_rows=...,
    kept_rows=...,
    bbox_elapsed_ms=...,
    refine_elapsed_ms=...,
    total_elapsed_ms=...,
    capped=...,
    note="",
)
```

API:

* `record(...)` — insert a new entry. Auto-trims to
  capacity (default 256).
* `recent(limit=10)` — most-recent N, newest last.
* `slowest(limit=5)` — biggest N by `total_elapsed_ms`.
* `average_total_ms()` — mean across the buffer.
* `reset()` — drop everything.

The diagnostics panel renders this via
`render_query_timing_history(log)` in
`core/diagnostics.py`.

## 4. The chunk-reuse cache

`db/streaming.py::ChunkReuseCache` is an LRU keyed by a
quantised pose + cone parameters + filter sets + epoch.

Key construction:

```python
key = make_cache_key(
    dataset_id="...",
    origin_pc=(x, y, z),
    forward=(fx, fy, fz),
    cone_half_angle_deg=30.0,
    near_pc=0.0, far_pc=500.0,
    selected_sources=("Gaia DR3",),
    selected_types=None,
    max_visible_objects=10_000,
    epoch=julian_date,
)
```

Two near-identical poses (within `pose_quantum_pc=0.001`)
produce the same key, which is what makes the cache useful
for an artist scrubbing through a timeline.

The cache holds at most `max_entries` (default 16) entries
of up to `max_rows_per_entry` (default 250 K) objects each.
Eviction is least-recently-used. Reads bump recency.

### Cached lookup pattern

```python
from db.streaming import cached_cone_lookup, make_cache_key

key = make_cache_key(...)
result = cached_cone_lookup(
    cache=session_cache,
    key=key,
    fresh_query=lambda: query_cone_for_navigator(db, params, ...),
)
if result.hit:
    log("served from cache")
```

`fresh_query` is called *only* on cache miss.

### Invalidation

The cache exposes three invalidation APIs:

* `invalidate_for_dataset(dataset_id)` — drop entries for
  one dataset. Used when the registry adds, removes, or
  re-indexes a dataset.
* `invalidate_for_epoch(epoch_key)` — drop entries whose
  epoch differs from the current. Used when the time
  navigator advances.
* `invalidate_all()` — drop everything. Used on
  document save, document switch, or "Reset Cache".
* `invalidate_predicate(fn)` — general-purpose; rarely
  needed.

The cache is **process-local** and disposable. Losing it
costs at most one re-query, never correctness.

## 5. Pagination

`db/streaming.py::iter_paged_cone(result, page_size=5_000)`
yields `CataloguePage` instances of the result's objects.
`page_size` defaults to 5 000 (matching the v1.1 importer
batch).

Use it when:

* You're materialising hundreds of thousands of objects
  and want to dispatch them through a `TaskQueue` so the
  UI stays responsive.
* You're streaming a sector through a network protocol —
  not in v3.0, but the shape is right for future
  use.

Each page exposes `.page_index`, `.objects`, `.is_last`,
`.size`. Implementations dispatching pages to the C4D
scene typically wrap each page as a step in a
`make_chunked_task(...)`-built runner.

## 6. Repeated-query detector

`RepeatedQueryStats.observe(key)` increments a counter for
each `CacheKey`. `stats.top(5)` returns the most-asked
keys. The diagnostics panel renders this so the artist
can tell when their workflow is asking for the same
sector twenty times — usually a sign that adding the
cache or widening the quantum would help.

## 7. Forward-aware AABB (deferred)

The v3.0 module documents a `forward_aware=True` mode
for `cone_aabb` that uses the forward vector to compute
a tighter AABB for narrow cones (≤ 10° half-angle). The
v3.0 implementation stays with the v1.1 sphere bound to
preserve behavioural compatibility with every existing
test. The tighter AABB is on the planned list (see
[`ROADMAP.md`](ROADMAP.md) §2).

## 8. Tests

* `test_v30_streaming` — pagination, cache hits/misses,
  invalidation, key-quantisation behaviour.
* `test_v30_query_caps` — `QueryCaps.effective_bbox_cap`,
  multiplier override, hard ceiling, timing-log
  insertion.
* `test_v30_repeated_queries` — `RepeatedQueryStats`
  counters, top-N ordering.

## 9. Known limitations

* Anisotropic catalogs still drive long bbox prefilters
  along the dense axis (galactic plane for Gaia, declination
  bands for SDSS). The forward-aware AABB will help when
  it ships.
* The cache is in-memory only; closing the document
  drops it. Persistent caching is documented in
  [`ROADMAP.md`](ROADMAP.md) §3 but not committed to.
* `lazy_metadata=True` is a placeholder; the column
  pruning hasn't shipped. The flag exists so call sites
  can opt in once it does without an API change.
