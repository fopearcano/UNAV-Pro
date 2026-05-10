# UNAV Pro — Presenter Notes

How v3.3 stores, surfaces, and exports presenter
notes.

For the milestone overview see
[`V3_3_PRESENTATION_MODE.md`](V3_3_PRESENTATION_MODE.md).

---

## 1. Two scopes

* **Presentation-level notes**
  (`PresentationSequence.presenter_notes`) — overall
  notes that apply to the whole talk. Typically
  intro / outro / general advice.
* **Step-level notes**
  (`PresentationStep.presenter_notes`) — notes that
  apply to one step. Typically off-script reminders,
  Q&A prompts, "if asked about X, mention Y."

Both are free-form strings (markdown / plain text).
The plugin reads + writes them but never interprets
the body.

## 2. Distinct from narration

Two parallel fields per step:

* `narration` — what the presenter **says**.
  Renders into the markdown summary. The audience
  effectively "hears" this through the presenter.
* `presenter_notes` — what the presenter **knows**.
  Only the presenter sees it (the
  `--include-presenter-notes` flag controls export
  inclusion).

A common pattern:

```
narration:
  "Saturn fills the frame here. Note the gap in the
   outer ring — that's the Encke division."

presenter_notes:
  "Encke division = a 325 km gap in the outer A ring,
   maintained by Pan. If asked: discovered 1837 by
   Encke. Don't go into the moonlets unless asked."
```

## 3. Reading at runtime

```python
from ui.presentation_panel import (
    presenter_notes_action, step_narration_action,
)

# Inside the dialog's tick handler:
notes = presenter_notes_action(state)
narration = step_narration_action(state)
# render notes in a side panel; narration in main view
```

Both helpers return `""` when no step is active.

## 4. Exporting

`render_presenter_notes(presentation)` produces a
plain-text dump suitable for printing or piping into a
teleprompter:

```
Presenter notes — Voyager Cinematic
============================================================

[Step 1] Saturn approach
  Narration:
    Saturn fills the frame here. Note the gap...
  Presenter notes:
    Encke division = a 325 km gap...

[Step 2] ...
```

`render_presentation_markdown(...,
include_presenter_notes=True)` interleaves the notes
into the full markdown summary as block quotes:

```markdown
### Step 1: Saturn approach
- Pause: 8.00 s

Saturn fills the frame...

> Presenter notes:
> Encke division = a 325 km gap...
```

The boolean lets the artist export a *clean* version
for the audience and a *full* version for the
presenter.

## 5. Workspace integration

Presenter notes ride into the v3.1 workspace's
`presentations/` subdirectory as
`<presentation_id>.notes.txt` files alongside the
JSON + markdown summary.

The v3.1 `NotesStore` continues to be the right home
for **project-level** notes (decisions, todos). The
v3.3 presenter notes are **presentation-scoped** — a
strictly different concern.

## 6. Privacy + safety

* Presenter notes are stored **inside the
  presentation JSON**. They survive every round-trip
  (manager save, mission-pack export, workspace
  copy).
* If you ship a presentation to an audience (e.g.
  for an exhibition kiosk), strip the notes first
  by exporting with `include_presenter_notes=False`.
* No network transfer. The notes never leave the
  workspace unless the artist explicitly exports
  them.

## 7. Tests

* `test_v33_presentation_sequence` covers serialisation
  round-trips for both note fields.
* `test_v33_export` covers the markdown +
  presenter-notes-dump renderers, plus the
  `include_presenter_notes=False` strip-mode.
