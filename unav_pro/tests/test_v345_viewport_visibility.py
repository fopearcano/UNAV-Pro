"""v3.45 viewport-visibility tests."""

from __future__ import annotations

import pytest

from c4d_objects.viewport_visibility import (
    KIND_ANNOTATION_LABEL,
    KIND_DEBUG_CONE,
    KIND_MISSION_PREVIEW,
    KIND_NAVIGATOR_NULL,
    KIND_OVERLAY_GEOMETRY,
    KIND_PROJECT_ROOT_NULL,
    KIND_SCIENCE_GEOMETRY,
    KIND_VISIBLE_SECTOR_POINT,
    KIND_WAYPOINT_NULL,
    LabelClutterPolicy,
    PROFILE_TABLE,
    UNAV_OBJECT_KINDS,
    VISIBILITY_PROFILES,
    VISIBILITY_STATES,
    VisibilityDecision,
    VisibilityProfile,
    VisibilityState,
    label_budget_for_distance,
    plan_visibility,
    select_labels_for_zoom,
    visibility_for,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_visibility_states_complete():
    expected = {
        VisibilityState.DEFAULT,
        VisibilityState.EDITOR_ON_RENDER_OFF,
        VisibilityState.EDITOR_OFF_RENDER_OFF,
        VisibilityState.EDITOR_ON_RENDER_ON,
    }
    assert expected == set(VISIBILITY_STATES)


def test_visibility_profiles_complete():
    expected = {
        VisibilityProfile.AUTHOR, VisibilityProfile.LECTURE,
        VisibilityProfile.BAKE, VisibilityProfile.HIDDEN,
    }
    assert expected == set(VISIBILITY_PROFILES)


def test_unav_object_kinds_complete():
    expected = {
        KIND_VISIBLE_SECTOR_POINT, KIND_OVERLAY_GEOMETRY,
        KIND_SCIENCE_GEOMETRY, KIND_MISSION_PREVIEW,
        KIND_WAYPOINT_NULL, KIND_ANNOTATION_LABEL,
        KIND_DEBUG_CONE, KIND_NAVIGATOR_NULL,
        KIND_PROJECT_ROOT_NULL,
    }
    # Imported as constants but missed one in
    # the import — check the inventory directly.
    assert {KIND_VISIBLE_SECTOR_POINT,
            KIND_OVERLAY_GEOMETRY,
            KIND_SCIENCE_GEOMETRY,
            KIND_MISSION_PREVIEW,
            KIND_WAYPOINT_NULL,
            KIND_ANNOTATION_LABEL,
            KIND_DEBUG_CONE,
            KIND_PROJECT_ROOT_NULL}.issubset(set(UNAV_OBJECT_KINDS))


# ---------------------------------------------------------------------------
# visibility_for
# ---------------------------------------------------------------------------


def test_visibility_for_author_keeps_visible_points_on():
    state = visibility_for(
        KIND_VISIBLE_SECTOR_POINT, VisibilityProfile.AUTHOR,
    )
    assert state == VisibilityState.EDITOR_ON_RENDER_ON


def test_visibility_for_lecture_hides_debug():
    state = visibility_for(KIND_DEBUG_CONE, VisibilityProfile.LECTURE)
    assert state == VisibilityState.EDITOR_OFF_RENDER_OFF


def test_visibility_for_bake_hides_overlays():
    state = visibility_for(
        KIND_OVERLAY_GEOMETRY, VisibilityProfile.BAKE,
    )
    assert state == VisibilityState.EDITOR_OFF_RENDER_OFF


def test_visibility_for_hidden_hides_everything():
    for kind in UNAV_OBJECT_KINDS:
        state = visibility_for(kind, VisibilityProfile.HIDDEN)
        assert state == VisibilityState.EDITOR_OFF_RENDER_OFF


def test_visibility_for_unknown_kind_returns_default():
    state = visibility_for("artist_kind", VisibilityProfile.AUTHOR)
    assert state == VisibilityState.DEFAULT


def test_profile_table_covers_every_kind_in_author():
    for kind in UNAV_OBJECT_KINDS:
        assert kind in PROFILE_TABLE[VisibilityProfile.AUTHOR]


# ---------------------------------------------------------------------------
# plan_visibility
# ---------------------------------------------------------------------------


def test_plan_visibility_emits_one_decision_per_object():
    decisions = plan_visibility(
        objects=[
            ("UNAV_Object_1", KIND_VISIBLE_SECTOR_POINT, None),
            ("UNAV_DebugCone", KIND_DEBUG_CONE, None),
        ],
        profile=VisibilityProfile.AUTHOR,
    )
    assert len(decisions) == 2


def test_plan_visibility_change_detection():
    decisions = plan_visibility(
        objects=[
            (
                "x", KIND_VISIBLE_SECTOR_POINT,
                VisibilityState.EDITOR_ON_RENDER_ON,
            ),
        ],
        profile=VisibilityProfile.AUTHOR,
    )
    assert decisions[0].is_change() is False


def test_plan_visibility_change_when_state_differs():
    decisions = plan_visibility(
        objects=[
            (
                "x", KIND_DEBUG_CONE,
                VisibilityState.EDITOR_ON_RENDER_OFF,
            ),
        ],
        profile=VisibilityProfile.LECTURE,
    )
    assert decisions[0].is_change() is True
    assert decisions[0].desired == VisibilityState.EDITOR_OFF_RENDER_OFF


def test_plan_visibility_preserves_object_label():
    decisions = plan_visibility(
        objects=[("MyLabel", KIND_VISIBLE_SECTOR_POINT, None)],
        profile=VisibilityProfile.AUTHOR,
    )
    assert decisions[0].object_label == "MyLabel"


# ---------------------------------------------------------------------------
# VisibilityDecision summary
# ---------------------------------------------------------------------------


def test_decision_summary_no_previous():
    d = VisibilityDecision(
        object_label="x", kind=KIND_DEBUG_CONE,
        desired=VisibilityState.EDITOR_OFF_RENDER_OFF,
    )
    assert "→" in d.short_summary()


def test_decision_summary_with_previous():
    d = VisibilityDecision(
        object_label="x", kind=KIND_DEBUG_CONE,
        desired=VisibilityState.EDITOR_OFF_RENDER_OFF,
        previous=VisibilityState.EDITOR_ON_RENDER_OFF,
    )
    text = d.short_summary()
    assert "editor_only_render_off" in text
    assert "hidden" in text


# ---------------------------------------------------------------------------
# Label clutter
# ---------------------------------------------------------------------------


def test_default_clutter_policy_budgets():
    pol = LabelClutterPolicy()
    assert pol.max_labels_close > pol.max_labels_mid
    assert pol.max_labels_mid > pol.max_labels_far


def test_label_budget_for_close_distance():
    pol = LabelClutterPolicy()
    assert label_budget_for_distance(10.0, pol) == pol.max_labels_close


def test_label_budget_for_mid_distance():
    pol = LabelClutterPolicy()
    assert label_budget_for_distance(100.0, pol) == pol.max_labels_mid


def test_label_budget_for_far_distance():
    pol = LabelClutterPolicy()
    assert label_budget_for_distance(1000.0, pol) == pol.max_labels_far


def test_label_budget_handles_zero_or_negative():
    pol = LabelClutterPolicy()
    assert label_budget_for_distance(0.0, pol) == pol.max_labels_close
    assert label_budget_for_distance(-5.0, pol) == pol.max_labels_close


def test_select_labels_truncates_to_budget():
    candidates = [(f"label_{i}", float(100 - i)) for i in range(50)]
    out = select_labels_for_zoom(
        candidates=candidates, distance=10.0,
        policy=LabelClutterPolicy(max_labels_close=5),
    )
    assert len(out) == 5


def test_select_labels_ranks_by_importance():
    candidates = [
        ("low", 0.1),
        ("high", 99.0),
        ("mid", 5.0),
    ]
    out = select_labels_for_zoom(
        candidates=candidates, distance=10.0,
        policy=LabelClutterPolicy(max_labels_close=2),
    )
    assert out == ["high", "mid"]


def test_select_labels_empty_input():
    out = select_labels_for_zoom(candidates=[], distance=10.0)
    assert out == []


def test_select_labels_zero_budget():
    out = select_labels_for_zoom(
        candidates=[("a", 1.0)], distance=1000.0,
        policy=LabelClutterPolicy(max_labels_far=0),
    )
    assert out == []
