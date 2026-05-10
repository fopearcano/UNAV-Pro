# UNAV Pro — Audience Mode

Reference for the v3.8 audience-mode toggle
(`unav_pro/presentation/exhibition_mode.py` +
`audience_overlays.py`).

For the milestone overview see
[`V3_8_EXHIBITION_WORKFLOWS.md`](V3_8_EXHIBITION_WORKFLOWS.md).

---

## 1. Two view modes

```python
class ViewMode(str, Enum):
    PRESENTER = "presenter"   # everything visible
    AUDIENCE = "audience"     # debug + notes hidden
```

The exhibition state carries a `view_mode` field;
the dialog flips it via *Audience View toggle*.

## 2. What changes

| Surface | Presenter view | Audience view |
| --- | --- | --- |
| Debug helpers (UNAV cone, scratch nulls) | visible | hidden |
| Presenter notes column | toggleable | hidden |
| Simplified labels | off | on |
| Highlighted-focus halo | on (current uid) | on (current uid) |
| Route emphasis | off | on |
| Chapter title overlay | toggleable | on |

The flag resolver lives in
`audience_overlays.flags_for_state(state)` —
pure helper; tests assert each combination.

## 3. Overlay-flag stripping

In audience mode, the v3.8 layer **strips** a
curated list of distracting flags from the v2.0
overlay settings + v2.1 science settings dicts:

```python
AUDIENCE_HIDDEN_OVERLAY_FLAGS = (
    "show_grid",
    "show_distance_rings",
)

AUDIENCE_HIDDEN_SCIENCE_FLAGS = (
    "show_motion_vectors",
    "show_object_density_volume",
)
```

`apply_audience_overlays(...)` returns fresh
settings dicts with the stripped flags set to
`False`. The original dicts **are not mutated**;
the dialog continues to use the artist's
settings whenever audience mode is off.

## 4. Highlight halo

```python
from presentation import highlight_for_state

instruction = highlight_for_state(state)
print(instruction.target_uid, instruction.halo_intensity)
```

When the exhibition state has a `highlighted_uid`,
the v3.8 layer hands the C4D backend a
`HighlightInstruction` with a halo radius +
intensity. The c4d-bound builder reads this and
flips a UNAV marker bit on the matching point
object. The halo lives until the highlight is
cleared (`clear_highlight_action`).

## 5. Presenter-notes toggle

Independent of view mode. The dialog typically
auto-flips it off when entering audience view +
back on when returning to presenter view, but
the artist can override via
`toggle_presenter_notes_action`.

## 6. Locked navigation

```python
state.lock_navigation(snapshot={"camera_xyz": ...})
```

Stores a navigator snapshot the dialog re-applies
if the artist somehow nudges the camera. The
snapshot is **opaque** to v3.8 — pure data the
dialog interprets. v3.8 doesn't impose a snapshot
schema.

## 7. Destructive-action guard

`PROTECTED_OPERATIONS` lists every operation the
exhibition state refuses while active:

* v3.4 reset tools (Reset UI, Reset Workspace,
  Clear Generated, Clear Cache, Rebuild
  Hierarchy).
* v3.45 scene rebuilds.
* Mission destructive ops (delete, clear
  preview, clear keyframes / markers).
* Route destructive ops (clear route, delete
  waypoint).
* Workspace destructive ops (overwrite save,
  remove dataset).

The dialog wraps every menu/button call in
`guard_action(op, state)`; blocked ops surface
a status-line warning.

## 8. Tests

* `test_v38_exhibition_mode` —
  activate / deactivate, view-mode toggle,
  presenter-notes toggle, lock / unlock,
  highlight, guard decisions for every protected
  operation.
* `test_v38_audience_overlays` —
  flags resolver per state combination,
  `apply_audience_overlays` strip behaviour,
  highlight instructions.
