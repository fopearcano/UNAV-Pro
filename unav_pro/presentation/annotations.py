"""v3.3 presentation annotation extensions.

Pure helpers that compute annotation visibility +
highlight state per presentation step. The v1.9
``MissionAnnotations`` layer remains the source of
truth for *where* annotations live in the scene; v3.3
adds the **per-step visibility / highlight overlay**
the presentation engine drives.

No mutation of v1.9 schemas. The presentation step
references annotations by their *index* in the
mission's ``scene_annotations`` list, so a step can
say "show annotations 0 + 2; highlight 1" without
touching the mission JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence


# ---------------------------------------------------------------------------
# Resolved view
# ---------------------------------------------------------------------------


@dataclass
class AnnotationDisplayState:
    """One annotation's display state for one step."""

    index: int
    visible: bool = True
    highlighted: bool = False
    presentation_only_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": int(self.index),
            "visible": bool(self.visible),
            "highlighted": bool(self.highlighted),
            "presentation_only_notes": self.presentation_only_notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AnnotationDisplayState":
        return cls(
            index=int(d.get("index", 0) or 0),
            visible=bool(d.get("visible", True)),
            highlighted=bool(d.get("highlighted", False)),
            presentation_only_notes=str(
                d.get("presentation_only_notes", "") or "",
            ),
        )


@dataclass
class StepAnnotationView:
    """Aggregate of every annotation's display state for
    one step."""

    step_id: str
    step_index: int
    states: List[AnnotationDisplayState] = field(default_factory=list)

    def visible_indices(self) -> List[int]:
        return sorted(s.index for s in self.states if s.visible)

    def highlighted_indices(self) -> List[int]:
        return sorted(
            s.index for s in self.states if s.visible and s.highlighted
        )


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def resolve_annotation_view(
    *,
    step_id: str,
    step_index: int,
    annotation_count: int,
    visible_indices: Sequence[int],
    highlighted_indices: Sequence[int],
    per_step_notes: Optional[Dict[int, str]] = None,
) -> StepAnnotationView:
    """Compute the per-annotation display state for one
    step.

    * ``annotation_count`` is the size of the active
      mission's ``scene_annotations`` list.
    * ``visible_indices`` empty ⇒ every annotation is
      visible (preserves v1.9 default).
    * ``highlighted_indices`` is intersected with the
      visible set; an annotation can only be highlighted
      when it is also visible.
    * ``per_step_notes`` lets the presentation attach
      narration text to a specific annotation for this
      step without touching the mission JSON.
    """
    notes = per_step_notes or {}
    visible_set = (
        set(int(i) for i in visible_indices)
        if visible_indices else None
    )
    highlight_set = set(int(i) for i in highlighted_indices)
    states: List[AnnotationDisplayState] = []
    for idx in range(int(annotation_count)):
        is_visible = (
            True if visible_set is None else (idx in visible_set)
        )
        states.append(AnnotationDisplayState(
            index=idx,
            visible=is_visible,
            highlighted=is_visible and (idx in highlight_set),
            presentation_only_notes=str(notes.get(idx, "")),
        ))
    return StepAnnotationView(
        step_id=step_id,
        step_index=step_index,
        states=states,
    )


def diff_annotation_views(
    previous: Optional[StepAnnotationView],
    current: StepAnnotationView,
) -> Dict[str, List[int]]:
    """Compute add / remove / highlight-changed sets
    between two consecutive steps' annotation views.

    Pure helper; the C4D builder uses this to drive a
    minimal scene update (show / hide / colour-flip)
    rather than a full rebuild.
    """
    prev_visible = (
        set(s.index for s in previous.states if s.visible)
        if previous is not None else set()
    )
    prev_highlighted = (
        set(s.index for s in previous.states if s.highlighted)
        if previous is not None else set()
    )
    cur_visible = set(s.index for s in current.states if s.visible)
    cur_highlighted = set(s.index for s in current.states if s.highlighted)
    return {
        "added": sorted(cur_visible - prev_visible),
        "removed": sorted(prev_visible - cur_visible),
        "highlight_added": sorted(
            cur_highlighted - prev_highlighted,
        ),
        "highlight_removed": sorted(
            prev_highlighted - cur_highlighted,
        ),
        "kept": sorted(cur_visible & prev_visible),
    }
