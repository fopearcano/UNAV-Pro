"""Tests for the v1.4 ``voyage.camera_path``."""

from __future__ import annotations

import math

import pytest

from voyage.camera_path import (
    IDENTITY_QUAT,
    CameraPath,
    CameraPathConfig,
    CameraSample,
    build_camera_path,
    build_route_from_mission,
)
from voyage.mission import Mission, MissionWaypoint


def _coord_mission(*positions, durations=None, epochs=None) -> Mission:
    durations = durations or [2.0] * len(positions)
    epochs = epochs or [None] * len(positions)
    waypoints = []
    for i, ((x, y, z), d, ep) in enumerate(zip(positions, durations, epochs)):
        waypoints.append(MissionWaypoint(
            kind="coordinate",
            x_c4d=x, y_c4d=y, z_c4d=z,
            label=f"wp{i}",
            duration_seconds=d,
            epoch_jd=ep,
        ))
    return Mission(title="m", waypoints=waypoints)


# ---------------------------------------------------------------------------
# build_camera_path
# ---------------------------------------------------------------------------


def test_empty_mission_yields_empty_path():
    path = build_camera_path(Mission())
    assert path.is_empty()


def test_single_waypoint_yields_static_path():
    m = _coord_mission((1.0, 2.0, 3.0))
    path = build_camera_path(m)
    assert path.waypoint_count() == 1
    sample = path.sample(0.5)
    assert sample.x == pytest.approx(1.0)
    assert sample.y == pytest.approx(2.0)
    assert sample.z == pytest.approx(3.0)


def test_two_waypoint_endpoints_are_exact():
    m = _coord_mission((0.0, 0.0, 0.0), (10.0, 0.0, 0.0))
    path = build_camera_path(m)
    a = path.sample(0.0)
    b = path.sample(1.0)
    assert (a.x, a.y, a.z) == pytest.approx((0.0, 0.0, 0.0))
    assert (b.x, b.y, b.z) == pytest.approx((10.0, 0.0, 0.0))


def test_three_waypoint_midpoint_lies_between_anchors():
    m = _coord_mission(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0),
    )
    path = build_camera_path(m)
    # Catmull-Rom doesn't make the geometric midpoint linear,
    # but it must lie inside the convex hull-ish region.
    sample = path.sample(0.5)
    assert 5.0 <= sample.x <= 12.0
    assert -5.0 <= sample.y <= 12.0


def test_unresolved_callback_fires_for_object_waypoints_without_position():
    m = Mission(waypoints=[
        MissionWaypoint(kind="object", uid="x:1"),  # no cached position
        MissionWaypoint(
            kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
        ),
    ])
    seen = []
    path = build_camera_path(m, on_unresolved=lambda i, w: seen.append(i))
    assert seen == [0]
    assert path.waypoint_count() == 1


def test_speed_multiplier_scales_total_duration():
    m = _coord_mission((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), durations=[2.0, 2.0])
    fast = build_camera_path(m, CameraPathConfig(speed_multiplier=2.0))
    slow = build_camera_path(m, CameraPathConfig(speed_multiplier=0.5))
    assert fast.total_duration_seconds() == pytest.approx(2.0)
    assert slow.total_duration_seconds() == pytest.approx(8.0)


def test_speed_multiplier_clamped():
    cfg = CameraPathConfig(speed_multiplier=100.0)
    assert cfg.speed_multiplier == 10.0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_path_sampling_is_deterministic():
    m = _coord_mission(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0),
    )
    path = build_camera_path(m)
    a = path.sample(0.37)
    b = path.sample(0.37)
    assert a.x == b.x and a.y == b.y and a.z == b.z


# ---------------------------------------------------------------------------
# Epoch interpolation
# ---------------------------------------------------------------------------


def test_epoch_interpolates_when_both_endpoints_present():
    m = _coord_mission(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0),
        epochs=[2451545.0, 2461041.5],
    )
    path = build_camera_path(m)
    mid = path.sample(0.5)
    expected = 0.5 * (2451545.0 + 2461041.5)
    assert mid.epoch_jd == pytest.approx(expected, rel=1e-3)


def test_epoch_falls_through_when_intermediate_waypoint_missing():
    """Waypoint without explicit epoch inherits the previous
    waypoint's epoch."""
    m = _coord_mission(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (20.0, 0.0, 0.0),
        epochs=[2451545.0, None, 2461041.5],
    )
    path = build_camera_path(m)
    # Second waypoint should hold epoch from the first.
    assert path.epochs[1] == pytest.approx(2451545.0)
    assert path.epochs[2] == pytest.approx(2461041.5)


def test_include_epoch_false_clears_path_epochs():
    m = _coord_mission(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0),
        epochs=[2451545.0, 2461041.5],
    )
    path = build_camera_path(m, CameraPathConfig(include_epoch=False))
    for ep in path.epochs:
        assert ep is None


# ---------------------------------------------------------------------------
# Orientation
# ---------------------------------------------------------------------------


def test_synthesised_orientation_is_unit_quaternion():
    m = _coord_mission((0.0, 0.0, 0.0), (10.0, 0.0, 0.0))
    path = build_camera_path(m)
    for q in path.orientations:
        n = math.sqrt(sum(c * c for c in q))
        assert n == pytest.approx(1.0, abs=1e-6)


def test_explicit_orientation_is_used_verbatim():
    custom = (0.7071, 0.0, 0.7071, 0.0)
    m = Mission(waypoints=[
        MissionWaypoint(
            kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
            orientation_quat=custom,
        ),
        MissionWaypoint(
            kind="coordinate", x_c4d=1.0, y_c4d=0.0, z_c4d=0.0,
        ),
    ])
    path = build_camera_path(m)
    # Normalised but should be very close to the input.
    for a, b in zip(path.orientations[0], custom):
        assert a == pytest.approx(b, abs=1e-3)


# ---------------------------------------------------------------------------
# Route preview
# ---------------------------------------------------------------------------


def test_build_route_from_mission_drops_unpositioned_waypoints():
    m = Mission(waypoints=[
        MissionWaypoint(kind="object", uid="x:1"),  # unresolved
        MissionWaypoint(
            kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
        ),
        MissionWaypoint(
            kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
        ),
    ])
    route = build_route_from_mission(m)
    assert len(route) == 2
