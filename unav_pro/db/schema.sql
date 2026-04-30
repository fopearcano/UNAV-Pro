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
VALUES ('schema_version', '2');

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

-- v1.2 — object_states: per-(uid, epoch) rows for objects whose
-- world-space position depends on time. Two flavours:
--
--   * ``state_type = 'proper_motion'`` — a Gaia-style row carrying
--     pmra / pmdec at a reference epoch. The temporal resolver
--     extrapolates linearly to the target epoch on read.
--
--   * ``state_type = 'ephemeris'`` — a JPL-style row carrying an
--     explicit (x, y, z) snapshot at a single epoch. Multiple
--     rows per uid form a time series; the resolver picks the
--     nearest snapshot or interpolates between two.
--
-- Static rows do NOT need a state row; ``objects`` already
-- carries their position. The resolver treats any uid without
-- a matching state row as static.
CREATE TABLE IF NOT EXISTS object_states (
    uid          TEXT NOT NULL REFERENCES objects(uid) ON DELETE CASCADE,
    epoch_jd     REAL NOT NULL,
    state_type   TEXT NOT NULL CHECK (
        state_type IN ('static', 'proper_motion', 'ephemeris')
    ),
    -- Cartesian-pc snapshot (used by ephemeris).
    x            REAL,
    y            REAL,
    z            REAL,
    -- Velocity AU/day (used by ephemeris when interpolation is desired).
    vx           REAL,
    vy           REAL,
    vz           REAL,
    -- Reference epoch for proper-motion rows; matches ``epoch_jd``
    -- when ``state_type = 'proper_motion'`` so a single index
    -- serves both.
    reference_epoch_jd REAL,
    -- Proper-motion components (mas/yr) for proper_motion rows.
    pmra_masyr   REAL,
    pmdec_masyr  REAL,
    PRIMARY KEY (uid, epoch_jd)
);

CREATE INDEX IF NOT EXISTS idx_object_states_epoch ON object_states (epoch_jd);
CREATE INDEX IF NOT EXISTS idx_object_states_uid_type ON object_states (uid, state_type);
