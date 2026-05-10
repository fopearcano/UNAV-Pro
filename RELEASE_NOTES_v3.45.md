# UNAV Pro v3.45 — Cinema 4D Native Integration Polish

Release date: 2026-05-10
Codename: *Cinema 4D Native Integration Polish*

v3.45 is the **native-integration polish** milestone.
Goal: make UNAV feel like a real Cinema 4D plug-in
rather than an external tool that happens to live
inside one. **Not** rendering. **Not** new authoring
surfaces. v3.4 runtime preserved byte-for-byte; v3.45
adds the consistency layer that ties every C4D-bound
operation together.

---

## Highlights

* **Declarative undo policy.** New
  `unav_pro/c4d_objects/undo_policy.py` documents
  every UNAV scene-mutating operation in a single
  table (`UNDO_POLICY`). The new `UndoSession`
  context manager wraps `StartUndo` / `AddUndo` /
  `EndUndo` / `EventAdd` and validates each
  `add(...)` against the policy. Tests can drive
  the session with `doc=None` to assert what an
  operation *would* record without booting Cinema
  4D.
* **Central naming policy.** New
  `unav_pro/c4d_objects/naming.py` produces the same
  scene-object / timeline-marker / baked-track name
  for the same input every time. `UNAV_` prefix
  for scene objects, `UNAV:` for timeline tokens,
  `UNAV:Bake:*` namespace for baked tracks.
* **Lifecycle planner.** New
  `unav_pro/c4d_objects/lifecycle.py` captures the
  five document lifecycle events (open / close /
  switch / reload / save) as pure planners. The
  c4d-bound dispatcher reads the
  `LifecycleActionPlan` and runs each step.
* **Object Manager view.** New
  `unav_pro/c4d_objects/object_manager_view.py`
  walks an `ObjectNode` tree and produces:
  per-category counts, a flattened depth-first
  listing, duplicate-root detection, orphan
  detection. The diagnostics panel renders the
  flattened view.
* **Viewport visibility planner.** New
  `unav_pro/c4d_objects/viewport_visibility.py`
  introduces four workflow profiles (Author /
  Lecture / Bake / Hidden) plus a label-clutter
  policy that picks the visible label set per
  camera distance.
* **Document summary.** Extended
  `core/diagnostics.py` with
  `build_document_summary` —
  the diagnostics panel renders a per-document
  snapshot (title, project-root presence, per-
  category counts, active mission, workspace).

## What's new in detail

### New modules

* `unav_pro/c4d_objects/undo_policy.py` — `UNDO_POLICY`,
  `UndoSession`, `UndoTraceEntry`,
  `resolve_undo_constant`, `policy_for`,
  `known_operations`.
* `unav_pro/c4d_objects/naming.py` — `safe_token`,
  `visible_sector_child_name`, `overlay_object_name`,
  `science_layer_object_name`,
  `mission_preview_name`, `waypoint_null_name`,
  `annotation_object_name`, `marker_token`,
  `parse_marker_token`, `is_unav_owned_name`,
  `baked_track_name`, `is_baked_track_name`,
  `display_label_for_visible`.
* `unav_pro/c4d_objects/lifecycle.py` —
  `LifecycleEvent`, `LifecycleActionPlan`,
  `plan_for_event`, `DocumentScope`,
  `MultiDocumentReport`,
  `build_multi_document_report`.
* `unav_pro/c4d_objects/object_manager_view.py` —
  `ObjectNode`, `count_unav_objects`,
  `flatten_unav_tree`,
  `render_object_manager_view`,
  `find_duplicate_roots`, `find_orphans`.
* `unav_pro/c4d_objects/viewport_visibility.py` —
  `VisibilityProfile`, `VisibilityState`,
  `visibility_for`, `plan_visibility`,
  `LabelClutterPolicy`,
  `label_budget_for_distance`,
  `select_labels_for_zoom`.

### Module extensions

* `core/diagnostics.py` gains
  `DocumentSummary` + `build_document_summary`.

### Documentation

* `docs/V3_45_C4D_INTEGRATION_AUDIT.md` — exhaustive
  audit of every C4D integration point.
* `docs/V3_45_NATIVE_C4D_WORKFLOW.md` — the workflow
  overview.
* `docs/UNDO_REDO_SUPPORT.md` — undo policy +
  `UndoSession` reference.
* `docs/OBJECT_MANAGER_STRUCTURE.md` — OM
  diagnostics + cleanup.
* `docs/MULTI_DOCUMENT_BEHAVIOR.md` — multi-doc +
  lifecycle reference.

### Release engineering

* `PLUGIN_VERSION` 3.4.0 → 3.4.5; codename *Cinema
  4D Native Integration Polish*.
* `RELEASE_NOTES_v3.45.md` (this file).
* CHANGELOG entry.
* Packaging script ships the five new docs +
  RELEASE_NOTES_v3.45.md.

## What didn't change

* No new on-disk schemas. Mission JSON, Route JSON,
  Camera Path JSON, Export Manifest, DB schema,
  binary format, provenance JSON, presentation JSON
  byte-identical to v3.4.
* No new runtime dependencies. Stdlib-only at
  runtime.
* No rendering, no IPC, no RelativityRender bridge,
  no threading.
* No new plug-in types. UNAV remains a single
  command plug-in + dialog.
* No replacement of core architecture. Every v0.1
  → v3.4 surface continues to work unmodified.

## Migration

* **Drop-in v3.4 upgrade.** v3.4 saves load cleanly
  in v3.45. No format change.
* The new modules are **opt-in**. v3.4 builders
  continue to work; the v3.45 helpers replace ad-
  hoc `StartUndo` / `AddUndo` calls + ad-hoc
  naming, but a builder that hasn't been migrated
  still ships sensible objects.

## Acceptance

* [x] UNAV behaves consistently inside Cinema 4D
  (centralised undo + naming policy).
* [x] Undo / redo works reliably (every UNDO-needing
  operation in `UNDO_POLICY`).
* [x] Object Manager stays organised (single
  canonical root + six child groups + duplicate /
  orphan detection).
* [x] Scene reloads are stable (lifecycle planner
  covers open / close / switch / reload).
* [x] Timeline integration feels native (baked
  tracks + markers under `UNAV:Bake:*` namespace).
* [x] Generated objects are deterministic (same
  input → same name).
* [x] Plug-in feels integrated into C4D workflow
  (workflow profiles, label-clutter policy,
  document summary).
* [x] No rendering engine assumptions.
* [x] No RelativityRender integration.

## Testing

* Full suite passes: **2488 tests** (2344 v3.4
  baseline + 144 new v3.45 tests).
* New v3.45 test files:
  * `test_v345_undo_policy` — policy table
    coverage, `UndoSession` lifecycle,
    validation, trace recording, outside-host
    degradation.
  * `test_v345_naming` — name determinism, marker
    round-trips, sanitisation, baked-track
    naming.
  * `test_v345_lifecycle` — every event ×
    workspace × multi-doc combination,
    `MultiDocumentReport` validation.
  * `test_v345_object_manager_view` —
    counts, flattened view, duplicate / orphan
    detection.
  * `test_v345_viewport_visibility` — profile
    table coverage, plan generation,
    label-clutter math.
  * `test_v345_document_summary` — empty +
    populated + duck-typed mission summaries.

## Boundary, restated

UNAV Pro v3.45 is an **astronomical navigation +
voyage / camera-animation tool for Cinema 4D**,
scaled for very large catalogs (v3.0), organised
for production projects (v3.1), trustworthy on real
data (v3.2), guided through presentations (v3.3),
hardened for internal beta testing (v3.4), and now
polished for native Cinema 4D integration (v3.45).

Rendering, IPC, real-time scientific simulation,
online services, and render-engine bridges remain
explicitly out of scope.

For the long-form view of the boundary see
[`docs/ROADMAP.md`](docs/ROADMAP.md) §4–§5.
