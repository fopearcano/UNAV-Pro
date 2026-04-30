# Spatial Query Strategy

How v1.1 turns a navigator cone into a SQL plan that runs at
single-millisecond latency against a million-row catalog. The
implementation lives in ``unav_pro/db/spatial_query.py``.

For the schema indexes the strategy depends on see
[`SQL_SCHEMA.md`](SQL_SCHEMA.md). For the broader v1.1
milestone see [`V1_1_QUERY_ENGINE.md`](V1_1_QUERY_ENGINE.md).

---

## 1. Two-step pattern

```
┌──────────────────────────────────────────────────────────┐
│ Step 1 — bbox prefilter (SQL)                             │
│                                                            │
│   cone_aabb(origin, forward, half_angle, far) -> (mn, mx) │
│   SELECT … FROM objects                                   │
│     WHERE cartesian_x BETWEEN ? AND ?                     │
│       AND cartesian_y BETWEEN ? AND ?                     │
│       AND cartesian_z BETWEEN ? AND ?                     │
│       (+ optional source / type filters)                  │
└────────────────────────────┬─────────────────────────────┘
                             │ candidates
                             ▼
┌──────────────────────────────────────────────────────────┐
│ Step 2 — exact cone refine (Python)                       │
│                                                            │
│   apply_filter(candidates, near, far, cone, sources, …)   │
│   ↓                                                       │
│   surviving CatalogObject list                            │
└──────────────────────────────────────────────────────────┘
```

* **Step 1** uses the ``cartesian_x/y/z`` B-tree indexes the
  schema ships. SQLite's planner picks whichever has the
  most-selective range; in practice, off-axis cones use all
  three.
* **Step 2** is the v0.2 ``core.spatial_filter.apply_filter``
  — the same exact-rejection logic the chunk path uses. Same
  guarantees: near/far clip, cone-angle, source / type filter,
  ``max_visible_objects`` cap, rank-by-distance ordering.

The bbox is a **sphere envelope**, not a tight cone bbox: the
box is ``[origin - far, origin + far]`` per axis, regardless of
the forward direction. That's a deliberate over-approximation —
it means the prefilter never excludes a true hit, no matter how
narrow or off-axis the cone, at the cost of a wider candidate
set.

---

## 2. ``cone_aabb(origin, forward, half_angle, far, *, near, pad)``

Pure function. Returns ``((min_x, min_y, min_z), (max_x, max_y, max_z))``
in parsec.

```python
half = float(far) + float(pad)
return (
    (origin[0] - half, origin[1] - half, origin[2] - half),
    (origin[0] + half, origin[1] + half, origin[2] + half),
)
```

Why a sphere, not a tight cone bbox?

* **Correctness.** The sphere ``|p - origin| <= far`` strictly
  contains every cone ``angle_from_forward <= half_angle &&
  |p - origin| <= far``. The bbox of the sphere is therefore
  a strict over-approximation of the cone's bbox.
* **Direction independence.** The cone's tight bbox depends
  on the forward vector + half-angle. Computing it correctly
  involves projecting the apex + four base corners onto each
  axis — possible, but extra code for a feature the bbox
  prefilter is meant to be cheap.
* **The exact step doesn't care.** Step 2 rejects everything
  outside the cone in Python, so widening the candidate set
  costs CPU only on the refine path. Empirically the candidate
  set is tens-of-thousands at the cone half-angles UNAV uses
  (15°–60°); the refine takes single-digit milliseconds.

A future ``cone_aabb_tight`` (taking forward + half-angle) is
fine to add if benchmarks show the refine pass dominates;
v1.1 ships the sphere envelope.

---

## 3. ``query_bbox(db, mn, mx, *, sources, types, max_rows)``

Direct prefilter. Used by tests and by callers who want the
candidate set without the cone refine. Returns a
``BBoxQueryResult`` with the candidate ``CatalogObject`` list,
elapsed time, and the SQL it ran (for diagnostics).

The SQL is parameterised; ``selected_sources`` /
``selected_types`` go into ``IN (...)`` placeholders, never
into the SQL string itself.

---

## 4. ``query_cone(db, origin, forward, ...)``

The full pipeline. Calls ``cone_aabb`` → ``query_bbox`` →
``apply_filter`` and times each phase. Returns a
``ConeQueryResult`` carrying:

* ``objects`` — the surviving ``CatalogObject`` list.
* ``candidate_rows`` — bbox prefilter hit count.
* ``kept_rows`` — exact-cone survivor count.
* ``bbox_min`` / ``bbox_max`` — for the dialog log.
* ``bbox_elapsed_ms`` / ``refine_elapsed_ms`` /
  ``total_elapsed_ms`` — phase timings.
* ``capped`` — survivors-pre-cap minus survivors-post-cap.

``far_pc`` must be finite (an infinite far would yield an
infinite bbox); callers using "infinity" semantically clip to
the navigator's ``far_clip_parsec`` upstream.

The ``query_cone_for_navigator(db, params, origin, forward)``
helper exists so ``sector_streaming`` doesn't have to unpack
``NavigationParams`` itself.

---

## 5. Candidate fan-out

How wide is the candidate set in practice? Some indicative
numbers for a uniform 1 M-row Gaia-style cube of side 1000 pc:

| Cone half-angle | far_pc | bbox volume / cube volume | candidates |
|----------------:|-------:|--------------------------:|-----------:|
|  15°            |   100  |  (200/1000)³ = 0.8 %       |  ~8 000    |
|  30°            |   500  | (1000/1000)³ = 100 %       |  ~1 000 000|
|  60°            |   100  |  (200/1000)³ = 0.8 %       |  ~8 000    |

The ``far_pc`` axis dominates. For most navigator settings,
the bbox is significantly smaller than the catalog and the
prefilter is the win.

---

## 6. Failure modes

* **DB does not exist.** ``DBManager.open`` raises;
  ``stream_sector_for_dataset`` catches the exception and
  records it on ``DatasetStreamResult.error``. The visible-
  sector pipeline keeps working with the remaining datasets.
* **DB is corrupt or has wrong schema version.**
  ``DBManager.apply_schema`` (or ``is_unav_db``) fails with a
  clear ``DBError``. The streaming layer treats this as
  per-dataset error, not a fatal one.
* **All ``cartesian_*`` are NULL on every row.** The bbox
  WHERE clause excludes NULLs by SQLite's three-valued logic;
  the candidate set is empty; the cone returns 0 hits.
  ``import_catalog_to_db`` calls ``compute_derived_fields``
  on the way in to avoid this.
* **far_pc = inf.** Rejected up front with a clear
  ``ValueError``.

---

## 7. Why not a spatial index extension?

SQLite has R-Tree and FTS5 modules, but:

* **R-Tree.** Requires shipping a virtual-table extension and
  restructuring the schema (R-Tree is its own table referencing
  ``objects.uid``). The B-tree-per-axis approach handles UNAV's
  query mix without that complexity.
* **GiST / SP-GiST.** PostgreSQL only.
* **Custom virtual tables.** Out of v1.1 scope; could land in
  v1.2 if benchmarks demand a tighter prefilter.

The current strategy is what the v1.1 acceptance criteria
need: B-tree-served bbox prefilter + Python refine, with the
escape hatches well-marked for v1.2+.
