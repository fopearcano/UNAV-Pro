"""v2.2 ``Playback.evaluate_at_frame`` / ``evaluate_at_seconds``
tests + ``bake_mission_to_timeline`` end-to-end."""

from __future__ import annotations

import math

import pytest

from c4d_objects.timeline_keys import (
    BakeRange,
    bake_mission_to_timeline,
)
from voyage import Mission, MissionWaypoint, build_camera_path, make_playback


def _two_wp_path():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        duration_seconds=2.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
                        duration_seconds=2.0),
    ])
    return m, build_camera_path(m), make_playback(m)


# ---------------------------------------------------------------------------
# Playback.evaluate_at_frame
# ---------------------------------------------------------------------------


def test_evaluate_at_frame_endpoints():
    m, p, pb = _two_wp_path()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    a = pb.evaluate_at_frame(0, fr)
    b = pb.evaluate_at_frame(99, fr)
    assert (a.x, a.y, a.z) == pytest.approx((0.0, 0.0, 0.0))
    assert (b.x, b.y, b.z) == pytest.approx((10.0, 0.0, 0.0))


def test_evaluate_at_frame_clamps():
    m, p, pb = _two_wp_path()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    a = pb.evaluate_at_frame(-100, fr)
    b = pb.evaluate_at_frame(99999, fr)
    assert (a.x, a.y, a.z) == pytest.approx((0.0, 0.0, 0.0))
    assert (b.x, b.y, b.z) == pytest.approx((10.0, 0.0, 0.0))


def test_evaluate_at_frame_does_not_move_cursor():
    m, p, pb = _two_wp_path()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    pb.step_forward(n=10)
    cursor = pb.step
    pb.evaluate_at_frame(50, fr)
    assert pb.step == cursor


def test_evaluate_at_seconds_consistent_with_at_frame():
    m, p, pb = _two_wp_path()
    fr = BakeRange(start_frame=0, end_frame=240, fps=30)
    a = pb.evaluate_at_frame(60, fr)
    b = pb.evaluate_at_seconds(2.0, fr)
    assert (a.x, a.y, a.z) == (b.x, b.y, b.z)


def test_evaluate_at_frame_empty_path():
    pb = make_playback(Mission())
    fr = BakeRange(start_frame=0, end_frame=10, fps=30)
    sample = pb.evaluate_at_frame(5, fr)
    assert sample.x == 0.0
    assert sample.y == 0.0


# ---------------------------------------------------------------------------
# bake_mission_to_timeline (no c4d)
# ---------------------------------------------------------------------------


def test_bake_returns_timeline_outside_c4d():
    """No Cinema 4D → keys + markers written are 0, but the
    pure-Python ``timeline`` is still produced so callers can
    inspect counts + warnings."""
    m, p, _ = _two_wp_path()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    timeline, keys, markers = bake_mission_to_timeline(
        m, p, frame_range=fr,
    )
    assert keys == 0  # no c4d available
    assert markers == 0
    assert len(timeline.samples) == 100


def test_bake_empty_path_returns_zero():
    m = Mission()
    p = build_camera_path(m)
    timeline, keys, markers = bake_mission_to_timeline(m, p)
    assert keys == 0
    assert markers == 0
    assert timeline.is_empty()


def test_bake_threads_through_fov():
    from animation import AnimatedStateConfig
    m, p, _ = _two_wp_path()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    cfg = AnimatedStateConfig(fov_rad=math.radians(50))
    timeline, _, _ = bake_mission_to_timeline(
        m, p, frame_range=fr, config=cfg,
    )
    for k in timeline.keyframes:
        assert k.fov_rad == pytest.approx(math.radians(50))


def test_bake_apply_markers_to_doc_false_skips_marker_pass():
    m, p, _ = _two_wp_path()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    timeline, _, markers = bake_mission_to_timeline(
        m, p, frame_range=fr, apply_markers_to_doc=False,
    )
    assert markers == 0
    # The timeline still carries the per-waypoint arrivals
    # so a later marker pass can use them.
    assert timeline.waypoint_arrival_frames


# ---------------------------------------------------------------------------
# Idempotency contract
# ---------------------------------------------------------------------------


def test_bake_is_deterministic():
    m, p, _ = _two_wp_path()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    a, _, _ = bake_mission_to_timeline(m, p, frame_range=fr)
    b, _, _ = bake_mission_to_timeline(m, p, frame_range=fr)
    assert len(a.samples) == len(b.samples)
    for sa, sb in zip(a.samples, b.samples):
        assert sa.camera_position == sb.camera_position
        assert sa.rotation_hpb == sb.rotation_hpb
