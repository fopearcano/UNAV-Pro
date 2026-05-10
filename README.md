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

### V. Large-Scale Workflow Optimization (v3.0)

v3.0 is the **scalability and streaming** milestone. Goal:
handle very large astronomical datasets stably inside
Cinema 4D. **Not** rendering. **Not** new authoring
surfaces. The runtime feature set is v2.5 byte-identical;
v3.0 adds the scaffolding underneath that makes the
existing surface survive 10 M-row catalogs and a working
artist's iterate-fast loop.

What's new:

* **Chunk-reuse cache** (`unav_pro/db/streaming.py::ChunkReuseCache`).
  LRU keyed by quantised pose + cone parameters + filter
  sets + epoch. Re-syncing at the same navigator pose
  serves the previous result. Cache invalidates on dataset
  change, epoch advance, or document save.
* **Paged loading** (`iter_paged_cone`). Streams a cone-
  query result page-by-page (default 5 000 rows per page)
  so a 250 K-row sector dispatches through the task queue
  without materialising the whole list.
* **Cone-query caps** (`QueryCaps` in
  `unav_pro/db/spatial_query.py`). Centralises bbox row
  caps + multipliers + hard ceilings. The default
  multiplier was bumped from 4× (v1.7) to 6× to give the
  cone refine more slack on anisotropic catalogs.
* **Query timing log** (`GLOBAL_QUERY_TIMING_LOG`).
  Bounded ring buffer of recent cone-query timings; the
  diagnostics panel renders "recent" + "slowest" + "mean".
* **Partial-rebuild planning** in `core/scene_sync.py`:
  `SyncDiff.is_unchanged`, `plan_overlay_rebuild`,
  `plan_science_rebuild`, `plan_mission_update`. The C4D
  builders read these to skip backend round-trips when
  nothing changed.
* **Task queue** (`unav_pro/core/task_queue.py`).
  Cooperative single-threaded queue with progress +
  cancellation. **No threads.** C4D API calls stay on the
  main thread. Long operations report progress between
  steps and honour cancellation cooperatively.
  `make_chunked_task(...)` builds a runner that walks
  units, reports progress, and exits early on cancel.
* **Diagnostics** (`unav_pro/core/diagnostics.py`). Pure
  helpers for the diagnostics panel: dataset memory
  estimate, visible-sector estimate, long-operation
  classifier, cache + timing renderers, overlay / science
  layer counts. `build_diagnostics_report(...)` is the
  single entry point.
* **Release artefacts** — `RELEASE_NOTES_v3.0.md`,
  CHANGELOG entry; the dialog status line shows the new
  version + codename on every open. Packaging script
  ships four new docs + the v3.0 release notes.
* **Tests** — `test_v30_streaming`,
  `test_v30_query_caps`, `test_v30_partial_sync`,
  `test_v30_task_queue`, `test_v30_diagnostics`. **118
  new tests; 1895 Python tests pass.**

Walkthroughs:
[`docs/V3_0_SCALABILITY_AND_STREAMING.md`](docs/V3_0_SCALABILITY_AND_STREAMING.md)
— milestone overview;
[`docs/LARGE_DATA_WORKFLOWS.md`](docs/LARGE_DATA_WORKFLOWS.md)
— artist-facing patterns;
[`docs/SAFE_TASK_QUEUE_MODEL.md`](docs/SAFE_TASK_QUEUE_MODEL.md)
— cooperative scheduling model;
[`docs/QUERY_OPTIMIZATION.md`](docs/QUERY_OPTIMIZATION.md)
— `db/spatial_query.py` + cache internals.

### U. Docs, Onboarding & Workflow Polish (v2.5)

v2.5 is the documentation, onboarding, and workflow-polish
release. **No new runtime systems**, no rendering, no IPC,
no RelativityRender bridge. The plugin's runtime surface is
byte-for-byte the same as v2.4; v2.5 adds the artist-facing
material that makes the v0.1 → v2.4 feature set learnable
in an afternoon.

What's new:

* **`docs/USER_MANUAL.md`** — canonical 12-section
  workflow reference. Read top-down on day one; skim by
  section header thereafter.
* **`docs/ARTIST_QUICKSTART.md`** — install → first
  cinematic in twelve numbered steps.
* **`docs/TD_GUIDE.md`** — technical-director / data-
  pipeline guide: schemas, performance limits (max
  visible objects, MAX_WAYPOINTS_PER_MISSION,
  MAX_FRAMES_FOR_BAKE, etc.), scene-sync model,
  timeline-bake model, lifecycle.
* **`docs/ROADMAP.md`** — implemented / planned /
  optional / explicitly out-of-scope. Restates the
  rendering / IPC / RelativityRender boundary as the v2.5
  contract.
* **`docs/QA_CHECKLIST.md`** §5 — eight-step manual end-
  to-end install test the release engineer runs on a
  fresh Cinema 4D (install → load sample → sync → inspect
  → mission → bake → export → reload).
* **`unav_pro/core/workflow_presets.py`** — thin artist-
  facing wrapper over the v1.9 voyage templates. Five
  presets (Solar System Flythrough, Stellar
  Neighbourhood, Hubble Flow Voyage, Blank Voyage,
  Selection Flythrough) with cinematic-ready defaults
  and recommended overlays per preset. Wrapper is fully
  transparent — every preset still resolves to a v1.9
  template builder, so the on-disk Mission JSON is
  byte-identical to the existing template path.
* **Release artefacts** — `RELEASE_NOTES_v2.5.md`,
  CHANGELOG entry; the dialog status line shows the new
  version + codename on every open. Packaging script
  ships the four new docs and the v2.5 release notes.
* **Tests** — `test_v25_workflow_presets` (preset shape,
  builder transparency, wrapper-vs-template equality)
  and `test_v25_docs` (doc-presence + anchor-section
  sanity).

Walkthroughs:
[`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) — the
artist reference,
[`docs/ARTIST_QUICKSTART.md`](docs/ARTIST_QUICKSTART.md) —
the 12-step quickstart,
[`docs/TD_GUIDE.md`](docs/TD_GUIDE.md) — the TD guide,
[`docs/ROADMAP.md`](docs/ROADMAP.md) — the forward-looking
scope.

### T. Production QA & Packaging (v2.4)

v2.4 turns the v2.3 codebase into something an artist can
install, sanity-check, and uninstall cleanly. **Release
engineering, not features.** No new navigation or rendering;
every change is reliability, packaging, or documentation.

What's new:

* **`unav_pro/version.py`** — single source of truth for
  the plugin version string. Surfaced in the dialog log,
  the export manifest, the packaging script.
* **`unav_pro/core/health_check.py`** — eight pre-flight
  probes (version, config dir, cache dir, dataset registry,
  sample catalog, DB module, voyage import, export import).
  Surfaced in the diagnostics panel via a new **Run Health
  Check** button.
* **`scripts/package_plugin.py`** — deterministic release-
  zip builder with required-file allowlist, exclude-fragment
  list, and a 5 MB per-file size cap. Output:
  `dist/unav_pro-<version>.zip`.
* **`scripts/run_tests.py`** — one-script test runner that
  classifies every `test_*.py` by category (state /
  animation / voyage / knowledge / overlays / science /
  export / v18 / v19 / release / other).
* **`dist/README.md`** — release-zip consumer guide.
* **`samples/minimal_unav_demo/`** — tiny self-contained
  catalog (5 rows) + mission JSON + route JSON + 30-second
  walkthrough README. Total budget under a few KB per file;
  ships in every release zip.
* **Doc refresh** — `docs/INSTALL_C4D_2023_PLUS.md`,
  new `docs/QUICK_START.md`, new `docs/TROUBLESHOOTING.md`.
  Three new docs: `V2_4_RELEASE_PREP.md`, `PACKAGING.md`,
  `QA_CHECKLIST.md`.
* **Release artefacts** — `RELEASE_NOTES_v2.4.md`,
  CHANGELOG entry, dialog status line shows the version on
  every open.
* **Tests** — `test_v24_version`, `test_v24_health_check`,
  `test_v24_packaging`, `test_v24_sample_demo`,
  `test_v24_run_tests`. 84 new tests; **1733 Python tests
  pass.**

Walkthroughs:
[`docs/V2_4_RELEASE_PREP.md`](docs/V2_4_RELEASE_PREP.md) —
milestone summary,
[`docs/PACKAGING.md`](docs/PACKAGING.md) — release-zip
mechanics + include / exclude rules,
[`docs/QA_CHECKLIST.md`](docs/QA_CHECKLIST.md) — pre-publish
ritual,
[`docs/QUICK_START.md`](docs/QUICK_START.md) — five-minute
install + smoke test,
[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) —
common fixes.

### S. Export Pipelines & Interchange (v2.3)

v2.3 makes UNAV's data **shareable**. Voyages, routes,
camera paths, timeline keyframes, and science-layer /
dataset summaries can be exported into self-describing
files other DCCs, archival workflows, or human readers can
consume — without UNAV running.

This is **not a render engine**. v2.3 is data interchange +
production workflow support. The visible-sector pipeline,
v2.0 overlays, v2.1 science layers, v2.2 timeline
integration, and the v1.x voyage tools are all unchanged.

What's new:

* **`export/` package** — central dispatch over eight
  stable formats: `mission_json`, `route_json`,
  `waypoint_csv`, `route_markdown`, `camera_path_json`,
  `timeline_keyframes_json`, `science_layer_json`,
  `dataset_summary_json`. Each is pre-flight-validated and
  atomically written.
* **Export package** — one-call directory builder that
  bundles missions, routes, camera paths, timeline data,
  dataset summaries, and arbitrary docs under a stable
  layout (`missions/`, `routes/`, `timelines/`,
  `camera_paths/`, `datasets/`, `summaries/`, `docs/`)
  with a top-level `manifest.json` carrying schema
  version, plugin version, coordinate convention, units,
  active datasets, and an inventory of every written
  file.
* **Camera-path interchange** — a DCC-agnostic JSON: per-
  frame position / HPB rotation / optional FOV / optional
  epoch / waypoint index, with an explicit `units` block
  so a Maya / Houdini / Blender importer knows exactly
  what it's reading.
* **Dataset summary** — JSON snapshot of the active dataset
  registry + navigator parameters + science-layer enable
  list + per-source / per-type histograms, with a plain-
  text renderer for the dialog log.
* **Pre-flight validators** — fail-closed `ValidationReport`
  for writable paths, missions, camera paths, registries,
  manifest integrity, duplicate filenames. Errors abort
  the export with no file written; warnings log and
  proceed.
* **Atomic writes everywhere** — every exporter goes
  through the v1.7 `safe_write_json` helper. A crash mid-
  write cannot truncate the previous valid file.
* **Filename hygiene** — mission titles with `/`, `:`, etc.
  are sanitised to safe filenames inside the package.
* **Dialog** — Missions tab gains six new export buttons:
  **Export Mission**, **Export Route**, **Export Camera
  Path**, **Export Timeline Data**, **Export Dataset
  Summary**, **Export Full Package…**.
* **Tests** — `test_v23_export_validation` (every
  validator), `test_v23_export_pipeline` (single-format
  exports, package builder, manifest round-trip, camera
  exchange, overwrite protection, sanitised filenames).
  57 new tests; **1649 Python tests pass.**

Walkthroughs:
[`docs/V2_3_EXPORT_PIPELINES.md`](docs/V2_3_EXPORT_PIPELINES.md)
— milestone summary,
[`docs/EXPORT_PACKAGE_FORMAT.md`](docs/EXPORT_PACKAGE_FORMAT.md)
— directory layout + manifest schema + versioning,
[`docs/CAMERA_PATH_INTERCHANGE.md`](docs/CAMERA_PATH_INTERCHANGE.md)
— DCC-agnostic camera JSON + units block + HPB convention,
[`docs/DATASET_SUMMARY_EXPORT.md`](docs/DATASET_SUMMARY_EXPORT.md)
— summary structure + reading outside UNAV.

### R. Animation & Timeline Integration (v2.2)

v2.2 polishes the v1.4 voyage stack + v1.8 timeline baker
into a workable animation-authoring pipeline inside Cinema
4D. Frame-aware mission state, UNAV-tagged timeline markers
(waypoint / epoch / sync / science), pure-read previews,
and a one-shot mission-to-timeline baker.

This is **not a render engine**. v2.2 is animation
*authoring*: keyframing, timeline markers, animated
navigation state. The visible-sector pipeline + v2.0
overlays + v2.1 science layers + v1.x voyage tools are
all unchanged.

What's new:

* **`animation/animated_state.py`** — pure-Python
  per-frame evaluator. ``AnimatedSample``,
  ``AnimatedTimeline``, ``evaluate_animated_state``,
  ``evaluate_at_frame`` / ``evaluate_at_seconds``
  (single-frame pure reads). Determinism: same input →
  byte-identical output.
* **`c4d_objects/timeline_markers.py`** — pure-Python
  ``MarkerRecord`` + ``MarkerBundle`` data layer +
  ``build_marker_bundle`` builder + ``apply_markers`` /
  ``clear_markers`` C4D applier. Idempotent via the
  ``UNAV:`` name prefix; markers placed by the artist
  or other plugins are untouched.
* **`c4d_objects/timeline_keys.py`** — extended with
  ``bake_mission_to_timeline``: keyframes (camera +
  navigator + optional FOV) + timeline markers in one
  transactional pass. The bake **never** triggers the
  visible-sector pipeline.
* **`voyage/playback.py`** — ``Playback.evaluate_at_frame``
  / ``evaluate_at_seconds``: side-effect-free pose
  readback at a Cinema 4D frame.
* **Dialog** — Missions tab gains **Clear UNAV Keyframes**,
  **Add Timeline Markers**, **Clear Timeline Markers**,
  **Preview at Frame**, **Sync Visible Sector at Frame**
  buttons + an **FOV (deg)** field + a **Preview frame**
  scrubber.
* **Tests** — ``test_v22_animated_state``,
  ``test_v22_timeline_markers``,
  ``test_v22_playback_and_bake`` (52 new tests; **1592
  Python tests pass**).
* **Marker-based sync, not per-frame.** Sync markers are
  *requests* the dialog / SceneHook honours separately;
  the bake never fires the visible-sector pipeline. See
  [`docs/SYNC_MARKERS_WORKFLOW.md`](docs/SYNC_MARKERS_WORKFLOW.md).

Walkthroughs:
[`docs/V2_2_ANIMATION_TIMELINE_INTEGRATION.md`](docs/V2_2_ANIMATION_TIMELINE_INTEGRATION.md)
— milestone summary,
[`docs/ANIMATED_UNAV_STATE.md`](docs/ANIMATED_UNAV_STATE.md)
— frame-aware evaluator contract,
[`docs/TIMELINE_MARKERS.md`](docs/TIMELINE_MARKERS.md) —
four marker kinds + idempotent applier,
[`docs/SYNC_MARKERS_WORKFLOW.md`](docs/SYNC_MARKERS_WORKFLOW.md)
— marker-based sync model.

### Q. Astrophysical Overlays & Science Layers (v2.1)

v2.1 adds **science-aware overlays** on top of v2.0's
procedural navigation overlays. Where v2.0 supplied neutral
navigation aids (grids, planes, distance rings), v2.1 lets
the artist drop layers that interpret the dataset: distance
/ redshift / magnitude shells, per-row motion vectors, per-
source bounding regions, solar-system orbital placeholders.

This is **not a render engine**. v2.1 layers materialise as
plain Cinema 4D scene objects under a dedicated
``UNAV_ScienceLayers`` root null — sibling of the v2.0
``UNAV_Overlays`` and the v0.1 ``UNAV_Starfield``, never
walks under either. The visible-sector pipeline + v2.0
overlays + v1.x voyage tools are all unchanged.

What's new:

* **`astro/overlay_layers.py`** — eight layer kinds:
  ``distance_shells`` / ``redshift_shells`` /
  ``magnitude_shells`` (real-but-cosmetic-mapping) +
  ``motion_vectors`` / ``catalog_source_regions`` /
  ``solar_system_orbits`` (dataset-driven) +
  ``constellation_boundaries`` / ``object_density_volume``
  (placeholders). Each carries its own `*Settings`
  dataclass.
* **`astro/science_layers.py`** — ``ScienceLayerSettings``
  aggregator + ``build_science_bundle`` orchestrator + the
  ``LAYER_SUPPORTED_SOURCES`` map documenting which catalog
  sources each layer benefits from.
* **`c4d_objects/overlays_builder.py`** — extended with
  ``apply_science_bundle()`` / ``clear_science_layers()``.
  Materialises bundles under ``UNAV_ScienceLayers``.
  **Idempotent**: re-build replaces per-layer containers in
  place; empty bundle drops the entire subtree.
* **`core/project_state.py`** — new `science_layers` dict on
  ``ProjectState``. Layer enable flags + per-layer knobs
  round-trip through the per-scene sidecar.
* **Dialog** — Overlays tab gains a Science Layers section
  with eight enable checkboxes + Build / Clear transports +
  status line.
* **Tests** — ``test_v21_science_layers`` (per-layer math,
  dataset-aware behaviour, settings round-trip, motion-vector
  caps), ``test_v21_persistence_and_builder`` (project-state
  round-trip incl. legacy v2.0 state, builder name contracts,
  no-c4d safety). 55 new tests; **1540 Python tests pass.**
* **Conservative scientific claims.** Every proxy / cosmetic
  mapping is documented; each layer that uses one logs a
  warning to the dialog. See
  [`docs/SCIENCE_LAYER_LIMITATIONS.md`](docs/SCIENCE_LAYER_LIMITATIONS.md).

Walkthroughs:
[`docs/V2_1_ASTROPHYSICAL_OVERLAYS.md`](docs/V2_1_ASTROPHYSICAL_OVERLAYS.md)
— milestone summary,
[`docs/SCIENCE_LAYER_SYSTEM.md`](docs/SCIENCE_LAYER_SYSTEM.md)
— eight layer kinds + math + idempotency contract,
[`docs/SCIENCE_LAYER_LIMITATIONS.md`](docs/SCIENCE_LAYER_LIMITATIONS.md)
— audit of every approximation / proxy / placeholder.

### P. Procedural Authoring Tools (v2.0)

v2.0 adds **procedural overlays** — navigation aids the
artist drops into the Cinema 4D scene without polluting the
real catalog data: coordinate grids, galactic / ecliptic
planes, distance rings, sector cone, route corridor, waypoint
labels.

This is **not a render engine**. v2.0 is authoring +
navigation support. Overlays sit under their own
``UNAV_Overlays`` root null and are siblings of the v0.1
``UNAV_Starfield`` — the visible-sector pipeline never sees
them and they cannot interfere with rendering or with dataset
objects.

What's new:

* **`procedural/overlays.py`** — pure-Python overlay
  computation. ``OverlaySettings`` dataclass + per-kind
  builders + ``build_overlay_bundle`` aggregator. Seven
  overlay kinds: `grid` / `galactic_plane` / `ecliptic_plane`
  / `distance_rings` / `sector_cone` / `route_corridor` /
  `waypoint_labels`.
* **`procedural/dataset_helpers.py`** — ``compute_bounding_sphere``
  (centroid + farthest-point radius), ``compute_source_distribution``
  (per-source / per-type histograms), plus placeholder helpers
  for the v2.x density-heatmap and redshift-shell overlays.
* **`c4d_objects/overlays_builder.py`** — c4d-bound applier.
  **Idempotent**: re-build replaces the per-kind containers
  in place; no scene-object duplication. Empty bundle drops
  the entire overlays subtree.
* **`core/project_state.py`** — new `overlays` dict on
  `ProjectState`. Overlay visibility + sizing round-trip
  through the per-scene sidecar via "Save UNAV State" /
  "Load UNAV State".
* **Dialog** — new **Overlays** tab with seven show/hide
  checkboxes, a radius scrubber, and **Build / Refresh** +
  **Clear Overlays** transports.
* **Tests** — ``test_v20_overlays`` (settings + math),
  ``test_v20_dataset_helpers`` (bounding sphere / source
  distribution / placeholders), ``test_v20_overlays_builder``
  (parent + container naming, no-c4d safety),
  ``test_v20_persistence`` (project-state round-trip). 64
  new tests; **1485 Python tests pass.**

Walkthroughs:
[`docs/V2_0_PROCEDURAL_AUTHORING_TOOLS.md`](docs/V2_0_PROCEDURAL_AUTHORING_TOOLS.md)
— milestone summary,
[`docs/OVERLAYS_SYSTEM.md`](docs/OVERLAYS_SYSTEM.md) —
seven overlay kinds + math + idempotency contract,
[`docs/DATASET_DERIVED_HELPERS.md`](docs/DATASET_DERIVED_HELPERS.md)
— bounding-sphere / source-distribution / placeholder helpers.

### O. Advanced Voyage Tools (v1.9)

v1.9 makes UNAV a professional voyage-planning and
animation-authoring tool inside Cinema 4D: richer waypoint
kinds, ready-made templates, route analytics, mission
organisation, annotation layers, and exporters.

This is **not a rendering release**. v1.9 is navigation
intelligence + animation planning. Every v1.4 / v1.8 mission
file round-trips through v1.9 byte-identical; v1.9 fields are
additive.

What's new:

* **Three new waypoint kinds** — ``search_result`` (uid +
  the query that found it), ``orbital`` (placeholder for
  epoch-driven bodies), ``annotation`` (pure metadata,
  never participates in the camera path). Plus three new
  optional fields on every kind: ``camera_offset``, ``tags``,
  ``search_query``.
* **Five voyage templates** — Solar System Tour, Nearest
  Stars Tour, Redshift Tour, Empty Voyage, Selected Objects
  Tour. Editable, not locked. The dialog's **Template** combo
  + **New From Template** button creates them.
* **Route analytics** — ``analyse_route(mission)`` computes
  segment distances, totals, ETAs, kind / type / source
  histograms, and epoch-consistency warnings. The dialog's
  **Route Analytics** button prints the report.
* **Mission organizer** — ``MissionManager`` gains
  ``duplicate``, ``rename``, ``add_tags`` / ``remove_tag``,
  ``search``, ``sort``, and full-library
  ``export_package`` / ``import_package``. Per-mission file
  writes route through v1.7's atomic ``safe_write_json``.
* **Annotation system** — three layers (waypoint / scene /
  mission). New ``SceneAnnotation`` dataclass + helpers,
  ``derive_notes(waypoint)`` synthesises plain-text prose
  from a waypoint's metadata.
* **Exporters** — ``mission_to_markdown`` (publication-style
  summary with route analytics + annotations) and
  ``mission_to_csv`` (one row per waypoint; spreadsheet-
  friendly). Both writers are atomic.
* **Dialog wiring** — Missions tab gains template picker +
  **New From Template**, **Duplicate Mission**,
  **Route Analytics**, **Export Markdown…** / **Export CSV…**,
  **Filter** + search input.
* **Tests** — `test_v19_waypoint_kinds`,
  `test_v19_templates`, `test_v19_route_analytics`,
  `test_v19_organizer`, `test_v19_annotations_export` cover
  every surface (95 new tests). **1421 Python tests pass.**

Walkthroughs:
[`docs/V1_9_ADVANCED_VOYAGE_TOOLS.md`](docs/V1_9_ADVANCED_VOYAGE_TOOLS.md)
— milestone summary,
[`docs/VOYAGE_TEMPLATES.md`](docs/VOYAGE_TEMPLATES.md) — the
five bundled templates + how to add new ones,
[`docs/ROUTE_ANALYTICS.md`](docs/ROUTE_ANALYTICS.md) —
analytics formula + warning conditions,
[`docs/MISSION_ORGANIZER.md`](docs/MISSION_ORGANIZER.md) —
duplicate / rename / tag / search / sort / packages,
[`docs/ANNOTATION_SYSTEM.md`](docs/ANNOTATION_SYSTEM.md) —
the three annotation layers + metadata-derived notes.

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
* [`docs/V1_9_ADVANCED_VOYAGE_TOOLS.md`](docs/V1_9_ADVANCED_VOYAGE_TOOLS.md) — v1.9 milestone summary: new waypoint kinds, templates, analytics, organizer, annotations, exporters.
* [`docs/VOYAGE_TEMPLATES.md`](docs/VOYAGE_TEMPLATES.md) — the five bundled mission templates + extension guide.
* [`docs/ROUTE_ANALYTICS.md`](docs/ROUTE_ANALYTICS.md) — distance / ETA / histogram / epoch-warning report contract.
* [`docs/MISSION_ORGANIZER.md`](docs/MISSION_ORGANIZER.md) — duplicate / rename / tag / search / sort / package import-export.
* [`docs/ANNOTATION_SYSTEM.md`](docs/ANNOTATION_SYSTEM.md) — three annotation layers + metadata-derived notes.
* [`docs/V2_0_PROCEDURAL_AUTHORING_TOOLS.md`](docs/V2_0_PROCEDURAL_AUTHORING_TOOLS.md) — v2.0 milestone summary: procedural overlays, dataset-derived helpers, persistence.
* [`docs/OVERLAYS_SYSTEM.md`](docs/OVERLAYS_SYSTEM.md) — seven overlay kinds + math + idempotency contract.
* [`docs/DATASET_DERIVED_HELPERS.md`](docs/DATASET_DERIVED_HELPERS.md) — bounding-sphere / source-distribution / placeholder helpers.
* [`docs/V2_1_ASTROPHYSICAL_OVERLAYS.md`](docs/V2_1_ASTROPHYSICAL_OVERLAYS.md) — v2.1 milestone summary: science layers + dataset-aware overlays.
* [`docs/SCIENCE_LAYER_SYSTEM.md`](docs/SCIENCE_LAYER_SYSTEM.md) — eight layer kinds, math, C4D builder idempotency.
* [`docs/SCIENCE_LAYER_LIMITATIONS.md`](docs/SCIENCE_LAYER_LIMITATIONS.md) — audit of every proxy / cosmetic mapping.
* [`docs/V2_2_ANIMATION_TIMELINE_INTEGRATION.md`](docs/V2_2_ANIMATION_TIMELINE_INTEGRATION.md) — v2.2 milestone summary: animated state, timeline markers, mission-to-timeline bake.
* [`docs/ANIMATED_UNAV_STATE.md`](docs/ANIMATED_UNAV_STATE.md) — frame-aware evaluator contract.
* [`docs/TIMELINE_MARKERS.md`](docs/TIMELINE_MARKERS.md) — four marker kinds + idempotent C4D applier.
* [`docs/SYNC_MARKERS_WORKFLOW.md`](docs/SYNC_MARKERS_WORKFLOW.md) — marker-based sync model + per-frame regeneration prohibition.
* [`docs/V2_3_EXPORT_PIPELINES.md`](docs/V2_3_EXPORT_PIPELINES.md) — v2.3 export milestone summary: eight formats + package builder + atomic writes.
* [`docs/EXPORT_PACKAGE_FORMAT.md`](docs/EXPORT_PACKAGE_FORMAT.md) — package directory layout + manifest schema + versioning.
* [`docs/CAMERA_PATH_INTERCHANGE.md`](docs/CAMERA_PATH_INTERCHANGE.md) — DCC-agnostic camera JSON + units block + HPB convention.
* [`docs/DATASET_SUMMARY_EXPORT.md`](docs/DATASET_SUMMARY_EXPORT.md) — dataset summary structure + reading outside UNAV.
* [`docs/V2_4_RELEASE_PREP.md`](docs/V2_4_RELEASE_PREP.md) — v2.4 release-engineering milestone summary.
* [`docs/PACKAGING.md`](docs/PACKAGING.md) — release-zip mechanics + include / exclude rules + required-file allowlist.
* [`docs/QA_CHECKLIST.md`](docs/QA_CHECKLIST.md) — pre-publish ritual every release runs through.
* [`docs/QUICK_START.md`](docs/QUICK_START.md) — five-minute install + smoke test.
* [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — common fixes for install / sync / bake / export issues.

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
* **v1.9** ships advanced voyage tools. Three new
  ``MissionWaypoint`` kinds (``search_result``, ``orbital``,
  ``annotation``) plus three optional fields
  (``camera_offset``, ``tags``, ``search_query``). Five
  ready-to-edit templates (``solar_system_tour``,
  ``nearest_stars_tour``, ``redshift_tour``, ``empty_voyage``,
  ``selected_objects_tour``). New ``voyage/route_analytics``
  module computes per-segment distances, ETA, histograms,
  and epoch-consistency warnings. ``MissionManager`` gains
  duplicate / rename / tag / search / sort + full-library
  package import/export. New ``voyage/annotations`` module
  with three annotation layers + a metadata-derived note
  synthesiser. New ``voyage/export`` module: Markdown +
  CSV exporters, both atomic. Dialog gains template picker,
  Duplicate / Analytics / Export Markdown / Export CSV /
  Filter buttons. Visible-sector pipeline + v1.8 timeline
  baking are unchanged. No rendering, no IPC. **1421
  Python tests pass.**
* **v2.0** ships procedural authoring tools. New
  ``procedural/`` package: pure-Python overlay computation
  (seven kinds — grid / galactic plane / ecliptic plane /
  distance rings / sector cone / route corridor / waypoint
  labels) plus dataset-derived helpers (bounding sphere,
  source distribution, density-heatmap + redshift-shell
  placeholders). New ``c4d_objects/overlays_builder.py``
  materialises bundles under an idempotent ``UNAV_Overlays``
  root null — re-builds replace in place; empty bundles drop
  the subtree. ``ProjectState`` carries an `overlays` dict so
  visibility + sizing persist across "Save / Load UNAV State".
  Dialog gains an **Overlays** tab with seven checkboxes +
  radius scrubber + Build / Clear transports. Visible-sector
  pipeline + v1.8 timeline baking + v1.9 voyage tools are
  all unchanged. No rendering, no IPC.
* **v2.1** ships astrophysical science layers. New
  ``astro/`` package with eight layer kinds —
  ``distance_shells``, ``redshift_shells`` (Hubble proxy,
  flagged), ``magnitude_shells`` (cosmetic mapping, flagged),
  ``motion_vectors`` (Gaia pmra/pmdec), ``catalog_source_regions``
  (per-source bounding spheres), ``solar_system_orbits``
  (placeholder rings), plus ``constellation_boundaries`` and
  ``object_density_volume`` placeholders. Settings round-trip
  through ``ProjectState.science_layers``; layers materialise
  under a separate ``UNAV_ScienceLayers`` root (idempotent).
  Dialog gains a Science Layers section in the Overlays tab.
  No scientific claims beyond data — every proxy / cosmetic
  mapping is logged as a warning and documented in
  ``SCIENCE_LAYER_LIMITATIONS.md``.
* **v2.2** ships animation + timeline integration polish.
  New ``animation/`` package with a frame-aware mission
  state evaluator (``AnimatedSample`` per frame, including
  navigator/camera positions, HPB rotation, optional FOV +
  epoch, ``waypoint_index``, ``is_sync_marker`` flag). New
  ``c4d_objects/timeline_markers.py`` drops UNAV-tagged
  markers (waypoint / epoch / sync / science) onto the
  Cinema 4D timeline; idempotent via the ``UNAV:`` name
  prefix. Extended ``timeline_keys`` with
  ``bake_mission_to_timeline`` — keyframes + markers in
  one transactional pass; the bake never triggers the
  visible-sector pipeline. ``Playback.evaluate_at_frame``
  / ``evaluate_at_seconds`` for pure-read previews. Dialog
  gains 5 new buttons + 2 new fields. Sync markers are
  *requests*, not actions — see
  ``SYNC_MARKERS_WORKFLOW.md``.
* **v2.3** ships the export pipelines + interchange layer.
  New ``export/`` package: ``ExportManager``-style dispatch
  over eight formats (mission JSON / route JSON / waypoint
  CSV / route Markdown / camera path JSON / timeline
  keyframes JSON / science layer JSON / dataset summary
  JSON), pre-flight ``ValidationReport`` (writable paths,
  missions, camera paths, registries, manifests, duplicate
  filenames), atomic writes via the v1.7 ``safe_write_json``
  helper. New ``export_package`` builder produces a
  self-describing directory tree with a stable manifest
  carrying schema version, plugin version, coordinate
  convention, units, and an inventory of every written
  file. New camera-path interchange JSON (DCC-agnostic;
  per-frame position + HPB rotation + optional FOV +
  optional epoch + waypoint index, with a units block).
  Dialog gains six Export buttons. Mission titles with
  illegal filename chars are sanitised.
* **v2.4** is the release-engineering milestone. Adds
  `unav_pro/version.py` (single source of truth for the
  plugin version), `core/health_check.py` (eight pre-flight
  probes with diagnostic-panel surface), `scripts/package_plugin.py`
  (deterministic release-zip builder with required-file
  allowlist + exclude-fragment list + 5 MB size cap),
  `scripts/run_tests.py` (one-script test runner with
  category classification), `samples/minimal_unav_demo/`
  (tiny self-contained catalog + mission + route +
  walkthrough README; ships in every release zip),
  `RELEASE_NOTES_v2.4.md` + CHANGELOG entry. Refreshed
  install docs (`INSTALL_C4D_2023_PLUS.md`, `QUICK_START.md`,
  `TROUBLESHOOTING.md`) + three new release-engineering
  docs (`V2_4_RELEASE_PREP.md`, `PACKAGING.md`,
  `QA_CHECKLIST.md`). Dialog status line shows the version
  on every open. **1733 Python tests pass.**

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
