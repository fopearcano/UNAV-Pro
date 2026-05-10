# UNAV Pro — User Manual

The artist-facing reference for UNAV Pro v2.5. One document
covers every workflow surface the dialog exposes; for the
five-minute install + first-mission run, see
[`ARTIST_QUICKSTART.md`](ARTIST_QUICKSTART.md). For the
technical-director / data-pipeline view, see
[`TD_GUIDE.md`](TD_GUIDE.md).

Read top-down on the first day. Skim by section header
later.

---

## Table of contents

1. [What UNAV is](#1-what-unav-is)
2. [What UNAV is not](#2-what-unav-is-not)
3. [Installation](#3-installation)
4. [First launch](#4-first-launch)
5. [Dataset workflow](#5-dataset-workflow)
6. [Navigator workflow](#6-navigator-workflow)
7. [Search workflow](#7-search-workflow)
8. [Mission workflow](#8-mission-workflow)
9. [Animation & timeline workflow](#9-animation--timeline-workflow)
10. [Overlay & science-layer workflow](#10-overlay--science-layer-workflow)
11. [Export workflow](#11-export-workflow)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. What UNAV is

**UNAV Pro is an astronomical navigation + voyage / camera-
animation tool for Cinema 4D.**

It lets an artist (or a technical director) load real
astronomical catalog data — Gaia DR3 stars, JPL Horizons
solar-system bodies, SDSS / DESI galaxies and quasars — into
a Cinema 4D scene as a navigator-bounded point cloud, plan
guided voyages through the data, and bake those voyages to
the timeline as keyframes that drive a Cinema 4D camera + a
navigator null.

The plugin runs entirely on Cinema 4D's bundled Python; no
external libraries (no `numpy`, no `astropy`, no
`astroquery`) are required at runtime. Catalog ingestion
happens offline via small CLI tools. Catalog data is
streamed lazily into the scene through a navigator's view
cone, so a multi-million-row catalog never enters memory.

Everything UNAV produces — missions, routes, camera paths,
timeline keyframes, dataset summaries — is exportable as
DCC-agnostic JSON. A Houdini / Maya / Blender import script
can consume the camera-path JSON without UNAV.

---

## 2. What UNAV is not

UNAV is **not a render engine**. It does not produce images.
It does not ship shaders, render kernels, or a renderer
bridge. It does not integrate with RelativityRender. It does
not open sockets, talk over IPC, or run a network protocol.

UNAV is **not a cosmology engine**. The redshift → distance
helper is a coarse Hubble-law proxy and is loudly tagged as
such. The magnitude-shell overlay uses a cosmetic mapping,
not a flux–distance converter.

UNAV is **not a real-time scientific simulator**. The v1.2
time-navigator advances proper motion linearly; the v1.4
mission playback is integer-step + dialog-driven, not
frame-rate-locked. The v2.1 solar-system orbit overlay is a
placeholder ring at the body's instantaneous heliocentric
distance, not the true ellipse.

UNAV is **not a render queue**. Bake the timeline; render
in Cinema 4D's native pipeline.

For the full audit of what each subsystem will and will not
say, see:

* [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) — corner
  cases UNAV deliberately defers.
* [`SCIENCE_LAYER_LIMITATIONS.md`](SCIENCE_LAYER_LIMITATIONS.md)
  — every science-layer proxy, mapping, and placeholder.
* [`METADATA_INTERPRETATION_LIMITS.md`](METADATA_INTERPRETATION_LIMITS.md)
  — what the v1.3 inspector will and will not claim.

---

## 3. Installation

### 3.1 Cinema 4D version

UNAV requires Cinema 4D **2023, 2024, or 2025** (API
≥ 26000). The plugin refuses to register on older hosts and
logs the reason cleanly.

### 3.2 Plugin folder

Unzip `unav_pro-<version>.zip` into your Cinema 4D plugins
folder:

* **macOS:** `~/Library/Preferences/Maxon/Maxon Cinema 4D
  2024_<HASH>/plugins/`
* **Windows:** `%APPDATA%\Maxon\Maxon Cinema 4D 2024_<HASH>\plugins\`
* **Linux:** `~/.config/Maxon/Maxon Cinema 4D 2024_<HASH>/plugins/`

The plugin directory must contain `unav_plugin.pyp`
directly: `plugins/unav_pro/unav_plugin.pyp`.

For per-OS path detail and symlink-for-development tips,
see [`INSTALL_C4D_2023_PLUS.md`](INSTALL_C4D_2023_PLUS.md).

### 3.3 First-time verification

1. Restart Cinema 4D.
2. **Extensions → Universal Navigator Pro**.
3. **Diagnostics → Run Health Check**.

A clean install reports `Health: OK (8 probe(s)).` with
every probe `[OK]`. Failures + warnings are documented
verbatim in [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

---

## 4. First launch

The dialog opens with eight tab groups:

* **Status log** — every UNAV log line. Read it when
  something goes wrong.
* **Datasets** — the active dataset registry.
* **Navigator** — the navigator-null pose + cone parameters.
* **Search** — find an object by name / uid / source.
* **Bookmarks** — saved anchors.
* **Missions** — the v1.4 voyage system + v2.2 timeline
  bake + v2.3 export buttons.
* **Overlays** — v2.0 procedural overlays + v2.1 science
  layers.
* **Diagnostics** — health check + ring-buffer log capture.

Open a fresh Cinema 4D scene. UNAV state at
`~/.unav_pro/` (config, bookmarks, dataset registry,
missions library) is preserved across sessions.

---

## 5. Dataset workflow

UNAV consumes catalog data in three forms:

| Form | When to use |
|------|-------------|
| **JSONL** | Default. The v0.x preprocessing CLIs produce JSONL; small-to-medium catalogs (≤ ~1M rows) work directly. |
| **Indexed JSONL** | Per-cell chunks under a `cache/<dataset>/index.json`. Streams cone-bounded subsets without loading the whole file. |
| **DB-backed (SQLite)** | The v1.1 import path. Up to ~10M rows with bbox-prefiltered cone queries. |

### 5.1 Loading a JSONL catalog

1. Run a preprocessing CLI (e.g. `tools/fetch_gaia_region.py`)
   to produce a `.jsonl` file.
2. **Dataset Manager…** → **Add Dataset** → pick the file.
3. Click **Load Active Datasets**.

The dialog log says `N objects merged`. The full record set
lives in the v0.6 `MetadataLookup` for inspector reads;
visible-sector streaming uses the file directly.

### 5.2 Building a spatial index

For ≥ 5k rows, build a chunked index so the navigator's
cone only loads the cells it touches:

```bash
python tools/build_spatial_index.py \
    --input data/gaia_pleiades.jsonl \
    --output cache/gaia_pleiades \
    --chunk-size 5000
```

In the dialog: **Dataset Manager… → Build Index** points the
entry at the cache directory. The registry's column flips
from `jsonl` to `idx`.

### 5.3 DB-backed datasets

Import a JSONL into SQLite for the largest catalogs:

```bash
python tools/import_catalog_to_db.py \
    --input data/gaia_pleiades.jsonl \
    --db data/unav.db
```

In the dialog: **Add DB-backed Dataset** → pick the `.db`.
The visible-sector pipeline routes through
`db/spatial_query.query_cone` instead of the JSONL streamer.

See [`DB_IMPORT_WORKFLOW.md`](DB_IMPORT_WORKFLOW.md) and
[`V1_1_QUERY_ENGINE.md`](V1_1_QUERY_ENGINE.md).

### 5.4 The bundled minimal demo

Every release zip ships
`samples/minimal_unav_demo/catalog.jsonl` — five rows, all
classes. Use it to verify the install before downloading
real data. See
[`samples/minimal_unav_demo/README.md`](../samples/minimal_unav_demo/README.md).

---

## 6. Navigator workflow

### 6.1 The navigator null

**Create Navigation Null**. UNAV inserts a `UNAV_Navigator`
null at the world origin. Its user data drives the visible-
sector cone:

* `cone_angle_deg` — half-angle of the view cone.
* `near_clip_parsec`, `far_clip_parsec` — depth range.
* `max_visible_objects` — safety cap; the v1.7 SQL `LIMIT`
  derives from this so the working memory is bounded.
* `selected_catalog_sources` — comma-separated source filter.
* `c4d_scale` — distance scale (`au` / `ly` / `pc` / `kpc` /
  `mpc`).

Move + rotate the navigator like any other Cinema 4D null.
The artist drives it; UNAV reads the pose at sync time.

### 6.2 Sync visible sector

**Sync Visible Sector**:

1. Reads the navigator pose + parameters.
2. Streams catalog candidates through the bbox-prefilter +
   exact-cone-refine path.
3. Diffs against the currently-materialised
   `UNAV_VisibleSector` children.
4. Removes objects that fell out of view; keeps survivors;
   adds the newly visible ones.
5. Fires Cinema 4D's `EventAdd` so the viewport refreshes.

Re-clicking Sync is incremental: only the delta is touched.
Selection / animation / per-object tags survive every
iteration.

### 6.3 Step navigation

The Navigation tab's **Step Forward** / **Step Backward**
buttons advance the navigator along its heading by
`step_pc` parsec per click. **Lock Target** snaps the
navigator's heading onto the selected UNAV object.

---

## 7. Search workflow

The Search tab queries the active datasets by free text:

```
Find    : sirius
Source  : (optional) Gaia DR3
Pick #  : 0
[Search]   [Focus]   [Lock Target]   [Add to Bookmarks]
```

Results are ranked by:

1. Exact uid match.
2. Exact name match.
3. Substring match against name / common_name / catalog
   source / object type.

Up to 500 hits are returned per query. The Pick # field
selects one by index; **Focus** snaps the navigator to its
position; **Lock Target** points the navigator at it
without moving the camera.

See [`SEARCH_AND_TARGET_LOCK.md`](SEARCH_AND_TARGET_LOCK.md).

---

## 8. Mission workflow

A *mission* is a saved sequence of waypoints with optional
epochs, durations, camera orientations, look-at targets,
roll, camera offset, tags, and notes. The Missions tab is
where the artist:

1. **New Mission** (or **New From Template** — see §8.5).
2. **Add Selected Object as Waypoint** /
   **Add Picked Bookmark as Waypoint**.
3. (Optional) **Preview Path** to drop a Cinema 4D
   `SplineObject` showing the camera curve.
4. Use the transport buttons (◀◀ Prev / ◀ Step / ▶ Play /
   ❚❚ Pause / ◼ Stop / Step ▶ / Next Wp ▶▶ / |◀ Start /
   End ▶|) or the Scrub slider to verify timing.
5. **Bake to Timeline** when ready.

### 8.1 Waypoint kinds

| Kind | Reference |
|------|-----------|
| `object` | A catalog uid resolved by the active lookup. |
| `coordinate` | A free 3D point in C4D world units. |
| `named` | A label-only anchor. |
| `bookmark` | A bookmark id from the v0.6 bookmarks list. |
| `search_result` | A uid + the search query that produced it. |
| `orbital` | Placeholder for an epoch-driven body (resolved like `object` today). |
| `annotation` | Pure metadata; never participates in the camera path. |

### 8.2 Waypoint fields

* `epoch_jd` — Julian Date the waypoint should be observed
  at; baked into the v2.2 animated state.
* `duration_seconds` / `pause_seconds` — travel time +
  dwell time.
* `orientation_quat` — explicit camera orientation.
* `look_at_uid` / `look_at_position` — point the camera at
  a target while the cursor is on the waypoint.
* `roll_deg` — camera roll about the forward axis.
* `camera_offset` — `(dx, dy, dz)` shift of the camera
  position from the navigator anchor.
* `tags` — free-form labels (lower-cased).
* `notes` — free text.

See [`V1_4_GUIDED_VOYAGES.md`](V1_4_GUIDED_VOYAGES.md),
[`V1_8_CINEMATIC_NAVIGATION.md`](V1_8_CINEMATIC_NAVIGATION.md),
[`V1_9_ADVANCED_VOYAGE_TOOLS.md`](V1_9_ADVANCED_VOYAGE_TOOLS.md).

### 8.3 Camera path

`camera_path.build_camera_path(mission, config)` produces an
evaluable `CameraPath`. Knobs:

* `interp_mode` — `smooth` (Catmull-Rom; default) or
  `linear` (straight-line per segment).
* `speed_multiplier` — uniformly scale every duration.
* `honour_pause_seconds`, `honour_look_at` — opt out of the
  v1.8 / v1.9 features.

The path is deterministic: same inputs → byte-identical
output.

### 8.4 Mission organiser

The v1.9 organiser exposes:

* **New From Template** picks one of the bundled templates
  (Solar System, Nearest Stars, Redshift, Empty,
  Selected Objects).
* **Duplicate Mission** clones the active mission with a
  fresh id.
* **Filter** searches missions by title / tag.
* **Export Markdown / CSV** writes a publication-style
  summary or a spreadsheet-ready row list.

### 8.5 Templates (workflow presets)

Built-in templates produce *editable* missions, not locked
presets:

* `solar_system_tour` — eight planets at a chosen epoch.
* `nearest_stars_tour` — Sun + closest neighbours
  (Gaia DR3).
* `redshift_tour` — increasing-z extragalactic anchors
  (loudly tagged `approximate`).
* `empty_voyage` — zero-waypoint scaffold.
* `selected_objects_tour` — one waypoint per supplied uid.

See [`VOYAGE_TEMPLATES.md`](VOYAGE_TEMPLATES.md).

---

## 9. Animation & timeline workflow

### 9.1 Bake

**Bake to Timeline** writes camera + navigator keyframes
for every frame in `[start_frame, end_frame]` and drops
UNAV-tagged timeline markers. The bake never triggers a
visible-sector sync; markers are *requests* the dialog (or
a future SceneHook) honours separately.

Timeline markers come in four kinds (all prefixed
`UNAV:`):

* `waypoint` — one per waypoint anchor frame.
* `epoch` — one per waypoint with an epoch change.
* `sync` — one per sync-marker frame.
* `science` — caller-supplied science-layer refresh frames.

Re-baking removes every previous UNAV-prefixed marker
before writing the new set; markers placed by the artist or
by other plugins are left untouched.

See [`V2_2_ANIMATION_TIMELINE_INTEGRATION.md`](V2_2_ANIMATION_TIMELINE_INTEGRATION.md),
[`TIMELINE_MARKERS.md`](TIMELINE_MARKERS.md), and
[`SYNC_MARKERS_WORKFLOW.md`](SYNC_MARKERS_WORKFLOW.md).

### 9.2 Preview at frame

**Preview at Frame** is a *pure read*: it logs the camera
pose at the dialog's `Preview frame` value without touching
the C4D scene. Useful for verifying alignment before a
bake.

### 9.3 Sync visible sector at frame

**Sync Visible Sector at Frame** triggers a single visible-
sector refresh against the mission state evaluated at that
frame. Useful when the artist wants the scene to reflect
the navigator pose at a specific timeline cursor without
running a full Sync click.

---

## 10. Overlay & science-layer workflow

### 10.1 Procedural overlays (v2.0)

The Overlays tab carries seven navigation-aid toggles:

* **Coordinate grid** — XY grid at the chosen step + extent.
* **Galactic plane** — great circle perpendicular to the
  galactic pole.
* **Ecliptic plane** — tilted ~23.44° about the ICRS +X
  axis.
* **Distance rings** — concentric XY circles at user-
  supplied parsec radii.
* **Sector cone** — wireframe of the navigator's view cone.
* **Route corridor** — centre line + parallel offset edges
  along the active route.
* **Waypoint labels** — text anchors floating above each
  waypoint.

Click **Build / Refresh** to materialise. Click **Clear
Overlays** to remove the entire `UNAV_Overlays` subtree.
Settings round-trip through the per-scene project state
sidecar.

See [`V2_0_PROCEDURAL_AUTHORING_TOOLS.md`](V2_0_PROCEDURAL_AUTHORING_TOOLS.md)
and [`OVERLAYS_SYSTEM.md`](OVERLAYS_SYSTEM.md).

### 10.2 Science layers (v2.1)

Below the procedural overlays, the **Science Layers**
section toggles eight kinds:

* **Distance shells** — three orthogonal great circles per
  radius. Real (no proxy).
* **Redshift shells** — Hubble-law proxy. **Tagged
  approximate; not for cosmology.**
* **Magnitude shells** — cosmetic mag→radius mapping.
  Visual aid only.
* **Motion vectors** — Gaia pmra / pmdec / radial
  velocity vectors per row.
* **Catalog source regions** — bounding sphere per
  catalog source.
* **Solar System orbits** — placeholder rings at JPL
  bodies' instantaneous distance.
* **Constellation boundaries** — placeholder.
* **Object density volume** — placeholder.

Every science layer that uses a proxy or cosmetic mapping
emits a warning to the dialog log; polyline labels carry
`(approximate)` / `(cosmetic)` / `(placeholder)` tags so
screenshots carry the disclaimer. See
[`SCIENCE_LAYER_LIMITATIONS.md`](SCIENCE_LAYER_LIMITATIONS.md).

Build / Clear behave the same as the v2.0 overlays;
settings round-trip through `ProjectState.science_layers`.

---

## 11. Export workflow

The Missions tab carries six **Export** buttons:

* **Export Mission** → mission JSON (v1.4 schema).
* **Export Route** → route JSON (v0.6 schema).
* **Export Camera Path** → DCC-agnostic JSON with per-frame
  position, HPB rotation, optional FOV, optional epoch,
  waypoint index, and a `units` block.
* **Export Timeline Data** → flat keyframe JSON.
* **Export Dataset Summary** → registry + navigator + science
  layer summary JSON.
* **Export Full Package…** → directory tree under
  `UNAV_Export/` with `manifest.json` carrying schema
  version, plugin version, coordinate convention, units, and
  an inventory of every written file.

Every exporter is fail-closed: any pre-flight error aborts
the export with no file written. Atomic writes go through
the v1.7 `safe_write_json` helper; a crash mid-write cannot
truncate a previously valid file.

See [`V2_3_EXPORT_PIPELINES.md`](V2_3_EXPORT_PIPELINES.md),
[`EXPORT_PACKAGE_FORMAT.md`](EXPORT_PACKAGE_FORMAT.md),
[`CAMERA_PATH_INTERCHANGE.md`](CAMERA_PATH_INTERCHANGE.md),
[`DATASET_SUMMARY_EXPORT.md`](DATASET_SUMMARY_EXPORT.md).

---

## 12. Troubleshooting

When something goes wrong:

1. Open **Diagnostics** → **Run Health Check**.
2. Read the dialog log.
3. Open `~/.unav_pro/logs/unav_pro.log` (rotating file).

Common failures + fixes are documented in
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md). The QA
checklist in [`QA_CHECKLIST.md`](QA_CHECKLIST.md) is the
canonical "are you sure it's UNAV?" filter — every item
there is a reproduction step a maintainer will ask for
first.

If you've worked through both docs and the issue remains,
file an issue with:

* the dialog log contents,
* `~/.unav_pro/logs/unav_pro.log`,
* the health-check output,
* the steps to reproduce.

---

## Appendix A — Glossary

| Term | Meaning |
|------|---------|
| Active dataset | A dataset entry with `enabled=True` in the registry. |
| Bookmark | A saved navigator anchor (object uid or coordinate). |
| Camera path | A built, evaluable trajectory derived from a mission. |
| Catalog object | One row in the canonical UNAV schema (`CatalogObject`). |
| Cone | The navigator's view frustum (origin + forward + half-angle + clip range). |
| Mission | An ordered sequence of waypoints + metadata. |
| Navigator | The `UNAV_Navigator` null whose pose drives the visible sector. |
| Route | A v0.6 ordered list of waypoints rendered as a Cinema 4D spline. |
| Science layer | A v2.1 dataset-aware overlay (e.g. motion vectors, source regions). |
| Visible sector | The set of catalog objects currently materialised under `UNAV_VisibleSector`. |
| Waypoint | One stop in a mission or route. |

## Appendix B — Doc reference (by topic)

* **Install:** [`INSTALL_C4D_2023_PLUS.md`](INSTALL_C4D_2023_PLUS.md), [`QUICK_START.md`](QUICK_START.md).
* **Architecture:** [`UNAV_PRO_ARCHITECTURE.md`](UNAV_PRO_ARCHITECTURE.md), [`PLUGIN_LIFECYCLE.md`](PLUGIN_LIFECYCLE.md), [`V1_7_ARCHITECTURE_AUDIT.md`](V1_7_ARCHITECTURE_AUDIT.md).
* **Data layer:** [`DATA_SOURCE_OVERVIEW.md`](DATA_SOURCE_OVERVIEW.md), [`SQL_SCHEMA.md`](SQL_SCHEMA.md), [`DB_IMPORT_WORKFLOW.md`](DB_IMPORT_WORKFLOW.md).
* **Time:** [`V1_2_TIME_NAVIGATION.md`](V1_2_TIME_NAVIGATION.md), [`EPOCHS_AND_JULIAN_DATES.md`](EPOCHS_AND_JULIAN_DATES.md).
* **Voyage stack:** [`V1_4_GUIDED_VOYAGES.md`](V1_4_GUIDED_VOYAGES.md), [`V1_8_CINEMATIC_NAVIGATION.md`](V1_8_CINEMATIC_NAVIGATION.md), [`V1_9_ADVANCED_VOYAGE_TOOLS.md`](V1_9_ADVANCED_VOYAGE_TOOLS.md).
* **Animation / timeline:** [`V2_2_ANIMATION_TIMELINE_INTEGRATION.md`](V2_2_ANIMATION_TIMELINE_INTEGRATION.md).
* **Overlays / science layers:** [`V2_0_PROCEDURAL_AUTHORING_TOOLS.md`](V2_0_PROCEDURAL_AUTHORING_TOOLS.md), [`V2_1_ASTROPHYSICAL_OVERLAYS.md`](V2_1_ASTROPHYSICAL_OVERLAYS.md).
* **Export:** [`V2_3_EXPORT_PIPELINES.md`](V2_3_EXPORT_PIPELINES.md).
* **Release:** [`V2_4_RELEASE_PREP.md`](V2_4_RELEASE_PREP.md), [`PACKAGING.md`](PACKAGING.md).
* **Limits:** [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md), [`SCIENCE_LAYER_LIMITATIONS.md`](SCIENCE_LAYER_LIMITATIONS.md), [`METADATA_INTERPRETATION_LIMITS.md`](METADATA_INTERPRETATION_LIMITS.md).
* **Roadmap:** [`ROADMAP.md`](ROADMAP.md).
