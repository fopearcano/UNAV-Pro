# UNAV Pro — v3.3 Presentation & Educational Mode

The v3.3 milestone is about **guided presentations,
scientific storytelling, lectures, exhibitions, and
cinematic demonstrations** inside Cinema 4D.

This is **not** rendering. **Not** new authoring
surfaces. The runtime feature surface is unchanged from
v3.2; v3.3 adds a **declarative presentation layer** on
top of the v0.1 → v3.2 stack.

For deep dives see:

* [`PRESENTATION_SEQUENCES.md`](PRESENTATION_SEQUENCES.md)
  — the step-based sequence shape.
* [`EDUCATIONAL_WORKFLOWS.md`](EDUCATIONAL_WORKFLOWS.md)
  — patterns for lectures + exhibitions.
* [`PRESENTER_NOTES.md`](PRESENTER_NOTES.md) — the
  notes layer.

---

## 1. The presentation

A *presentation* is an **ordered list of steps** an
artist guides an audience through. Each step owns:

* a camera pose (or "inherit from the previous step");
* an active waypoint reference (resolved against the
  presentation's mission);
* visible overlay + science-layer flags;
* visible + highlighted annotation indices;
* an active epoch (Julian date);
* narration (read aloud) + presenter notes (private);
* a pause duration.

`PresentationSequence` is the top-level document:
title + description + ordered steps + presenter notes.
`PresentationStep` is one step. Both are pure-Python
dataclasses with stable JSON I/O.

## 2. Determinism

Steps are addressed by zero-based index. Every step
carries an immutable `step_id`. The
`resolved_steps()` walker folds inheritance chains
front-to-back so the C4D builder reads complete steps
without peeking at neighbours.

Same input → same output, byte for byte. This makes
presentations reproducible across artists + machines.

## 3. New modules

* `unav_pro/presentation/presentation_sequence.py` —
  `PresentationSequence`, `PresentationStep`,
  `ResolvedStep`.
* `unav_pro/presentation/presentation_state.py` —
  runtime tracker (`PresentationState`,
  `PresentationSnapshot`).
* `unav_pro/presentation/annotations.py` — per-step
  annotation visibility + highlight resolver.
* `unav_pro/presentation/overlay_states.py` — per-step
  overlay + science-layer flag merge.
* `unav_pro/presentation/manager.py` — disk-backed
  CRUD store (`PresentationManager`).
* `unav_pro/presentation/export.py` — Markdown
  summary, presenter-notes dump, package payload.
* `unav_pro/ui/presentation_panel.py` — pure-Python
  facade for the dialog's *Presentation* panel.

## 4. The dialog's Presentation panel

Eight buttons; each calls a thin facade in
`unav_pro/ui/presentation_panel.py`:

* **Start Presentation…**
* **Next Step**
* **Previous Step**
* **Jump To Step…**
* **Pause** / **Resume**
* **End Presentation**
* **Presenter Notes**

The facade is pure Python — tests exercise the
lifecycle without faking any UI primitives.

## 5. Workspace integration

A v3.1 workspace can store presentations alongside
missions:

```
UNAV_Project/
├── missions/
│   └── voyager-arrival.json
├── presentations/                  ← new in v3.3 layout
│   └── voyager-talk.json
├── exports/
│   └── 2026-05-10/
│       └── presentations/
│           ├── voyager-talk.json
│           ├── voyager-talk.md
│           └── voyager-talk.notes.txt
└── …
```

The export builder picks up the v3.3 markdown summary
+ presenter notes alongside the mission / route /
timeline assets.

## 6. Acceptance criteria

* [x] User can create guided presentations.
  `PresentationManager.create(...)` persists; the v3.3
  `manager.py` mirrors the v1.4 `MissionManager`
  shape.
* [x] Presentation steps are deterministic.
  `resolved_steps()` produces byte-identical output
  for byte-identical input.
* [x] Overlays / annotations can be controlled per
  step. Each step's `overlay_flags`,
  `science_flags`, `visible_annotation_indices`,
  `highlighted_annotation_indices` are resolved
  via the v3.3 helpers.
* [x] Presenter notes persist. `presenter_notes` is
  a first-class field on both
  `PresentationSequence` and `PresentationStep`;
  the manager stores them; the export pipeline
  emits a plain-text dump.
* [x] Presentations integrate with missions /
  workspaces. `PresentationSequence.mission_ref`
  references a v1.4 `Mission`; the v3.3 export
  payload merges into the v2.3 export package.
* [x] No renderer assumptions, no IPC, no
  RelativityRender bridge.

## 7. What v3.3 is **not**

* Not a teleprompter (no scrolling text engine).
* Not a slide editor (no rich-text body).
* Not a recording tool (no audio / video capture).
* Not a remote-control protocol (no IPC, no
  network).
* Not a layout engine (no on-screen labels, lower
  thirds, captions).

## 8. Tests

* `test_v33_presentation_sequence` —
  `PresentationStep` / `PresentationSequence`
  serialisation, validation, step ordering,
  resolved-step inheritance.
* `test_v33_presentation_state` — lifecycle
  (idle / running / paused / finished),
  navigation, snapshot rendering.
* `test_v33_annotations` — visibility / highlight
  resolver, diff helper.
* `test_v33_overlay_states` — flag merge, diff,
  resolved-layer states.
* `test_v33_manager` — CRUD, disk round-trip,
  reorder.
* `test_v33_export` — Markdown summary,
  presenter-notes dump, package payload.
* `test_v33_panel_actions` — pure UI facade
  end-to-end.
