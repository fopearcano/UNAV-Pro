"""Tests for core.navigation_controller (v0.6 step movement)."""

from __future__ import annotations

import math

import pytest

from core.navigation_controller import (
    DEFAULT_STEP_DISTANCE_PC,
    MAX_STEP_DISTANCE_PC,
    MIN_STEP_DISTANCE_PC,
    NavigationController,
    StepSafetyReport,
    StepSpeed,
    check_step_safety,
    forward_from_yaw_pitch,
    step_position,
)


# ---------------------------------------------------------------------------
# StepSpeed
# ---------------------------------------------------------------------------


def test_step_speed_default():
    s = StepSpeed()
    assert s.step_distance_pc == DEFAULT_STEP_DISTANCE_PC
    assert s.acceleration == 1.0
    assert s.effective_step_pc == DEFAULT_STEP_DISTANCE_PC


def test_step_speed_rejects_zero_or_negative():
    with pytest.raises(ValueError):
        StepSpeed(step_distance_pc=0)
    with pytest.raises(ValueError):
        StepSpeed(step_distance_pc=-1)
    with pytest.raises(ValueError):
        StepSpeed(acceleration=0)


def test_step_speed_clamps_to_max():
    s = StepSpeed(step_distance_pc=1.0e9)
    assert s.step_distance_pc == MAX_STEP_DISTANCE_PC


def test_step_speed_clamps_to_min():
    s = StepSpeed(step_distance_pc=1.0e-12)
    assert s.step_distance_pc == MIN_STEP_DISTANCE_PC


def test_effective_step_with_acceleration():
    s = StepSpeed(step_distance_pc=2.0, acceleration=3.0)
    assert s.effective_step_pc == pytest.approx(6.0)


# ---------------------------------------------------------------------------
# step_position
# ---------------------------------------------------------------------------


def test_step_forward_moves_along_unit_vector():
    pos = step_position(
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
        StepSpeed(step_distance_pc=2.5),
    )
    assert pos == (2.5, 0.0, 0.0)


def test_step_backward_with_direction_minus_one():
    pos = step_position(
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
        StepSpeed(step_distance_pc=2.5),
        direction=-1,
    )
    assert pos == (-2.5, 0.0, 0.0)


def test_step_zero_forward_leaves_position_unchanged():
    pos = step_position(
        (1.0, 2.0, 3.0), (0.0, 0.0, 0.0),
        StepSpeed(),
    )
    assert pos == (1.0, 2.0, 3.0)


def test_step_normalizes_non_unit_forward():
    pos = step_position(
        (0.0, 0.0, 0.0), (3.0, 4.0, 0.0),
        StepSpeed(step_distance_pc=10.0),
    )
    # 3,4,0 has length 5; unit = (0.6, 0.8, 0); step 10 → (6, 8, 0).
    assert pos[0] == pytest.approx(6.0)
    assert pos[1] == pytest.approx(8.0)


def test_step_with_acceleration_multiplies_distance():
    pos = step_position(
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
        StepSpeed(step_distance_pc=1.0, acceleration=5.0),
    )
    assert pos == (5.0, 0.0, 0.0)


def test_negative_direction_steps_backward_regardless_of_magnitude():
    pos_a = step_position(
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), StepSpeed(step_distance_pc=1.0),
        direction=-3,
    )
    pos_b = step_position(
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), StepSpeed(step_distance_pc=1.0),
        direction=-1,
    )
    assert pos_a == pos_b == (-1.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# forward_from_yaw_pitch
# ---------------------------------------------------------------------------


def test_forward_at_zero_is_minus_z():
    fv = forward_from_yaw_pitch(0.0, 0.0)
    assert fv == pytest.approx((0.0, 0.0, -1.0))


def test_forward_yaw_90_is_minus_x():
    fv = forward_from_yaw_pitch(90.0, 0.0)
    assert fv[0] == pytest.approx(-1.0, abs=1e-9)
    assert abs(fv[1]) < 1e-9
    assert abs(fv[2]) < 1e-9


def test_forward_pitch_90_is_plus_y():
    fv = forward_from_yaw_pitch(0.0, 90.0)
    assert fv[1] == pytest.approx(1.0, abs=1e-9)
    assert abs(fv[2]) < 1e-9


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


def test_check_step_safety_in_range():
    r = check_step_safety(
        (10.0, 0.0, 0.0), near_clip_pc=0.0, far_clip_pc=100.0,
    )
    assert r.in_range
    assert r.proposed_distance_from_origin_pc == pytest.approx(10.0)


def test_check_step_safety_outside_far_clip():
    r = check_step_safety(
        (200.0, 0.0, 0.0), near_clip_pc=0.0, far_clip_pc=100.0,
    )
    assert not r.in_range
    assert "OUTSIDE" in r.short_summary()


# ---------------------------------------------------------------------------
# NavigationController
# ---------------------------------------------------------------------------


def test_controller_steps_forward_increments_counter():
    c = NavigationController()
    new_pos = c.step_forward((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    assert new_pos != (0.0, 0.0, 0.0)
    assert c.steps_taken == 1
    assert "forward" in c.last_summary


def test_controller_step_backward_increments_counter():
    c = NavigationController()
    c.step_backward((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    assert c.steps_taken == 1
    assert "backward" in c.last_summary


def test_controller_zero_forward_does_not_count_as_step():
    c = NavigationController()
    pos = c.step_forward((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    assert pos == (0.0, 0.0, 0.0)
    assert c.steps_taken == 0


def test_controller_set_speed_replaces_step_distance():
    c = NavigationController()
    c.set_speed(step_distance_pc=10.0, acceleration=2.0)
    assert c.speed.effective_step_pc == pytest.approx(20.0)


def test_controller_reset_clears_counter_and_summary():
    c = NavigationController()
    c.step_forward((0, 0, 0), (1, 0, 0))
    c.reset()
    assert c.steps_taken == 0
    assert c.last_summary == ""
