-- UNAV Pro — v1.1 SQLite schema.
--
-- Two tables: lightweight per-row data on `objects` (the rendering /
-- filtering hot path) and a parallel `metadata` table carrying the
-- raw `metadata_json` blob. Splitting them lets the rendering /
-- visible-sector / search paths read only the small columns and
-- skip the per-row JSON until the inspector actually needs it.
--
-- Indexes target the v0.6 search filters (source, object_type, name)
-- plus the v1.1 spatial queries (cartesian_x/y/z + ra/dec).
--
-- Versioning: the `unav_meta` table carries a single row with the
-- schema version. Loaders refuse files whose version does not match
-- the build's `SCHEMA_VERSION`. Migrations are documented in
-- `docs/SQL_SCHEMA.md`.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS unav_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

INSERT OR IGNORE INTO unav_meta (key, value)
VALUES ('schema_version', '1');

-- Hot-path row: the ~10 columns the dialog uses for search /
-- visible-sector candidate selection. Wide enough to skip the
-- metadata JOIN on the search panel; narrow enough that even a
-- 10 M-row catalog stays cache-friendly on B-tree scans.
CREATE TABLE IF NOT EXISTS objects (
    uid               TEXT PRIMARY KEY,
    source            TEXT NOT NULL,
    object_type       TEXT,
    name              TEXT,
    common_name       TEXT,
    ra_deg            REAL NOT NULL,
    dec_deg           REAL NOT NULL,
    distance_parsec   REAL,
    redshift          REAL,
    apparent_magnitude REAL,
    color_index       REAL,
    cartesian_x       REAL,
    cartesian_y       REAL,
    cartesian_z       REAL
);

-- Parallel metadata blob. Lazy-loaded by the inspector; never
-- touched by the search / visible-sector paths.
CREATE TABLE IF NOT EXISTS metadata (
    uid           TEXT PRIMARY KEY REFERENCES objects(uid) ON DELETE CASCADE,
    metadata_json TEXT NOT NULL
);

-- Spatial / filtering indexes.
-- ``ra_deg, dec_deg`` is the equatorial-pre-filter index (used by
-- callers that filter on RA/Dec windows before computing Cartesian).
CREATE INDEX IF NOT EXISTS idx_objects_radec   ON objects (ra_deg, dec_deg);
-- One per Cartesian axis so SQLite's planner can use any combination
-- in the bbox WHERE clause.
CREATE INDEX IF NOT EXISTS idx_objects_x       ON objects (cartesian_x);
CREATE INDEX IF NOT EXISTS idx_objects_y       ON objects (cartesian_y);
CREATE INDEX IF NOT EXISTS idx_objects_z       ON objects (cartesian_z);
-- Categorical filters used by the search panel.
CREATE INDEX IF NOT EXISTS idx_objects_source  ON objects (source);
CREATE INDEX IF NOT EXISTS idx_objects_type    ON objects (object_type);
-- Ranges used by the search panel.
CREATE INDEX IF NOT EXISTS idx_objects_mag     ON objects (apparent_magnitude);
CREATE INDEX IF NOT EXISTS idx_objects_redshift ON objects (redshift);
CREATE INDEX IF NOT EXISTS idx_objects_distance ON objects (distance_parsec);
-- Optional: substring-friendly name lookup. SQLite has no built-in
-- contains-index but lower-casing once into ``name_lc`` lets
-- ``LIKE 'sirius%'`` use the B-tree.
CREATE INDEX IF NOT EXISTS idx_objects_name_lc ON objects (LOWER(name));
CREATE INDEX IF NOT EXISTS idx_objects_common_name_lc ON objects (LOWER(common_name));
