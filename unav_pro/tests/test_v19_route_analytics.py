"""v1.9 route-analytics tests."""

from __future__ import annotations

import math

import pytest

from voyage import Mission, MissionWaypoint, analyse_route
from voyage.route_analytics import (
    DEFAULT_TRAVEL_SPEED_PC_PER_S,
    EPOCH_SPREAD_WARN_THRESHOLD_DAYS,
)


def _three_wp_mission(*, with_pc=True, with_epoch=False):
    """Three coordinate waypoints in a straight line on the X
    axis, optionally with parsec positions and epoch."""
    waypoints = []
    for i in range(3):
        wp = MissionWaypoint(
            kind="coordinate",
            x_c4d=float(i * 10), y_c4d=0.0, z_c4d=0.0,
            label=f"wp{i}",
            duration_seconds=2.0,
            x_pc=float(i * 5) if with_pc else None,
            y_pc=0.0 if with_pc else None,
            z_pc=0.0 if with_pc else None,
            epoch_jd=2451545.0 + i if with_epoch else None,
        )
        waypoints.append(wp)
    return Mission(waypoints=waypoints)


# ---------------------------------------------------------------------------
# Distances
# ---------------------------------------------------------------------------


def test_total_c4d_distance():
    m = _three_wp_mission()
    rpt = analyse_route(m)
    # 3 waypoints at x=0,10,20 → two segments of length 10.
    assert rpt.total_distance_c4d == pytest.approx(20.0)


def test_total_pc_distance_when_all_have_pc():
    m = _three_wp_mission(with_pc=True)
    rpt = analyse_route(m)
    # Each segment: 5 pc.
    assert rpt.total_distance_pc == pytest.approx(10.0)


def test_total_pc_unknown_when_any_missing():
    m = _three_wp_mission(with_pc=True)
    m.waypoints[1].x_pc = None  # one waypoint without parsec coords
    rpt = analyse_route(m)
    assert rpt.total_distance_pc is None
    assert rpt.has_unknown_distances()


def test_estimated_travel_time_uses_default_speed():
    m = _three_wp_mission(with_pc=True)
    rpt = analyse_route(m)
    expected = 10.0 / DEFAULT_TRAVEL_SPEED_PC_PER_S
    assert rpt.estimated_travel_seconds == pytest.approx(expected)


def test_estimated_travel_time_respects_custom_speed():
    m = _three_wp_mission(with_pc=True)
    rpt = analyse_route(m, travel_speed_pc_per_s=2.0)
    assert rpt.estimated_travel_seconds == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------


def test_kind_count_includes_annotation():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="annotation", label="note"),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
    ])
    rpt = analyse_route(m)
    assert rpt.waypoint_kind_counts.get("annotation") == 1
    assert rpt.waypoint_kind_counts.get("coordinate") == 2


def test_object_type_and_source_histograms():
    m = Mission(waypoints=[
        MissionWaypoint(
            kind="object", uid="x:1",
            x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
            catalog_source="Gaia DR3", object_type="star",
        ),
        MissionWaypoint(
            kind="object", uid="x:2",
            x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
            catalog_source="JPL Horizons", object_type="planet",
        ),
    ])
    rpt = analyse_route(m)
    assert rpt.catalog_source_counts == {"Gaia DR3": 1, "JPL Horizons": 1}
    assert rpt.object_type_counts == {"star": 1, "planet": 1}


def test_tags_unioned_across_mission_and_waypoints():
    m = Mission(waypoints=[
        MissionWaypoint(
            kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
            tags=["solar"],
        ),
        MissionWaypoint(
            kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
            tags=["star"],
        ),
    ], tags=["demo"])
    rpt = analyse_route(m)
    assert set(rpt.tags) == {"solar", "star", "demo"}


# ---------------------------------------------------------------------------
# Epoch consistency
# ---------------------------------------------------------------------------


def test_epoch_spread_recorded_when_present():
    m = _three_wp_mission(with_epoch=True)
    rpt = analyse_route(m)
    assert rpt.epoch_min_jd == pytest.approx(2451545.0)
    assert rpt.epoch_max_jd == pytest.approx(2451547.0)
    assert rpt.epoch_spread_days == pytest.approx(2.0)
    assert rpt.has_epoch_warning() is False


def test_long_epoch_spread_triggers_warning():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate",
                        x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        epoch_jd=2451545.0),  # J2000
        MissionWaypoint(kind="coordinate",
                        x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
                        epoch_jd=2451545.0 + EPOCH_SPREAD_WARN_THRESHOLD_DAYS + 100),
    ])
    rpt = analyse_route(m)
    assert rpt.has_epoch_warning()
    assert "long temporal range" in rpt.epoch_spread_warning


def test_no_epoch_warning_when_no_waypoint_carries_one():
    m = _three_wp_mission(with_epoch=False)
    rpt = analyse_route(m)
    assert rpt.epoch_min_jd is None
    assert rpt.epoch_spread_warning is None


def test_waypoints_without_epoch_listed():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
                        epoch_jd=2451545.0),
    ])
    rpt = analyse_route(m)
    assert rpt.waypoints_without_epoch == [0]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_render_text_lists_segment_count():
    m = _three_wp_mission(with_pc=True, with_epoch=True)
    text = analyse_route(m).render_text()
    assert "Segments       : 2" in text
    assert "Waypoint Kinds" in text
    assert "Epoch Range" in text


def test_render_text_includes_warnings_when_present():
    m = _three_wp_mission(with_pc=True)
    m.waypoints[1].x_pc = None
    text = analyse_route(m).render_text()
    assert "Warnings" in text
    assert "no parsec position" in text


def test_render_text_no_warnings_when_clean():
    m = _three_wp_mission(with_pc=True)
    text = analyse_route(m).render_text()
    assert "Warnings" not in text


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_analyse_route_is_deterministic():
    m = _three_wp_mission(with_pc=True, with_epoch=True)
    a = analyse_route(m).render_text()
    b = analyse_route(m).render_text()
    assert a == b
