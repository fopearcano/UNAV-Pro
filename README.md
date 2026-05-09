# UNAV Pro — Cinema 4D Universal Navigator

Real-data-driven interstellar navigation inside Cinema 4D 2023+.
Fetch real astrophysical catalogs (Gaia, SDSS, DESI, NASA/JPL Horizons),
filter them through a navigator-defined view cone, and materialize
only the visible objects in the C4D scene as a fully editable point
cloud — with metadata inspection, route planning, and per-source
visual encoding.

---

## What it does

* **Real catalog data, offline.** Plain-Python connectors fetch
  small sky regions from Gaia DR3, SDSS DR18, DESI EDR, and JPL
  Horizons and write a UNAV-format JSONL catalog. No `astroquery`,
  no `astropy`, no credentials.
* **Navigator-bounded scene.** A `UNAV_Navigator` null in the C4D
  scene defines an origin + forward + cone half-angle + clip range.
  Generation **never** materializes the full catalog — only what
  passes the cone is built.
* **Diff-and-update workflow.** Re-clicking *Sync Visible Sector*
  removes objects that fell out of view, keeps survivors untouched,
  and adds the newly visible ones. Selection / animation / per-
  object tags survive every iteration.
* **Live metadata inspector.** Click any UNAV object → the panel
  fills with full RA/Dec/distance/magnitude/spectral type. The
  marker on the C4D node carries only the uid; the full record
  comes from the catalog lookup.
* **Route planner.** Add waypoints (catalog objects, free
  coordinates, or named anchors), draw a linear spline through
  them, focus the navigator on any waypoint.
* **Per-source visual encoding.** Six colour modes (natural
  spectral / catalog source / object type / redshift / magnitude
  / BP-RP) and three size modes (magnitude / object type /
  uniform), with self-healing fallbacks for mixed catalogs.
* **Hard safety guardrails.** A 100 000-object hard cap, a
  visible-sector-only mode that refuses to build without a
  navigator, advisory warnings for big catalogs / heavy scenes /
  large `.c4d` files, and a minimal-marker policy that keeps the
  full metadata blob *out* of every node by default.
* **Project persistence.** *Save UNAV State* writes the
  navigator + route + active datasets + visual encoding into the
  C4D document's BaseContainer **and** a sidecar JSON, so a `.c4d`
  reopens with the scene exactly as it was assembled.

## What it does not do — yet

The Python prototype is intentionally a floor, not a ceiling:

* **Millions of points.** The current build path tops out around
  10 k–100 k C4D nulls before viewport responsiveness suffers. The
  C++ / GPU path needed to scale to a million-plus is described in
  [`docs/ROADMAP_CPP_GPU_VERSION.md`](docs/ROADMAP_CPP_GPU_VERSION.md).
* **Real-time / animated navigation.** There is no per-frame
  re-sync yet; *Sync Visible Sector* is user-triggered. The
  *MessageData* hook is reserved by the Auto Sync checkbox.
* **Cosmology-aware distances.** Redshift-to-distance is a coarse
  Hubble-law inversion gated at z ≤ 0.1; high-z quasars sit on a
  placeholder sphere.
* **Crossmatch.** Rows from two catalogs that describe the same
  physical object are not reconciled into one inspector entry.
* **Render-pass parity.** UNAV objects are nulls; a full
  *Thinking Particles* / matrix-instance render path is reserved
  but not yet implemented.

The full backlog lives in [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

---

## Requirements

* Cinema 4D **2023, 2024, or 2025** (API ≥ 26000). The plugin
  refuses to register on older hosts and logs the reason cleanly.
* Stdlib-only at runtime — no `numpy`, `astropy`, `astroquery`,
  `pandas`. The whole thing runs on the Python interpreter that
  Cinema 4D ships with.
* For the offline preprocessing tools (`tools/*`): the same
  Python interpreter (or any modern Python 3.9+).

---

## Install

See [`docs/INSTALL_C4D_2023_PLUS.md`](docs/INSTALL_C4D_2023_PLUS.md)
for per-OS plugin paths and symlink-for-development instructions.

The short version: copy or symlink the `unav_pro/` directory into
your Cinema 4D plugins folder. Restart C4D. **Extensions →
Universal Navigator Pro**.

---

## Quick start (5 minutes)

### A. Bundled-sample path (no internet required)

```text
1. Open Cinema 4D 2023+.
2. Extensions → Universal Navigator Pro.
3. Click "Create Navigation Null"            (creates UNAV_Navigator)
4. Click "Generate Point Cloud"              (uses bundled 100-row sample)
5. Click any sample-* object in the OM.
6. Click "Inspect Selected Object"           (full metadata appears)
7. Click "Add Selected Object as Waypoint"   (route gains a stop)
8. Repeat 5+7, then "Build Route Spline".
9. Click "Save UNAV State"                   (state goes into the .c4d).
```

Out of the box you get the bundled `sample_catalog_100.jsonl`
(synthetic, deterministic, 60 stars + 25 galaxies + 10 quasars +
5 nebulae) so the workflow is exercise-able without any download.

### B. Gaia DR3 real-data path

```bash
# Offline preprocessing (no Cinema 4D needed)
python tools/fetch_gaia_region.py \
    --ra 56.75 --dec 24.12 --radius-deg 1.0 \
    --limit 5000 \
    --output data/catalogs/gaia_pleiades_sample.jsonl \
    --build-index cache/gaia_pleiades
```

Then in C4D: **Dataset Manager… → Add Dataset** the JSONL,
**Load Active Datasets**, **Create Navigation Null**, **Sync
Visible Sector**. The plugin streams only the chunks the
navigator's cone touches; the full Gaia subset never enters
memory. Full walkthrough in
[`docs/V0_3_GAIA_DR3_WORKFLOW.md`](docs/V0_3_GAIA_DR3_WORKFLOW.md).

### C. JPL Horizons solar-system path (v0.4)

```bash
# Fetch a planet pack at one epoch (offline; no Cinema 4D required)
python tools/fetch_jpl_solar_system.py \
    --epoch "2026-01-01T00:00:00" \
    --bodies "Mercury,Venus,Earth,Mars,Jupiter,Saturn,Uranus,Neptune,Pluto,Moon=moon" \
    --center "500@10" \
    --output data/catalogs/jpl_solar_system_2026.jsonl \
    --build-index cache/jpl_solar_system_2026
```

For a single body (e.g. one probe or one comet) use
`tools/fetch_jpl_body.py --body "Mars" --epoch "2026-01-01T00:00:00"
--center "500@10" --output data/catalogs/jpl_mars_2026.jsonl`.
Full walkthrough in
[`docs/V0_4_JPL_HORIZONS_WORKFLOW.md`](docs/V0_4_JPL_HORIZONS_WORKFLOW.md);
the coordinate / epoch contract is in
[`docs/SOLAR_SYSTEM_COORDINATES_AND_EPOCHS.md`](docs/SOLAR_SYSTEM_COORDINATES_AND_EPOCHS.md).

### D. SDSS / DESI extragalactic path (v0.5)

```bash
# SDSS — photometry + optional spectro redshifts
python tools/fetch_sdss_region.py \
    --ra 180.0 --dec 0.0 --radius-deg 0.5 \
    --limit 5000 \
    --output data/catalogs/sdss_region_sample.jsonl \
    --build-index cache/sdss_region_sample

# DESI — spectroscopic redshifts
python tools/fetch_desi_region.py \
    --ra 180.0 --dec 0.0 --radius-deg 0.5 \
    --limit 5000 \
    --output data/catalogs/desi_region_sample.jsonl \
    --build-index cache/desi_region_sample
```

Both connectors emit galaxies / quasars / stars normalized to
the UNAV schema with redshift-aware metadata. Full walkthrough
in [`docs/V0_5_SDSS_DESI_WORKFLOW.md`](docs/V0_5_SDSS_DESI_WORKFLOW.md);
the redshift→distance contract and limitations are in
[`docs/REDSHIFT_DISTANCE_LIMITATIONS.md`](docs/REDSHIFT_DISTANCE_LIMITATIONS.md);
the redshift visual encoding is in
[`docs/EXTRAGALACTIC_VISUAL_ENCODING.md`](docs/EXTRAGALACTIC_VISUAL_ENCODING.md).

### E. Mixed Gaia + JPL + SDSS + DESI scene

Run all four fetches above, then in C4D **Dataset Manager… → Add
Dataset** for *each* JSONL (point each entry at its matching
`cache/...` index), click **Load Active Datasets**, then
**Create Navigation Null** and **Sync Visible Sector**. The four
sources coexist by design — connector uid prefixes (`gaia:` /
`jpl:` / `sdss:` / `desi:`) are disjoint, `catalog_source`
labels (`Gaia DR3` / `JPL Horizons` / `SDSS` / `DESI`) stay
distinct in the visual encoder and the metadata inspector, and
the dataset registry's `<entry.name>:` namespace layers on top.
Full walkthrough in
[`docs/MIXED_DATASET_WORKFLOW.md`](docs/MIXED_DATASET_WORKFLOW.md).

### N. Cinematic Navigation Polish (v1.8)

v1.8 polishes UNAV's v1.4 voyage system into a practical
animation-authoring tool inside Cinema 4D.

This is **not a rendering release**. v1.8 is camera movement,
route animation, mission playback polish, and Cinema 4D
timeline integration. The visible-sector pipeline is
deliberately untouched; catalog ingest, DB queries, render
backends, and binary export are unchanged.

What's new:

* **Camera-path additions** — `MissionWaypoint` gains
  `pause_seconds` (dwell), `look_at_uid` /
  `look_at_position` (camera target), and `roll_deg`
  (camera roll). `CameraPathConfig` gains an `interp_mode`
  (`smooth` / `linear`) and `tessellate_path()` for the
  preview spline. All v1.4 missions round-trip
  byte-identical; v1.8 fields are additive.
* **Playback polish** — `Playback.jump_to_start()`,
  `jump_to_end()`, `scrub_to_progress(p)`, the new
  `progress` property, and the side-effect-free
  `evaluate_at_progress(p)` for live-preview during scrub.
* **Cinema 4D timeline baking** — new
  `c4d_objects/timeline_keys.py` with a pure-Python
  `generate_keyframes()` (testable without c4d) plus a
  c4d-bound `apply_keyframes()` applier. Bakes camera +
  navigator position / rotation channels — never touches the
  visible-sector pipeline.
* **Path-preview spline** — new
  `c4d_objects/path_preview.py` drops a
  `UNAV_Mission_Preview` `SplineObject` into the active
  document so the artist can see the curve before baking.
* **Dialog wiring** — Missions tab gains **Preview Path** /
  **Clear Path Preview** / **Bake to Timeline** buttons,
  **|◀ Start** / **End ▶|** transport buttons, an **Interp**
  combo (smooth/linear), a **Scrub** slider (0..1000), and
  **Start frame** / **End frame** numeric inputs.
* **Tests** — `test_v18_camera_path`, `test_v18_playback`,
  `test_v18_timeline_keys`, `test_v18_path_preview` cover
  interpolation, scrub, frame mapping, keyframe gen,
  missing-waypoint fallback. **1326 Python tests pass.**

Walkthroughs:
[`docs/V1_8_CINEMATIC_NAVIGATION.md`](docs/V1_8_CINEMATIC_NAVIGATION.md)
— milestone summary,
[`docs/CAMERA_PATH_AUTHORING.md`](docs/CAMERA_PATH_AUTHORING.md)
— pause / look-at / roll / interp,
[`docs/TIMELINE_BAKING.md`](docs/TIMELINE_BAKING.md) —
keyframe generation + Cinema 4D applier,
[`docs/MISSION_PLAYBACK_POLISH.md`](docs/MISSION_PLAYBACK_POLISH.md)
— transport semantics + scrub-slider integration.

### M. Stabilization & Architecture Cleanup (v1.7)

v1.7 is **not a feature release**. It is a reliability,
consistency, and maintainability pass over the v1.0–v1.4
stack. UNAV is now a stable professional plugin: same
features, fewer fragile edges, one source of truth for
state, consistent UI terminology, deterministic cleanup.

What changed:

* **`core/state_manager.py`** — new central facade for every
  UNAV singleton (config, bookmarks, dataset registry,
  metadata lookup, time navigator, missions). The
  diagnostics panel uses `health_summary()` to render a
  one-line status per subsystem.
* **Atomic JSON writes** — every persistence surface
  (config, bookmarks, registry, mission files) routes
  through `safe_write_json()`. A crash mid-write can no
  longer truncate a valid file.
* **Bounded-memory cone queries** — `db/spatial_query`
  auto-derives a SQL `LIMIT` from the navigator's
  `max_visible_objects` so a loose cone against a
  million-row catalog can't fetchall() the entire bbox
  into Python.
* **`DatasetRegistry.reload()`** + **`time_navigator.default_state(reload=True)`**
  — uniform reload semantics across every singleton.
* **Defensive scene walks** — `_current_visible_objects`
  now logs and skips half-deleted children instead of
  crashing the iteration on a back-to-back sync race.
* **UI verb consistency** — bookmark "Reload" → "Sync";
  every persistence-style button now reads the same.
* **5 new test files** + an updated suite passing **1255
  tests** including new repeated-sync / mode-switch /
  registry-reload / atomic-write coverage.

Walkthroughs:
[`docs/V1_7_STABILIZATION.md`](docs/V1_7_STABILIZATION.md) —
milestone summary,
[`docs/V1_7_ARCHITECTURE_AUDIT.md`](docs/V1_7_ARCHITECTURE_AUDIT.md)
— internal as-is picture,
[`docs/PLUGIN_LIFECYCLE.md`](docs/PLUGIN_LIFECYCLE.md) —
startup / persistence / sync / shutdown lifecycle,
[`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) —
the corner cases v1.7 deliberately defers.

### L. Guided Voyages (v1.4)

v1.4 turns UNAV into a tool for **structured interstellar
journeys**. Build a *mission* — an ordered list of waypoints
sourced from catalog objects, bookmarks, free coordinates,
or named anchors — and play it back through a deterministic
cinematic camera path.

```text
1. Open the Missions tab (next to Search / Bookmarks / Navigation).
2. Type a title, click "New Mission".
3. Select a UNAV object → Inspect → "Add Selected Object as Waypoint".
4. Pick a bookmark → "Add Picked Bookmark as Waypoint".
5. Click "Preview as Route Spline" to see the path.
6. Click ▶ Play to scrub the camera through the waypoints.
```

Per-waypoint optionals: epoch (the v1.2 Time Navigator state
the playback should set when the cursor crosses this
waypoint), orientation quaternion, dwell duration, free-text
notes. Missions persist to ``~/.unav_pro/missions/`` and
roundtrip through Import/Export.

The playback engine is **deterministic** — same step → same
pose, every time — and **frame-rate independent**: the dialog
chooses how often `advance()` fires; the engine just reports
the recommended interval. Visible-sector sync fires on
transport jumps, at a bounded cadence during continuous play,
and is automatically throttled when the artist scrubs faster
than the pipeline can keep up.

Walkthroughs:
[`docs/V1_4_GUIDED_VOYAGES.md`](docs/V1_4_GUIDED_VOYAGES.md)
— milestone summary,
[`docs/MISSION_FORMAT.md`](docs/MISSION_FORMAT.md) — JSON
layout + schema versioning,
[`docs/CINEMATIC_CAMERA_PATHS.md`](docs/CINEMATIC_CAMERA_PATHS.md)
— Catmull-Rom + slerp + epoch lerp,
[`docs/PLAYBACK_SYSTEM.md`](docs/PLAYBACK_SYSTEM.md) —
transport semantics + sync cadence + safety contract.

### K. Astrophysical Knowledge Layer (v1.3)

v1.3 makes UNAV *explain* what you're selecting. Click any
catalog object and the metadata inspector now renders:

* a **classification** (star / galaxy / quasar / planet /
  moon / asteroid / comet / spacecraft / unknown) with a
  coarse confidence tag and a one-line reason;
* a structured set of sections — **Basic Identity**,
  **Position**, **Motion**, **Photometry**, **Redshift /
  Cosmology**, **Catalog Notes**, **Plain-language Summary**,
  **Missing Data**, **Available Actions**;
* a deterministic plain-text summary that **never invents
  facts** — missing fields are listed explicitly under
  "Missing Data".

No external AI, no network calls, no astropy. Pure stdlib.
Same input → byte-identical output. The summary describes a
Sun-like star differently from a high-redshift galaxy
differently from Mars, and surfaces the v1.2 epoch context
when the row is solar-system.

Walkthroughs:
[`docs/V1_3_KNOWLEDGE_LAYER.md`](docs/V1_3_KNOWLEDGE_LAYER.md)
— milestone summary,
[`docs/ASTROPHYSICAL_FIELD_GLOSSARY.md`](docs/ASTROPHYSICAL_FIELD_GLOSSARY.md)
— every field name the inspector renders, with definitions,
[`docs/OBJECT_CLASSIFICATION_RULES.md`](docs/OBJECT_CLASSIFICATION_RULES.md)
— the deterministic classifier cascade,
[`docs/METADATA_INTERPRETATION_LIMITS.md`](docs/METADATA_INTERPRETATION_LIMITS.md)
— what v1.3 will and will not say about an object.

### J. Time Navigator (v1.2)

v1.2 makes UNAV epoch-aware. Every position carries the time it
is valid for; the user can step that time forward and backward
to watch the scene evolve. Gaia stars with non-zero proper
motion drift across the sky; JPL planets fetched as multi-epoch
time series translate between snapshots.

```bash
# Fetch a 2026 weekly sweep of the inner planets into the DB.
python tools/fetch_jpl_solar_system.py \
    --start "2026-01-01T00:00:00" \
    --end   "2026-12-31T00:00:00" \
    --step-days 7 \
    --bodies "Mercury,Venus,Earth,Mars,Jupiter,Saturn,Uranus,Neptune" \
    --output data/catalogs/jpl_2026_weekly.jsonl \
    --db     data/unav.db
```

Then in C4D: open the **Time Navigator** panel (right side of
the main dialog), set an epoch (ISO datetime, JD, Jyear, or a
named anchor like ``J2016.0``), and click **<** / **>** to step.
**Sync at epoch** re-runs the visible sector for every active
dataset at the current time.

Walkthroughs:
[`docs/V1_2_TIME_NAVIGATION.md`](docs/V1_2_TIME_NAVIGATION.md) —
milestone summary,
[`docs/EPOCHS_AND_JULIAN_DATES.md`](docs/EPOCHS_AND_JULIAN_DATES.md)
— time model,
[`docs/GAIA_PROPER_MOTION_LIMITATIONS.md`](docs/GAIA_PROPER_MOTION_LIMITATIONS.md)
— what the linear propagation does (and does not) approximate,
[`docs/JPL_TIME_SERIES_WORKFLOW.md`](docs/JPL_TIME_SERIES_WORKFLOW.md)
— multi-epoch ephemeris fetch + DB ingest.

### I. SQL-backed query engine (v1.1)

v1.1 turns UNAV from a viewer into a query engine. Catalogs
land in a SQLite database; the search panel runs SQL with
typed filters (source / type / magnitude / redshift / distance
ranges + pagination); the visible-sector pipeline pulls
candidates via a bbox-prefilter + exact-cone-refine path
instead of streaming chunked JSONL. JSONL stays first-class —
the DB is a parallel query backend, not a replacement.

```bash
# Import a JSONL catalog into the v1.1 SQLite DB.
python tools/import_catalog_to_db.py \
    --input data/catalogs/gaia_pleiades.jsonl \
    --db data/unav.db
```

Then in C4D: **Dataset Manager… → Add DB-backed Dataset → pick
``data/unav.db``**. The registry shows ``db`` instead of
``idx`` for that entry; Sync Visible Sector routes it through
the SQL spatial-query path; the Search panel surfaces the SQL
elapsed time on every query.

Walkthroughs:
[`docs/V1_1_QUERY_ENGINE.md`](docs/V1_1_QUERY_ENGINE.md) —
milestone summary,
[`docs/V1_1_DATABASE_BACKEND.md`](docs/V1_1_DATABASE_BACKEND.md)
— SQLite vs DuckDB,
[`docs/SQL_SCHEMA.md`](docs/SQL_SCHEMA.md) — schema reference,
[`docs/SPATIAL_QUERY_STRATEGY.md`](docs/SPATIAL_QUERY_STRATEGY.md)
— bbox prefilter math,
[`docs/DB_IMPORT_WORKFLOW.md`](docs/DB_IMPORT_WORKFLOW.md) —
importer CLI.

### H. Native Point Viewer (v1.0 stable)

v1.0 turns the v0.9 prototype into a stable production-grade
render mode: GPU buffer architecture with safe CPU fallback,
shader-style render config (size scale, brightness, distance
fade, debug colour), camera-relative coordinates via the v2
binary format, accelerated picking with a uniform-grid spatial
index, and per-load safety guards. The dialog's Native Point
Viewer strip shows file path, point count, GPU buffer status,
memory estimate, and last reload time.

```bash
# Honest numbers benchmark — synthetic catalog, every phase timed.
python tools/benchmark_visible_sector_export.py \
    --points 100000 --version v2 --camera-relative
```

```bash
# Pack a navigator-filtered visible sector into the v0.8 binary
# format the v0.9 native plugin reads.
python tools/export_visible_sector_binary.py \
    --dataset cache/gaia_pleiades \
    --navigator-state navigator.json \
    --output ~/.unav_pro/native_bridge/visible_sector.bin
```

Walkthroughs:
[`docs/V1_0_GPU_RENDERER.md`](docs/V1_0_GPU_RENDERER.md),
[`docs/GPU_BUFFER_ARCHITECTURE.md`](docs/GPU_BUFFER_ARCHITECTURE.md),
[`docs/CAMERA_RELATIVE_RENDERING.md`](docs/CAMERA_RELATIVE_RENDERING.md),
[`docs/PICKING_SYSTEM.md`](docs/PICKING_SYSTEM.md),
[`docs/PERFORMANCE_TARGETS.md`](docs/PERFORMANCE_TARGETS.md).
The v0.9 prototype docs remain valid for the bridge protocol /
fallback semantics:
[`docs/V0_9_NATIVE_VIEWER_PROTOTYPE.md`](docs/V0_9_NATIVE_VIEWER_PROTOTYPE.md),
[`docs/BINARY_BRIDGE_WORKFLOW.md`](docs/BINARY_BRIDGE_WORKFLOW.md),
[`docs/NATIVE_LIMITATIONS.md`](docs/NATIVE_LIMITATIONS.md).
The v0.8 feasibility pack remains the design reference:
[`docs/V0_8_NATIVE_CPP_FEASIBILITY.md`](docs/V0_8_NATIVE_CPP_FEASIBILITY.md),
[`docs/MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md`](docs/MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md),
[`docs/NATIVE_VIEWPORT_DRAWING_RESEARCH.md`](docs/NATIVE_VIEWPORT_DRAWING_RESEARCH.md),
[`docs/PYTHON_TO_CPP_MIGRATION_PLAN.md`](docs/PYTHON_TO_CPP_MIGRATION_PLAN.md),
[`docs/BINARY_VISIBLE_SECTOR_FORMAT.md`](docs/BINARY_VISIBLE_SECTOR_FORMAT.md).

### G. Render Mode (v0.7) — Debug Objects / Instances / Point Cloud

For larger scenes, switch the Render Mode strip in the dialog
from **Debug Objects** (one ``c4d.Onull`` per visible row, the
v0.1 default; cap 10 000) to **Instances** (one shared template
+ one ``c4d.Oinstance`` per row; cap 200 000) or
**Point Cloud (experimental)** (search-based inspection only;
cap 1 000 000). Mode switching is a Sync click; per-mode caps
and soft warnings live in
``unav_pro/core/render_mode.py``. Full walkthrough in
[`docs/V0_7_PERFORMANCE_LAYER.md`](docs/V0_7_PERFORMANCE_LAYER.md);
the backend interface in
[`docs/RENDER_BACKENDS.md`](docs/RENDER_BACKENDS.md);
Instance Mode trade-offs in
[`docs/INSTANCE_MODE_LIMITATIONS.md`](docs/INSTANCE_MODE_LIMITATIONS.md);
the future GPU path in
[`docs/FUTURE_GPU_POINT_RENDERER.md`](docs/FUTURE_GPU_POINT_RENDERER.md).

### F. Navigator UX (v0.6) — search, lock, bookmark, step

Once any dataset is loaded into the C4D plugin, the v0.6 tabs at
the bottom of the dialog give you:

* **Search** — type a name / uid / source / object type, get a
  ranked list across every active dataset, then **Focus** /
  **Lock Target** / **Add to Bookmarks**.
* **Bookmarks** — persistent saved anchors at
  `~/.unav_pro/bookmarks.json`. Add from a search result, capture
  the navigator's current position, focus / remove / reorder.
* **Navigation** — step the navigator forward / backward along
  its heading at a configurable parsec-per-step speed; lock /
  unlock a target.

Full walkthrough in
[`docs/V0_6_NAVIGATOR_UX.md`](docs/V0_6_NAVIGATOR_UX.md);
search + target-lock contracts in
[`docs/SEARCH_AND_TARGET_LOCK.md`](docs/SEARCH_AND_TARGET_LOCK.md);
bookmarks format in
[`docs/BOOKMARKS_SYSTEM.md`](docs/BOOKMARKS_SYSTEM.md);
route refinements in
[`docs/ROUTE_WORKFLOW_V2.md`](docs/ROUTE_WORKFLOW_V2.md).

---

## Data workflow (real catalogs)

UNAV Pro's data path is offline and chunked: catalogs are fetched
into JSONL by the CLI tools, indexed once, then queried by the
plugin one cone at a time. The plugin **never** loads the whole
catalog into RAM.

### 1. Fetch a Gaia sample

```bash
python tools/fetch_gaia_region.py \
    --ra 56.75 --dec 24.12 --radius-deg 1.0 \
    --limit 5000 \
    --output data/gaia_pleiades.jsonl
```

That hits the public Gaia ESA archive's TAP endpoint with an
ICRS cone-search ADQL query, normalizes the columns to UNAV's
schema, and writes JSONL. Sister tools exist for SDSS, DESI, and
JPL Horizons; see [`docs/DATA_SOURCE_OVERVIEW.md`](docs/DATA_SOURCE_OVERVIEW.md).

### 2. Build the spatial index (recommended for ≥ 5 k rows)

```bash
python tools/build_spatial_index.py \
    --input data/gaia_pleiades.jsonl \
    --output cache/gaia_pleiades \
    --chunk-size 5000
```

Bucketizes objects into a uniform parsec-Cartesian grid; produces
`cache/gaia_pleiades/index.json` plus per-cell JSONL chunks.
Queries load only the chunks the cone touches.
See [`docs/SPATIAL_INDEXING_AND_CHUNKING.md`](docs/SPATIAL_INDEXING_AND_CHUNKING.md).

### 3. Register the catalog with the dataset manager

* Open the **Dataset Manager…** dialog.
* **Add Dataset** → pick `data/gaia_pleiades.jsonl`. The registry
  scans it and shows row count, bounding radius, available fields,
  and source list.
* Click **Build Index** if you didn't run the CLI above.
* Click **Load Active Datasets** to merge every enabled entry into
  the metadata lookup. uids are namespaced as
  `<dataset_name>:<original_uid>` so multi-catalog scenes don't
  collide.

See [`docs/DATASET_MANAGER.md`](docs/DATASET_MANAGER.md) and
[`docs/DATA_SOURCE_OVERVIEW.md`](docs/DATA_SOURCE_OVERVIEW.md).

### 4. Generate a visible sector

* Click **Create Navigation Null** if you haven't already. Position
  and rotate it where you want the scene centered.
* Edit the navigator's user data: `cone_angle_deg`,
  `near_clip_parsec`, `far_clip_parsec`, `max_visible_objects`.
* Click **Generate Point Cloud**. The active filter runs against
  the navigator's pose; only the surviving objects become C4D
  nulls under `UNAV_Starfield → UNAV_VisibleSector`.

To iterate without rebuilding from scratch, click **Sync Visible
Sector** instead — it diffs the materialized set against the new
filter result and only adds/removes the delta.

See [`docs/RAY_CONE_FILTERING.md`](docs/RAY_CONE_FILTERING.md) and
[`docs/SCENE_SYNC_WORKFLOW.md`](docs/SCENE_SYNC_WORKFLOW.md).

### 5. Inspect metadata

Select any UNAV object in the Object Manager → **Inspect Selected
Object**. The metadata panel fills with identity / astrometry /
photometry sections plus the raw JSON. **Copy Metadata JSON**
emits a self-contained payload to the clipboard.

See [`docs/METADATA_INSPECTOR.md`](docs/METADATA_INSPECTOR.md).

### 6. Plan a route

Select a UNAV object → **Add Selected Object as Waypoint**. Repeat
for as many stops as you want. **Build Route Spline** draws a
linear C4D `SplineObject` through the resolvable waypoints.
**Focus Navigator on Waypoint** snaps the navigator to the last
waypoint added.

See [`docs/ROUTE_PLANNER.md`](docs/ROUTE_PLANNER.md).

### 7. Save state

**Save UNAV State** writes the navigator, route, active datasets,
visual encoding, and the saved-config snapshot into both:

* the C4D document's `BaseContainer` (so it persists with the
  `.c4d` save), and
* `~/.unav_pro/projects/<scene-stem>.json` (sidecar for cross-
  machine workflows).

**Load UNAV State** restores the same. See
[`docs/PERSISTENCE_AND_CONFIG.md`](docs/PERSISTENCE_AND_CONFIG.md).

---

## Project layout

```
unav_pro/                          # the plugin package
  unav_plugin.pyp                   # C4D entry point
  core/                             # pure CPython logic + state
    config.py, dataset_registry.py, logger.py, metadata_lookup.py
    navigation_state.py, project_state.py, route.py, safety.py
    scene_sync.py, spatial_filter.py, spatial_index.py
    visual_encoding.py, version_check.py, ...
  data/
    schema.py, catalog_io.py, sample_catalog_generator.py
    connectors/                     # gaia / sdss / desi / jpl_horizons
    samples/sample_catalog_100.jsonl
  c4d_objects/                      # ObjectData / TagData equivalents
    point_cloud_builder.py, navigation_null.py
  ui/                               # GeDialog subclasses
    main_dialog.py, dataset_manager.py, diagnostics_panel.py
    metadata_panel.py, route_panel.py
  tests/                            # pytest, c4d-free
tools/                              # offline preprocessing CLIs
docs/                               # per-feature deep docs
```

The architectural rationale lives in [`docs/UNAV_PRO_ARCHITECTURE.md`](docs/UNAV_PRO_ARCHITECTURE.md);
the plugin's package layout is documented in [`docs/PLUGIN_STRUCTURE.md`](docs/PLUGIN_STRUCTURE.md).

---

## Documentation map

* [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) — every dialog button
  and what it does, in order.
* [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md) —
  architecture, conventions, and how to add a new connector.
* [`docs/PRO_WORKFLOW.md`](docs/PRO_WORKFLOW.md) — recommended
  professional workflow assembling a multi-catalog scene end to
  end.
* [`docs/DATA_SOURCE_OVERVIEW.md`](docs/DATA_SOURCE_OVERVIEW.md) —
  Gaia / SDSS / DESI / JPL Horizons connectors at a glance.
* [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) — what doesn't work
  yet, and why.
* [`docs/ROADMAP_CPP_GPU_VERSION.md`](docs/ROADMAP_CPP_GPU_VERSION.md) —
  Python prototype bottlenecks, C++/Maxon SDK migration, GPU
  rendering, real-time sector streaming.
* [`docs/INSTALL_C4D_2023_PLUS.md`](docs/INSTALL_C4D_2023_PLUS.md) — install + troubleshoot.
* [`docs/V0_2_SECTOR_STREAMING_WORKFLOW.md`](docs/V0_2_SECTOR_STREAMING_WORKFLOW.md) — v0.2 streaming contract.
* [`docs/V0_3_GAIA_DR3_WORKFLOW.md`](docs/V0_3_GAIA_DR3_WORKFLOW.md) — v0.3 Gaia regional import.
* [`docs/GAIA_QUERY_LIMITS_AND_SAFETY.md`](docs/GAIA_QUERY_LIMITS_AND_SAFETY.md) — Gaia caps + safety.
* [`docs/V0_4_JPL_HORIZONS_WORKFLOW.md`](docs/V0_4_JPL_HORIZONS_WORKFLOW.md) — v0.4 JPL solar-system epoch import.
* [`docs/SOLAR_SYSTEM_COORDINATES_AND_EPOCHS.md`](docs/SOLAR_SYSTEM_COORDINATES_AND_EPOCHS.md) — heliocentric ICRF + epoch contract.
* [`docs/MIXED_DATASET_WORKFLOW.md`](docs/MIXED_DATASET_WORKFLOW.md) — Gaia + JPL + SDSS + DESI together in one C4D scene.
* [`docs/V0_5_SDSS_DESI_WORKFLOW.md`](docs/V0_5_SDSS_DESI_WORKFLOW.md) — v0.5 SDSS / DESI extragalactic import.
* [`docs/REDSHIFT_DISTANCE_LIMITATIONS.md`](docs/REDSHIFT_DISTANCE_LIMITATIONS.md) — redshift→distance proxy, when it fires, when it refuses.
* [`docs/EXTRAGALACTIC_VISUAL_ENCODING.md`](docs/EXTRAGALACTIC_VISUAL_ENCODING.md) — redshift colour mode + extragalactic palette.
* [`docs/V0_6_NAVIGATOR_UX.md`](docs/V0_6_NAVIGATOR_UX.md) — v0.6 navigator UX layer (search, target lock, bookmarks, route refinements, step navigation).
* [`docs/SEARCH_AND_TARGET_LOCK.md`](docs/SEARCH_AND_TARGET_LOCK.md) — search semantics + target-lock pose computation.
* [`docs/BOOKMARKS_SYSTEM.md`](docs/BOOKMARKS_SYSTEM.md) — persistent bookmarks, on-disk format, focus semantics.
* [`docs/ROUTE_WORKFLOW_V2.md`](docs/ROUTE_WORKFLOW_V2.md) — insert / replace / reorder + per-segment distance table.
* [`docs/V0_7_PERFORMANCE_LAYER.md`](docs/V0_7_PERFORMANCE_LAYER.md) — v0.7 render-backend layer (Debug Objects / Instances / Point Cloud).
* [`docs/RENDER_BACKENDS.md`](docs/RENDER_BACKENDS.md) — backend interface contract.
* [`docs/INSTANCE_MODE_LIMITATIONS.md`](docs/INSTANCE_MODE_LIMITATIONS.md) — what Instance Mode can and cannot do today.
* [`docs/FUTURE_GPU_POINT_RENDERER.md`](docs/FUTURE_GPU_POINT_RENDERER.md) — the GPU path the Point Cloud backend will become.
* [`docs/V0_8_NATIVE_CPP_FEASIBILITY.md`](docs/V0_8_NATIVE_CPP_FEASIBILITY.md) — v0.8 native-CPP feasibility spike summary.
* [`docs/MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md`](docs/MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md) — which C4D SDK plugin types apply to UNAV.
* [`docs/NATIVE_VIEWPORT_DRAWING_RESEARCH.md`](docs/NATIVE_VIEWPORT_DRAWING_RESEARCH.md) — viewport-draw API research for the v0.9 renderer.
* [`docs/PYTHON_TO_CPP_MIGRATION_PLAN.md`](docs/PYTHON_TO_CPP_MIGRATION_PLAN.md) — phased migration ledger.
* [`docs/BINARY_VISIBLE_SECTOR_FORMAT.md`](docs/BINARY_VISIBLE_SECTOR_FORMAT.md) — on-disk format the native plugin reads.
* [`docs/V0_9_NATIVE_VIEWER_PROTOTYPE.md`](docs/V0_9_NATIVE_VIEWER_PROTOTYPE.md) — v0.9 prototype summary + acceptance criteria.
* [`docs/BINARY_BRIDGE_WORKFLOW.md`](docs/BINARY_BRIDGE_WORKFLOW.md) — the file-based Python ↔ C++ bridge protocol.
* [`docs/NATIVE_LIMITATIONS.md`](docs/NATIVE_LIMITATIONS.md) — what the v0.9 prototype deliberately doesn't do.
* [`docs/V1_0_GPU_RENDERER.md`](docs/V1_0_GPU_RENDERER.md) — v1.0 native GPU point renderer summary + acceptance.
* [`docs/GPU_BUFFER_ARCHITECTURE.md`](docs/GPU_BUFFER_ARCHITECTURE.md) — three-class buffer / renderer architecture with CPU fallback.
* [`docs/CAMERA_RELATIVE_RENDERING.md`](docs/CAMERA_RELATIVE_RENDERING.md) — floating-origin pattern at the v2 binary format + renderer level.
* [`docs/PICKING_SYSTEM.md`](docs/PICKING_SYSTEM.md) — the three-layer picker (brute-force, accel grid, search fallback).
* [`docs/PERFORMANCE_TARGETS.md`](docs/PERFORMANCE_TARGETS.md) — v1.0 honest-numbers targets + the benchmark CLI.
* [`docs/V1_1_QUERY_ENGINE.md`](docs/V1_1_QUERY_ENGINE.md) — v1.1 SQL-backed query engine summary + acceptance.
* [`docs/V1_1_DATABASE_BACKEND.md`](docs/V1_1_DATABASE_BACKEND.md) — SQLite vs DuckDB choice + tuning.
* [`docs/SQL_SCHEMA.md`](docs/SQL_SCHEMA.md) — schema + indexes reference.
* [`docs/SPATIAL_QUERY_STRATEGY.md`](docs/SPATIAL_QUERY_STRATEGY.md) — bbox prefilter + exact cone refine.
* [`docs/DB_IMPORT_WORKFLOW.md`](docs/DB_IMPORT_WORKFLOW.md) — JSONL → SQLite importer CLI.
* [`docs/V1_2_TIME_NAVIGATION.md`](docs/V1_2_TIME_NAVIGATION.md) — v1.2 milestone summary: epoch-aware positions, proper motion, ephemeris states, Time Navigator dialog.
* [`docs/EPOCHS_AND_JULIAN_DATES.md`](docs/EPOCHS_AND_JULIAN_DATES.md) — the v1.2 time model (ISO ↔ JD ↔ Jyear, named epochs, ``coerce_epoch``).
* [`docs/GAIA_PROPER_MOTION_LIMITATIONS.md`](docs/GAIA_PROPER_MOTION_LIMITATIONS.md) — what the linear ICRS propagation does and does not approximate.
* [`docs/JPL_TIME_SERIES_WORKFLOW.md`](docs/JPL_TIME_SERIES_WORKFLOW.md) — multi-epoch JPL Horizons fetch into the v1.2 ``object_states`` table.
* [`docs/V1_3_KNOWLEDGE_LAYER.md`](docs/V1_3_KNOWLEDGE_LAYER.md) — v1.3 milestone summary: classifier, summary generator, glossary, upgraded inspector.
* [`docs/ASTROPHYSICAL_FIELD_GLOSSARY.md`](docs/ASTROPHYSICAL_FIELD_GLOSSARY.md) — definitions of every field the inspector renders.
* [`docs/OBJECT_CLASSIFICATION_RULES.md`](docs/OBJECT_CLASSIFICATION_RULES.md) — deterministic per-source classifier cascade.
* [`docs/METADATA_INTERPRETATION_LIMITS.md`](docs/METADATA_INTERPRETATION_LIMITS.md) — what v1.3 will and will not say about a row.
* [`docs/V1_4_GUIDED_VOYAGES.md`](docs/V1_4_GUIDED_VOYAGES.md) — v1.4 milestone summary: mission system, cinematic camera paths, deterministic playback.
* [`docs/MISSION_FORMAT.md`](docs/MISSION_FORMAT.md) — on-disk mission JSON layout + schema versioning.
* [`docs/CINEMATIC_CAMERA_PATHS.md`](docs/CINEMATIC_CAMERA_PATHS.md) — Catmull-Rom + slerp + epoch lerp, deterministic guarantees.
* [`docs/PLAYBACK_SYSTEM.md`](docs/PLAYBACK_SYSTEM.md) — transport semantics, sync cadence, safety contract.
* [`docs/V1_7_STABILIZATION.md`](docs/V1_7_STABILIZATION.md) — v1.7 stabilization milestone summary.
* [`docs/V1_7_ARCHITECTURE_AUDIT.md`](docs/V1_7_ARCHITECTURE_AUDIT.md) — v1.7 internal as-is audit (state surfaces, scene-sync risks, memory caps).
* [`docs/PLUGIN_LIFECYCLE.md`](docs/PLUGIN_LIFECYCLE.md) — startup / persistence / sync / shutdown lifecycle in detail.
* [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) — the corner cases v1.7 deliberately defers (with reasoning).
* [`docs/V1_8_CINEMATIC_NAVIGATION.md`](docs/V1_8_CINEMATIC_NAVIGATION.md) — v1.8 milestone summary: pause / look-at / roll / interp / scrub / bake.
* [`docs/CAMERA_PATH_AUTHORING.md`](docs/CAMERA_PATH_AUTHORING.md) — authoring deep-dive (waypoint additions, interpolation modes, tessellation).
* [`docs/TIMELINE_BAKING.md`](docs/TIMELINE_BAKING.md) — Cinema 4D keyframe baking contract (frame mapping, FPS, HPB conversion, decoupling from sector sync).
* [`docs/MISSION_PLAYBACK_POLISH.md`](docs/MISSION_PLAYBACK_POLISH.md) — new transport methods + scrub-slider integration + side-effect-free evaluation.

Per-feature deep docs:
[`UNAV_PRO_ARCHITECTURE`](docs/UNAV_PRO_ARCHITECTURE.md) ·
[`UNAV_PRO_DATA_PIPELINE`](docs/UNAV_PRO_DATA_PIPELINE.md) ·
[`UNAV_PRO_C4D_PLUGIN_STRATEGY`](docs/UNAV_PRO_C4D_PLUGIN_STRATEGY.md) ·
[`PLUGIN_STRUCTURE`](docs/PLUGIN_STRUCTURE.md) ·
[`POINT_CLOUD_GENERATION`](docs/POINT_CLOUD_GENERATION.md) ·
[`NAVIGATION_NULL_SYSTEM`](docs/NAVIGATION_NULL_SYSTEM.md) ·
[`RAY_CONE_FILTERING`](docs/RAY_CONE_FILTERING.md) ·
[`SPATIAL_INDEXING_AND_CHUNKING`](docs/SPATIAL_INDEXING_AND_CHUNKING.md) ·
[`SCENE_SYNC_WORKFLOW`](docs/SCENE_SYNC_WORKFLOW.md) ·
[`VISUAL_ENCODING`](docs/VISUAL_ENCODING.md) ·
[`METADATA_INSPECTOR`](docs/METADATA_INSPECTOR.md) ·
[`ROUTE_PLANNER`](docs/ROUTE_PLANNER.md) ·
[`DATASET_MANAGER`](docs/DATASET_MANAGER.md) ·
[`PERSISTENCE_AND_CONFIG`](docs/PERSISTENCE_AND_CONFIG.md) ·
[`DIAGNOSTICS`](docs/DIAGNOSTICS.md) ·
[`LARGE_DATA_SAFETY`](docs/LARGE_DATA_SAFETY.md) ·
[`GAIA_CONNECTOR`](docs/GAIA_CONNECTOR.md) ·
[`SDSS_CONNECTOR`](docs/SDSS_CONNECTOR.md) ·
[`DESI_CONNECTOR`](docs/DESI_CONNECTOR.md) ·
[`JPL_HORIZONS_CONNECTOR`](docs/JPL_HORIZONS_CONNECTOR.md).

---

## Testing

`pytest` from the `unav_pro/` directory:

```bash
cd unav_pro
python -m pytest tests/ -q
```

The suite is c4d-free: every module that touches the C4D host
guards its import behind `try: import c4d` and exposes pure
helpers that exercise without one. **500+ tests** at the time of
writing, covering catalog I/O, spatial filtering and indexing,
scene-sync diffing, route distance computation, persistence
round-trip, safety evaluators, the four real-catalog connectors
with mocked HTTP, and the dataclass shape of every UI controller.

---

## Status

The plugin is a working Python prototype with the architecture set
up so each piece can be replaced individually with a native /
GPU-accelerated implementation when needed. The long-term migration
plan is in [`docs/ROADMAP_CPP_GPU_VERSION.md`](docs/ROADMAP_CPP_GPU_VERSION.md);
the per-milestone phasing is in
[`docs/PYTHON_TO_CPP_MIGRATION_PLAN.md`](docs/PYTHON_TO_CPP_MIGRATION_PLAN.md).

### Current

* **v0.7** ships the render-backend layer (Debug Objects /
  Instances / Point Cloud-experimental) with per-mode safety
  caps and the search-based metadata fallback.
* **v0.8** locks the C++ surface and ships the binary
  visible-sector exporter (Python writer + reader + CLI) plus
  the four feasibility / migration docs.
* **v0.9** closes the bridge: a real C++
  `UnavPointBuffer::loadFromFile`, a fourth Render Mode, the
  file-based JSON bridge protocol, and three new dialog
  buttons.
* **v1.0** turns Native Point Viewer into a stable mode:
  GPU-buffer architecture with safe CPU fallback, shader-style
  render config, camera-relative coordinates via the v2
  binary format, accelerated picking with a uniform-grid
  spatial index, and a benchmark CLI for honest performance
  measurement.
* **v1.1** turns UNAV into a query engine. Catalogs land in
  a SQLite DB; the search panel runs typed SQL filters with
  pagination + timing; the visible-sector pipeline pulls from
  the DB via a bbox-prefilter + exact-cone-refine path; the
  Native Viewer keeps drawing the same v2 binary file. JSONL
  remains first-class.
* **v1.2** makes UNAV epoch-aware. ``core/time_model.py``
  centralises ISO ↔ JD ↔ Jyear conversions; the SQLite schema
  bumps to v2 with a new ``object_states`` time-series table;
  Gaia stars propagate via linear ICRS great-circle
  approximation; JPL bodies land as multi-epoch ``ephemeris``
  rows; the Time Navigator dialog panel lets the artist scrub
  the scene's epoch; the visible-sector binary export gains a
  v3 layout with ``epoch_jd`` + ``state_mode`` in the header.
  **1053 Python tests pass.**
* **v1.3** adds an astrophysical knowledge layer. A
  deterministic classifier (`star`/`galaxy`/`quasar`/`planet`/
  `moon`/`asteroid`/`comet`/`spacecraft`/`unknown`), a plain-
  text summary generator, a glossary of catalog terms, and
  physical-interpretation helpers (`spectral_class_hint`,
  `distance_quality`, `motion_summary`). The metadata
  inspector renders nine structured sections — Basic Identity,
  Position, Motion, Photometry, Redshift, Catalog Notes,
  Summary, Missing Data, Available Actions — and the rules
  never invent facts: missing fields are listed explicitly.
  No AI, no network.
* **v1.4** ships the guided voyage system. Missions
  (ordered waypoint sequences with optional epochs,
  orientations, durations, notes) persist to
  `~/.unav_pro/missions/`. A Catmull-Rom + slerp camera path
  builder produces an evaluable trajectory; a deterministic
  integer-step playback engine drives it with `play` /
  `pause` / `stop` / `step` / `next` / `prev` / `jump`
  transports. The Missions tab plus six transport buttons
  ship alongside `Import…` / `Export…` for sharing missions
  between machines. Visible-sector sync fires on transport
  jumps + at a bounded cadence during play; fast scrubs are
  auto-throttled. Same input → byte-identical output.
* **v1.7** is the stabilization milestone. New
  `core/state_manager.py` facade unifies every UNAV
  singleton (config, bookmarks, dataset registry, metadata
  lookup, time navigator, missions). Atomic JSON writes via
  `safe_write_json` protect every persistence surface from
  truncation on crash. Cone queries auto-derive a SQL
  `LIMIT` from `max_visible_objects` to bound working
  memory on million-row catalogs. Scene-walk hardening
  prevents iteration crashes during back-to-back sync.
  Uniform reload semantics across every singleton. UI verb
  consistency. New `V1_7_*`, `PLUGIN_LIFECYCLE`,
  `KNOWN_LIMITATIONS` docs. **No new features; 1255
  Python tests pass.**
* **v1.8** is the cinematic-navigation polish. The v1.4
  voyage system gains pause / look-at / roll waypoint
  fields and a smooth/linear interpolation switch on the
  camera path. Playback adds `jump_to_start`,
  `jump_to_end`, `scrub_to_progress`, and a
  side-effect-free `evaluate_at_progress` for live-preview
  during scrub. New `c4d_objects/timeline_keys.py` bakes a
  mission's camera path into the Cinema 4D timeline as
  keyframes (pure-Python generator + c4d-bound applier);
  new `c4d_objects/path_preview.py` drops a preview spline
  into the active document. Dialog gains **Preview Path**,
  **Clear Preview**, **Bake to Timeline**, scrub slider,
  start/end frame inputs, and an interp mode dropdown.
  Visible-sector generation stays decoupled from animation.
  No render-engine assumptions; no IPC. **1326 Python
  tests pass.**

### Current limitations

* **Per-point native draw** still uses `BaseDraw::DrawPoint`.
  The v1.0 GPU buffer abstraction is in place; the
  `DrawArrayWithVertexBuffer` swap is the next milestone's
  work.
* **CPU fallback by default for the native renderer.**
  `uploadImpl` returns `false`; the renderer walks the CPU
  shadow per draw.
* **No depth-buffer pick yet.** The accelerated picking is
  CPU-side (uniform grid).
* **Auto Sync still manual.** The Reload Native Viewer button
  / command is the trigger.
* **SQL backend is SQLite only.** DuckDB is the documented
  upgrade path — see
  [`docs/V1_1_DATABASE_BACKEND.md`](docs/V1_1_DATABASE_BACKEND.md).
* **Plugin IDs are placeholders.** Real PluginCafe IDs arrive
  with the v1.x build-harness landing.

### Next step

* **v1.x** — `BaseDraw::DrawArrayWithVertexBuffer` swap inside
  `SdkRenderer::drawImpl` (and the corresponding `uploadImpl`
  flip), `BaseDraw::PickObject` integration for pixel-accurate
  selection, an FTS5-backed name search, and a SceneHook that
  polls the request file per redraw for live Auto Sync — which
  also unlocks the per-frame play sweep the v1.2 Time Navigator
  panel has wired but parked, and the per-frame
  ``Playback.advance()`` cadence the v1.4 voyage engine needs
  for hands-free playback. The v1.2 epoch model + DB schema
  v2 + binary v3 + v1.3 knowledge layer + v1.4 mission /
  camera-path / playback contracts all stay unchanged behind
  the GPU / picking work.
