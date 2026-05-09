"""v1.8 path-preview helper tests (pure-Python only).

The c4d-bound applier (``apply_preview_spline`` /
``clear_preview_spline``) is exercised by the dialog at
runtime and not unit-tested here.
"""

from __future__ import annotations

import pytest

from c4d_objects.path_preview import (
    apply_preview_spline,
    build_preview_points,
    clear_preview_spline,
)
from voyage import Mission, MissionWaypoint, build_camera_path


def test_build_preview_points_empty_path():
    pts = build_preview_points(build_camera_path(Mission()))
    assert pts == []


def test_build_preview_points_two_waypoints_returns_endpoints():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
    ])
    pts = build_preview_points(build_camera_path(m), samples_per_segment=4)
    assert pts[0] == pytest.approx((0.0, 0.0, 0.0))
    assert pts[-1] == pytest.approx((10.0, 0.0, 0.0))


def test_build_preview_points_count():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=20.0, y_c4d=0.0, z_c4d=0.0),
    ])
    path = build_camera_path(m)
    pts = build_preview_points(path, samples_per_segment=8)
    assert len(pts) == 8 * 2 + 1


def test_apply_preview_spline_no_c4d_returns_false():
    """Outside Cinema 4D the applier must return False without
    raising."""
    assert apply_preview_spline([(0.0, 0.0, 0.0)]) is False


def test_apply_preview_spline_empty_points_returns_false():
    assert apply_preview_spline([]) is False


def test_clear_preview_spline_no_c4d_returns_false():
    assert clear_preview_spline() is False
