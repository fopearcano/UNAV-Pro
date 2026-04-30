"""Tests for the v1.4 ``voyage.playback`` engine."""

from __future__ import annotations

import pytest

from voyage.camera_path import CameraPathConfig, build_camera_path
from voyage.mission import Mission, MissionWaypoint
from voyage.playback import (
    DEFAULT_MAX_VISIBLE_OBJECTS,
    Playback,
    PlaybackConfig,
    PlaybackTick,
    make_playback,
)


def _three_wp_mission(epochs=None, durations=(2.0, 2.0, 2.0)) -> Mission:
    epochs = epochs or [None, None, None]
    return Mission(waypoints=[
        MissionWaypoint(
            kind="coordinate",
            x_c4d=float(i * 10), y_c4d=0.0, z_c4d=0.0,
            label=f"wp{i}",
            duration_seconds=durations[i],
            epoch_jd=epochs[i],
        )
        for i in range(3)
    ])


# ---------------------------------------------------------------------------
# Construction / basic plumbing
# ---------------------------------------------------------------------------


def test_make_playback_produces_total_steps():
    pb = make_playback(_three_wp_mission())
    assert pb.total_steps > 0
    # Anchors should align with the three waypoints.
    assert len(pb.waypoint_step_anchors) == 3
    assert pb.waypoint_step_anchors[0] == 0
    assert pb.waypoint_step_anchors[-1] == pb.total_steps


def test_empty_mission_has_zero_steps():
    pb = make_playback(Mission())
    assert pb.total_steps == 0
    assert pb.advance() is None
    assert pb.play() is None


def test_single_resolved_waypoint_has_zero_steps():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
    ])
    pb = make_playback(m)
    assert pb.total_steps == 0


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


def test_play_flips_playing_flag():
    pb = make_playback(_three_wp_mission())
    assert not pb.is_playing
    pb.play()
    assert pb.is_playing
    pb.pause()
    assert not pb.is_playing


def test_step_forward_advances_cursor():
    pb = make_playback(_three_wp_mission())
    initial = pb.step
    tick = pb.step_forward(n=5)
    assert tick is not None
    assert pb.step == initial + 5
    assert tick.step == pb.step


def test_step_backward_clamps_at_zero():
    pb = make_playback(_three_wp_mission())
    tick = pb.step_backward(n=10)
    assert pb.step == 0
    assert tick.step == 0


def test_step_forward_clamps_at_total_and_finishes():
    pb = make_playback(_three_wp_mission())
    pb.step_forward(n=pb.total_steps + 5)
    assert pb.step == pb.total_steps
    assert pb.is_finished


def test_loop_wraps_around():
    pb = make_playback(
        _three_wp_mission(),
        config=PlaybackConfig(loop=True),
    )
    pb.step_forward(n=pb.total_steps + 3)
    # Loop wraps: 3 steps past end = 3 from start.
    assert pb.step == 3 % pb.total_steps


def test_jump_to_waypoint_moves_to_anchor():
    pb = make_playback(_three_wp_mission())
    tick = pb.jump_to_waypoint(2)
    assert tick.trigger_sync  # jumps always sync
    assert pb.step == pb.waypoint_step_anchors[2]


def test_jump_to_next_waypoint_after_partial_step():
    pb = make_playback(_three_wp_mission())
    pb.step_forward(n=5)
    tick = pb.jump_to_next_waypoint()
    # Should land on waypoint 1's anchor (next from current
    # step somewhere between wp0 and wp1).
    assert pb.step == pb.waypoint_step_anchors[1]


def test_jump_to_previous_waypoint_at_anchor_steps_back_one():
    pb = make_playback(_three_wp_mission())
    pb.jump_to_waypoint(2)
    pb.jump_to_previous_waypoint()
    assert pb.step == pb.waypoint_step_anchors[1]


def test_jump_to_previous_waypoint_mid_segment_rewinds_to_current_anchor():
    pb = make_playback(_three_wp_mission())
    # Move past wp1 anchor so we're mid-segment between wp1
    # and wp2.
    pb.step_forward(n=pb.waypoint_step_anchors[1] + 5)
    pb.jump_to_previous_waypoint()
    # "Previous" mid-segment rewinds to current waypoint anchor.
    assert pb.step == pb.waypoint_step_anchors[1]


def test_stop_resets_to_zero():
    pb = make_playback(_three_wp_mission())
    pb.step_forward(n=10)
    pb.stop()
    assert pb.step == 0
    assert not pb.is_playing


def test_advance_does_nothing_when_not_playing():
    pb = make_playback(_three_wp_mission())
    pb.step_forward(n=5)
    initial = pb.step
    pb.advance()
    assert pb.step == initial


def test_advance_ticks_when_playing():
    pb = make_playback(_three_wp_mission())
    pb.play()
    pb.advance()
    assert pb.step == 1


# ---------------------------------------------------------------------------
# Sync callback cadence
# ---------------------------------------------------------------------------


def test_sync_callback_fires_on_jump():
    seen = []
    pb = make_playback(
        _three_wp_mission(),
        sync_callback=lambda tick: seen.append(("jump", tick.step)),
    )
    pb.jump_to_waypoint(1)
    assert any(t == "jump" for t, _ in seen)


def test_sync_callback_fires_at_cadence():
    seen = []
    pb = make_playback(
        _three_wp_mission(),
        config=PlaybackConfig(sync_every_n_steps=3),
        sync_callback=lambda tick: seen.append(tick.step),
    )
    for _ in range(10):
        pb.step_forward(n=1)
    assert len(seen) >= 3


def test_apply_callback_fires_per_transport_call():
    """One apply per ``step_forward()`` call (the transport's
    integer ``n`` is consumed in a single move)."""
    seen = []
    pb = make_playback(
        _three_wp_mission(),
        apply=lambda tick: seen.append(tick.step),
    )
    pb.step_forward(n=1)
    pb.step_forward(n=1)
    pb.step_forward(n=1)
    assert seen == [1, 2, 3]


# ---------------------------------------------------------------------------
# Speed / safety
# ---------------------------------------------------------------------------


def test_set_speed_clamps_to_range():
    pb = make_playback(_three_wp_mission())
    pb.set_speed(0.001)
    # Clamps to 0.1.
    assert pb._config.speed_multiplier == 0.1
    pb.set_speed(100.0)
    assert pb._config.speed_multiplier == 10.0


def test_set_speed_zero_raises():
    pb = make_playback(_three_wp_mission())
    with pytest.raises(ValueError):
        pb.set_speed(0.0)


def test_default_max_visible_objects_in_config():
    cfg = PlaybackConfig()
    assert cfg.max_visible_objects == DEFAULT_MAX_VISIBLE_OBJECTS


# ---------------------------------------------------------------------------
# Epoch threading
# ---------------------------------------------------------------------------


def test_tick_carries_epoch_when_path_has_one():
    pb = make_playback(
        _three_wp_mission(epochs=[2451545.0, 2451545.0, 2461041.5]),
    )
    pb.step_forward(n=pb.total_steps // 2)
    last_tick = pb.step_forward(n=1)
    assert last_tick is not None
    assert last_tick.sample.epoch_jd is not None


def test_tick_epoch_none_when_disabled():
    from voyage.camera_path import CameraPathConfig
    pb = make_playback(
        _three_wp_mission(epochs=[2451545.0, None, 2461041.5]),
        path_config=CameraPathConfig(include_epoch=False),
    )
    tick = pb.step_forward(n=5)
    assert tick.sample.epoch_jd is None


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_playback_is_deterministic():
    a = make_playback(_three_wp_mission())
    b = make_playback(_three_wp_mission())
    for _ in range(20):
        ta = a.step_forward(n=3)
        tb = b.step_forward(n=3)
        assert ta.sample.x == tb.sample.x
        assert ta.sample.y == tb.sample.y
        assert ta.step == tb.step
