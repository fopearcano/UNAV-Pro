# Changelog

All notable changes to UNAV Pro are tracked here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [3.3.0] — Presentation & Educational Mode

Guided-presentation milestone. Goal: let UNAV drive
lectures, exhibitions, scientific storytelling, and
cinematic demonstrations inside Cinema 4D. **Not**
rendering. **Not** new authoring surfaces. v3.2
runtime preserved byte-identical; v3.3 adds a
declarative presentation layer on top.

### Added

* `unav_pro/presentation/` (new package):
  * `presentation_sequence.py` — declarative
    sequence shape (`PresentationSequence`,
    `PresentationStep`, `ResolvedStep`); steps
    inherit Optional fields from the previous step,
    so `resolved_steps()` yields complete records.
  * `presentation_state.py` — runtime tracker
    (`PresentationState` with idle / running /
    paused / finished states; navigation;
    `lock_navigation`).
  * `annotations.py` — per-step visibility +
    highlight resolver + diff helper.
  * `overlay_states.py` — per-step overlay /
    science-layer flag merge + diff.
  * `manager.py` — disk-backed CRUD store
    mirroring the v1.4 `MissionManager` shape.
  * `export.py` — Markdown summary, presenter-
    notes plain-text dump, package payload for
    the v2.3 export builder.
* `unav_pro/ui/presentation_panel.py` — pure-Python
  facade for the dialog's *Presentation* panel
  (Start / Next / Previous / Jump / Pause / Resume
  / End / Presenter Notes).
* New docs:
  `docs/V3_3_PRESENTATION_MODE.md`,
  `docs/PRESENTATION_SEQUENCES.md`,
  `docs/EDUCATIONAL_WORKFLOWS.md`,
  `docs/PRESENTER_NOTES.md`.
* `RELEASE_NOTES_v3.3.md`.
* New tests: `test_v33_presentation_sequence`,
  `test_v33_presentation_state`,
  `test_v33_annotations`,
  `test_v33_overlay_states`,
  `test_v33_manager`,
  `test_v33_export`,
  `test_v33_panel_actions`. **152 new tests.**

### Changed

* `scripts/package_plugin.py` ships the four new
  docs + the v3.3 release notes.
* `unav_pro/version.py::PLUGIN_VERSION` 3.2.0 →
  3.3.0; codename *Presentation & Educational
  Mode*.

### Unchanged

* Every v0.1 → v3.2 feature surface is preserved.
* Mission JSON, Route JSON, Camera Path JSON,
  Export Manifest, DB schema, binary format,
  provenance JSON are byte-identical to v3.2.
* Runtime stays stdlib-only. No threading; no IPC;
  no rendering.

---

## [3.2.0] — Data Integrity & Provenance

Production validation and scientific data integrity
milestone. Goal: make UNAV trustworthy when handling
real astronomical data, coordinates, epochs, metadata,
and exports. **Not** rendering. **Not** new authoring
surfaces. v3.1 runtime preserved byte-identical; v3.2
adds provenance + validation scaffolding underneath.

### Added

* `unav_pro/data/provenance.py` — `ProvenanceRecord`
  + `ProvenanceSummary`, `attach_provenance`,
  `read_provenance`, `summarise_provenance`,
  `build_record`. Records live in
  `metadata_json["provenance"]`.
* `unav_pro/data/validation_report.py` —
  `ValidationReport`, `ValidationIssue`,
  `validate_objects`. Eight per-row probes
  (missing coordinates, invalid parallax, missing
  epoch, invalid redshift, malformed metadata,
  suspicious distance, unsupported units, no
  provenance) plus duplicate-uid detection.
  Markdown / JSON renderers; compact
  `export_summary()` for manifest embedding.
* `unav_pro/knowledge/provenance_view.py` —
  `build_provenance_view(obj)` for the metadata
  inspector.
* `tools/audit_dataset.py` — CLI that runs the
  audit against a JSONL catalog. Markdown report
  by default; optional JSON sidecar; non-zero
  exit on errors.
* New docs:
  `docs/V3_2_DATA_INTEGRITY.md`,
  `docs/DATA_PROVENANCE.md`,
  `docs/DATA_VALIDATION_REPORTS.md`,
  `docs/SCIENTIFIC_LIMITATIONS.md`.
* `RELEASE_NOTES_v3.2.md`.
* New tests: `test_v32_provenance`,
  `test_v32_validation`, `test_v32_audit_cli`,
  `test_v32_export_integration`,
  `test_v32_inspector_view`. **93 new tests.**

### Changed

* `PackageManifest` (export package) gains four
  self-describing fields: `provenance_summary`,
  `audit_summary`, `coordinate_conventions`,
  `known_limitations`. Legacy v3.1 / v2.3
  manifests load without any of these fields.
* `unav_pro/data/__init__.py` re-exports the v3.2
  provenance + validation API.
* `scripts/package_plugin.py` ships the four new
  docs + the v3.2 release notes;
  `REQUIRED_FILES` updated.
* `unav_pro/version.py::PLUGIN_VERSION` 3.1.0 →
  3.2.0; codename *Data Integrity & Provenance*.

### Unchanged

* Every v0.1 → v3.1 feature surface is preserved.
* Mission JSON, Route JSON, Camera Path JSON, DB
  schema, binary format are byte-identical to v3.1.
  The new `provenance` key inside `metadata_json` is
  additive and ignored by older readers.
* Runtime stays stdlib-only. No threading; no IPC;
  no rendering.

---

## [3.1.0] — Project Workspaces & Scene Organization

Collaborative project structure milestone. Goal: make
UNAV usable inside real production projects with
organised scenes, reusable voyage assets, and team-
friendly structure. **Not** rendering. **Not** new
authoring surfaces. The v3.0 runtime surface is
preserved byte-identical; v3.1 adds the scaffolding
artists need to organise multi-mission projects.

### Added

* `unav_pro/project/` — new package with the workspace
  layer:
  * `project_manifest.py` — `ProjectManifest` schema
    (`schema_version: 1`) + references for datasets,
    missions, routes, timelines, overlay / science
    settings.
  * `workspace.py` — `Workspace` facade,
    `create_workspace`, `open_workspace`, eight-subdir
    layout (`datasets/`, `cache/`, `missions/`,
    `routes/`, `exports/`, `overlays/`, `timelines/`,
    `notes/`).
  * `notes.py` — markdown-based project / mission /
    dataset notes.
  * `mission_packs.py` — `MissionPack` bundle format +
    `import_pack` with collision strategies (`skip` /
    `replace` / `rename`).
  * `panel_actions.py` — pure facade for the dialog's
    Project panel.
* `unav_pro/c4d_objects/scene_structure.py` — canonical
  `UNAV_Project` hierarchy (six children); pure
  planning helpers + c4d-bound builders. Migrates legacy
  roots (`UNAV_Starfield`, etc.) automatically.
* New docs:
  `docs/V3_1_PROJECT_WORKSPACES.md`,
  `docs/SCENE_ORGANIZATION.md`,
  `docs/MISSION_ASSET_MANAGEMENT.md`,
  `docs/PROJECT_NOTES_SYSTEM.md`.
* `RELEASE_NOTES_v3.1.md`.
* New tests:
  `test_v31_project_manifest`,
  `test_v31_workspace`,
  `test_v31_scene_structure`,
  `test_v31_mission_packs`,
  `test_v31_notes`,
  `test_v31_panel_actions`. **137 new tests.**

### Changed

* `scripts/package_plugin.py` ships the four new docs
  + the v3.1 release notes; `REQUIRED_FILES` updated.
* `unav_pro/version.py::PLUGIN_VERSION` 3.0.0 →
  3.1.0; codename *Project Workspaces & Scene
  Organization*.

### Unchanged

* Every v0.1 → v3.0 feature surface is preserved.
* Mission JSON, Route JSON, Camera Path JSON, Export
  Manifest, DB schema, binary format are byte-identical
  to v3.0. The new `ProjectManifest` schema is
  additive.
* Runtime stays stdlib-only. No threading; no IPC;
  no rendering.

---

## [3.0.0] — Large-Scale Workflow Optimization

Scalability + streaming milestone. Goal: handle very
large astronomical datasets stably inside Cinema 4D.
**Not** rendering. **Not** new authoring surfaces. The
runtime feature surface is v2.5 byte-identical; v3.0
adds the scaffolding underneath.

### Added

* `unav_pro/db/streaming.py` — paged dataset loading
  (`iter_paged_cone`), chunk-reuse LRU cache
  (`ChunkReuseCache`), repeated-query detector.
  Cache keys are quantised over pose + cone +
  filter sets + epoch so near-identical poses reuse
  results.
* `unav_pro/core/task_queue.py` — cooperative
  single-threaded task queue with progress +
  cancellation. **No threads.** `Task`, `TaskQueue`,
  `make_chunked_task`, `GLOBAL_TASK_QUEUE`.
* `unav_pro/core/diagnostics.py` — pure helpers for
  the diagnostics panel: dataset memory estimate,
  visible-sector estimate, long-operation
  classifier, cache + timing renderers, overlay /
  science layer counts.
* New docs:
  `docs/V3_0_SCALABILITY_AND_STREAMING.md`,
  `docs/LARGE_DATA_WORKFLOWS.md`,
  `docs/SAFE_TASK_QUEUE_MODEL.md`,
  `docs/QUERY_OPTIMIZATION.md`.
* `RELEASE_NOTES_v3.0.md`.
* New v3.0 tests:
  `test_v30_streaming`, `test_v30_query_caps`,
  `test_v30_partial_sync`, `test_v30_task_queue`,
  `test_v30_diagnostics`. **118 new tests.**

### Changed

* `unav_pro/db/spatial_query.py` gains `QueryCaps`,
  `QueryTimingLog`, and `GLOBAL_QUERY_TIMING_LOG`.
  `query_cone` / `query_cone_for_navigator` accept
  `caps=`, `timing_log=`, `timing_note=` kwargs. The
  default bbox-cap multiplier was bumped from 4×
  (v1.7) to 6×.
* `unav_pro/core/scene_sync.py` gains
  `SyncDiff.is_unchanged` and three rebuild
  planners: `plan_overlay_rebuild`,
  `plan_science_rebuild`, `plan_mission_update`.
* `scripts/package_plugin.py` ships the four new
  docs + the v3.0 release notes;
  `REQUIRED_FILES` updated.
* `unav_pro/version.py::PLUGIN_VERSION` 2.5.0 →
  3.0.0; codename *Large-Scale Workflow
  Optimization*.

### Unchanged

* Every v0.1 → v2.5 feature surface is preserved.
* No new on-disk schemas. Mission JSON, Route JSON,
  Camera Path JSON, Export Manifest, DB schema,
  binary format are byte-identical to v2.5.
* Runtime stays stdlib-only. No threading; no IPC;
  no rendering.

---

## [2.5.0] — Docs, Onboarding & Workflow Polish

Documentation, onboarding, and workflow-polish milestone.
No new runtime systems; no rendering; no IPC; no
RelativityRender bridge. Full v2.4 runtime is preserved
byte-for-byte.

### Added

* `docs/USER_MANUAL.md` — canonical 12-section artist
  workflow reference.
* `docs/ARTIST_QUICKSTART.md` — install → first cinematic
  in twelve numbered steps.
* `docs/TD_GUIDE.md` — technical-director / data-pipeline
  guide (schemas, performance limits, lifecycle).
* `docs/ROADMAP.md` — implemented / planned / optional /
  explicitly out-of-scope. Restates the rendering / IPC /
  RelativityRender boundary.
* `RELEASE_NOTES_v2.5.md` — this milestone's release notes.
* `unav_pro/core/workflow_presets.py` — thin artist-facing
  wrapper over the v1.9 voyage templates. Five presets
  with cinematic-ready defaults and recommended overlays
  per preset.
* `unav_pro/tests/test_v25_workflow_presets.py` and
  `unav_pro/tests/test_v25_docs.py` — new v2.5 coverage.

### Changed

* `docs/QA_CHECKLIST.md` gains §5 — an eight-step manual
  end-to-end install test the release engineer runs on a
  fresh Cinema 4D.
* `scripts/package_plugin.py`'s `PACKAGE_INCLUDE`,
  `PACKAGE_DOCS`, and `REQUIRED_FILES` lists pick up the
  four new docs + the v2.5 release notes.
* `unav_pro/version.py::PLUGIN_VERSION` bumped to
  `2.5.0`; codename updated to *Docs, Onboarding &
  Workflow Polish*.

### Unchanged

* Every v0.1 → v2.4 feature surface is preserved.
* Mission JSON, Route JSON, Camera Path JSON, Export
  Manifest, DB schema, and binary format are unchanged.
* Runtime stays stdlib-only.

---

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
