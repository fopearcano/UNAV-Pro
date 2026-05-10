# UNAV Pro v3.8 — Exhibition & Guided Tour Workflows

Release date: 2026-05-10
Codename: *Exhibition & Guided Tour Workflows*

v3.8 polishes the v3.3 presentation system for
**museum / dome / exhibition / lecture use** inside
Cinema 4D. **Not** rendering. **Not** new authoring
surfaces. **Not** a real kiosk app. v3.7 runtime
preserved byte-for-byte.

---

## Highlights

* **Guided tour chapters**
  (`unav_pro/presentation/chapters.py`). `Chapter` +
  `ChapteredPresentation` + sequence-coverage check.
  Chapters reference v3.3 step ids by name (no
  embedded copies); per-chapter overlay / science /
  annotation flags; estimated duration; tags.
* **Exhibition mode**
  (`unav_pro/presentation/exhibition_mode.py`).
  `ExhibitionState` runtime wrapper with locked-
  navigation, audience/presenter view toggle,
  presenter-notes toggle, highlight, current-chapter
  cursor. Plus a destructive-action **guard** —
  `PROTECTED_OPERATIONS` lists every operation
  refused while a tour is active.
* **Presentation transitions**
  (`unav_pro/presentation/transitions.py`). Pure
  deterministic sequencer. Four kinds:
  `hard_cut`, `smooth_camera`,
  `crossfade_placeholder` (metadata only — no
  rendering fade), `waypoint_pause`.
* **Audience-friendly overlays**
  (`unav_pro/presentation/audience_overlays.py`).
  `AudienceOverlayFlags` resolver + curated
  strip-list for distracting overlay / science
  flags + `HighlightInstruction` for emphasis
  halos.
* **Exhibition export**
  (`unav_pro/presentation/exhibition_export.py`).
  Three-file package (chaptered JSON + chapter
  summary Markdown + cue sheet Markdown). Atomic
  writes. Optional `presenter_notes` strip mode.
* **Exhibition panel facade**
  (`unav_pro/ui/exhibition_panel.py`). Eight pure
  panel actions + chapter cursor + guard helper +
  three exporters.

## What didn't change

* No new on-disk schemas for v0.x → v3.7 surfaces.
* No new runtime dependencies. Stdlib-only.
* No rendering, no IPC, no RelativityRender, no
  threading.
* No physics, no PRNG.
* The v3.3 `PresentationSequence` schema stays
  exactly as it was — chapters reference its step
  ids without modification.

## Acceptance

* [x] Users can structure guided tours into
  chapters.
* [x] Exhibition mode prevents accidental workflow
  disruption (`PROTECTED_OPERATIONS` guard).
* [x] Audience / presenter views work
  (`ViewMode.AUDIENCE` / `ViewMode.PRESENTER`).
* [x] Presentation transitions are deterministic
  (`build_transition_sequence`).
* [x] Exhibition packages export correctly
  (JSON + chapter summary + cue sheet).
* [x] No rendering assumptions
  (`crossfade_placeholder` emits metadata only).

## Testing

* Full suite passes: **3039 tests** (2870 v3.7
  baseline + 169 new v3.8 tests).
* New v3.8 test files:
  * `test_v38_chapters` — chapter
    serialisation, sequence coverage,
    validation, factory builder.
  * `test_v38_exhibition_mode` —
    activate/deactivate, view-mode + notes
    toggles, lock / unlock, highlight, guard
    decisions.
  * `test_v38_transitions` — four transition
    kinds + multi-step sequencing +
    determinism.
  * `test_v38_audience_overlays` — flags
    resolver per state combo + strip
    behaviour + highlight instructions.
  * `test_v38_exhibition_export` — package
    payload + chapter summary + cue sheet +
    atomic writes.
  * `test_v38_exhibition_panel` — pure facade
    end-to-end.

## Boundary, restated

UNAV Pro v3.8 remains an **astronomical navigation
+ voyage / camera-animation tool for Cinema 4D**.
Rendering, IPC, real-time scientific simulation,
online services, and render-engine bridges remain
explicitly out of scope.

For the long-form view of the boundary see
[`docs/ROADMAP.md`](docs/ROADMAP.md) §4.
