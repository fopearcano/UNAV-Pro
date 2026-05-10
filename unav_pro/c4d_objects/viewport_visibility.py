"""v3.45 viewport visibility planning.

Pre-v3.45 the dialog flipped Cinema 4D's editor /
render visibility toggles (``ID_BASEOBJECT_VISIBILITY_*``)
ad-hoc per builder. v3.45 collects the policy:

* every UNAV-owned object gets a documented visibility
  state (``EDITOR_ON_RENDER_OFF`` for debug nulls,
  ``EDITOR_ON_RENDER_ON`` for visible-sector points,
  ``EDITOR_ONLY`` for label nulls);
* a ``VisibilityProfile`` lets the artist switch the
  whole UNAV layer between *Author* (everything
  visible), *Lecture* (overlays + annotations
  hidden), and *Bake* (debug helpers off,
  visible-sector points on).
* a ``LabelClutterPolicy`` decides which waypoint
  labels stay visible at zoom level X — pure
  computation; the c4d-bound builder applies the
  decision via ``BaseObject.SetEditorMode``.

Pure stdlib; no Cinema 4D imports. Tests assert the
policy decisions without a host.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Visibility states
# ---------------------------------------------------------------------------


class VisibilityState(str, Enum):
    """The four visibility states UNAV uses. ``str``
    base so equality + serialisation just work."""

    DEFAULT = "default"               # editor + render follow project default
    EDITOR_ON_RENDER_OFF = "editor_only_render_off"
    EDITOR_OFF_RENDER_OFF = "hidden"
    EDITOR_ON_RENDER_ON = "editor_render_on"


VISIBILITY_STATES = tuple(VisibilityState)


# ---------------------------------------------------------------------------
# Object kinds (UNAV-internal)
# ---------------------------------------------------------------------------


KIND_VISIBLE_SECTOR_POINT: str = "visible_sector_point"
KIND_OVERLAY_GEOMETRY: str = "overlay_geometry"
KIND_SCIENCE_GEOMETRY: str = "science_geometry"
KIND_MISSION_PREVIEW: str = "mission_preview"
KIND_WAYPOINT_NULL: str = "waypoint_null"
KIND_ANNOTATION_LABEL: str = "annotation_label"
KIND_DEBUG_CONE: str = "debug_cone"
KIND_NAVIGATOR_NULL: str = "navigator_null"
KIND_PROJECT_ROOT_NULL: str = "project_root_null"

UNAV_OBJECT_KINDS: Tuple[str, ...] = (
    KIND_VISIBLE_SECTOR_POINT, KIND_OVERLAY_GEOMETRY,
    KIND_SCIENCE_GEOMETRY, KIND_MISSION_PREVIEW,
    KIND_WAYPOINT_NULL, KIND_ANNOTATION_LABEL,
    KIND_DEBUG_CONE, KIND_NAVIGATOR_NULL,
    KIND_PROJECT_ROOT_NULL,
)


# ---------------------------------------------------------------------------
# Visibility profiles
# ---------------------------------------------------------------------------


class VisibilityProfile(str, Enum):
    """Coarse "what's the artist doing right now"
    setting that drives the whole UNAV layer's
    visibility."""

    AUTHOR = "author"   # everything visible
    LECTURE = "lecture" # debug + annotations hidden
    BAKE = "bake"       # debug hidden, points + paths visible
    HIDDEN = "hidden"   # nothing visible


VISIBILITY_PROFILES = tuple(VisibilityProfile)


#: Per-profile mapping of object kind → visibility
#: state. Decisions chosen for the typical workflow:
#: *Author* sees everything; *Lecture* hides debug
#: helpers + label nulls; *Bake* hides everything that
#: would render but isn't part of the cinematic;
#: *Hidden* makes the whole layer invisible.
PROFILE_TABLE: Dict[VisibilityProfile, Dict[str, VisibilityState]] = {
    VisibilityProfile.AUTHOR: {
        KIND_VISIBLE_SECTOR_POINT: VisibilityState.EDITOR_ON_RENDER_ON,
        KIND_OVERLAY_GEOMETRY: VisibilityState.EDITOR_ON_RENDER_OFF,
        KIND_SCIENCE_GEOMETRY: VisibilityState.EDITOR_ON_RENDER_OFF,
        KIND_MISSION_PREVIEW: VisibilityState.EDITOR_ON_RENDER_OFF,
        KIND_WAYPOINT_NULL: VisibilityState.EDITOR_ON_RENDER_OFF,
        KIND_ANNOTATION_LABEL: VisibilityState.EDITOR_ON_RENDER_OFF,
        KIND_DEBUG_CONE: VisibilityState.EDITOR_ON_RENDER_OFF,
        KIND_NAVIGATOR_NULL: VisibilityState.EDITOR_ON_RENDER_OFF,
        KIND_PROJECT_ROOT_NULL: VisibilityState.EDITOR_ON_RENDER_OFF,
    },
    VisibilityProfile.LECTURE: {
        KIND_VISIBLE_SECTOR_POINT: VisibilityState.EDITOR_ON_RENDER_ON,
        KIND_OVERLAY_GEOMETRY: VisibilityState.EDITOR_ON_RENDER_OFF,
        KIND_SCIENCE_GEOMETRY: VisibilityState.EDITOR_ON_RENDER_OFF,
        KIND_MISSION_PREVIEW: VisibilityState.EDITOR_OFF_RENDER_OFF,
        KIND_WAYPOINT_NULL: VisibilityState.EDITOR_OFF_RENDER_OFF,
        KIND_ANNOTATION_LABEL: VisibilityState.EDITOR_OFF_RENDER_OFF,
        KIND_DEBUG_CONE: VisibilityState.EDITOR_OFF_RENDER_OFF,
        KIND_NAVIGATOR_NULL: VisibilityState.EDITOR_OFF_RENDER_OFF,
        KIND_PROJECT_ROOT_NULL: VisibilityState.EDITOR_ON_RENDER_OFF,
    },
    VisibilityProfile.BAKE: {
        KIND_VISIBLE_SECTOR_POINT: VisibilityState.EDITOR_ON_RENDER_ON,
        KIND_OVERLAY_GEOMETRY: VisibilityState.EDITOR_OFF_RENDER_OFF,
        KIND_SCIENCE_GEOMETRY: VisibilityState.EDITOR_OFF_RENDER_OFF,
        KIND_MISSION_PREVIEW: VisibilityState.EDITOR_OFF_RENDER_OFF,
        KIND_WAYPOINT_NULL: VisibilityState.EDITOR_OFF_RENDER_OFF,
        KIND_ANNOTATION_LABEL: VisibilityState.EDITOR_OFF_RENDER_OFF,
        KIND_DEBUG_CONE: VisibilityState.EDITOR_OFF_RENDER_OFF,
        KIND_NAVIGATOR_NULL: VisibilityState.EDITOR_OFF_RENDER_OFF,
        KIND_PROJECT_ROOT_NULL: VisibilityState.EDITOR_ON_RENDER_OFF,
    },
    VisibilityProfile.HIDDEN: {
        kind: VisibilityState.EDITOR_OFF_RENDER_OFF
        for kind in UNAV_OBJECT_KINDS
    },
}


def visibility_for(
    kind: str, profile: VisibilityProfile,
) -> VisibilityState:
    """Look up the visibility state for one object kind
    under one profile. Unknown kinds default to
    ``DEFAULT`` so artist-introduced UNAV-prefixed
    objects are left alone."""
    table = PROFILE_TABLE.get(profile, {})
    return table.get(kind, VisibilityState.DEFAULT)


# ---------------------------------------------------------------------------
# Per-object decision
# ---------------------------------------------------------------------------


@dataclass
class VisibilityDecision:
    """The c4d-bound applier consumes a list of these."""

    object_label: str
    kind: str
    desired: VisibilityState
    previous: Optional[VisibilityState] = None

    def is_change(self) -> bool:
        if self.previous is None:
            return self.desired is not VisibilityState.DEFAULT
        return self.desired != self.previous

    def short_summary(self) -> str:
        if self.previous is None:
            return f"{self.object_label} → {self.desired.value}"
        return (
            f"{self.object_label}: {self.previous.value} "
            f"→ {self.desired.value}"
        )


def plan_visibility(
    *,
    objects: Sequence[Tuple[str, str, Optional[VisibilityState]]],
    profile: VisibilityProfile,
) -> List[VisibilityDecision]:
    """Compose the per-object visibility plan.

    ``objects`` is a sequence of
    ``(object_label, kind, previous_state)`` triples.
    Returns the list of decisions the c4d-bound
    applier should run; ``is_change()`` lets it skip
    no-ops.
    """
    decisions: List[VisibilityDecision] = []
    for label, kind, previous in objects:
        desired = visibility_for(kind, profile)
        decisions.append(VisibilityDecision(
            object_label=str(label or ""),
            kind=str(kind or ""),
            desired=desired,
            previous=previous,
        ))
    return decisions


# ---------------------------------------------------------------------------
# Label clutter reduction
# ---------------------------------------------------------------------------


@dataclass
class LabelClutterPolicy:
    """Policy for "how many labels can the editor show
    at once before it's a mess." Pure parameters; the
    ``select_labels_for_zoom`` helper consumes them."""

    #: Maximum simultaneous labels to render at the
    #: closest zoom level.
    max_labels_close: int = 24
    #: Maximum at the mid zoom level.
    max_labels_mid: int = 12
    #: Maximum at the far zoom level.
    max_labels_far: int = 4
    #: Distance (in C4D world units) below which we use
    #: the ``close`` budget.
    close_threshold: float = 50.0
    #: Distance below which we use the ``mid`` budget.
    mid_threshold: float = 200.0


def label_budget_for_distance(
    distance: float, policy: Optional[LabelClutterPolicy] = None,
) -> int:
    """Return the maximum number of labels to display
    at the camera ↔ scene distance ``distance`` (in
    C4D world units)."""
    pol = policy or LabelClutterPolicy()
    if distance <= 0:
        return pol.max_labels_close
    if distance < pol.close_threshold:
        return pol.max_labels_close
    if distance < pol.mid_threshold:
        return pol.max_labels_mid
    return pol.max_labels_far


def select_labels_for_zoom(
    *,
    candidates: Sequence[Tuple[str, float]],
    distance: float,
    policy: Optional[LabelClutterPolicy] = None,
) -> List[str]:
    """Pure helper: given a list of
    ``(label, importance)`` pairs and the current
    camera distance, return the names of the labels
    that should remain visible.

    Importance is a numeric "how much does the artist
    want to see this label" score; higher is more
    important. The helper ranks by importance and
    truncates to the per-zoom budget so the editor
    never renders more labels than the policy allows.
    """
    pol = policy or LabelClutterPolicy()
    budget = label_budget_for_distance(distance, pol)
    if budget <= 0 or not candidates:
        return []
    ranked = sorted(
        ((str(label), float(score)) for label, score in candidates),
        key=lambda kv: (-kv[1], kv[0]),
    )
    return [label for (label, _score) in ranked[:budget]]
