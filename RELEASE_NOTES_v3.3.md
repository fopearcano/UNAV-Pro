# UNAV Pro v3.3 — Presentation & Educational Mode

Release date: 2026-05-10
Codename: *Presentation & Educational Mode*

v3.3 lets UNAV drive **guided presentations,
scientific storytelling, lectures, exhibitions, and
cinematic demonstrations** inside Cinema 4D.

This is **not** rendering. **Not** new authoring
surfaces. The runtime feature surface is unchanged from
v3.2; v3.3 adds a **declarative presentation layer** on
top of the v0.1 → v3.2 stack.

---

## Highlights

* **Presentation sequences.** New
  `unav_pro/presentation/presentation_sequence.py`
  defines `PresentationSequence` (top-level
  document) and `PresentationStep` (one step). Each
  step owns a camera pose, an active waypoint
  reference, overlay + science-layer flags,
  annotation visibility, an active epoch, narration
  text, presenter notes, and a pause duration.
  `Optional` fields default to "inherit from the
  previous step." `resolved_steps()` walks the chain
  front-to-back and produces deterministic
  `ResolvedStep` records.
* **Runtime state tracker.** New
  `presentation_state.py` provides
  `PresentationState` with explicit lifecycle
  states (idle / running / paused / finished),
  `next_step` / `previous_step` / `jump_to`
  navigation, and a `lock_navigation(...)` hook
  for kiosk-style stable views.
* **Per-step annotation visibility.** New
  `presentation/annotations.py` resolves visible +
  highlighted annotations per step;
  `diff_annotation_views` lets the C4D builder
  apply minimal scene updates between steps.
* **Per-step overlay + science states.** New
  `presentation/overlay_states.py` merges step flag
  dicts into base settings dicts and reports flag
  transitions for the v3.0 partial-rebuild
  planners.
* **Disk-backed CRUD store.** New
  `presentation/manager.py` mirrors the v1.4
  `MissionManager` shape:
  `PresentationManager.create / update / delete /
  list_all / reorder`. Atomic writes; corruption-
  resistant reload.
* **Export pipelines.** New `presentation/export.py`
  emits Markdown summaries (with or without
  presenter notes), plain-text presenter-note
  dumps, and a `PresentationPackagePayload` that
  rides into the v2.3 export package.
* **Pure-Python panel facade.** New
  `unav_pro/ui/presentation_panel.py` exposes the
  eight Presentation-panel actions (Start / Next /
  Previous / Jump / Pause / Resume / End /
  Presenter Notes) as plain functions the dialog
  calls. Tested without any UI primitives.

## What's new in detail

### New package: `unav_pro/presentation/`

* `__init__.py` — package exports.
* `presentation_sequence.py` — declarative
  shape (`PresentationSequence`,
  `PresentationStep`, `ResolvedStep`).
* `presentation_state.py` — runtime tracker.
* `annotations.py` — per-step annotation visibility.
* `overlay_states.py` — per-step flag merges.
* `manager.py` — disk-backed CRUD store.
* `export.py` — Markdown summary + presenter-notes
  dump + package payload.

### New module: `unav_pro/ui/presentation_panel.py`

Pure-Python facade for the dialog's *Presentation*
panel buttons.

### Documentation

* `docs/V3_3_PRESENTATION_MODE.md` — milestone
  overview.
* `docs/PRESENTATION_SEQUENCES.md` — step + sequence
  shape.
* `docs/EDUCATIONAL_WORKFLOWS.md` — patterns for
  lectures, exhibitions, cinematic recordings.
* `docs/PRESENTER_NOTES.md` — the notes layer.

### Release engineering

* `PLUGIN_VERSION` 3.2.0 → 3.3.0; codename
  *Presentation & Educational Mode*.
* `RELEASE_NOTES_v3.3.md` (this file).
* CHANGELOG entry.
* Packaging script ships the four new docs +
  RELEASE_NOTES_v3.3.md.

## What didn't change

* No new on-disk schemas for v0.x → v3.2 surfaces.
  Mission JSON, Route JSON, Camera Path JSON,
  Export Manifest, DB schema, binary format,
  provenance JSON are byte-identical to v3.2.
* No new runtime dependencies. Stdlib-only at
  runtime.
* No rendering, no IPC, no RelativityRender bridge.
* No threading. Existing v3.0 cooperative task
  queue is unchanged.
* No replacement of core architecture. v0.1 →
  v3.2 authoring surfaces continue to work
  unmodified.

## Migration

* **Drop-in v3.2 upgrade.** v3.2 saves load cleanly
  in v3.3. No format change; no new schemas under
  existing surfaces.
* The v3.3 presentation layer is **opt-in**. A
  workspace that doesn't author presentations
  produces an identical workspace tree (the
  `presentations/` subdir from v3.1 sits
  unpopulated).
* v1.4 missions continue to drive cinematic camera
  motion; presentations *reference* missions
  through `mission_ref` but don't replace them.

## Acceptance

* [x] User can create guided presentations.
  `PresentationManager.create` persists; the
  manager mirrors the v1.4 `MissionManager` shape.
* [x] Presentation steps are deterministic.
  `resolved_steps()` produces byte-identical
  output for byte-identical input.
* [x] Overlays + annotations can be controlled per
  step. `overlay_flags`, `science_flags`,
  `visible_annotation_indices`,
  `highlighted_annotation_indices` are folded in
  by the v3.3 helpers.
* [x] Presenter notes persist. First-class fields
  on both `PresentationSequence` and
  `PresentationStep`; written by the manager;
  emitted by the export pipeline.
* [x] Presentations integrate with missions /
  workspaces. `mission_ref` references a v1.4
  mission; the export payload merges into the
  v2.3 package; the v3.1 workspace's
  `presentations/` subdir holds the JSON files.
* [x] No renderer assumptions, no IPC, no
  RelativityRender bridge.

## Testing

* Full suite passes: **2277 tests** (2125 v3.2
  baseline + 152 new v3.3 tests).
* New v3.3 test files:
  * `test_v33_presentation_sequence` —
    sequence/step round-trip, validation,
    inheritance, ordering.
  * `test_v33_presentation_state` — lifecycle,
    navigation, snapshots, locked navigation.
  * `test_v33_annotations` — per-step visibility,
    highlight intersection, diff helper.
  * `test_v33_overlay_states` — flag merge,
    diff, resolved-layer states.
  * `test_v33_manager` — disk round-trip,
    corruption resistance, reorder.
  * `test_v33_export` — markdown + presenter
    notes + payload + atomic write.
  * `test_v33_panel_actions` — pure UI facade
    end-to-end.

## Boundary, restated

UNAV Pro v3.3 is an **astronomical navigation +
voyage / camera-animation tool for Cinema 4D**,
scaled for very large catalogs (v3.0), organised
for production projects (v3.1), trustworthy on real
data (v3.2), and now guided through presentations
(v3.3). Rendering, IPC, real-time scientific
simulation, online services, and render-engine
bridges remain explicitly out of scope.

For the long-form view of the boundary see
[`docs/ROADMAP.md`](docs/ROADMAP.md) §4–§5.
