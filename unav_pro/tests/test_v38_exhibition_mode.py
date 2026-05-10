"""v3.8 exhibition-mode tests."""

from __future__ import annotations

import pytest

from presentation import (
    PROTECTED_OPERATIONS,
    VIEW_MODES,
    ExhibitionState,
    GuardDecision,
    ViewMode,
    guard_action,
    guarded_operations,
)


# ---------------------------------------------------------------------------
# View modes constant
# ---------------------------------------------------------------------------


def test_view_modes_complete():
    assert {ViewMode.PRESENTER, ViewMode.AUDIENCE} == set(VIEW_MODES)


def test_view_mode_string_values():
    assert ViewMode.PRESENTER.value == "presenter"
    assert ViewMode.AUDIENCE.value == "audience"


# ---------------------------------------------------------------------------
# Default state
# ---------------------------------------------------------------------------


def test_default_state_idle():
    state = ExhibitionState()
    assert state.active is False
    assert state.locked_navigation is False
    assert state.view_mode is ViewMode.PRESENTER
    assert state.show_presenter_notes is True
    assert state.is_presenter_view
    assert not state.is_audience_view


# ---------------------------------------------------------------------------
# activate / deactivate
# ---------------------------------------------------------------------------


def test_activate_locks_navigation_by_default():
    state = ExhibitionState()
    state.activate()
    assert state.active is True
    assert state.locked_navigation is True


def test_activate_with_audience_view():
    state = ExhibitionState()
    state.activate(view_mode=ViewMode.AUDIENCE)
    assert state.is_audience_view


def test_activate_stores_locked_state_snapshot():
    state = ExhibitionState()
    state.activate(locked_navigation_state={"x": 1})
    assert state.locked_navigation_state == {"x": 1}


def test_deactivate_resets_everything():
    state = ExhibitionState()
    state.activate(view_mode=ViewMode.AUDIENCE)
    state.highlight("uid:42")
    state.set_current_chapter("ch-1")
    state.show_presenter_notes = False
    state.deactivate()
    assert state.active is False
    assert state.view_mode is ViewMode.PRESENTER
    assert state.show_presenter_notes is True
    assert state.highlighted_uid == ""
    assert state.current_chapter_id == ""


def test_deactivate_idempotent():
    state = ExhibitionState()
    state.deactivate()
    state.deactivate()
    assert state.active is False


# ---------------------------------------------------------------------------
# Toggles
# ---------------------------------------------------------------------------


def test_toggle_view_mode_flips():
    state = ExhibitionState()
    state.activate()
    new = state.toggle_view_mode()
    assert new is ViewMode.AUDIENCE
    new = state.toggle_view_mode()
    assert new is ViewMode.PRESENTER


def test_set_view_mode_rejects_non_enum():
    state = ExhibitionState()
    with pytest.raises(ValueError):
        state.set_view_mode("audience")  # type: ignore[arg-type]


def test_toggle_presenter_notes():
    state = ExhibitionState()
    new = state.toggle_presenter_notes()
    assert new is False
    new = state.toggle_presenter_notes()
    assert new is True


# ---------------------------------------------------------------------------
# Lock / unlock
# ---------------------------------------------------------------------------


def test_lock_navigation_with_snapshot():
    state = ExhibitionState()
    state.lock_navigation(snapshot={"camera": (1, 2, 3)})
    assert state.locked_navigation is True
    assert state.locked_navigation_state == {"camera": (1, 2, 3)}


def test_unlock_navigation_clears_snapshot():
    state = ExhibitionState()
    state.lock_navigation(snapshot={"camera": (1, 2, 3)})
    state.unlock_navigation()
    assert state.locked_navigation is False
    assert state.locked_navigation_state is None


def test_lock_navigation_none_snapshot_keeps_lock():
    state = ExhibitionState()
    state.lock_navigation()
    assert state.locked_navigation is True
    assert state.locked_navigation_state is None


# ---------------------------------------------------------------------------
# Highlight + chapter
# ---------------------------------------------------------------------------


def test_highlight_sets_uid():
    state = ExhibitionState()
    state.highlight("gaia:beta:1")
    assert state.highlighted_uid == "gaia:beta:1"


def test_clear_highlight_resets():
    state = ExhibitionState()
    state.highlight("x")
    state.clear_highlight()
    assert state.highlighted_uid == ""


def test_highlight_with_none_or_empty_clears():
    state = ExhibitionState()
    state.highlight("x")
    state.highlight("")
    assert state.highlighted_uid == ""


def test_set_current_chapter():
    state = ExhibitionState()
    state.set_current_chapter("ch-saturn")
    assert state.current_chapter_id == "ch-saturn"


# ---------------------------------------------------------------------------
# Short summary
# ---------------------------------------------------------------------------


def test_short_summary_idle():
    assert "idle" in ExhibitionState().short_summary()


def test_short_summary_active():
    state = ExhibitionState()
    state.activate(view_mode=ViewMode.AUDIENCE)
    state.highlight("uid:x")
    s = state.short_summary()
    assert "active" in s
    assert "audience" in s
    assert "nav=locked" in s
    assert "uid:x" in s


def test_short_summary_unlocked_nav():
    state = ExhibitionState()
    state.activate(locked_navigation=False)
    assert "nav=free" in state.short_summary()


def test_short_summary_notes_hidden():
    state = ExhibitionState()
    state.activate(show_presenter_notes=False)
    assert "notes=hidden" in state.short_summary()


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


def test_guard_idle_state_allows_everything():
    state = ExhibitionState()
    decision = guard_action("reset_workspace_state", state)
    assert decision.blocked is False


def test_guard_active_blocks_protected_operation():
    state = ExhibitionState()
    state.activate()
    decision = guard_action("reset_workspace_state", state)
    assert decision.blocked is True
    assert "exhibition" in decision.reason.lower()


def test_guard_active_allows_unprotected_operation():
    state = ExhibitionState()
    state.activate()
    decision = guard_action("inspect_metadata", state)
    assert decision.blocked is False


def test_guard_handles_blank_operation():
    state = ExhibitionState()
    state.activate()
    decision = guard_action("", state)
    assert decision.blocked is False


def test_guard_decision_summary_format():
    state = ExhibitionState()
    state.activate()
    decision = guard_action("clear_route", state)
    assert decision.short_summary().startswith("BLOCKED")


def test_guard_decision_allow_summary():
    state = ExhibitionState()
    decision = guard_action("inspect", state)
    assert decision.short_summary().startswith("allow")


def test_guarded_operations_includes_v34_resets():
    ops = guarded_operations()
    for required in (
        "reset_workspace_state",
        "clear_generated_objects",
        "rebuild_scene_hierarchy",
    ):
        assert required in ops


def test_guarded_operations_includes_mission_destructive():
    ops = guarded_operations()
    for required in (
        "delete_mission",
        "clear_unav_keyframes",
        "clear_timeline_markers",
    ):
        assert required in ops


def test_protected_operations_constant_matches_helper():
    assert sorted(guarded_operations()) == sorted(PROTECTED_OPERATIONS)
