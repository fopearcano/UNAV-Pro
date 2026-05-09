"""v1.8 playback transport additions.

Covers:
* ``jump_to_start`` / ``jump_to_end``
* ``scrub_to_progress``
* ``evaluate_at_progress`` (pure read; cursor / play flag
  unchanged)
* ``progress`` property
"""

from __future__ import annotations

import pytest

from voyage import Mission, MissionWaypoint, make_playback


def _two_wp_path():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        duration_seconds=2.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
                        duration_seconds=2.0),
    ])
    return make_playback(m)


# ---------------------------------------------------------------------------
# Jump to start / end
# ---------------------------------------------------------------------------


def test_jump_to_start_resets_cursor():
    pb = _two_wp_path()
    pb.step_forward(n=20)
    assert pb.step > 0
    tick = pb.jump_to_start()
    assert tick is not None
    assert pb.step == 0
    assert tick.trigger_sync is True


def test_jump_to_start_does_not_flip_play_flag():
    pb = _two_wp_path()
    pb.play()
    assert pb.is_playing
    pb.jump_to_start()
    # The artist asked to rewind; they may still want to resume.
    assert pb.is_playing


def test_jump_to_end_snaps_to_total_steps():
    pb = _two_wp_path()
    tick = pb.jump_to_end()
    assert tick is not None
    assert pb.step == pb.total_steps
    assert tick.trigger_sync is True


def test_jump_to_end_clears_play_flag():
    """End-of-run terminates playback."""
    pb = _two_wp_path()
    pb.play()
    pb.jump_to_end()
    assert pb.is_playing is False


def test_jump_to_start_no_op_on_empty_path():
    pb = make_playback(Mission())
    assert pb.jump_to_start() is None
    assert pb.jump_to_end() is None


# ---------------------------------------------------------------------------
# Scrub
# ---------------------------------------------------------------------------


def test_scrub_to_progress_moves_cursor():
    pb = _two_wp_path()
    tick = pb.scrub_to_progress(0.5)
    assert tick is not None
    # Cursor lands at half of total_steps (rounded).
    assert pb.step == round(pb.total_steps * 0.5)


def test_scrub_to_progress_clamps_below_zero():
    pb = _two_wp_path()
    pb.scrub_to_progress(-0.5)
    assert pb.step == 0


def test_scrub_to_progress_clamps_above_one():
    pb = _two_wp_path()
    pb.scrub_to_progress(1.5)
    assert pb.step == pb.total_steps


def test_scrub_always_fires_sync():
    pb = _two_wp_path()
    tick = pb.scrub_to_progress(0.25)
    assert tick.trigger_sync is True


def test_scrub_no_op_on_empty_path():
    pb = make_playback(Mission())
    assert pb.scrub_to_progress(0.5) is None


# ---------------------------------------------------------------------------
# Progress property
# ---------------------------------------------------------------------------


def test_progress_starts_at_zero():
    pb = _two_wp_path()
    assert pb.progress == 0.0


def test_progress_after_step_forward():
    pb = _two_wp_path()
    pb.step_forward(n=10)
    assert 0.0 < pb.progress < 1.0


def test_progress_after_jump_to_end_is_one():
    pb = _two_wp_path()
    pb.jump_to_end()
    assert pb.progress == 1.0


def test_progress_after_scrub_matches_input():
    pb = _two_wp_path()
    pb.scrub_to_progress(0.4)
    # Rounding error is at most one step's worth.
    assert abs(pb.progress - 0.4) < 1.0 / pb.total_steps


# ---------------------------------------------------------------------------
# evaluate_at_progress — side-effect-free
# ---------------------------------------------------------------------------


def test_evaluate_at_progress_does_not_move_cursor():
    pb = _two_wp_path()
    pb.step_forward(n=5)
    cursor_before = pb.step
    sample = pb.evaluate_at_progress(0.9)
    assert pb.step == cursor_before  # cursor unchanged
    # And the returned sample reflects the requested progress.
    assert 8.0 < sample.x < 10.5  # roughly 90% of the way to (10, 0, 0)


def test_evaluate_at_progress_does_not_fire_apply():
    seen = []
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
    ])
    pb = make_playback(m, apply=lambda tick: seen.append(tick.step))
    sample = pb.evaluate_at_progress(0.5)
    assert seen == []  # apply was not called
    assert sample is not None


def test_evaluate_at_progress_does_not_fire_sync():
    seen = []
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
    ])
    pb = make_playback(
        m, sync_callback=lambda tick: seen.append(tick.step),
    )
    pb.evaluate_at_progress(0.5)
    assert seen == []


def test_evaluate_at_progress_clamps():
    pb = _two_wp_path()
    a = pb.evaluate_at_progress(-1.0)
    b = pb.evaluate_at_progress(0.0)
    assert (a.x, a.y) == (b.x, b.y)
    c = pb.evaluate_at_progress(2.0)
    d = pb.evaluate_at_progress(1.0)
    assert (c.x, c.y) == (d.x, d.y)


def test_evaluate_at_progress_returns_zero_pose_for_empty_path():
    pb = make_playback(Mission())
    sample = pb.evaluate_at_progress(0.5)
    assert sample.x == 0.0
    assert sample.y == 0.0
    assert sample.z == 0.0


def test_evaluate_at_progress_is_deterministic():
    pb = _two_wp_path()
    a = pb.evaluate_at_progress(0.42)
    b = pb.evaluate_at_progress(0.42)
    assert (a.x, a.y, a.z) == (b.x, b.y, b.z)
    assert a.orientation == b.orientation
