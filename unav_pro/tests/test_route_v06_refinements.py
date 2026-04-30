"""Tests for v0.6 route refinements: insert_at, replace_at, move,
plus the v2 segment renderer."""

from __future__ import annotations

import pytest

from core.metadata_lookup import MetadataLookup
from core.route import (
    Route,
    Waypoint,
    compute_route,
    make_lookup_resolver,
    render_summary_v2,
)
from data.schema import CatalogObject


def _wp_obj(uid, label):
    return Waypoint(kind="object", label=label, uid=uid)


def _wp_coord(label, x, y, z):
    return Waypoint(
        kind="coordinate", label=label, x_c4d=x, y_c4d=y, z_c4d=z,
        x_pc=x, y_pc=y, z_pc=z,
    )


# ---------------------------------------------------------------------------
# insert_at
# ---------------------------------------------------------------------------


def test_insert_at_appends_when_index_is_end():
    r = Route()
    r.add(_wp_obj("a", "A"))
    r.insert_at(1, _wp_obj("b", "B"))
    assert [w.uid for w in r.waypoints] == ["a", "b"]


def test_insert_at_inserts_at_middle():
    r = Route()
    r.add(_wp_obj("a", "A"))
    r.add(_wp_obj("c", "C"))
    r.insert_at(1, _wp_obj("b", "B"))
    assert [w.uid for w in r.waypoints] == ["a", "b", "c"]


def test_insert_at_clamps_negative_index():
    r = Route()
    r.add(_wp_obj("a", "A"))
    r.insert_at(-100, _wp_obj("b", "B"))
    assert r.waypoints[0].uid == "b"


def test_insert_at_clamps_overshooting_index_to_append():
    r = Route()
    r.add(_wp_obj("a", "A"))
    r.insert_at(99, _wp_obj("b", "B"))
    assert r.waypoints[-1].uid == "b"


# ---------------------------------------------------------------------------
# replace_at
# ---------------------------------------------------------------------------


def test_replace_at_swaps_waypoint_and_returns_old():
    r = Route()
    a = _wp_obj("a", "A")
    b = _wp_obj("b", "B")
    r.add(a)
    old = r.replace_at(0, b)
    assert old is a
    assert r.waypoints[0] is b


def test_replace_at_returns_none_for_out_of_range():
    r = Route()
    r.add(_wp_obj("a", "A"))
    assert r.replace_at(99, _wp_obj("z", "Z")) is None


# ---------------------------------------------------------------------------
# move
# ---------------------------------------------------------------------------


def test_move_reorders_in_place():
    r = Route()
    r.add(_wp_obj("a", "A"))
    r.add(_wp_obj("b", "B"))
    r.add(_wp_obj("c", "C"))
    assert r.move(0, 2)
    assert [w.uid for w in r.waypoints] == ["b", "c", "a"]


def test_move_clamps_target_to_valid_range():
    r = Route()
    r.add(_wp_obj("a", "A"))
    r.add(_wp_obj("b", "B"))
    assert r.move(0, 99)
    assert [w.uid for w in r.waypoints] == ["b", "a"]


def test_move_returns_false_for_empty_route():
    r = Route()
    assert r.move(0, 0) is False


def test_move_returns_false_for_out_of_range_source():
    r = Route()
    r.add(_wp_obj("a", "A"))
    assert r.move(99, 0) is False


def test_move_to_same_index_is_noop_but_returns_true():
    r = Route()
    r.add(_wp_obj("a", "A"))
    r.add(_wp_obj("b", "B"))
    assert r.move(0, 0)
    assert [w.uid for w in r.waypoints] == ["a", "b"]


# ---------------------------------------------------------------------------
# Distance computation respects refinements
# ---------------------------------------------------------------------------


def test_distance_after_insert_includes_new_segment():
    r = Route()
    r.add(_wp_coord("A", 0.0, 0.0, 0.0))
    r.add(_wp_coord("C", 10.0, 0.0, 0.0))
    summary = compute_route(r)
    assert summary.total_distance_c4d == pytest.approx(10.0)
    # Now insert B at the midpoint.
    r.insert_at(1, _wp_coord("B", 5.0, 0.0, 0.0))
    summary = compute_route(r)
    # 0→5 + 5→10 = 10 still (collinear), but two segments now.
    assert len(summary.segments) == 2
    assert summary.total_distance_c4d == pytest.approx(10.0)


def test_distance_after_remove_drops_segment():
    r = Route()
    r.add(_wp_coord("A", 0.0, 0.0, 0.0))
    r.add(_wp_coord("B", 3.0, 4.0, 0.0))   # 5 from A
    r.add(_wp_coord("C", 3.0, 4.0, 12.0))  # 12 from B
    s1 = compute_route(r)
    assert s1.total_distance_c4d == pytest.approx(17.0)
    r.remove_at(1)
    s2 = compute_route(r)
    # New distance is A→C directly: sqrt(3²+4²+12²) = 13.
    assert s2.total_distance_c4d == pytest.approx(13.0)


def test_render_summary_v2_includes_segment_table():
    r = Route()
    r.add(_wp_coord("A", 0.0, 0.0, 0.0))
    r.add(_wp_coord("B", 1.0, 0.0, 0.0))
    summary = compute_route(r)
    out = render_summary_v2(r, summary)
    assert "Segments:" in out
    assert "A → B" in out


def test_render_summary_v2_marks_unresolved_segments():
    """An object waypoint with no cached coords and no lookup hit
    is unresolved; the v2 renderer should label its segment."""
    r = Route()
    r.add(_wp_coord("A", 0.0, 0.0, 0.0))
    r.add(_wp_obj("absent:1", "Absent"))
    summary = compute_route(r)
    out = render_summary_v2(r, summary)
    assert "unresolved" in out
