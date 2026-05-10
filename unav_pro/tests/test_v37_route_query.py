"""v3.7 route-aware query tests."""

from __future__ import annotations

import math

import pytest

from data import CatalogObject
from query import (
    DEFAULT_CORRIDOR_RADIUS_PC,
    ClosestPerWaypoint,
    RouteQueryReport,
    RouteSummary,
    closest_object_to_each_waypoint,
    distance_point_to_polyline,
    distance_point_to_segment,
    find_objects_between_waypoints,
    find_objects_near_route,
    polyline_from_waypoints,
    summarise_route_distribution,
)


def _row(uid, x, y, z, **kw):
    base = dict(
        uid=uid, catalog_source="Test",
        object_type="star", ra_deg=0.0, dec_deg=0.0,
        cartesian_x=float(x), cartesian_y=float(y),
        cartesian_z=float(z),
    )
    base.update(kw)
    return CatalogObject(**base)


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------


def test_distance_point_to_segment_perpendicular_drop():
    # Point at (5, 5, 0) projects onto segment (0,0,0)→(10,0,0)
    # at (5, 0, 0); distance is 5.
    d = distance_point_to_segment(
        (5.0, 5.0, 0.0), (0.0, 0.0, 0.0), (10.0, 0.0, 0.0),
    )
    assert math.isclose(d, 5.0, rel_tol=1e-6)


def test_distance_point_to_segment_clamps_at_endpoints():
    # Point past the end of the segment should be
    # measured from the endpoint, not the projected
    # line.
    d = distance_point_to_segment(
        (15.0, 0.0, 0.0), (0.0, 0.0, 0.0), (10.0, 0.0, 0.0),
    )
    assert math.isclose(d, 5.0, rel_tol=1e-6)


def test_distance_point_to_degenerate_segment():
    """A zero-length segment falls back to point-to-
    point distance."""
    d = distance_point_to_segment(
        (3.0, 4.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0),
    )
    assert math.isclose(d, 5.0, rel_tol=1e-6)


def test_distance_point_to_polyline_picks_closest_segment():
    polyline = [
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0),
    ]
    d = distance_point_to_polyline((5.0, 1.0, 0.0), polyline)
    assert math.isclose(d, 1.0, rel_tol=1e-6)


def test_distance_point_to_empty_polyline_inf():
    d = distance_point_to_polyline((1.0, 2.0, 3.0), [])
    assert d == float("inf")


def test_distance_point_to_single_point_polyline():
    d = distance_point_to_polyline(
        (3.0, 4.0, 0.0), [(0.0, 0.0, 0.0)],
    )
    assert math.isclose(d, 5.0, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# polyline_from_waypoints
# ---------------------------------------------------------------------------


def test_polyline_from_waypoints_extracts_c4d_coords():
    class WP:
        def __init__(self, x, y, z):
            self.x_c4d = x
            self.y_c4d = y
            self.z_c4d = z
    out = polyline_from_waypoints([WP(0, 0, 0), WP(10, 0, 0)])
    assert out == [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)]


def test_polyline_from_waypoints_skips_missing_coords():
    class WP:
        def __init__(self, x=None, y=None, z=None):
            self.x_c4d = x
            self.y_c4d = y
            self.z_c4d = z
    out = polyline_from_waypoints([
        WP(),  # missing all
        WP(10, 0, 0),
    ])
    assert out == [(10.0, 0.0, 0.0)]


# ---------------------------------------------------------------------------
# find_objects_near_route
# ---------------------------------------------------------------------------


def test_near_route_returns_objects_in_corridor():
    polyline = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)]
    rows = [
        _row("a", 5, 1, 0),    # 1 pc from segment
        _row("b", 5, 100, 0),  # 100 pc — outside
        _row("c", 5, 0.5, 0),  # 0.5 pc — closer than a
    ]
    rep = find_objects_near_route(
        polyline=polyline,
        candidates=rows,
        corridor_radius_pc=5.0,
        max_results=10,
    )
    uids = [r.uid for r in rep.results]
    assert uids == ["c", "a"]


def test_near_route_caps_results():
    polyline = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)]
    rows = [_row(f"u{i}", 5, 0.1 * i, 0) for i in range(20)]
    rep = find_objects_near_route(
        polyline=polyline,
        candidates=rows,
        corridor_radius_pc=10.0,
        max_results=5,
    )
    assert rep.returned == 5
    assert rep.matched_before_cap == 20


def test_near_route_warns_on_empty_polyline():
    rep = find_objects_near_route(
        polyline=[],
        candidates=[_row("a", 0, 0, 0)],
    )
    assert rep.warnings


def test_near_route_rejects_invalid_radius():
    with pytest.raises(ValueError):
        find_objects_near_route(
            polyline=[(0, 0, 0), (1, 0, 0)],
            candidates=[],
            corridor_radius_pc=0.0,
        )


def test_default_corridor_radius_documented():
    assert DEFAULT_CORRIDOR_RADIUS_PC == 5.0


def test_near_route_skips_rows_without_position():
    polyline = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)]
    rows = [
        _row("a", 5, 0, 0),
        CatalogObject(
            uid="b", catalog_source="Test",
            object_type="star", ra_deg=0.0, dec_deg=0.0,
        ),  # no Cartesian
    ]
    rep = find_objects_near_route(
        polyline=polyline, candidates=rows,
        corridor_radius_pc=5.0,
    )
    uids = [r.uid for r in rep.results]
    assert uids == ["a"]


# ---------------------------------------------------------------------------
# find_objects_between_waypoints
# ---------------------------------------------------------------------------


def test_between_waypoints_uses_one_segment():
    rep = find_objects_between_waypoints(
        a=(0, 0, 0), b=(10, 0, 0),
        candidates=[_row("a", 5, 1, 0)],
        corridor_radius_pc=5.0,
    )
    assert rep.returned == 1
    assert rep.results[0].uid == "a"


# ---------------------------------------------------------------------------
# closest_object_to_each_waypoint
# ---------------------------------------------------------------------------


def test_closest_per_waypoint_picks_nearest_each():
    rows = [
        _row("a", 0, 0, 0),
        _row("b", 10, 0, 0),
        _row("c", 50, 0, 0),
    ]
    matches = closest_object_to_each_waypoint(
        waypoints=[(0, 0, 0), (10, 0, 0)],
        candidates=rows,
    )
    assert len(matches) == 2
    assert matches[0].closest.uid == "a"
    assert matches[1].closest.uid == "b"


def test_closest_per_waypoint_handles_no_candidates():
    matches = closest_object_to_each_waypoint(
        waypoints=[(0, 0, 0)],
        candidates=[],
    )
    assert matches[0].closest is None
    assert matches[0].distance_pc is None


def test_closest_per_waypoint_index_zero_based():
    rows = [_row("a", 0, 0, 0)]
    matches = closest_object_to_each_waypoint(
        waypoints=[(0, 0, 0), (10, 0, 0)],
        candidates=rows,
    )
    assert [m.waypoint_index for m in matches] == [0, 1]


# ---------------------------------------------------------------------------
# summarise_route_distribution
# ---------------------------------------------------------------------------


def test_route_summary_counts_per_source():
    rows = [
        _row("a", 5, 0, 0, catalog_source="Gaia"),
        _row("b", 5, 0, 0, catalog_source="Gaia"),
        _row("c", 5, 0, 0, catalog_source="JPL"),
    ]
    summary = summarise_route_distribution(
        polyline=[(0, 0, 0), (10, 0, 0)],
        candidates=rows,
        corridor_radius_pc=5.0,
    )
    assert summary.total == 3
    assert summary.per_source.get("Gaia") == 2
    assert summary.per_source.get("JPL") == 1


def test_route_summary_counts_per_type():
    rows = [
        _row("a", 5, 0, 0, object_type="star"),
        _row("b", 5, 0, 0, object_type="galaxy"),
        _row("c", 5, 0, 0, object_type="star"),
    ]
    summary = summarise_route_distribution(
        polyline=[(0, 0, 0), (10, 0, 0)],
        candidates=rows,
        corridor_radius_pc=5.0,
    )
    assert summary.per_type["star"] == 2
    assert summary.per_type["galaxy"] == 1


def test_route_summary_short_summary_includes_count():
    rows = [_row("a", 5, 0, 0)]
    summary = summarise_route_distribution(
        polyline=[(0, 0, 0), (10, 0, 0)],
        candidates=rows,
        corridor_radius_pc=5.0,
    )
    assert "1 object" in summary.short_summary()


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_route_query_deterministic():
    polyline = [(0, 0, 0), (10, 0, 0)]
    rows = [_row(f"u{i}", 5, 0.1 * i, 0) for i in range(8)]
    a = find_objects_near_route(
        polyline=polyline, candidates=rows,
        corridor_radius_pc=2.0,
    )
    b = find_objects_near_route(
        polyline=polyline, candidates=rows,
        corridor_radius_pc=2.0,
    )
    assert [r.uid for r in a.results] == [r.uid for r in b.results]
