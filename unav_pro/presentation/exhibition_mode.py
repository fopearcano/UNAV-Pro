"""v3.8 exhibition mode.

A *protective* runtime layer that wraps the v3.3
``PresentationState``:

* **Locked navigation** — the navigator's pose is
  frozen for the duration of the exhibition; the
  presenter can still advance steps but can't
  accidentally re-orient the camera.
* **Audience view toggle** — when audience-view is
  on, debug overlays + presenter notes are hidden
  from the viewport; the presenter sees them
  through their own panel.
* **Presenter notes toggle** — independent of
  audience view; lets the presenter hide their own
  notes when reading off-screen.
* **Destructive-action guard** — a list of
  blocked operations the dialog refuses to run
  while the exhibition is active (Reset Workspace,
  Clear Generated Objects, Delete Mission, etc.).

Pure stdlib; no Cinema 4D imports. Tests drive the
state transitions directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# View modes
# ---------------------------------------------------------------------------


class ViewMode(str, Enum):
    """Two display profiles the exhibition exposes."""

    PRESENTER = "presenter"  # everything visible
    AUDIENCE = "audience"    # debug + notes hidden


VIEW_MODES = tuple(ViewMode)


# ---------------------------------------------------------------------------
# Destructive-action guard
# ---------------------------------------------------------------------------


#: Operations the exhibition refuses while active.
#: The dialog wraps every menu/button call in
#: ``guard_action(op, state)``; blocked ops surface
#: a status-line warning instead of running.
PROTECTED_OPERATIONS: Tuple[str, ...] = (
    # v3.4 reset tools — all destructive when run
    # mid-exhibition.
    "reset_ui_state",
    "reset_workspace_state",
    "clear_generated_objects",
    "clear_cache_references",
    "rebuild_scene_hierarchy",

    # v3.45 scene rebuilds.
    "ensure_project_hierarchy",
    "cleanup_legacy_roots",

    # v1.4 mission destructive ops.
    "delete_mission",
    "clear_mission_preview",
    "clear_unav_keyframes",
    "clear_timeline_markers",

    # v0.6 route destructive ops.
    "clear_route",
    "delete_route_waypoint",

    # v3.1 workspace destructive ops.
    "save_workspace_overwrite",
    "remove_dataset_from_workspace",
)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class ExhibitionState:
    """Runtime state for the v3.8 exhibition wrapper.

    Construct empty, then ``activate(...)`` when the
    presenter starts the show. ``deactivate()`` returns
    everything to the v3.3 default behaviour.
    """

    active: bool = False
    locked_navigation: bool = False
    view_mode: ViewMode = ViewMode.PRESENTER
    show_presenter_notes: bool = True
    highlighted_uid: str = ""
    current_chapter_id: str = ""
    locked_navigation_state: Optional[Dict[str, Any]] = None

    # ---------------------------------------------------- predicates
    @property
    def is_audience_view(self) -> bool:
        return self.view_mode is ViewMode.AUDIENCE

    @property
    def is_presenter_view(self) -> bool:
        return self.view_mode is ViewMode.PRESENTER

    # ---------------------------------------------------- lifecycle
    def activate(
        self,
        *,
        view_mode: ViewMode = ViewMode.PRESENTER,
        show_presenter_notes: bool = True,
        locked_navigation: bool = True,
        locked_navigation_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Enter exhibition mode. ``locked_navigation``
        defaults to True — that's the conservative
        behaviour for a museum kiosk."""
        self.active = True
        self.view_mode = view_mode
        self.show_presenter_notes = bool(show_presenter_notes)
        self.locked_navigation = bool(locked_navigation)
        self.locked_navigation_state = (
            None if locked_navigation_state is None
            else dict(locked_navigation_state)
        )

    def deactivate(self) -> None:
        """Leave exhibition mode. Idempotent — calling
        twice in a row is a no-op the second time."""
        self.active = False
        self.locked_navigation = False
        self.view_mode = ViewMode.PRESENTER
        self.show_presenter_notes = True
        self.highlighted_uid = ""
        self.current_chapter_id = ""
        self.locked_navigation_state = None

    # ---------------------------------------------------- toggles
    def set_view_mode(self, mode: ViewMode) -> None:
        if not isinstance(mode, ViewMode):
            raise ValueError(
                f"view_mode must be a ViewMode enum, got {type(mode).__name__}"
            )
        self.view_mode = mode

    def toggle_view_mode(self) -> ViewMode:
        """Flip between presenter ↔ audience. Returns
        the new mode."""
        self.view_mode = (
            ViewMode.AUDIENCE if self.view_mode is ViewMode.PRESENTER
            else ViewMode.PRESENTER
        )
        return self.view_mode

    def toggle_presenter_notes(self) -> bool:
        """Flip the presenter-notes visibility flag.
        Returns the new value."""
        self.show_presenter_notes = not self.show_presenter_notes
        return self.show_presenter_notes

    def lock_navigation(
        self, snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Lock navigation. Optionally captures a
        navigator snapshot the dialog re-applies if
        the artist somehow nudges it."""
        self.locked_navigation = True
        self.locked_navigation_state = (
            None if snapshot is None else dict(snapshot)
        )

    def unlock_navigation(self) -> None:
        self.locked_navigation = False
        self.locked_navigation_state = None

    def highlight(self, uid: str) -> None:
        """Mark ``uid`` as the currently-highlighted
        object. The audience-overlays layer reads
        this to draw an emphasis halo."""
        self.highlighted_uid = str(uid or "")

    def clear_highlight(self) -> None:
        self.highlighted_uid = ""

    def set_current_chapter(self, chapter_id: str) -> None:
        self.current_chapter_id = str(chapter_id or "")

    # ---------------------------------------------------- snapshot
    def short_summary(self) -> str:
        if not self.active:
            return "Exhibition: idle"
        bits = ["Exhibition: active"]
        bits.append(f"view={self.view_mode.value}")
        if self.locked_navigation:
            bits.append("nav=locked")
        else:
            bits.append("nav=free")
        if self.show_presenter_notes:
            bits.append("notes=visible")
        else:
            bits.append("notes=hidden")
        if self.highlighted_uid:
            bits.append(f"focus='{self.highlighted_uid}'")
        return " · ".join(bits)


# ---------------------------------------------------------------------------
# Guard helpers
# ---------------------------------------------------------------------------


@dataclass
class GuardDecision:
    """Outcome of checking one operation against the
    exhibition state. Pure data the dialog reads."""

    operation: str
    blocked: bool
    reason: str = ""

    def short_summary(self) -> str:
        if self.blocked:
            return f"BLOCKED: {self.operation} — {self.reason}"
        return f"allow: {self.operation}"


def guard_action(
    operation: str, state: ExhibitionState,
) -> GuardDecision:
    """Pure decision: is ``operation`` allowed under
    the current exhibition state?

    The decision is **always allow** when exhibition
    mode is inactive. When active, every operation
    in :data:`PROTECTED_OPERATIONS` is refused with a
    short reason.
    """
    op = str(operation or "").strip()
    if not op:
        return GuardDecision(
            operation=op, blocked=False,
            reason="empty operation; nothing to guard",
        )
    if not state.active:
        return GuardDecision(operation=op, blocked=False)
    if op in PROTECTED_OPERATIONS:
        return GuardDecision(
            operation=op, blocked=True,
            reason=(
                "exhibition mode protects against destructive "
                "actions while a guided tour is running. End "
                "the exhibition first."
            ),
        )
    return GuardDecision(operation=op, blocked=False)


def guarded_operations() -> List[str]:
    """Return the v3.8 protected-ops list. Useful for
    the dialog's *Diagnostics* panel."""
    return list(PROTECTED_OPERATIONS)
