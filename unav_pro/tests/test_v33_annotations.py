"""v3.3 presentation-annotation tests."""

from __future__ import annotations

import pytest

from presentation import (
    AnnotationDisplayState,
    StepAnnotationView,
    diff_annotation_views,
    resolve_annotation_view,
)


# ---------------------------------------------------------------------------
# AnnotationDisplayState
# ---------------------------------------------------------------------------


def test_state_round_trip():
    s = AnnotationDisplayState(
        index=2, visible=True, highlighted=True,
        presentation_only_notes="Note this",
    )
    rt = AnnotationDisplayState.from_dict(s.to_dict())
    assert rt.index == 2
    assert rt.visible is True
    assert rt.highlighted is True
    assert rt.presentation_only_notes == "Note this"


# ---------------------------------------------------------------------------
# resolve_annotation_view
# ---------------------------------------------------------------------------


def test_empty_visible_means_all_visible():
    """Per the v3.3 spec, an empty visible-indices list
    treats every annotation as visible (preserves the
    v1.9 default)."""
    view = resolve_annotation_view(
        step_id="s1", step_index=0,
        annotation_count=3,
        visible_indices=[],
        highlighted_indices=[],
    )
    assert all(s.visible for s in view.states)


def test_explicit_visible_indices_filter():
    view = resolve_annotation_view(
        step_id="s1", step_index=0,
        annotation_count=3,
        visible_indices=[0, 2],
        highlighted_indices=[],
    )
    visibility = [s.visible for s in view.states]
    assert visibility == [True, False, True]


def test_highlighted_intersected_with_visible():
    """An annotation cannot be highlighted unless it is
    also visible."""
    view = resolve_annotation_view(
        step_id="s1", step_index=0,
        annotation_count=3,
        visible_indices=[0],
        highlighted_indices=[1, 2],  # both invisible
    )
    assert view.highlighted_indices() == []


def test_highlighted_when_visible():
    view = resolve_annotation_view(
        step_id="s1", step_index=0,
        annotation_count=3,
        visible_indices=[0, 1],
        highlighted_indices=[1],
    )
    assert view.highlighted_indices() == [1]


def test_per_step_notes_attached():
    view = resolve_annotation_view(
        step_id="s1", step_index=0,
        annotation_count=2,
        visible_indices=[0, 1],
        highlighted_indices=[],
        per_step_notes={1: "Note for #1"},
    )
    assert view.states[0].presentation_only_notes == ""
    assert view.states[1].presentation_only_notes == "Note for #1"


def test_view_visible_indices_sorted():
    view = resolve_annotation_view(
        step_id="s1", step_index=0,
        annotation_count=3,
        visible_indices=[2, 0, 1],
        highlighted_indices=[],
    )
    assert view.visible_indices() == [0, 1, 2]


def test_view_handles_zero_annotations():
    view = resolve_annotation_view(
        step_id="s1", step_index=0,
        annotation_count=0,
        visible_indices=[0],
        highlighted_indices=[],
    )
    assert view.states == []


# ---------------------------------------------------------------------------
# diff_annotation_views
# ---------------------------------------------------------------------------


def test_diff_added_and_removed():
    prev = resolve_annotation_view(
        step_id="a", step_index=0, annotation_count=3,
        visible_indices=[0, 1], highlighted_indices=[],
    )
    cur = resolve_annotation_view(
        step_id="b", step_index=1, annotation_count=3,
        visible_indices=[1, 2], highlighted_indices=[],
    )
    diff = diff_annotation_views(prev, cur)
    assert diff["added"] == [2]
    assert diff["removed"] == [0]
    assert diff["kept"] == [1]


def test_diff_highlight_added_removed():
    prev = resolve_annotation_view(
        step_id="a", step_index=0, annotation_count=3,
        visible_indices=[0, 1, 2], highlighted_indices=[0],
    )
    cur = resolve_annotation_view(
        step_id="b", step_index=1, annotation_count=3,
        visible_indices=[0, 1, 2], highlighted_indices=[1],
    )
    diff = diff_annotation_views(prev, cur)
    assert diff["highlight_added"] == [1]
    assert diff["highlight_removed"] == [0]


def test_diff_with_no_previous_treats_all_as_added():
    cur = resolve_annotation_view(
        step_id="b", step_index=0, annotation_count=2,
        visible_indices=[0, 1], highlighted_indices=[],
    )
    diff = diff_annotation_views(None, cur)
    assert diff["added"] == [0, 1]
    assert diff["removed"] == []
    assert diff["kept"] == []


def test_diff_identical_views_yields_no_changes():
    cur = resolve_annotation_view(
        step_id="b", step_index=0, annotation_count=2,
        visible_indices=[0, 1], highlighted_indices=[1],
    )
    diff = diff_annotation_views(cur, cur)
    assert diff["added"] == []
    assert diff["removed"] == []
    assert diff["highlight_added"] == []
    assert diff["highlight_removed"] == []
    assert diff["kept"] == [0, 1]
