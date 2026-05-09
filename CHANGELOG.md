# Changelog

All notable changes to UNAV Pro are tracked here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [2.4.0] — Production QA & Packaging

Release-engineering milestone. No new navigation or rendering
features; every change is reliability, packaging, or
documentation.

### Added

* `unav_pro/version.py` — single source of truth for the
  plugin version string. Surfaced in the dialog log, the
  export manifest, and the packaging script.
* `unav_pro/core/health_check.py` — pre-flight diagnostics
  that verify plugin paths, config / cache writability,
  dataset registry, sample data, DB availability. Exposed
  in the diagnostics panel.
* `scripts/package_plugin.py` — release-zip builder that
  excludes tests / cache / generated data / heavy
  catalogs and validates contents.
* `scripts/run_tests.py` — one-script test runner.
* `dist/README.md` — release-zip consumer guide.
* `samples/minimal_unav_demo/` — tiny catalog + mission +
  route + README, safe to ship in the release zip.
* `RELEASE_NOTES_v2.4.md` — this milestone's release notes.
* New docs: `V2_4_RELEASE_PREP.md`, `PACKAGING.md`,
  `QA_CHECKLIST.md`.

### Changed

* `INSTALL_C4D_2023_PLUS.md`, `QUICK_START.md`, and
  `TROUBLESHOOTING.md` refreshed for the v2.4 install flow.

### Unchanged

* Every v1.x + v2.0–v2.3 feature surface is preserved.
* On-disk schemas (missions, routes, package manifests,
  camera exchange, dataset summary, science layers, overlay
  settings) round-trip byte-identical.
* DB schema v2, binary v3, mission schema v1 are unchanged.

## [0.1.0] — Universal Navigator Pro (Python prototype)

The first milestone release: a working C4D 2023+ Python plugin
that turns real-data catalogs into a navigator-bounded point
cloud, with metadata inspection, route planning, scene-sync
diff/update, persistence, and hard safety guardrails. Stdlib-only
at runtime; offline-first preprocessing; all c4d-bound code
guarded for tests.

### Added — Plugin core

* C4D 2023+ entry point (`unav_plugin.pyp`) with version gate,
  rotating-file logger, ring-buffer log capture, and idempotent
  command/dialog registration.
* Main control dialog (`Extensions → Universal Navigator Pro`)
  with grouped actions, status log, metadata panel, and route
  panel.

### Added — Data layer

* Canonical `CatalogObject` schema with required identity +
  optional astrometry / photometry fields, computed Cartesian
  and C4D-units coordinates, and a per-row `metadata_json` blob.
* JSONL and CSV catalog I/O with format dispatch by extension,
  bad-row tolerance, and structured validation summaries.
* Bundled deterministic sample catalog (`sample_catalog_100.jsonl`,
  60 stars / 25 galaxies / 10 quasars / 5 nebulae) regenerated
  by `data/sample_catalog_generator.py`.
* Four real-catalog connectors, all stdlib-only and
  fetcher-injectable for offline tests:
  * Gaia DR3 / DR2 (TAP / ADQL cone search).
  * NASA / JPL Horizons (single-body static ephemeris).
  * SDSS DR18 / DR17 (SkyServer SQL with optional spectro join).
  * DESI EDR / DR1 (NOIRLab Astro Data Lab TAP, optional
    `SPECTYPE` filter).
* Shared connector helpers (`data/connectors/_normalize.py`):
  `to_float`, `to_int`, `parse_csv` with banner-strip support.

### Added — Spatial layer

* Pure-CPython `core/spatial_filter.py`: cone + distance gate
  with per-reason rejection counts, source / type filters, and a
  brightness-or-distance sort under a hard `max_visible_objects`
  cap.
* Chunked `core/spatial_index.py`: uniform parsec-Cartesian grid
  written to `index.json` + per-cell JSONL chunks; the AABB-vs-
  cone gate is a conservative no-false-negative test that loads
  only the candidate cells' chunks.

### Added — Scene generation

* `c4d_objects/point_cloud_builder.py` builds the
  `UNAV_Starfield → UNAV_VisibleSector` hierarchy with one
  `c4d.Onull` per surviving catalog row; minimal-marker policy
  on by default (uid + source + type + name + RA/Dec/distance,
  no full metadata blob).
* Diff-and-update workflow (`core/scene_sync.py`): adds /
  removes / keeps individual uids without touching the rest of
  the visible sector. Optional debug-cone visualization under
  `UNAV_Debug`.
* Visual encoding (`core/visual_encoding.py`): six colour modes
  (natural / catalog source / object type / redshift / magnitude
  / BP-RP) with self-healing fallbacks; three size modes;
  size + brightness scalars.

### Added — Navigator + filtering

* `c4d_objects/navigation_null.py`: builds the three-object
  hierarchy (`UNAV_Navigator`, `UNAV_Camera`, `UNAV_ViewRay`)
  carrying eight `NavigationParams` fields as C4D user data plus
  a JSON-encoded copy on the marker container for round-trip
  safety.
* `get_navigation_origin / forward_vector / filter_params`
  accessors that the spatial filter consumes.

### Added — Metadata + route

* `core/metadata_lookup.py`: in-memory uid → CatalogObject index
  with lazy default loaded from the bundled sample.
* `ui/metadata_panel.py`: live inspector with four sections
  (Identity / Astrometry / Photometry / Raw JSON) and a *Copy
  Metadata JSON* clipboard payload.
* `core/route.py` + `ui/route_panel.py`: waypoint-list data
  model (object / coordinate / named kinds), distance summary in
  C4D units and parsec, linear `c4d.SplineObject` builder, and
  *Focus Navigator on Waypoint*.

### Added — Persistence + diagnostics + safety

* `core/config.py`: per-user preferences at
  `~/.unav_pro/config.json`, never raises on read/write failure.
* `core/project_state.py`: per-scene snapshot persisted into
  both the `BaseDocument` BaseContainer and a sidecar JSON at
  `~/.unav_pro/projects/<scene>.json`.
* `core/dataset_registry.py` + `ui/dataset_manager.py`: register
  / index / merge / namespace catalog files with persistence to
  `~/.unav_pro/datasets.json`.
* `core/logger.py` + `ui/diagnostics_panel.py`: ring-buffer log
  handler, environment snapshot (C4D / Python / platform /
  plugin root / cache / datasets / lookup / generated count),
  Diagnostics dialog with Refresh / Copy / Open Log Folder /
  Clear.
* `core/safety.py`: 100 000-object hard cap (default), warning
  threshold, dataset / scene / file-size advisories, visible-
  sector-only mode (default), loud `allow_full_catalog` override,
  minimal-marker policy. Refuses scene bloat by default.

### Added — Offline preprocessing CLIs

* `tools/fetch_gaia_region.py`,
  `tools/fetch_jpl_body.py`,
  `tools/fetch_sdss_region.py`,
  `tools/fetch_desi_region.py` — all stdlib-only, no creds.
* `tools/build_spatial_index.py` — chunked-grid writer.

### Added — Documentation

* Top-level: `README.md`, `docs/USER_GUIDE.md`,
  `docs/DEVELOPER_GUIDE.md`, `docs/PRO_WORKFLOW.md`,
  `docs/DATA_SOURCE_OVERVIEW.md`, `docs/LIMITATIONS.md`,
  `docs/ROADMAP_CPP_GPU_VERSION.md`,
  `docs/INSTALL_C4D_2023_PLUS.md`.
* Per-feature: `UNAV_PRO_ARCHITECTURE.md`,
  `UNAV_PRO_DATA_PIPELINE.md`,
  `UNAV_PRO_C4D_PLUGIN_STRATEGY.md`, `PLUGIN_STRUCTURE.md`,
  `POINT_CLOUD_GENERATION.md`, `NAVIGATION_NULL_SYSTEM.md`,
  `RAY_CONE_FILTERING.md`, `SPATIAL_INDEXING_AND_CHUNKING.md`,
  `SCENE_SYNC_WORKFLOW.md`, `VISUAL_ENCODING.md`,
  `METADATA_INSPECTOR.md`, `ROUTE_PLANNER.md`,
  `DATASET_MANAGER.md`, `PERSISTENCE_AND_CONFIG.md`,
  `DIAGNOSTICS.md`, `LARGE_DATA_SAFETY.md`,
  `GAIA_CONNECTOR.md`, `SDSS_CONNECTOR.md`,
  `DESI_CONNECTOR.md`, `JPL_HORIZONS_CONNECTOR.md`.

### Tests

* 551 c4d-free pytest tests covering catalog I/O, schema
  validation, coordinate conversion, spatial filter and index,
  scene-sync diff, route distance computation, persistence
  round-trip, safety evaluators, all four connectors with
  mocked HTTP, dataset-registry merge with uid namespacing,
  diagnostics ring buffer + environment snapshot, and the
  c4d-guard correctness of every UI controller.

### Known limitations (deferred to v0.2+)

See `docs/LIMITATIONS.md`. Headline items:

* ≤ 100 000 generated objects per scene (Python allocator
  ceiling).
* No real-time / animated navigation (Auto Sync placeholder).
* No live route playback (data model only).
* Coarse cosmology — Hubble-law inversion gated at z ≤ 0.1.
* No catalog crossmatch.
* UNAV objects are nulls; matrix-instance / TP render path not
  shipped.
* Plugin IDs are dev placeholders; replace before public
  distribution.
* Connectors do not retry on transient HTTP failures.

[0.1.0]: ../../tags/v0.1
