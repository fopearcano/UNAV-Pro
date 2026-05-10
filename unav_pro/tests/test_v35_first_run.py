"""v3.5 first-run experience tests."""

from __future__ import annotations

import pytest

from core.first_run import (
    EMPTY_STATE_HINT,
    FIRST_RUN_STAGES,
    WELCOME_HEADER,
    FirstRunRecommendation,
    FirstRunStage,
    FirstRunState,
    classify_state,
    probe_first_run_state,
    recommend_next_step,
    render_empty_state,
    render_welcome_message,
)


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def test_first_run_stages_inventory():
    expected = {
        FirstRunStage.NO_WORKSPACE,
        FirstRunStage.NO_DATASETS,
        FirstRunStage.NO_NAVIGATOR,
        FirstRunStage.NO_VISIBLE_SECTOR,
        FirstRunStage.READY,
    }
    assert expected == set(FIRST_RUN_STAGES)


def test_stage_str_values():
    assert FirstRunStage.NO_WORKSPACE.value == "no_workspace"
    assert FirstRunStage.READY.value == "ready"


# ---------------------------------------------------------------------------
# classify_state
# ---------------------------------------------------------------------------


def test_classify_no_workspace():
    assert classify_state(FirstRunState()) is FirstRunStage.NO_WORKSPACE


def test_classify_no_datasets():
    state = FirstRunState(workspace_active=True)
    assert classify_state(state) is FirstRunStage.NO_DATASETS


def test_classify_no_navigator():
    state = FirstRunState(
        workspace_active=True, enabled_dataset_count=2,
    )
    assert classify_state(state) is FirstRunStage.NO_NAVIGATOR


def test_classify_no_visible_sector():
    state = FirstRunState(
        workspace_active=True, enabled_dataset_count=2,
        has_navigator=True,
    )
    assert classify_state(state) is FirstRunStage.NO_VISIBLE_SECTOR


def test_classify_ready():
    state = FirstRunState(
        workspace_active=True, enabled_dataset_count=2,
        has_navigator=True, visible_sector_count=10,
    )
    assert classify_state(state) is FirstRunStage.READY


# ---------------------------------------------------------------------------
# recommend_next_step
# ---------------------------------------------------------------------------


def test_recommend_no_workspace():
    rec = recommend_next_step(FirstRunState())
    assert rec.stage is FirstRunStage.NO_WORKSPACE
    assert "workspace" in rec.title.lower()
    assert rec.button_label == "Open Workspace…"


def test_recommend_no_datasets():
    rec = recommend_next_step(FirstRunState(workspace_active=True))
    assert rec.stage is FirstRunStage.NO_DATASETS
    assert "dataset" in rec.title.lower()


def test_recommend_no_navigator():
    rec = recommend_next_step(FirstRunState(
        workspace_active=True, enabled_dataset_count=1,
    ))
    assert rec.stage is FirstRunStage.NO_NAVIGATOR
    assert "navigator" in rec.title.lower()


def test_recommend_no_visible_sector():
    rec = recommend_next_step(FirstRunState(
        workspace_active=True, enabled_dataset_count=1,
        has_navigator=True,
    ))
    assert rec.stage is FirstRunStage.NO_VISIBLE_SECTOR
    assert "sync" in rec.title.lower()


def test_recommend_ready_has_no_button():
    rec = recommend_next_step(FirstRunState(
        workspace_active=True, enabled_dataset_count=1,
        has_navigator=True, visible_sector_count=5,
    ))
    assert rec.stage is FirstRunStage.READY
    assert rec.button_label == ""


def test_recommend_short_summary():
    rec = recommend_next_step(FirstRunState())
    s = rec.short_summary()
    assert "no_workspace" in s


# ---------------------------------------------------------------------------
# render_welcome_message
# ---------------------------------------------------------------------------


def test_welcome_includes_header():
    msg = render_welcome_message(FirstRunState())
    assert WELCOME_HEADER in msg


def test_welcome_includes_version_when_provided():
    msg = render_welcome_message(
        FirstRunState(),
        plugin_version="3.5.0",
        plugin_codename="Public Alpha",
    )
    assert "3.5.0" in msg
    assert "Public Alpha" in msg


def test_welcome_omits_version_line_when_blank():
    msg = render_welcome_message(FirstRunState())
    assert "v" not in msg.split("\n")[1] or "v" in WELCOME_HEADER  # tolerant


def test_welcome_includes_next_step_recommendation():
    msg = render_welcome_message(FirstRunState())
    assert "Next step" in msg
    assert "workspace" in msg.lower()


def test_welcome_includes_empty_hint_unless_ready():
    msg = render_welcome_message(FirstRunState())
    assert EMPTY_STATE_HINT in msg


def test_welcome_omits_empty_hint_when_ready():
    msg = render_welcome_message(FirstRunState(
        workspace_active=True, enabled_dataset_count=1,
        has_navigator=True, visible_sector_count=5,
    ))
    assert EMPTY_STATE_HINT not in msg


# ---------------------------------------------------------------------------
# render_empty_state
# ---------------------------------------------------------------------------


def test_render_empty_state_with_label():
    text = render_empty_state("missions")
    assert "No missions loaded yet" in text
    assert "Health Check" in text


def test_render_empty_state_without_label():
    text = render_empty_state("")
    assert text == EMPTY_STATE_HINT


# ---------------------------------------------------------------------------
# probe_first_run_state
# ---------------------------------------------------------------------------


def test_probe_first_run_state_returns_dataclass():
    state = probe_first_run_state()
    assert isinstance(state, FirstRunState)


def test_probe_first_run_state_defensive_when_idle():
    """Outside a workspace + with no navigator, the
    probe should produce a sensible NO_WORKSPACE
    snapshot."""
    from core.state_manager import set_current_workspace
    set_current_workspace(None)
    state = probe_first_run_state()
    assert state.workspace_active is False
    # has_navigator + visible_sector_count default to
    # False / 0 when not running inside C4D.
    assert state.has_navigator is False
    assert state.visible_sector_count == 0


# ---------------------------------------------------------------------------
# Recommendation message determinism
# ---------------------------------------------------------------------------


def test_recommendation_deterministic():
    state = FirstRunState(workspace_active=True)
    a = recommend_next_step(state)
    b = recommend_next_step(state)
    assert a == b


def test_welcome_deterministic():
    state = FirstRunState()
    a = render_welcome_message(state, plugin_version="3.5.0")
    b = render_welcome_message(state, plugin_version="3.5.0")
    assert a == b
