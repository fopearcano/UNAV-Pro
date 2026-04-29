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
helpers that exercise without one. **529 tests** at the time of
writing, covering catalog I/O, spatial filtering and indexing,
scene-sync diffing, route distance computation, persistence
round-trip, safety evaluators, the four real-catalog connectors
with mocked HTTP, and the dataclass shape of every UI controller.

---

## Status

The plugin is a working Python prototype with the architecture set
up so each piece can be replaced individually with a native /
GPU-accelerated implementation when needed. The migration plan is
in [`docs/ROADMAP_CPP_GPU_VERSION.md`](docs/ROADMAP_CPP_GPU_VERSION.md).
