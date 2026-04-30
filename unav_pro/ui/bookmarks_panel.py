"""Bookmarks panel — c4d-bound glue between the v0.6 bookmarks UI
and ``core.bookmarks``.

Pure bookmark data lives in ``unav_pro/core/bookmarks.py``. This
module owns the operations that need to know about the live
``MetadataLookup`` or the active C4D document: turning a bookmark
into a focus / target-lock pose, persisting the list back to disk,
and producing a status line for the dialog log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False

from core.bookmarks import (
    Bookmark,
    BookmarkList,
    bookmark_from_coordinate,
    bookmark_from_search_result,
    bookmark_from_target_lock,
    load_bookmarks,
    render_bookmarks,
    save_bookmarks,
)
from core.logging_util import get_logger
from core.metadata_lookup import MetadataLookup, default_lookup
from core.target_lock import TargetLock, acquire_target

_log = get_logger("ui.bookmarks_panel")


# ---------------------------------------------------------------------------
# Add/remove convenience
# ---------------------------------------------------------------------------


def add_search_result(
    bookmarks: BookmarkList,
    result,
    *,
    label: Optional[str] = None,
    persist: bool = True,
    path: Optional[str] = None,
) -> Tuple[bool, str]:
    """Add a ``SearchResult`` as an object bookmark. Returns
    ``(was_added, status_line)``."""
    bm = bookmark_from_search_result(result, label=label)
    added, returned = bookmarks.add(bm)
    if not added:
        return False, (
            f"Bookmark: '{returned.display_label()}' already in the list."
        )
    if persist:
        save_bookmarks(bookmarks, path)
    return True, f"Bookmark: added '{returned.display_label()}'."


def add_target_lock(
    bookmarks: BookmarkList,
    lock: TargetLock,
    *,
    label: Optional[str] = None,
    persist: bool = True,
    path: Optional[str] = None,
) -> Tuple[bool, str]:
    """Add the active target lock as an object bookmark."""
    bm = bookmark_from_target_lock(lock, label=label)
    added, returned = bookmarks.add(bm)
    if not added:
        return False, (
            f"Bookmark: '{returned.display_label()}' already in the list."
        )
    if persist:
        save_bookmarks(bookmarks, path)
    return True, f"Bookmark: added '{returned.display_label()}'."


def add_coordinate(
    bookmarks: BookmarkList,
    position_c4d: Tuple[float, float, float],
    label: str,
    *,
    position_pc: Optional[Tuple[float, float, float]] = None,
    persist: bool = True,
    path: Optional[str] = None,
) -> Tuple[bool, str]:
    """Add a free coordinate bookmark."""
    bm = bookmark_from_coordinate(
        position_c4d, label, position_pc=position_pc,
    )
    added, returned = bookmarks.add(bm)
    if not added:
        return False, (
            f"Bookmark: '{returned.display_label()}' already in the list."
        )
    if persist:
        save_bookmarks(bookmarks, path)
    return True, f"Bookmark: added '{returned.display_label()}'."


def remove(
    bookmarks: BookmarkList,
    bookmark_id: str,
    *,
    persist: bool = True,
    path: Optional[str] = None,
) -> Tuple[bool, str]:
    removed = bookmarks.remove(bookmark_id)
    if removed is None:
        return False, "Bookmark: id not found."
    if persist:
        save_bookmarks(bookmarks, path)
    return True, f"Bookmark: removed '{removed.display_label()}'."


def reorder(
    bookmarks: BookmarkList,
    bookmark_id: str,
    new_index: int,
    *,
    persist: bool = True,
    path: Optional[str] = None,
) -> Tuple[bool, str]:
    ok = bookmarks.move(bookmark_id, new_index)
    if not ok:
        return False, "Bookmark: id not found."
    if persist:
        save_bookmarks(bookmarks, path)
    return True, f"Bookmark: moved to position {new_index}."


# ---------------------------------------------------------------------------
# Focus
# ---------------------------------------------------------------------------


@dataclass
class FocusPose:
    """Where the navigator should be after a bookmark click."""

    position_c4d: Tuple[float, float, float]
    label: str
    is_resolved: bool = True
    status_line: str = ""


def focus_pose_for(
    bookmark: Bookmark,
    *,
    lookup: Optional[MetadataLookup] = None,
) -> FocusPose:
    """Resolve ``bookmark`` to a navigator-position triple.

    Object bookmarks consult the lookup; coordinate bookmarks use
    their own cached `x/y/z_c4d`. Returns an unresolved pose with a
    status line when the lookup misses (so the dialog can show the
    miss without crashing)."""
    if bookmark.kind == "coordinate":
        if not bookmark.has_c4d_position():
            return FocusPose(
                position_c4d=(0.0, 0.0, 0.0),
                label=bookmark.display_label(),
                is_resolved=False,
                status_line=(
                    f"Bookmark: '{bookmark.display_label()}' has no "
                    "C4D position."
                ),
            )
        return FocusPose(
            position_c4d=(
                float(bookmark.x_c4d),
                float(bookmark.y_c4d),
                float(bookmark.z_c4d),
            ),
            label=bookmark.display_label(),
            is_resolved=True,
            status_line=(
                f"Bookmark: focus at '{bookmark.display_label()}'."
            ),
        )

    # object bookmark
    table = lookup if lookup is not None else default_lookup()
    if not bookmark.uid:
        return FocusPose(
            position_c4d=(0.0, 0.0, 0.0),
            label=bookmark.display_label(),
            is_resolved=False,
            status_line=(
                f"Bookmark: '{bookmark.display_label()}' carries no uid."
            ),
        )
    lock = acquire_target(bookmark.uid, table)
    if lock is None or not lock.is_resolved:
        # Fall back to cached coords if available.
        if bookmark.has_c4d_position():
            return FocusPose(
                position_c4d=(
                    float(bookmark.x_c4d),
                    float(bookmark.y_c4d),
                    float(bookmark.z_c4d),
                ),
                label=bookmark.display_label(),
                is_resolved=True,
                status_line=(
                    f"Bookmark: '{bookmark.display_label()}' resolved "
                    "from cached coordinates (catalog miss)."
                ),
            )
        return FocusPose(
            position_c4d=(0.0, 0.0, 0.0),
            label=bookmark.display_label(),
            is_resolved=False,
            status_line=(
                f"Bookmark: '{bookmark.display_label()}' not in the "
                "active lookup; load the matching dataset."
            ),
        )
    return FocusPose(
        position_c4d=lock.position_c4d,
        label=lock.label,
        is_resolved=True,
        status_line=f"Bookmark: focus at '{lock.label}'.",
    )


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def empty_panel_text() -> str:
    return (
        "No bookmarks yet. Search for an object and click 'Add to "
        "Bookmarks', or capture the navigator's current position."
    )


def render(bookmarks: BookmarkList) -> str:
    return render_bookmarks(bookmarks)
