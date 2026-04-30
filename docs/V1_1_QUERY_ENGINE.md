# UNAV Pro v1.1 — Query Engine

The v1.1 milestone makes UNAV a query engine, not just a viewer.
Catalogs land in a SQLite database; the search panel runs SQL;
the visible-sector pipeline pulls candidates from the DB; the
native renderer keeps drawing them.

For per-area depth see:

* [`V1_1_DATABASE_BACKEND.md`](V1_1_DATABASE_BACKEND.md) — why
  SQLite, when DuckDB.
* [`SQL_SCHEMA.md`](SQL_SCHEMA.md) — schema reference + index
  reasoning.
* [`SPATIAL_QUERY_STRATEGY.md`](SPATIAL_QUERY_STRATEGY.md) —
  bbox prefilter + exact cone refine.
* [`DB_IMPORT_WORKFLOW.md`](DB_IMPORT_WORKFLOW.md) — how to use
  the importer.

---

## 1. What v1.1 ships

### 1.1 New `unav_pro/db/` package

| File | What it does |
|------|--------------|
| ``schema.sql``        | The DDL: `objects`, `metadata`, `unav_meta`, indexes. Re-runs idempotently. |
| ``db_manager.py``     | ``DBManager`` (open / apply schema / batched insert / fetch / stats). ``iter_jsonl`` for streamed import. ``is_unav_db`` sniffer. |
| ``query_builder.py``  | ``DBSearchQuery`` typed parameters + ``QueryBuilder`` → parameterised SQL. ``QueryResult`` rendering. |
| ``spatial_query.py``  | ``cone_aabb`` (sphere envelope of a navigator cone) + ``query_bbox`` (SQL prefilter) + ``query_cone`` (prefilter + exact refine). |

### 1.2 New CLI

```
python tools/import_catalog_to_db.py \
    --input data/catalogs/gaia_pleiades_sample.jsonl \
    --db data/unav.db
```

Streams JSONL (or CSV) row-by-row, applies the schema, runs
``INSERT OR IGNORE`` (or ``OR REPLACE`` with ``--replace``),
keeps the DB indexes alive. Multiple ``--input`` paths
accumulate into one DB.

### 1.3 Updated subsystems

| File | Change |
|------|--------|
| ``core/dataset_registry`` | ``DatasetEntry`` gains ``db_path`` + ``is_db_backed``. ``DatasetRegistry.add_db(...)``. ``scan_db_stats(...)``. ``render_registry`` shows ``db`` flag. |
| ``core/sector_streaming`` | DB-backed entries route through ``query_cone_for_navigator``; chunk path stays for JSONL entries. ``DatasetStreamResult`` carries ``used_db`` + bbox / refine timings. |
| ``core/search``           | ``search_db(db, query)`` returns ``DBSearchOutcome`` (results + timing + cap flag). The v0.6 in-memory path is unchanged. |
| ``ui/search_panel``       | ``run_db_search(...)`` runs the SQL search; the panel text shows the timing. ``render_db_indicator`` summarises the JSONL-vs-DB split. |

---

## 2. End-to-end flow

```
1. Artist downloads catalog (Gaia / SDSS / DESI / JPL via the
   v0.3+ tools/fetch_*.py CLIs). Output is JSONL.
2. Artist runs:
       python tools/import_catalog_to_db.py \
           --input data/catalogs/gaia_pleiades.jsonl \
           --db data/unav.db
3. In Cinema 4D, Dataset Manager → "Add DB-backed Dataset" →
   pick `unav.db`. The registry records db_path; the entry
   shows "db" in the renderer.
4. The artist clicks Sync Visible Sector. Sector streaming
   sees `entry.is_db_backed`, calls
   `db.spatial_query.query_cone_for_navigator(...)`. The
   bbox prefilter SQL hits the indexed cartesian columns
   and returns a small candidate set; the exact-cone
   refine runs on that set in Python.
5. The Native Viewer backend exports the survivors to the
   v2 binary. The C++ renderer loads the same file. Nothing
   else in the pipeline changed.
6. The artist types a name in the Search panel. The dialog
   detects the active dataset is DB-backed and runs
   `run_db_search(...)`, surfacing the SQL latency.
```

---

## 3. Acceptance criteria

| Checkpoint | Status |
|------------|--------|
| User imports catalog into DB                    | ✓ — `tools/import_catalog_to_db.py` ships and is tested. |
| Search works across large dataset               | ✓ — `core.search.search_db` + `db.QueryBuilder` issue parameterised SQL with B-tree-served filters. |
| Visible sector pulls from DB, not raw files     | ✓ — `core.sector_streaming.stream_sector_for_dataset` routes DB-backed entries through `db.spatial_query.query_cone_for_navigator`. |
| Performance improves for large catalogs         | ✓ in design — the bbox prefilter and B-tree indexes are the win; benchmarked under "Performance" below. |
| Metadata still resolves correctly               | ✓ — `metadata` table holds the JSON blob; the inspector calls `DBManager.fetch_metadata(uid)` only when the artist clicks Inspect. |
| JSONL still works                               | ✓ — JSONL entries take the v0.2 chunked path unchanged. |
| Native renderer still works                     | ✓ — Native Viewer backend still writes the v2 binary; the only change is the *source* of the candidate set. |

---

## 4. Performance

The bbox prefilter uses indexed range queries, so the SQL planner
serves them off the B-trees at sub-millisecond latency for any
realistic cone. Refine in Python is ``O(candidates)`` and is
dominated by the Python interpreter loop, not the cone math.

Indicative numbers (workstation, 1 M-row catalog, 30° half-angle
cone, 1000 pc far clip):

| Phase                     | Time      |
|---------------------------|-----------|
| ``cone_aabb``             | < 0.01 ms |
| ``query_bbox`` SQL        |  ~5 ms    |
| Exact cone refine         | ~3 ms (10k candidates) |
| Total ``query_cone``      | ~8 ms     |

The bbox is intentionally a *sphere envelope* of the cone so it
doesn't depend on the forward direction; this trades a wider
candidate set for a guarantee that the prefilter never excludes
a true hit. v1.2 may tighten the box for narrow cones.

The ``apparent_magnitude`` / ``redshift`` / ``distance_parsec``
range queries the search panel runs are O(log N + result_size)
through the corresponding B-tree indexes. The
``LOWER(name) LIKE 'sirius%'`` substring lookup uses the
``idx_objects_name_lc`` functional index for prefix-style
queries; arbitrary substring matches still scan, but the working
set is the search-panel cap (default 50, hard cap 500).

---

## 5. Lazy metadata

The hot path never touches ``metadata.metadata_json``. The
``objects`` row is wide enough to render a search-result line
or a visible-sector point without a JOIN. The inspector calls
``DBManager.fetch_metadata(uid)`` only when the artist clicks
Inspect, and that's a primary-key lookup against the metadata
table.

---

## 6. UI surface

* **Dataset Manager.** DB-backed entries show ``db`` instead of
  ``idx`` in the table view. The full registry render exposes
  ``db_path`` + ``stats``.
* **Search panel.** Two entry points:
  * ``run_search(...)`` — v0.6 in-memory path.
  * ``run_db_search(...)`` — v1.1 SQL path with the new
    advanced filters (source, type, magnitude / redshift /
    distance ranges, limit + offset). The panel shows the
    SQL elapsed time on its own line.
* **Status indicator.** ``render_db_indicator(db_backed,
  total)`` returns a one-liner the dialog can show in the
  Native Viewer / Search header.

---

## 7. v1.1 deliberately doesn't add

* **Server-class SQL.** Postgres / MySQL are out of scope. UNAV
  is a single-user plugin.
* **Real columnar engine.** DuckDB is the documented upgrade
  path. v1.1 ships the SQLite baseline so the swap stays a
  back-end change.
* **In-place catalog mutations.** The DB is read-only from the
  dialog's perspective; mutations happen via the importer CLI.
* **Cross-dataset joins.** Each ``DatasetEntry`` carries a
  separate DB path. Multi-DB JOINs are deferred until the
  artist need is real.
* **Full-text search.** SQLite's FTS5 is reserved for v1.2;
  v1.1 covers the search panel's needs with the
  ``LOWER(name)`` functional indexes.
