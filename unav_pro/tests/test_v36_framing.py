"""v3.6 framing tests."""

from __future__ import annotations

import math

import pytest

from cinematic import (
    DEFAULT_HORIZONTAL_FOV_DEG,
    FRAMING_PRESETS,
    IDENTITY_QUAT,
    PRESET_TABLE,
    CameraPose,
    FramingPreset,
    WaypointFraming,
    blend_look_at,
    compose_look_at_pose,
    framing_distance_for_subject_size,
    look_at_quaternion,
    parameters_for,
)


# ---------------------------------------------------------------------------
# Preset table
# ---------------------------------------------------------------------------


def test_framing_presets_complete():
    expected = {
        FramingPreset.CLOSE, FramingPreset.MEDIUM,
        FramingPreset.WIDE, FramingPreset.EXTREME_WIDE,
        FramingPreset.EXTREME_SCALE,
    }
    assert expected == set(FRAMING_PRESETS)


def test_preset_table_covers_every_preset():
    for preset in FramingPreset:
        assert preset in PRESET_TABLE


def test_preset_apparent_fractions_decrease_in_size():
    """CLOSE should be biggest; EXTREME_SCALE should
    be tiniest."""
    fractions = [
        PRESET_TABLE[p].apparent_angular_fraction
        for p in (
            FramingPreset.CLOSE, FramingPreset.MEDIUM,
            FramingPreset.WIDE, FramingPreset.EXTREME_WIDE,
            FramingPreset.EXTREME_SCALE,
        )
    ]
    assert fractions == sorted(fractions, reverse=True)


def test_parameters_for_close():
    params = parameters_for(FramingPreset.CLOSE)
    assert params.name is FramingPreset.CLOSE
    assert params.apparent_angular_fraction > 0.5


def test_parameters_for_unknown_raises():
    with pytest.raises(KeyError):
        parameters_for("not_a_preset")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# framing_distance_for_subject_size
# ---------------------------------------------------------------------------


def test_framing_distance_positive():
    d = framing_distance_for_subject_size(
        subject_extent=1.0,
        camera_horizontal_fov_deg=36.0,
        preset=FramingPreset.MEDIUM,
    )
    assert d > 0


def test_framing_distance_close_smaller_than_wide():
    """Filling more of the frame requires the camera
    to be closer."""
    d_close = framing_distance_for_subject_size(
        subject_extent=10.0,
        preset=FramingPreset.CLOSE,
    )
    d_wide = framing_distance_for_subject_size(
        subject_extent=10.0,
        preset=FramingPreset.WIDE,
    )
    assert d_close < d_wide


def test_framing_distance_zero_extent_raises():
    with pytest.raises(ValueError):
        framing_distance_for_subject_size(
            subject_extent=0.0,
            preset=FramingPreset.MEDIUM,
        )


def test_framing_distance_invalid_fov_raises():
    with pytest.raises(ValueError):
        framing_distance_for_subject_size(
            subject_extent=1.0,
            camera_horizontal_fov_deg=0.0,
        )
    with pytest.raises(ValueError):
        framing_distance_for_subject_size(
            subject_extent=1.0,
            camera_horizontal_fov_deg=180.0,
        )


def test_framing_distance_clamps_at_minimum():
    """A tiny subject can't push the camera below the
    preset's min_distance."""
    d = framing_distance_for_subject_size(
        subject_extent=0.001,
        preset=FramingPreset.CLOSE,
    )
    assert d >= parameters_for(FramingPreset.CLOSE).min_distance


def test_framing_distance_first_principles_math():
    """Sanity check the trig: at 36° FOV with the
    CLOSE preset (60% of frame), a 1-pc subject
    should land at roughly d = 0.5 / tan((0.6 * 36)/2 °)."""
    d = framing_distance_for_subject_size(
        subject_extent=1.0,
        camera_horizontal_fov_deg=36.0,
        preset=FramingPreset.CLOSE,
    )
    expected = 0.5 / math.tan(math.radians(0.6 * 36.0 / 2.0))
    assert math.isclose(d, expected, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# look_at_quaternion
# ---------------------------------------------------------------------------


def test_look_at_quaternion_returns_4_tuple():
    q = look_at_quaternion(
        camera_position=(0, 0, 100),
        target=(0, 0, 0),
    )
    assert len(q) == 4
    # Quaternion should be unit-length.
    norm = math.sqrt(sum(c * c for c in q))
    assert math.isclose(norm, 1.0, rel_tol=1e-6)


def test_look_at_quaternion_identity_for_degenerate():
    """Camera + target coincide ⇒ identity quat."""
    q = look_at_quaternion(
        camera_position=(0, 0, 0),
        target=(0, 0, 0),
    )
    assert q == IDENTITY_QUAT


def test_look_at_quaternion_handles_world_up_parallel():
    """Forward parallel to world_up should not crash;
    helper picks a stable alternative."""
    q = look_at_quaternion(
        camera_position=(0, 100, 0),
        target=(0, 0, 0),
        world_up=(0, 1, 0),
    )
    assert len(q) == 4


# ---------------------------------------------------------------------------
# compose_look_at_pose
# ---------------------------------------------------------------------------


def test_compose_look_at_pose_with_explicit_position():
    pose = compose_look_at_pose(
        target=(0, 0, 0),
        camera_position=(0, 0, 100),
    )
    assert isinstance(pose, CameraPose)
    assert pose.target == (0, 0, 0)
    assert pose.position == (0, 0, 100)


def test_compose_look_at_pose_with_subject_extent():
    pose = compose_look_at_pose(
        target=(0, 0, 0),
        subject_extent=2.0,
        preset=FramingPreset.MEDIUM,
    )
    assert pose.position[2] != 0  # pulled back along default Z axis


def test_compose_look_at_requires_position_or_extent():
    with pytest.raises(ValueError):
        compose_look_at_pose(target=(0, 0, 0))


def test_compose_look_at_target_offset_applied():
    pose = compose_look_at_pose(
        target=(0, 0, 0),
        camera_position=(0, 0, 100),
        target_offset=(5.0, 0.0, 0.0),
    )
    assert pose.target[0] == 5.0


def test_compose_look_at_includes_fov():
    pose = compose_look_at_pose(
        target=(0, 0, 0),
        camera_position=(0, 0, 100),
        camera_horizontal_fov_deg=24.0,
    )
    assert pose.fov_deg == 24.0


def test_camera_pose_look_direction_normalized():
    pose = CameraPose(
        position=(0, 0, 0), target=(10, 0, 0),
    )
    direction = pose.look_direction()
    assert math.isclose(
        math.sqrt(sum(c * c for c in direction)),
        1.0, rel_tol=1e-6,
    )


def test_camera_pose_look_direction_degenerate():
    pose = CameraPose(position=(0, 0, 0), target=(0, 0, 0))
    direction = pose.look_direction()
    assert direction == (0.0, 0.0, 1.0)


# ---------------------------------------------------------------------------
# blend_look_at (slerp)
# ---------------------------------------------------------------------------


def test_blend_look_at_endpoint_zero():
    a = (1.0, 0.0, 0.0, 0.0)
    b = (0.7071, 0.7071, 0.0, 0.0)
    out = blend_look_at(a, b, 0.0)
    assert out == a


def test_blend_look_at_endpoint_one():
    a = (1.0, 0.0, 0.0, 0.0)
    b = look_at_quaternion(
        camera_position=(0, 0, 100), target=(0, 50, 0),
    )
    out = blend_look_at(a, b, 1.0)
    # Should renormalise to b.
    for ai, bi in zip(out, b):
        assert math.isclose(ai, bi, abs_tol=1e-6)


def test_blend_look_at_clamps_t():
    a = (1.0, 0.0, 0.0, 0.0)
    b = (0.0, 1.0, 0.0, 0.0)
    out_low = blend_look_at(a, b, -1.0)
    assert out_low == a
    out_high = blend_look_at(a, b, 5.0)
    # b normalised
    assert math.isclose(sum(c * c for c in out_high), 1.0, rel_tol=1e-6)


def test_blend_look_at_handles_near_parallel():
    """Two near-parallel quaternions should blend
    without raising (the branch uses linear blend
    instead of slerp)."""
    a = (1.0, 0.0, 0.0, 0.0)
    b = (0.9999999, 1e-7, 0.0, 0.0)
    out = blend_look_at(a, b, 0.5)
    assert math.isclose(sum(c * c for c in out), 1.0, rel_tol=1e-4)


# ---------------------------------------------------------------------------
# WaypointFraming
# ---------------------------------------------------------------------------


def test_waypoint_framing_short_summary():
    f = WaypointFraming(
        waypoint_index=3, preset=FramingPreset.WIDE, fov_deg=24.0,
    )
    s = f.short_summary()
    assert "WP003" in s
    assert "wide" in s
    assert "24" in s


def test_waypoint_framing_default_preset():
    f = WaypointFraming(waypoint_index=0)
    assert f.preset is FramingPreset.MEDIUM


def test_default_fov_is_documented():
    assert DEFAULT_HORIZONTAL_FOV_DEG == 36.0
