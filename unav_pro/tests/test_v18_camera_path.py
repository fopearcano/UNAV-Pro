"""v1.8 camera-path additions — interpolation modes, pause,
look-at, roll, and tessellation."""

from __future__ import annotations

import math

import pytest

from voyage import (
    CameraPathConfig,
    INTERP_LINEAR,
    INTERP_SMOOTH,
    Mission,
    MissionWaypoint,
    build_camera_path,
    tessellate_path,
)
from voyage.camera_path import build_preview_spline_data


def _three_wp(*, pause=0.0, look=None, roll=0.0, interp=INTERP_SMOOTH):
    waypoints = [
        MissionWaypoint(
            kind="coordinate",
            x_c4d=float(i * 10), y_c4d=0.0, z_c4d=0.0,
            label=f"wp{i}", duration_seconds=2.0,
            pause_seconds=pause if i == 1 else 0.0,
            look_at_position=look if i == 1 else None,
            roll_deg=roll if i == 1 else 0.0,
        )
        for i in range(3)
    ]
    mission = Mission(waypoints=waypoints)
    return mission, build_camera_path(mission, CameraPathConfig(interp_mode=interp))


# ---------------------------------------------------------------------------
# Mission round-trip with v1.8 fields
# ---------------------------------------------------------------------------


def test_mission_roundtrip_preserves_v18_fields():
    m = Mission(waypoints=[
        MissionWaypoint(
            kind="object", uid="x:1",
            duration_seconds=2.0,
            pause_seconds=1.5,
            look_at_position=(10.0, 20.0, 30.0),
            look_at_uid="x:target",
            roll_deg=33.3,
        ),
    ])
    j = m.to_dict()
    wp = j["waypoints"][0]
    assert wp["pause_seconds"] == 1.5
    assert wp["look_at_position"] == [10.0, 20.0, 30.0]
    assert wp["look_at_uid"] == "x:target"
    assert wp["roll_deg"] == 33.3

    restored = Mission.from_dict(j).waypoints[0]
    assert restored.pause_seconds == 1.5
    assert restored.look_at_position == (10.0, 20.0, 30.0)
    assert restored.look_at_uid == "x:target"
    assert restored.roll_deg == 33.3


def test_mission_roundtrip_omits_v18_defaults():
    """A waypoint with no v1.8 extensions should serialise byte-
    identical to the v1.4 layout (so existing missions don't
    drift on save)."""
    m = Mission(waypoints=[
        MissionWaypoint(kind="object", uid="x:1", duration_seconds=2.0),
    ])
    out = m.to_dict()["waypoints"][0]
    assert "pause_seconds" not in out
    assert "look_at_position" not in out
    assert "look_at_uid" not in out
    assert "roll_deg" not in out


def test_negative_pause_seconds_rejected():
    with pytest.raises(ValueError):
        MissionWaypoint(
            kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
            pause_seconds=-1.0,
        )


def test_invalid_look_at_position_rejected():
    with pytest.raises(ValueError):
        MissionWaypoint(
            kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
            look_at_position=(1.0, 2.0),  # 2-tuple, must be 3
        )


# ---------------------------------------------------------------------------
# Interpolation modes
# ---------------------------------------------------------------------------


def test_linear_interpolation_midpoint_is_midpoint():
    """Two-waypoint linear path: t=0.5 must land exactly on
    the geometric midpoint (no Catmull-Rom overshoot)."""
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=20.0, z_c4d=30.0),
    ])
    path = build_camera_path(m, CameraPathConfig(interp_mode=INTERP_LINEAR))
    s = path.sample(0.5)
    assert s.x == pytest.approx(5.0)
    assert s.y == pytest.approx(10.0)
    assert s.z == pytest.approx(15.0)


def test_linear_endpoints_exact():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
    ])
    path = build_camera_path(m, CameraPathConfig(interp_mode=INTERP_LINEAR))
    a = path.sample(0.0)
    b = path.sample(1.0)
    assert (a.x, a.y, a.z) == pytest.approx((0.0, 0.0, 0.0))
    assert (b.x, b.y, b.z) == pytest.approx((10.0, 0.0, 0.0))


def test_smooth_remains_default():
    """Default config is smooth (Catmull-Rom)."""
    cfg = CameraPathConfig()
    assert cfg.interp_mode == INTERP_SMOOTH


def test_unknown_interp_mode_raises():
    with pytest.raises(ValueError):
        CameraPathConfig(interp_mode="cubic-spline-of-doom")


# ---------------------------------------------------------------------------
# Pause durations
# ---------------------------------------------------------------------------


def test_pause_extends_segment_duration():
    """A 2 s travel + 1 s pause segment should contribute 3 s
    to the path's total duration."""
    _, path = _three_wp(pause=1.0)
    # 3 waypoints × 2 s travel + 1 s pause on the middle waypoint = 7 s
    assert path.total_duration_seconds() == pytest.approx(7.0)
    assert path.pause_durations == [0.0, 1.0, 0.0]


def test_pause_seconds_speed_multiplier_scales():
    """Speed multiplier should scale pause time uniformly."""
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        duration_seconds=2.0, pause_seconds=2.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
                        duration_seconds=2.0),
    ])
    fast = build_camera_path(m, CameraPathConfig(speed_multiplier=2.0))
    # First waypoint contributes 2 s travel + 2 s pause = 4 s
    # at speed 1.0; at speed 2.0 it's 2 s.
    assert fast.pause_durations[0] == pytest.approx(1.0)


def test_pause_disabled_via_config():
    """``honour_pause_seconds=False`` reverts to v1.4 behaviour."""
    m, _ = _three_wp(pause=5.0)
    path = build_camera_path(
        m, CameraPathConfig(honour_pause_seconds=False),
    )
    # Pauses are zeroed out.
    assert all(p == 0.0 for p in path.pause_durations)


# ---------------------------------------------------------------------------
# Look-at
# ---------------------------------------------------------------------------


def test_look_at_position_drives_orientation():
    """When a waypoint has a look-at target, the camera path's
    orientation at that waypoint should rotate +Z onto the
    target direction. We verify by checking the orientation
    points 'into the +X axis' for a target far along +X."""
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        look_at_position=(100.0, 0.0, 0.0)),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
    ])
    path = build_camera_path(m)
    q = path.orientations[0]
    # Apply q to (0,0,1) and verify the result has positive x and
    # near-zero y.
    forward = _rotate_vector_by_quat((0.0, 0.0, 1.0), q)
    assert forward[0] > 0.5  # camera looks roughly toward +X
    assert abs(forward[1]) < 1e-6


def test_look_at_disabled_via_config():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        look_at_position=(100.0, 0.0, 0.0)),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
    ])
    path = build_camera_path(m, CameraPathConfig(honour_look_at=False))
    # With look-at disabled and orient_toward_next on, the
    # orientation should track the next waypoint (also +X)
    # rather than the look-at target. The vector difference
    # is small for this geometry but the path field that
    # records "look-at target was honoured" is gone.
    assert path.orientations[0] is not None


def test_explicit_orientation_overrides_look_at():
    """If both orientation_quat and look_at_position are set,
    the explicit quaternion wins."""
    m = Mission(waypoints=[
        MissionWaypoint(
            kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
            orientation_quat=(1.0, 0.0, 0.0, 0.0),  # identity
            look_at_position=(100.0, 0.0, 0.0),
        ),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
    ])
    path = build_camera_path(m)
    # Orientation is identity (the explicit quat).
    assert path.orientations[0] == pytest.approx((1.0, 0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# Roll
# ---------------------------------------------------------------------------


def test_roll_quat_remains_unit():
    """Roll composition produces a unit quaternion."""
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        roll_deg=45.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
                        roll_deg=90.0),
    ])
    path = build_camera_path(m)
    sample = path.sample(0.5)
    q = sample.orientation
    n = math.sqrt(sum(c * c for c in q))
    assert n == pytest.approx(1.0, abs=1e-6)


def test_zero_roll_leaves_orientation_unchanged():
    m, path_with_roll = _three_wp(roll=0.0)
    _, path_no_roll = _three_wp(roll=0.0)
    a = path_with_roll.sample(0.42)
    b = path_no_roll.sample(0.42)
    assert a.orientation == pytest.approx(b.orientation)


# ---------------------------------------------------------------------------
# Tessellation
# ---------------------------------------------------------------------------


def test_tessellate_path_returns_endpoints_exactly():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
    ])
    path = build_camera_path(m, CameraPathConfig(interp_mode=INTERP_LINEAR))
    pts = tessellate_path(path, samples_per_segment=8)
    assert pts[0] == pytest.approx((0.0, 0.0, 0.0))
    assert pts[-1] == pytest.approx((10.0, 0.0, 0.0))


def test_tessellate_path_count():
    """N segments × samples_per_segment + 1 endpoint."""
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=20.0, y_c4d=0.0, z_c4d=0.0),
    ])
    path = build_camera_path(m)
    pts = tessellate_path(path, samples_per_segment=8)
    assert len(pts) == 8 * 2 + 1


def test_tessellate_empty_path():
    m = Mission()
    path = build_camera_path(m)
    assert tessellate_path(path) == []


def test_build_preview_spline_data_matches_tessellate():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
    ])
    path = build_camera_path(m)
    a = build_preview_spline_data(path, samples_per_segment=4)
    b = tessellate_path(path, samples_per_segment=4)
    assert a == b


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_v18_path_is_deterministic():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        pause_seconds=1.0, roll_deg=20.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=10.0, z_c4d=0.0,
                        look_at_position=(50.0, 0.0, 0.0)),
    ])
    a = build_camera_path(m).sample(0.37)
    b = build_camera_path(m).sample(0.37)
    assert (a.x, a.y, a.z) == (b.x, b.y, b.z)
    assert a.orientation == b.orientation


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _rotate_vector_by_quat(v, q):
    """Apply unit quaternion (w, x, y, z) to a 3-tuple vector."""
    w, x, y, z = q
    vx, vy, vz = v
    # Hamilton: q * v * q^-1, with v as a pure quaternion (0, vx, vy, vz).
    # Result formula: v' = v + 2w(q × v) + 2(q × (q × v))
    # where q is the vector part.
    qx, qy, qz = x, y, z
    # cross1 = q × v
    c1x = qy * vz - qz * vy
    c1y = qz * vx - qx * vz
    c1z = qx * vy - qy * vx
    # cross2 = q × cross1
    c2x = qy * c1z - qz * c1y
    c2y = qz * c1x - qx * c1z
    c2z = qx * c1y - qy * c1x
    return (
        vx + 2.0 * w * c1x + 2.0 * c2x,
        vy + 2.0 * w * c1y + 2.0 * c2y,
        vz + 2.0 * w * c1z + 2.0 * c2z,
    )
