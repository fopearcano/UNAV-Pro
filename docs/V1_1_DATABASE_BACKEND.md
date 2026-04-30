# UNAV Pro v1.1 — Database Backend Choice

UNAV's v1.1 milestone replaces the in-memory search and the
chunk-file streaming with a real query layer. This doc records
**why** SQLite is the v1.1 backend, and **when** the
DuckDB upgrade path lights up.

For the rest of the v1.1 milestone see
[`V1_1_QUERY_ENGINE.md`](V1_1_QUERY_ENGINE.md).

---

## 1. The shortlist

| Backend | Reason it's on the list                                                   |
|---------|----------------------------------------------------------------------------|
| **SQLite** | Stdlib (`sqlite3`); zero install footprint; file-per-DB; B-tree indexes. |
| **DuckDB** | Columnar; vectorised execution; better at multi-million-row aggregates. |
| **PostgreSQL** | Server-class SQL; out of scope (UNAV is a single-user plugin).      |
| **In-memory only** | The v0.6 status quo; doesn't scale past a few hundred-K rows.   |

---

## 2. Decision: SQLite as the v1.1 baseline

### 2.1 What sells SQLite

* **Stdlib.** ``sqlite3`` ships with every Python interpreter
  Cinema 4D bundles. Adding DuckDB means shipping a wheel into
  the C4D plugin folder and navigating Maxon's tighter
  Python-2024+ limits.
* **One-file portability.** Artists copy a ``.db`` file like
  they copy a JSONL. The Dataset Manager treats it like any
  other catalog source.
* **Sufficient for the v1.1 acceptance criteria.** A 1 M-row
  catalog with B-tree indexes on the spatial / categorical
  columns answers a navigator-cone query in low single-digit
  milliseconds — the ``cartesian_x/y/z`` indexes are exactly
  what the bbox prefilter needs.
* **WAL mode + non-blocking reads.** Lets the dialog query the
  same DB the importer is writing into without an exclusive
  lock.
* **SQL is the contract.** Switching to DuckDB later is a
  back-end swap, not an API redesign — both speak SQL with
  bind parameters, both honour ``PRAGMA``-friendly tuning.

### 2.2 What's it bad at

* **Aggregations across the whole catalog.** SQLite is row-
  oriented; ``SELECT COUNT(*) WHERE source = ?`` is fast
  thanks to the index, but ``SELECT ROUND(magnitude, 1),
  COUNT(*) ... GROUP BY ...`` over 100 M rows takes
  appreciable seconds.
* **Wide-row reads.** A pure SQLite plan reads whole rows from
  the page cache; columnar engines read just the columns the
  query needs.
* **No vectorised string LIKE.** Substring search is per-row.
  v1.1 mitigates with ``LOWER(name)`` indexes; v1.2+ may
  shell out to FTS5 if the search panel demands it.

### 2.3 The DuckDB ceiling

DuckDB lights up the moment any of the following becomes true:

1. The artist regularly imports catalogs ≥ 50 M rows and feels
   the latency of a `WHERE source = ? AND apparent_magnitude
   BETWEEN ?` filter under SQLite.
2. The dataset manager grows analytics surfaces ("histogram of
   redshifts in the active sector") that need the columnar
   execution to be tolerable.
3. A DuckDB wheel ships pre-bundled in the bundled Python C4D
   uses (Maxon doesn't ship one as of 2026, but the door is
   open).

The plan: make ``DBManager`` thin enough that the v1.x DuckDB
swap is a parallel ``DuckDBManager`` class behind the same
entry points (`apply_schema`, `import_iter`, `execute(sql,
params)`, `stats()`). The ``QueryBuilder`` is already SQL-
agnostic.

---

## 3. The v1.1 SQLite tuning

The bundled ``schema.sql`` runs three pragmas at apply time:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
```

* **WAL** lets readers and writers run concurrently; the
  importer streams INSERTs while the dialog runs queries.
* **synchronous=NORMAL** is the right knob for a desktop app
  that can tolerate the loss of the last WAL block on a hard
  power-off (the artist re-runs the importer if it ever
  matters).
* **foreign_keys=ON** so the metadata-cascade-on-delete
  behaviour from the schema actually fires.

Indexes (full list in [`SQL_SCHEMA.md`](SQL_SCHEMA.md)):

* ``ra_deg, dec_deg`` — equatorial range queries.
* ``cartesian_x``, ``cartesian_y``, ``cartesian_z`` — the
  spatial bbox prefilter (one B-tree per axis so SQLite's
  planner can pick whichever has the most selective range).
* ``source``, ``object_type`` — the search panel's categorical
  filters.
* ``apparent_magnitude``, ``redshift``, ``distance_parsec`` —
  the search panel's range filters.
* ``LOWER(name)``, ``LOWER(common_name)`` — substring lookup
  on the search panel's text input.

---

## 4. What stays the same

* **JSONL pipeline.** ``tools/fetch_*.py``, the v0.7+ render
  backends, and the v1.0 native viewer all keep working
  unchanged. JSONL is the *ingest* format; the DB is the
  *query* backend.
* **Visible-sector binary.** v1.0's v2 binary file format
  doesn't change. The export still pipes through the v1.0
  ``binary_export`` writer; the only difference is the source
  of the per-pose object set is now a SQL query instead of a
  chunked-file stream.
* **Native renderer.** Receives the same ``UnavStarfield``
  load request. The bridge file format is identical.

---

## 5. v1.1 deliverables

Tracked in [`V1_1_QUERY_ENGINE.md`](V1_1_QUERY_ENGINE.md). The
layer ships:

* ``unav_pro/db/`` — SQLite manager + query builder + spatial
  helpers.
* ``tools/import_catalog_to_db.py`` — JSONL → SQLite importer.
* ``core/sector_streaming`` — routes through the SQL spatial
  query when a DB is attached to a dataset entry.
* ``core/search`` — SQL-backed entry point alongside the
  in-memory one.
* ``ui/search_panel`` — advanced filter inputs + query timing.

Tests cover every surface (72 new Python tests, raising the
suite to 968 passing).

---

## 6. Backwards compatibility

* **Schema version 1.** ``unav_meta.schema_version = 1``.
  v1.2+ migrations bump this and add a migration function
  in ``DBManager``.
* **Existing JSONL datasets keep working.** They show up
  next to DB-backed entries in the registry; the dialog
  picks the right streaming path per entry via
  ``DatasetEntry.is_db_backed``.
* **Native renderer is unchanged.** Whether the visible
  sector originated from a chunked index or a SQL cone
  query, it ends up in the same v2 binary file and the
  same C++ buffer.
