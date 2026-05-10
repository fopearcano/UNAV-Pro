"""v3.7 query-result action helpers.

For each ``QueryResult`` the dialog can:

* **Focus navigator** — produce a ``NavigationFocus``
  record the navigation controller consumes.
* **Add bookmark** — produce a ``BookmarkDelta``.
* **Add to route** — produce a ``RouteWaypointDelta``.
* **Add to mission** — produce a
  ``MissionWaypointDelta``.
* **Inspect metadata** — produce an
  ``InspectorRequest`` the metadata panel reads.
* **Export result list** — handled in
  :mod:`export`.

Every helper is **pure** — returns a plain dataclass
the dialog applies via the existing v0.6 / v1.4
state-managers. No mutation; no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple


Vec3 = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# Focus navigator
# ---------------------------------------------------------------------------


@dataclass
class NavigationFocus:
    """Pure-data instruction: "point the navigator at
    ``target_uid``." The dialog reads this + calls
    its target-lock workflow."""

    target_uid: str
    target_position_pc: Optional[Vec3] = None
    label: str = ""

    def short_summary(self) -> str:
        if self.label:
            return f"focus '{self.label}' [{self.target_uid}]"
        return f"focus [{self.target_uid}]"


def focus_navigator_action(result) -> NavigationFocus:
    """Translate a ``QueryResult`` into a
    ``NavigationFocus``. Defensive against partial
    results (a result with no position still
    produces a uid-only focus)."""
    if result is None:
        raise ValueError("result is required")
    snapshot = getattr(result, "snapshot", None)
    pos: Optional[Vec3] = None
    if snapshot is not None:
        x = getattr(snapshot, "cartesian_x", None)
        y = getattr(snapshot, "cartesian_y", None)
        z = getattr(snapshot, "cartesian_z", None)
        if x is not None and y is not None and z is not None:
            pos = (float(x), float(y), float(z))
    return NavigationFocus(
        target_uid=str(getattr(result, "uid", "") or ""),
        target_position_pc=pos,
        label=str(getattr(result, "common_name", "") or ""),
    )


# ---------------------------------------------------------------------------
# Bookmark delta
# ---------------------------------------------------------------------------


@dataclass
class BookmarkDelta:
    """Append a bookmark for the result. The dialog
    forwards this to the v0.6 ``BookmarkList``."""

    label: str
    uid: str
    catalog_source: str = ""
    notes: str = ""

    def short_summary(self) -> str:
        return f"bookmark '{self.label}' [{self.uid}]"


def bookmark_action(result) -> BookmarkDelta:
    if result is None:
        raise ValueError("result is required")
    label = str(
        getattr(result, "common_name", "")
        or getattr(result, "uid", "")
        or "(unnamed)"
    )
    return BookmarkDelta(
        label=label,
        uid=str(getattr(result, "uid", "") or ""),
        catalog_source=str(getattr(result, "catalog_source", "") or ""),
    )


# ---------------------------------------------------------------------------
# Route waypoint delta
# ---------------------------------------------------------------------------


@dataclass
class RouteWaypointDelta:
    """Append a waypoint to the active route."""

    kind: str
    uid: str
    label: str
    catalog_source: str = ""
    notes: str = ""

    def short_summary(self) -> str:
        return f"route+ '{self.label}' [{self.uid}]"


def add_to_route_action(result) -> RouteWaypointDelta:
    if result is None:
        raise ValueError("result is required")
    return RouteWaypointDelta(
        kind="object",
        uid=str(getattr(result, "uid", "") or ""),
        label=str(
            getattr(result, "common_name", "")
            or getattr(result, "uid", "")
            or "(unnamed)"
        ),
        catalog_source=str(getattr(result, "catalog_source", "") or ""),
    )


# ---------------------------------------------------------------------------
# Mission waypoint delta
# ---------------------------------------------------------------------------


@dataclass
class MissionWaypointDelta:
    """Append a waypoint to the active mission."""

    kind: str
    uid: str
    label: str
    catalog_source: str = ""
    object_type: str = ""
    duration_seconds: float = 4.0

    def short_summary(self) -> str:
        return f"mission+ '{self.label}' [{self.uid}]"


def add_to_mission_action(
    result, *, duration_seconds: float = 4.0,
) -> MissionWaypointDelta:
    if result is None:
        raise ValueError("result is required")
    if duration_seconds < 0:
        raise ValueError("duration_seconds must be >= 0")
    object_type = str(getattr(result, "object_type", "") or "")
    kind = "orbital" if object_type in (
        "planet", "moon", "asteroid", "comet",
    ) else "object"
    return MissionWaypointDelta(
        kind=kind,
        uid=str(getattr(result, "uid", "") or ""),
        label=str(
            getattr(result, "common_name", "")
            or getattr(result, "uid", "")
            or "(unnamed)"
        ),
        catalog_source=str(getattr(result, "catalog_source", "") or ""),
        object_type=object_type,
        duration_seconds=float(duration_seconds),
    )


# ---------------------------------------------------------------------------
# Inspect metadata
# ---------------------------------------------------------------------------


@dataclass
class InspectorRequest:
    """Pure instruction: open the metadata inspector
    for the given uid. The dialog forwards this to
    its v1.3 inspector pipeline."""

    uid: str
    label: str = ""

    def short_summary(self) -> str:
        return f"inspect [{self.uid}]"


def inspect_action(result) -> InspectorRequest:
    if result is None:
        raise ValueError("result is required")
    return InspectorRequest(
        uid=str(getattr(result, "uid", "") or ""),
        label=str(getattr(result, "common_name", "") or ""),
    )


# ---------------------------------------------------------------------------
# Bulk helpers
# ---------------------------------------------------------------------------


def add_all_to_route(results: Sequence) -> List[RouteWaypointDelta]:
    """Convenience: build one ``RouteWaypointDelta``
    per result. Used by the dialog's *Add All to
    Route* action."""
    return [add_to_route_action(r) for r in results if r is not None]


def add_all_to_mission(
    results: Sequence,
    *,
    duration_seconds: float = 4.0,
) -> List[MissionWaypointDelta]:
    return [
        add_to_mission_action(r, duration_seconds=duration_seconds)
        for r in results if r is not None
    ]


def bookmark_all(results: Sequence) -> List[BookmarkDelta]:
    return [bookmark_action(r) for r in results if r is not None]
