"""v3.8 exhibition-panel tests."""

from __future__ import annotations

import os

import pytest

from presentation import (
    Chapter, ChapteredPresentation,
    ExhibitionState, ViewMode,
)
from ui.exhibition_panel import (
    ChapterCursor,
    ExhibitionPanelError,
    clear_highlight_action,
    end_exhibition_action,
    export_chapter_summary_action,
    export_cue_sheet_action,
    export_exhibition_package_action,
    guard_panel_action,
    guarded_operations_action,
    highlight_object_action,
    jump_to_chapter_action,
    lock_navigation_action,
    next_chapter_action,
    previous_chapter_action,
    resolve_audience_flags_action,
    resolve_highlight_action,
    start_exhibition_action,
    toggle_presenter_notes_action,
    toggle_view_mode_action,
    unlock_navigation_action,
)


def _chaptered() -> ChapteredPresentation:
    cp = ChapteredPresentation(
        presentation_id="p", title="Tour",
    )
    cp.add_chapter(Chapter(title="Intro", step_ids=["s1"]))
    cp.add_chapter(Chapter(title="Saturn", step_ids=["s2"]))
    cp.add_chapter(Chapter(title="Outro", step_ids=["s3"]))
    return cp


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_start_exhibition_action():
    state = ExhibitionState()
    out = start_exhibition_action(state)
    assert out.active is True
    assert out.locked_navigation is True


def test_start_with_audience_view():
    state = ExhibitionState()
    start_exhibition_action(state, view_mode=ViewMode.AUDIENCE)
    assert state.is_audience_view


def test_start_rejects_none_state():
    with pytest.raises(ExhibitionPanelError):
        start_exhibition_action(None)  # type: ignore[arg-type]


def test_end_exhibition_returns_to_idle():
    state = ExhibitionState()
    start_exhibition_action(state)
    end_exhibition_action(state)
    assert state.active is False


# ---------------------------------------------------------------------------
# Toggles
# ---------------------------------------------------------------------------


def test_toggle_view_mode_action():
    state = ExhibitionState()
    start_exhibition_action(state)
    new = toggle_view_mode_action(state)
    assert new is ViewMode.AUDIENCE


def test_toggle_view_mode_rejects_inactive():
    state = ExhibitionState()
    with pytest.raises(ExhibitionPanelError):
        toggle_view_mode_action(state)


def test_toggle_presenter_notes_action():
    state = ExhibitionState()
    start_exhibition_action(state)
    new = toggle_presenter_notes_action(state)
    assert new is False


def test_toggle_presenter_notes_rejects_inactive():
    state = ExhibitionState()
    with pytest.raises(ExhibitionPanelError):
        toggle_presenter_notes_action(state)


def test_lock_navigation_action_with_snapshot():
    state = ExhibitionState()
    start_exhibition_action(state, locked_navigation=False)
    lock_navigation_action(state, snapshot={"camera": (1, 2, 3)})
    assert state.locked_navigation is True
    assert state.locked_navigation_state == {"camera": (1, 2, 3)}


def test_lock_navigation_rejects_inactive():
    state = ExhibitionState()
    with pytest.raises(ExhibitionPanelError):
        lock_navigation_action(state)


def test_unlock_navigation_action():
    state = ExhibitionState()
    start_exhibition_action(state)
    unlock_navigation_action(state)
    assert state.locked_navigation is False


def test_highlight_object_action():
    state = ExhibitionState()
    start_exhibition_action(state)
    highlight_object_action(state, "uid:42")
    assert state.highlighted_uid == "uid:42"


def test_highlight_action_rejects_non_string():
    state = ExhibitionState()
    start_exhibition_action(state)
    with pytest.raises(ExhibitionPanelError):
        highlight_object_action(state, 42)  # type: ignore[arg-type]


def test_clear_highlight_action():
    state = ExhibitionState()
    start_exhibition_action(state)
    state.highlight("x")
    clear_highlight_action(state)
    assert state.highlighted_uid == ""


# ---------------------------------------------------------------------------
# Chapter cursor
# ---------------------------------------------------------------------------


def test_cursor_idle_state():
    cursor = ChapterCursor(_chaptered())
    assert cursor.current_chapter is None
    assert "idle" in cursor.short_summary()


def test_next_chapter_advances():
    cursor = ChapterCursor(_chaptered())
    chapter = next_chapter_action(cursor)
    assert chapter is not None
    assert chapter.title == "Intro"
    assert cursor.current_chapter_index == 0


def test_next_chapter_returns_none_at_end():
    cursor = ChapterCursor(_chaptered())
    cursor.current_chapter_index = 2  # last
    chapter = next_chapter_action(cursor)
    assert chapter is None


def test_previous_chapter_rewinds():
    cursor = ChapterCursor(_chaptered())
    cursor.current_chapter_index = 1
    chapter = previous_chapter_action(cursor)
    assert chapter is not None
    assert cursor.current_chapter_index == 0


def test_previous_chapter_returns_none_at_start():
    cursor = ChapterCursor(_chaptered())
    cursor.current_chapter_index = -1
    assert previous_chapter_action(cursor) is None


def test_jump_to_chapter_action():
    cursor = ChapterCursor(_chaptered())
    chapter = jump_to_chapter_action(cursor, 2)
    assert chapter is not None
    assert chapter.title == "Outro"


def test_jump_to_chapter_rejects_out_of_range():
    cursor = ChapterCursor(_chaptered())
    with pytest.raises(ExhibitionPanelError):
        jump_to_chapter_action(cursor, 99)


def test_jump_to_chapter_rejects_non_integer():
    cursor = ChapterCursor(_chaptered())
    with pytest.raises(ExhibitionPanelError):
        jump_to_chapter_action(cursor, "two")  # type: ignore[arg-type]


def test_jump_to_chapter_empty_presentation_raises():
    cursor = ChapterCursor(ChapteredPresentation())
    with pytest.raises(ExhibitionPanelError):
        jump_to_chapter_action(cursor, 0)


def test_chapter_advance_updates_state_when_provided():
    state = ExhibitionState()
    start_exhibition_action(state)
    cursor = ChapterCursor(_chaptered())
    chapter = next_chapter_action(cursor, state)
    assert state.current_chapter_id == chapter.chapter_id


# ---------------------------------------------------------------------------
# Audience flags + highlight resolution
# ---------------------------------------------------------------------------


def test_resolve_audience_flags():
    state = ExhibitionState()
    start_exhibition_action(state, view_mode=ViewMode.AUDIENCE)
    flags = resolve_audience_flags_action(state)
    assert flags.simplified_labels is True


def test_resolve_highlight():
    state = ExhibitionState()
    start_exhibition_action(state)
    highlight_object_action(state, "uid:99")
    inst = resolve_highlight_action(state)
    assert inst.target_uid == "uid:99"


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


def test_guard_panel_action_blocks_when_active():
    state = ExhibitionState()
    start_exhibition_action(state)
    decision = guard_panel_action("reset_workspace_state", state)
    assert decision.blocked is True


def test_guard_panel_action_allows_when_idle():
    state = ExhibitionState()
    decision = guard_panel_action("reset_workspace_state", state)
    assert decision.blocked is False


def test_guarded_operations_action_returns_list():
    out = guarded_operations_action()
    assert isinstance(out, list)
    assert "reset_workspace_state" in out


# ---------------------------------------------------------------------------
# Export actions
# ---------------------------------------------------------------------------


def test_export_exhibition_package_action(tmp_path):
    cp = _chaptered()
    out = export_exhibition_package_action(
        chaptered=cp,
        output_dir=str(tmp_path / "out"),
    )
    assert len(out) == 3
    for path in out:
        assert os.path.isfile(path)


def test_export_package_rejects_none_chaptered(tmp_path):
    with pytest.raises(ExhibitionPanelError):
        export_exhibition_package_action(
            chaptered=None,  # type: ignore[arg-type]
            output_dir=str(tmp_path / "x"),
        )


def test_export_package_rejects_blank_dir():
    with pytest.raises(ExhibitionPanelError):
        export_exhibition_package_action(
            chaptered=_chaptered(),
            output_dir="",
        )


def test_export_chapter_summary_action_returns_markdown():
    md = export_chapter_summary_action(_chaptered())
    assert "Voyager Tour" not in md  # title is "Tour" in helper
    assert "Tour" in md
    assert "Chapter 1: Intro" in md


def test_export_chapter_summary_rejects_none():
    with pytest.raises(ExhibitionPanelError):
        export_chapter_summary_action(None)  # type: ignore[arg-type]


def test_export_cue_sheet_action_returns_markdown():
    md = export_cue_sheet_action(_chaptered())
    assert "Cue Sheet" in md
    assert "s1" in md


def test_export_cue_sheet_rejects_none():
    with pytest.raises(ExhibitionPanelError):
        export_cue_sheet_action(None)  # type: ignore[arg-type]
