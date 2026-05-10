# Changelog

All notable changes to UNAV Pro are tracked here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [3.8.0] — Exhibition & Guided Tour Workflows

Exhibition / guided-tour milestone. Goal: polish
the v3.3 presentation system for museum / dome /
exhibition / lecture use. **Not** rendering.
**Not** new authoring surfaces. **Not** a real
kiosk app. v3.7 runtime preserved byte-for-byte.

### Added

* `unav_pro/presentation/chapters.py` — `Chapter`
  + `ChapteredPresentation` + `chapters_from_step_groups`.
  Chapters reference v3.3 step ids; per-chapter
  overlay / science / annotation flags;
  sequence-coverage check.
* `unav_pro/presentation/exhibition_mode.py` —
  `ExhibitionState` (active flag, locked
  navigation, view mode, presenter notes
  toggle, highlight, current chapter) +
  `PROTECTED_OPERATIONS` guard list +
  `guard_action` decision helper.
* `unav_pro/presentation/transitions.py` —
  pure deterministic sequencer. Four kinds:
  `hard_cut`, `smooth_camera`,
  `crossfade_placeholder` (metadata only),
  `waypoint_pause`.
* `unav_pro/presentation/audience_overlays.py` —
  `AudienceOverlayFlags` + `HighlightInstruction`
  + per-state resolver + strip-list applier.
* `unav_pro/presentation/exhibition_export.py` —
  exhibition package (JSON + chapter summary +
  cue sheet) + atomic writes.
* `unav_pro/ui/exhibition_panel.py` — pure-
  Python facade for the dialog's Exhibition
  panel.
* New docs:
  `docs/V3_8_EXHIBITION_WORKFLOWS.md`,
  `docs/GUIDED_TOUR_CHAPTERS.md`,
  `docs/AUDIENCE_MODE.md`,
  `docs/PRESENTATION_TRANSITIONS.md`.
* `RELEASE_NOTES_v3.8.md`.
* New tests: `test_v38_chapters`,
  `test_v38_exhibition_mode`,
  `test_v38_transitions`,
  `test_v38_audience_overlays`,
  `test_v38_exhibition_export`,
  `test_v38_exhibition_panel`.
  **169 new tests.**

### Changed

* `unav_pro/presentation/__init__.py` re-exports
  every new v3.8 surface.
* `scripts/package_plugin.py` ships the four new
  docs + the v3.8 release notes.
* `unav_pro/version.py::PLUGIN_VERSION` 3.7.0 →
  3.8.0; codename *Exhibition & Guided Tour
  Workflows*.

### Unchanged

* Every v0.1 → v3.7 feature surface is preserved.
* Mission JSON, Route JSON, Camera Path JSON,
  Export Manifest, DB schema, binary format,
  provenance JSON, presentation JSON byte-
  identical to v3.7. Chapters live in their own
  schema.
* Runtime stays stdlib-only. No threading;
  no IPC; no rendering; no PRNG state.

---

## [3.7.0] — Advanced Astronomical Queries

Discovery / search milestone. Goal: turn UNAV into
a strong astronomical search and exploration tool
inside Cinema 4D. **Not** rendering. **Not** new
authoring surfaces. **Not** new data fetchers. v3.6
runtime preserved byte-for-byte.

### Added

* `unav_pro/query/` (new package):
  * `advanced_query.py` — `AdvancedQuery` +
    `run_query` + `QueryReport`. Eleven query
    kinds; deterministic ranking with stable uid
    tie-break.
  * `query_presets.py` — eight named factory
    presets + `PRESET_REGISTRY` for the dialog.
  * `route_query.py` — polyline-corridor +
    per-waypoint nearest-neighbour helpers +
    route summary.
  * `result_actions.py` — pure helpers
    translating a `QueryResult` into bookmark /
    route / mission / focus / inspector deltas
    + bulk variants.
  * `export.py` — JSON / CSV / Markdown
    exporters + atomic file-write helpers.
* `unav_pro/ui/advanced_query_panel.py` — pure
  panel-action facade (`query_from_form`,
  `run_query_action`, `select_preset_action`,
  `export_results_*_action`,
  `run_route_query_action`).
* New docs:
  `docs/V3_7_ADVANCED_ASTRONOMICAL_QUERIES.md`,
  `docs/QUERY_PRESETS.md`,
  `docs/ROUTE_AWARE_QUERIES.md`,
  `docs/EPOCH_AWARE_QUERY_LIMITATIONS.md`.
* `RELEASE_NOTES_v3.7.md`.
* New tests: `test_v37_advanced_query`,
  `test_v37_query_presets`,
  `test_v37_route_query`,
  `test_v37_result_actions`,
  `test_v37_query_export`,
  `test_v37_advanced_query_panel`.
  **145 new tests.**

### Changed

* `scripts/package_plugin.py` ships the four new
  docs + the v3.7 release notes.
* `unav_pro/version.py::PLUGIN_VERSION` 3.6.0 →
  3.7.0; codename *Advanced Astronomical
  Queries*.

### Unchanged

* Every v0.1 → v3.6 feature surface is preserved.
* Mission JSON, Route JSON, Camera Path JSON,
  Export Manifest, DB schema, binary format,
  provenance JSON, presentation JSON byte-
  identical to v3.6.
* Runtime stays stdlib-only. No threading; no IPC;
  no rendering; no PRNG state.

---

## [3.6.0] — Procedural Cinematic Helpers

Cinematic-helpers milestone. Goal: make UNAV more
useful for cinematic navigation, shot planning, and
artistic voyage creation. **Not** rendering. **Not**
physics. v3.5 runtime preserved byte-for-byte.

### Added

* `unav_pro/cinematic/` (new package):
  * `framing.py` — five framing presets, framing-
    distance trig, ``compose_look_at_pose``,
    slerp ``blend_look_at``.
  * `motion.py` — drift / orbit / flyby /
    approach-depart sample generators + six
    easing presets. Deterministic.
  * `route_beautify.py` — Chaikin + Gaussian
    smoothing + sharp-angle detector. Preserves
    input.
* `unav_pro/c4d_objects/camera_rigs.py` — four
  rig kinds (orbit / target-follow / flyby /
  locked-target) under ``UNAV_CameraRigs``.
  Idempotent.
* `unav_pro/ui/cinematic_panel.py` — pure-Python
  facade for the dialog's Cinematic panel.
* New docs:
  `docs/V3_6_PROCEDURAL_CINEMATIC_HELPERS.md`,
  `docs/CAMERA_RIGS.md`,
  `docs/CINEMATIC_FRAMING.md`,
  `docs/ROUTE_BEAUTIFICATION.md`.
* `RELEASE_NOTES_v3.6.md`.
* New tests: `test_v36_framing`,
  `test_v36_motion`,
  `test_v36_route_beautify`,
  `test_v36_camera_rigs`,
  `test_v36_cinematic_panel`. **135 new tests.**

### Changed

* `unav_pro/c4d_objects/undo_policy.py` —
  ``UNDO_POLICY`` gains five cinematic
  operations: `build_camera_rig`,
  `remove_camera_rig`,
  `ensure_camera_rigs_root`,
  `apply_framing_preset`,
  `apply_route_beautify`.
* `scripts/package_plugin.py` ships the four new
  docs + the v3.6 release notes.
* `unav_pro/version.py::PLUGIN_VERSION` 3.5.0 →
  3.6.0; codename *Procedural Cinematic Helpers*.

### Unchanged

* Every v0.1 → v3.5 feature surface is preserved.
* Mission JSON, Route JSON, Camera Path JSON,
  Export Manifest, DB schema, binary format,
  provenance JSON, presentation JSON, issue-
  report bundle byte-identical to v3.5.
* Runtime stays stdlib-only. No threading; no IPC;
  no rendering.

---

## [3.5.0] — Public Alpha

Public-alpha release. **Not** a feature phase. **Not**
rendering. **Not** new authoring surfaces. v3.45 runtime
preserved byte-for-byte; v3.5 is packaging +
communication + first-user readiness.

### Added

* `LICENSE` (Apache License, Version 2.0) at the
  repository root.
* `NOTICE.md` with Apache 2.0 attribution + bundled-
  data disclosure (synthetic samples; no real catalog
  data redistributed).
* `docs/DATA_SOURCE_ATTRIBUTION.md` — per-source
  citation + license notes for Gaia DR3, SDSS DR18,
  DESI EDR, and JPL Horizons.
* `unav_pro/core/issue_report.py` — produces a
  Markdown issue-report bundle (plug-in version,
  Cinema 4D / Python / OS info, workspace status,
  dataset status, latest health check, last 50
  status-log lines). Surfaced in the dialog as
  *Diagnostics → Create Issue Report*.
* `unav_pro/core/first_run.py` — welcome banner +
  five-stage next-step recommendation engine
  (`no_workspace` → `no_datasets` → `no_navigator`
  → `no_visible_sector` → `ready`).
* New docs:
  `docs/PUBLIC_ALPHA_TESTING_GUIDE.md`,
  `docs/ISSUE_REPORTING.md`,
  `docs/FIRST_RUN_GUIDE.md`.
* `RELEASE_NOTES_v3.5_PUBLIC_ALPHA.md`.
* New tests: `test_v35_issue_report`,
  `test_v35_first_run`,
  `test_v35_package_manifest`,
  `test_v35_release_artifacts`.
  **102 new tests.**

### Changed

* `README.md` — public-facing banner + matrix
  table (license / Cinema 4D / Python / runtime
  deps / tested OS / status / first-run / issue-
  reporting / data-attribution).
  *Reporting issues* + *License + attribution*
  sections inserted before the milestone history.
* `scripts/package_plugin.py` ships LICENSE +
  NOTICE.md + the four new docs + the v3.5
  release notes; `REQUIRED_FILES` updated.
* `unav_pro/version.py::PLUGIN_VERSION` 3.4.5 →
  3.5.0; codename *Public Alpha*.

### Unchanged

* Every v0.1 → v3.45 feature surface is preserved.
* Mission JSON, Route JSON, Camera Path JSON,
  Export Manifest, DB schema, binary format,
  provenance JSON, presentation JSON are byte-
  identical to v3.45.
* Runtime stays stdlib-only. No threading; no IPC;
  no rendering.

---

## [3.4.5] — Cinema 4D Native Integration Polish

Native-integration polish milestone. Goal: make UNAV
feel like a real Cinema 4D plug-in rather than an
external tool that happens to live inside one.
**Not** rendering. **Not** new authoring surfaces.
v3.4 runtime preserved byte-identical; v3.45 adds the
consistency layer that ties every C4D-bound
operation together.

### Added

* `unav_pro/c4d_objects/undo_policy.py` —
  declarative `UNDO_POLICY` table covering 15
  operations + `UndoSession` context manager.
  Validates each `add(...)` against the policy.
* `unav_pro/c4d_objects/naming.py` — central
  deterministic naming for visible-sector
  children, overlays, science layers, mission
  previews, waypoint nulls, annotations, marker
  tokens, baked tracks. `UNAV_` scene prefix +
  `UNAV:` timeline prefix.
* `unav_pro/c4d_objects/lifecycle.py` — pure
  scene-lifecycle planner covering five events
  (open / close / switch / reload / save) +
  `MultiDocumentReport`.
* `unav_pro/c4d_objects/object_manager_view.py` —
  pure scene-hierarchy summariser.
  `count_unav_objects`, `flatten_unav_tree`,
  `find_duplicate_roots`, `find_orphans`,
  `render_object_manager_view`.
* `unav_pro/c4d_objects/viewport_visibility.py` —
  four workflow profiles (Author / Lecture /
  Bake / Hidden) + label-clutter policy.
* `core/diagnostics.py::build_document_summary`
  + `DocumentSummary` for the per-document panel
  view.
* New docs:
  `docs/V3_45_C4D_INTEGRATION_AUDIT.md`,
  `docs/V3_45_NATIVE_C4D_WORKFLOW.md`,
  `docs/UNDO_REDO_SUPPORT.md`,
  `docs/OBJECT_MANAGER_STRUCTURE.md`,
  `docs/MULTI_DOCUMENT_BEHAVIOR.md`.
* `RELEASE_NOTES_v3.45.md`.
* New tests: `test_v345_undo_policy`,
  `test_v345_naming`, `test_v345_lifecycle`,
  `test_v345_object_manager_view`,
  `test_v345_viewport_visibility`,
  `test_v345_document_summary`. **144 new tests.**

### Changed

* `scripts/package_plugin.py` ships the v3.45
  release notes + the five new docs.
* `unav_pro/version.py::PLUGIN_VERSION` 3.4.0 →
  3.4.5; codename *Cinema 4D Native Integration
  Polish*.

### Unchanged

* Every v0.1 → v3.4 feature surface is preserved.
* Mission JSON, Route JSON, Camera Path JSON,
  Export Manifest, DB schema, binary format,
  provenance JSON, presentation JSON are byte-
  identical to v3.4.
* Runtime stays stdlib-only. No threading; no IPC;
  no rendering.

---

## [3.4.0] — Internal Beta Hardening

Internal-beta hardening milestone. Goal: prepare UNAV
for serious internal testing as a stable Cinema 4D
plugin. **Not** a feature phase; **not** rendering;
**not** new authoring surfaces. v3.3 runtime preserved
byte-identical; v3.4 adds release discipline and the
scaffolding testers need.

### Added

* `unav_pro/core/reset_tools.py` — five idempotent
  reset operations (`reset_ui_state`,
  `reset_workspace_state`,
  `clear_generated_objects_report`,
  `clear_cache_references`,
  `rebuild_hierarchy_report`). Pure planning helpers;
  on-disk artefacts never touched.
* Six new health-check probes:
  `python_runtime`, `c4d_host`, `workspace`,
  `active_mission`, `visible_sector`, `presentation`.
  Diagnostics panel now lists 14 probes.
* `current_workspace` / `set_current_workspace` and
  `current_mission` / `set_current_mission` accessors
  on `core/state_manager.py`.
* `samples/internal_beta_demo/` — self-contained
  workspace with five Gaia rows, three JPL bodies,
  a three-stop mission, a route, a presentation,
  and project notes.
* New docs:
  `docs/V3_4_INTERNAL_BETA_CHECKLIST.md` (17-section
  manual test pass).
* `RELEASE_NOTES_v3.4_INTERNAL_BETA.md`.
* New tests: `test_v34_reset_tools`,
  `test_v34_health_check`,
  `test_v34_beta_demo`,
  `test_v34_run_tests_categories`. **67 new tests.**

### Changed

* `scripts/run_tests.py::TEST_CATEGORIES` gains six
  buckets: `workflow`, `scalability`, `workspace`,
  `integrity`, `presentation`, `beta`.
* `scripts/package_plugin.py` ships the v3.4 release
  notes + checklist + new internal-beta sample
  workspace.
* `docs/TROUBLESHOOTING.md` — appended a v3.4 reset-
  tools section.
* `unav_pro/version.py::PLUGIN_VERSION` 3.3.0 →
  3.4.0; codename *Internal Beta Hardening*.

### Unchanged

* Every v0.1 → v3.3 feature surface is preserved.
* Mission JSON, Route JSON, Camera Path JSON,
  Export Manifest, DB schema, binary format,
  provenance JSON, presentation JSON are byte-
  identical to v3.3.
* Runtime stays stdlib-only. No threading; no IPC;
  no rendering.

---

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
