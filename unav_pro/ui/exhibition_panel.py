"""v3.8 Exhibition panel — pure-Python facade.

Eight panel actions:

* **Start Exhibition Mode** — activate the v3.8
  exhibition wrapper around the v3.3 presentation
  state.
* **End Exhibition Mode** — return everything to
  the v3.3 default behaviour.
* **Next Chapter** / **Previous Chapter** — drive
  the chapter cursor + advance the underlying
  v3.3 presentation step.
* **Audience View toggle** — flip presenter ↔
  audience.
* **Presenter Notes toggle** — show / hide
  presenter notes.
* **Lock Navigation** / **Unlock Navigation** —
  freeze the navigator pose for the duration.
* **Highlight Current Object** — emphasise the
  active waypoint's uid.

Every helper is a pure function; the dialog wires
them to its widgets and renders the returned data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Tuple

from presentation.chapters import (
    Chapter, ChapteredPresentation,
)
from presentation.exhibition_mode import (
    ExhibitionState, GuardDecision, ViewMode,
    guard_action, guarded_operations,
)
from presentation.audience_overlays import (
    AudienceOverlayFlags, HighlightInstruction,
    flags_for_state, highlight_for_state,
)
from presentation.exhibition_export import (
    ExhibitionPackagePayload,
    build_exhibition_package,
    render_chapter_summary,
    render_cue_sheet,
    write_exhibition_package,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ExhibitionPanelError(RuntimeError):
    """Raised on panel-action failures."""


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def start_exhibition_action(
    state: ExhibitionState,
    *,
    view_mode: ViewMode = ViewMode.PRESENTER,
    show_presenter_notes: bool = True,
    locked_navigation: bool = True,
    locked_navigation_state: Optional[dict] = None,
) -> ExhibitionState:
    if state is None:
        raise ExhibitionPanelError("no exhibition state supplied")
    state.activate(
        view_mode=view_mode,
        show_presenter_notes=show_presenter_notes,
        locked_navigation=locked_navigation,
        locked_navigation_state=locked_navigation_state,
    )
    return state


def end_exhibition_action(
    state: ExhibitionState,
) -> ExhibitionState:
    if state is None:
        raise ExhibitionPanelError("no exhibition state supplied")
    state.deactivate()
    return state


# ---------------------------------------------------------------------------
# Toggles
# ---------------------------------------------------------------------------


def toggle_view_mode_action(
    state: ExhibitionState,
) -> ViewMode:
    if state is None:
        raise ExhibitionPanelError("no exhibition state supplied")
    if not state.active:
        raise ExhibitionPanelError(
            "exhibition not active; cannot flip view mode"
        )
    return state.toggle_view_mode()


def toggle_presenter_notes_action(
    state: ExhibitionState,
) -> bool:
    if state is None:
        raise ExhibitionPanelError("no exhibition state supplied")
    if not state.active:
        raise ExhibitionPanelError(
            "exhibition not active; cannot toggle presenter notes"
        )
    return state.toggle_presenter_notes()


def lock_navigation_action(
    state: ExhibitionState,
    *,
    snapshot: Optional[dict] = None,
) -> ExhibitionState:
    if state is None:
        raise ExhibitionPanelError("no exhibition state supplied")
    if not state.active:
        raise ExhibitionPanelError(
            "exhibition not active; cannot lock navigation"
        )
    state.lock_navigation(snapshot=snapshot)
    return state


def unlock_navigation_action(
    state: ExhibitionState,
) -> ExhibitionState:
    if state is None:
        raise ExhibitionPanelError("no exhibition state supplied")
    state.unlock_navigation()
    return state


def highlight_object_action(
    state: ExhibitionState, uid: str,
) -> ExhibitionState:
    if state is None:
        raise ExhibitionPanelError("no exhibition state supplied")
    if not isinstance(uid, str):
        raise ExhibitionPanelError("uid must be a string")
    state.highlight(uid)
    return state


def clear_highlight_action(
    state: ExhibitionState,
) -> ExhibitionState:
    if state is None:
        raise ExhibitionPanelError("no exhibition state supplied")
    state.clear_highlight()
    return state


# ---------------------------------------------------------------------------
# Chapter navigation
# ---------------------------------------------------------------------------


@dataclass
class ChapterCursor:
    """Pure-data cursor: which chapter is current,
    which step inside it, etc. The dialog stores
    one of these next to its presentation runtime
    state."""

    chaptered: ChapteredPresentation
    current_chapter_index: int = -1

    @property
    def current_chapter(self) -> Optional[Chapter]:
        if (
            self.current_chapter_index < 0
            or self.current_chapter_index >= len(self.chaptered.chapters)
        ):
            return None
        return self.chaptered.chapters[self.current_chapter_index]

    def reset(self) -> None:
        self.current_chapter_index = -1

    def short_summary(self) -> str:
        if self.current_chapter is None:
            return "chapter cursor: idle"
        return (
            f"chapter {self.current_chapter_index + 1}/"
            f"{len(self.chaptered.chapters)}: "
            f"{self.current_chapter.short_summary()}"
        )


def next_chapter_action(
    cursor: ChapterCursor,
    state: Optional[ExhibitionState] = None,
) -> Optional[Chapter]:
    if cursor is None:
        raise ExhibitionPanelError("no chapter cursor supplied")
    total = len(cursor.chaptered.chapters)
    if total == 0:
        raise ExhibitionPanelError(
            "chaptered presentation has no chapters"
        )
    if cursor.current_chapter_index + 1 >= total:
        return None
    cursor.current_chapter_index += 1
    chapter = cursor.current_chapter
    if state is not None and chapter is not None:
        state.set_current_chapter(chapter.chapter_id)
    return chapter


def previous_chapter_action(
    cursor: ChapterCursor,
    state: Optional[ExhibitionState] = None,
) -> Optional[Chapter]:
    if cursor is None:
        raise ExhibitionPanelError("no chapter cursor supplied")
    if cursor.current_chapter_index <= 0:
        return None
    cursor.current_chapter_index -= 1
    chapter = cursor.current_chapter
    if state is not None and chapter is not None:
        state.set_current_chapter(chapter.chapter_id)
    return chapter


def jump_to_chapter_action(
    cursor: ChapterCursor,
    index: int,
    state: Optional[ExhibitionState] = None,
) -> Optional[Chapter]:
    if cursor is None:
        raise ExhibitionPanelError("no chapter cursor supplied")
    try:
        idx = int(index)
    except (TypeError, ValueError) as exc:
        raise ExhibitionPanelError(
            f"chapter index must be an integer; got {index!r}"
        ) from exc
    total = len(cursor.chaptered.chapters)
    if total == 0:
        raise ExhibitionPanelError(
            "chaptered presentation has no chapters"
        )
    if not 0 <= idx < total:
        raise ExhibitionPanelError(
            f"chapter index {idx} out of range (0..{total - 1})"
        )
    cursor.current_chapter_index = idx
    chapter = cursor.current_chapter
    if state is not None and chapter is not None:
        state.set_current_chapter(chapter.chapter_id)
    return chapter


# ---------------------------------------------------------------------------
# Overlay-flag resolver
# ---------------------------------------------------------------------------


def resolve_audience_flags_action(
    state: ExhibitionState,
) -> AudienceOverlayFlags:
    if state is None:
        raise ExhibitionPanelError("no exhibition state supplied")
    return flags_for_state(state)


def resolve_highlight_action(
    state: ExhibitionState,
) -> HighlightInstruction:
    if state is None:
        raise ExhibitionPanelError("no exhibition state supplied")
    return highlight_for_state(state)


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


def guard_panel_action(
    operation: str, state: ExhibitionState,
) -> GuardDecision:
    if state is None:
        raise ExhibitionPanelError("no exhibition state supplied")
    return guard_action(operation, state)


def guarded_operations_action() -> List[str]:
    return guarded_operations()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_exhibition_package_action(
    *,
    chaptered: ChapteredPresentation,
    output_dir: str,
    presentation_json: str = "",
    include_presenter_notes: bool = True,
) -> List[str]:
    if chaptered is None:
        raise ExhibitionPanelError("no chaptered presentation")
    if not output_dir:
        raise ExhibitionPanelError("output_dir is empty")
    payload = build_exhibition_package(
        chaptered=chaptered,
        presentation_json=presentation_json,
        include_presenter_notes=include_presenter_notes,
    )
    return write_exhibition_package(payload, output_dir)


def export_chapter_summary_action(
    chaptered: ChapteredPresentation,
    *,
    include_presenter_notes: bool = True,
) -> str:
    if chaptered is None:
        raise ExhibitionPanelError("no chaptered presentation")
    return render_chapter_summary(
        chaptered, include_presenter_notes=include_presenter_notes,
    )


def export_cue_sheet_action(
    chaptered: ChapteredPresentation,
    *,
    include_presenter_notes: bool = True,
) -> str:
    if chaptered is None:
        raise ExhibitionPanelError("no chaptered presentation")
    return render_cue_sheet(
        chaptered, include_presenter_notes=include_presenter_notes,
    )
