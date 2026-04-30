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
  measurement. **896 Python tests + 30 C++ tests pass.**

### Current limitations (v1.0)

* **Per-point draw** still uses `BaseDraw::DrawPoint`. The GPU
  buffer abstraction is in place; v1.1 swaps the SDK draw call
  to `DrawArrayWithVertexBuffer` for a ~10× draw speedup at
  large point counts.
* **CPU fallback by default.** v1.0's `uploadImpl` returns
  `false` — the renderer walks the CPU shadow per draw. v1.1
  flips it to a real GPU upload.
* **No depth-buffer pick yet.** The accelerated picking is
  CPU-side (uniform grid). v1.1's `BaseDraw::PickObject`
  integration adds pixel-accurate picking.
* **Auto Sync still manual.** The Reload Native Viewer button
  / command is the trigger; v1.2's SceneHook auto-polls.
* **Plugin IDs are placeholders.** Real PluginCafe IDs arrive
  with v1.1's build-harness landing.

### Next step

* **v1.1** — `BaseDraw::DrawArrayWithVertexBuffer` swap inside
  `SdkRenderer::drawImpl` (and the corresponding `uploadImpl`
  flip), `BaseDraw::PickObject` integration for pixel-accurate
  selection, and PluginCafe-issued IDs. The buffer / renderer
  / bridge contract stays unchanged — the swap is a one-file
  change behind the existing `UnavGpuBuffer` /
  `UnavRenderer` interfaces.
