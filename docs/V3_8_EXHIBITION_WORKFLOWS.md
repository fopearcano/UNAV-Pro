# UNAV Pro — v3.8 Exhibition & Guided Tour Workflows

The v3.8 milestone polishes the v3.3 presentation
system for **museum / dome / exhibition / lecture
use** inside Cinema 4D. **Not** rendering. **Not**
new authoring surfaces. v3.7 runtime preserved
byte-for-byte; v3.8 layers exhibition-mode +
chapters + transitions + audience overlays on top
of the v3.3 stack.

For deep dives see:

* [`GUIDED_TOUR_CHAPTERS.md`](GUIDED_TOUR_CHAPTERS.md)
  — chapter shape, sequencing, coverage check.
* [`AUDIENCE_MODE.md`](AUDIENCE_MODE.md) —
  audience-vs-presenter view toggle, overlay
  hiding rules, presenter-notes visibility.
* [`PRESENTATION_TRANSITIONS.md`](PRESENTATION_TRANSITIONS.md)
  — deterministic transition sequencing (no
  rendering fades).

---

## 1. New surfaces

* **`unav_pro/presentation/chapters.py`** —
  `Chapter` + `ChapteredPresentation` + helpers
  (`chapters_from_step_groups`, coverage report).
* **`unav_pro/presentation/exhibition_mode.py`** —
  `ExhibitionState` runtime wrapper +
  `PROTECTED_OPERATIONS` guard list +
  `guard_action` decision helper.
* **`unav_pro/presentation/transitions.py`** —
  four transition kinds (`hard_cut`,
  `smooth_camera`, `crossfade_placeholder`,
  `waypoint_pause`) + deterministic sequencer.
* **`unav_pro/presentation/audience_overlays.py`** —
  `AudienceOverlayFlags` + `HighlightInstruction`
  + per-state resolver.
* **`unav_pro/presentation/exhibition_export.py`** —
  exhibition package + chapter summary + cue
  sheet exporters.
* **`unav_pro/ui/exhibition_panel.py`** — pure
  Python facade for the dialog's *Exhibition*
  panel.

## 2. Lifecycle

```
idle  →  start_exhibition_action()  →  active
active →  next_chapter / previous_chapter / jump
       →  toggle_view_mode / toggle_presenter_notes
       →  lock_navigation / unlock_navigation
       →  highlight_object / clear_highlight
active →  end_exhibition_action()  →  idle
```

While the exhibition is active, the v3.8 *guard*
refuses every operation in
`PROTECTED_OPERATIONS` — destructive things like
*Reset Workspace* / *Clear Generated UNAV
Objects* / *Delete Mission* — so a presenter
can't fat-finger their way out of a
performance.

## 3. Determinism

Every helper in the v3.8 layer is **pure** +
**deterministic**:

* Chapters serialise to byte-stable JSON.
* Transitions produce identical frame lists for
  identical inputs.
* Audience overlays compute identical flag
  dictionaries for identical exhibition state.
* Exports compute identical Markdown / JSON
  modulo the timestamp.

Tests assert these directly.

## 4. Acceptance

* [x] User can structure guided tours into chapters.
* [x] Exhibition mode prevents accidental workflow
  disruption (`PROTECTED_OPERATIONS` guard).
* [x] Audience / presenter views work
  (`ViewMode.AUDIENCE` / `ViewMode.PRESENTER`).
* [x] Presentation transitions are deterministic
  (`build_transition_sequence`).
* [x] Exhibition packages export correctly
  (JSON + chapter summary + cue sheet).
* [x] No rendering assumptions (the
  `crossfade_placeholder` transition emits
  fade-fraction metadata only; no actual fade
  is rendered).

## 5. Out of scope

* No real kiosk app. v3.8's exhibition mode is a
  *protective layer* on top of the dialog;
  there's no separate launcher / window manager.
* No physics or PRNG.
* No external renderer integration.
* No socket / IPC / OSC remote-control. The
  presenter drives the panel by hand.

## 6. Tests

* `test_v38_chapters` — chapter
  serialisation, sequence coverage, validation,
  step-id reverse map.
* `test_v38_exhibition_mode` —
  activate / deactivate, view-mode + notes
  toggles, lock / unlock navigation, highlight,
  guard decisions.
* `test_v38_transitions` — four kinds of
  sequencing + multi-step sequence builder +
  determinism.
* `test_v38_audience_overlays` — flags resolver
  + apply over settings dicts + highlight
  instructions.
* `test_v38_exhibition_export` — package
  payload + chapter summary + cue sheet + atomic
  writes.
* `test_v38_exhibition_panel` — pure facade
  end-to-end + chapter cursor + guard panel.
