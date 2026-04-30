# SQL Schema

Reference for the v1.1 SQLite catalog database. The schema is
shipped as ``unav_pro/db/schema.sql`` and applied by
``DBManager.apply_schema()`` (idempotent). It is also runnable
via ``sqlite3 unav.db < unav_pro/db/schema.sql`` for
out-of-process tooling.

For the broader v1.1 milestone see
[`V1_1_QUERY_ENGINE.md`](V1_1_QUERY_ENGINE.md). For the bbox
+ cone strategy that drives the spatial indexes' design see
[`SPATIAL_QUERY_STRATEGY.md`](SPATIAL_QUERY_STRATEGY.md).

---

## 1. Tables

### 1.1 ``unav_meta``

Single-row metadata table that pins the schema version. The
loader rejects DBs whose version doesn't match the build's
``SCHEMA_VERSION``.

```sql
CREATE TABLE unav_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
INSERT OR IGNORE INTO unav_meta (key, value)
    VALUES ('schema_version', '1');
```

### 1.2 ``objects``

The hot-path row. Wide enough that the search panel and the
visible-sector cone query never need to JOIN, narrow enough
that even a 10 M-row catalog stays cache-friendly.

```sql
CREATE TABLE objects (
    uid                 TEXT PRIMARY KEY,
    source              TEXT NOT NULL,
    object_type         TEXT,
    name                TEXT,
    common_name         TEXT,
    ra_deg              REAL NOT NULL,
    dec_deg             REAL NOT NULL,
    distance_parsec     REAL,
    redshift            REAL,
    apparent_magnitude  REAL,
    color_index         REAL,
    cartesian_x         REAL,
    cartesian_y         REAL,
    cartesian_z         REAL
);
```

Notes:

* ``uid`` is the primary key. Re-imports use ``INSERT OR IGNORE``
  by default; the importer's ``--replace`` flag opts into ``OR
  REPLACE``.
* ``source`` is the human-readable label (``"Gaia DR3"``,
  ``"SDSS"``, ``"DESI"``, ``"JPL Horizons"``, …) the v0.5+
  connectors emit, not the raw release token.
* ``cartesian_x/y/z`` are computed (parsec) coordinates derived
  from ``equatorial_to_cartesian_pc``. They're populated by the
  importer (it calls ``compute_derived_fields`` on the way in).
* Numeric columns allow NULL so partial catalogs (positions but
  no magnitude, redshift but no distance) round-trip cleanly.

### 1.3 ``metadata``

Parallel JSON blob table. Lazy-loaded by the inspector; never
touched on the search / visible-sector hot paths.

```sql
CREATE TABLE metadata (
    uid           TEXT PRIMARY KEY REFERENCES objects(uid)
                       ON DELETE CASCADE,
    metadata_json TEXT NOT NULL
);
```

The ``ON DELETE CASCADE`` lets ``DBManager.delete_uid(uid)`` wipe
the parallel metadata row in the same transaction.

---

## 2. Indexes

```sql
-- Spatial / equatorial.
CREATE INDEX idx_objects_radec    ON objects (ra_deg, dec_deg);
CREATE INDEX idx_objects_x        ON objects (cartesian_x);
CREATE INDEX idx_objects_y        ON objects (cartesian_y);
CREATE INDEX idx_objects_z        ON objects (cartesian_z);
-- Categorical.
CREATE INDEX idx_objects_source   ON objects (source);
CREATE INDEX idx_objects_type     ON objects (object_type);
-- Range filters.
CREATE INDEX idx_objects_mag      ON objects (apparent_magnitude);
CREATE INDEX idx_objects_redshift ON objects (redshift);
CREATE INDEX idx_objects_distance ON objects (distance_parsec);
-- Substring lookup (functional indexes for prefix matches).
CREATE INDEX idx_objects_name_lc  ON objects (LOWER(name));
CREATE INDEX idx_objects_common_name_lc ON objects (LOWER(common_name));
```

Index reasoning:

* **One per Cartesian axis.** SQLite's planner picks whichever
  range is the most selective. For a navigator cone the bbox is
  a sphere envelope (``[origin - far, origin + far]`` per axis),
  so any of x/y/z prunes the candidate set; the planner picks
  the tightest.
* **``ra_deg, dec_deg`` composite.** Useful for callers who
  want an equatorial-window lookup before computing Cartesian
  (a future "browse a sky region" panel).
* **``LOWER(name)`` functional indexes.** SQLite supports
  expression indexes; the search panel's ``LIKE 'token%'``
  query against the lower-cased name then matches the index
  directly. Substring matches still degrade to a scan, but the
  search panel's hard cap (500 results) keeps the working set
  bounded.

---

## 3. Pragmas

The schema file sets:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
```

* ``foreign_keys = ON`` — required for the metadata cascade.
* ``journal_mode = WAL`` — readers don't block writers; the
  importer can stream INSERTs while the dialog runs queries.
* ``synchronous = NORMAL`` — the right knob for a desktop app
  that tolerates losing the last WAL block on a hard
  power-off.

---

## 4. Versioning

Schema version is the value of the ``unav_meta.schema_version``
row. The build's ``unav_pro.db.db_manager.SCHEMA_VERSION``
constant is the single source of truth on the code side.

* **v1** (this milestone) — every section above.
* **v2** (reserved) — first migration target. Examples:
  * Per-row tile id for spatial-coarsening.
  * Optional FTS5 virtual table for substring search.
  * `cartesian_*` projected to a per-DB sector origin (the v1.0
    camera-relative pattern, applied to the SQL store too).

When v2 lands the manager will grow a ``migrate(from_version)``
method; until then, mismatched versions fail closed with a
clear ``DBError``.

---

## 5. How to apply by hand

The schema file is plain SQL — no Python required:

```bash
sqlite3 data/unav.db < unav_pro/db/schema.sql
```

Re-running is safe (every ``CREATE`` uses ``IF NOT EXISTS``).
The DB so produced is bit-for-bit compatible with the
``DBManager``-applied version.

---

## 6. Where the schema is **not**

* **No row-level visual encoding.** Colour / size are baked
  into the v1.0 binary visible sector at export time, not
  stored on the row. The importer's job is positions +
  metadata, not the artist's display preferences.
* **No per-render-mode caches.** The renderer's GPU shadow is
  re-derived from the binary file, not from the DB.
* **No cross-source primary key.** Each catalog row keeps its
  connector-prefixed uid (`gaia:…`, `sdss:…`, …); collisions
  are impossible by construction.
