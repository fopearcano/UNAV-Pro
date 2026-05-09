"""v2.2 animated state evaluator tests."""

from __future__ import annotations

import math

import pytest

from animation import (
    AnimatedSample,
    AnimatedStateConfig,
    AnimatedTimeline,
    evaluate_animated_state,
    evaluate_at_frame,
    evaluate_at_seconds,
    frame_to_progress,
    frame_to_seconds,
    seconds_to_frame,
)
from c4d_objects.timeline_keys import BakeRange
from voyage import Mission, MissionWaypoint, build_camera_path


def _two_wp_mission(*, with_epochs=False, with_offset=False):
    waypoints = [
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        label="A", duration_seconds=2.0,
                        epoch_jd=2451545.0 if with_epochs else None),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
                        label="B", duration_seconds=2.0,
                        epoch_jd=2461041.5 if with_epochs else None,
                        camera_offset=(2.0, 0.0, 0.0) if with_offset else None),
    ]
    m = Mission(waypoints=waypoints)
    return m, build_camera_path(m)


def _three_wp_mission():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        label="A", duration_seconds=2.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
                        label="B", duration_seconds=2.0,
                        epoch_jd=2451545.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=10.0, z_c4d=0.0,
                        label="C", duration_seconds=2.0,
                        epoch_jd=2461041.5),
    ])
    return m, build_camera_path(m)


# ---------------------------------------------------------------------------
# Frame ↔ time conversions
# ---------------------------------------------------------------------------


def test_frame_to_seconds_basic():
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    assert frame_to_seconds(0, fr) == 0.0
    assert frame_to_seconds(30, fr) == 1.0
    assert frame_to_seconds(99, fr) == pytest.approx(99 / 30.0)


def test_frame_to_seconds_with_offset_start():
    fr = BakeRange(start_frame=24, end_frame=119, fps=24)
    assert frame_to_seconds(24, fr) == 0.0
    assert frame_to_seconds(48, fr) == 1.0


def test_seconds_to_frame_inverts():
    fr = BakeRange(start_frame=0, end_frame=240, fps=30)
    assert seconds_to_frame(0.0, fr) == 0
    assert seconds_to_frame(2.0, fr) == 60
    # Round-trip.
    for f in (0, 30, 90, 240):
        assert seconds_to_frame(frame_to_seconds(f, fr), fr) == f


def test_frame_to_progress_clamps():
    fr = BakeRange(start_frame=0, end_frame=100, fps=30)
    assert frame_to_progress(-5, fr) == 0.0
    assert frame_to_progress(200, fr) == 1.0
    assert frame_to_progress(50, fr) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# evaluate_animated_state — basic shape
# ---------------------------------------------------------------------------


def test_animated_timeline_count_matches_frame_range():
    m, p = _two_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=49, fps=25)
    tl = evaluate_animated_state(m, p, frame_range=fr)
    assert len(tl.samples) == 50
    assert len(tl.keyframes) == 50


def test_animated_timeline_endpoints_match_path_endpoints():
    m, p = _two_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    tl = evaluate_animated_state(m, p, frame_range=fr)
    assert tl.samples[0].camera_position == pytest.approx((0.0, 0.0, 0.0))
    assert tl.samples[-1].camera_position == pytest.approx((10.0, 0.0, 0.0))


def test_empty_mission_returns_empty_timeline():
    m = Mission()
    p = build_camera_path(m)
    tl = evaluate_animated_state(m, p)
    assert tl.is_empty()
    assert any("≥ 2 resolvable waypoints" in w for w in tl.warnings)


def test_single_wp_mission_returns_empty_timeline():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
    ])
    p = build_camera_path(m)
    tl = evaluate_animated_state(m, p)
    assert tl.is_empty()


# ---------------------------------------------------------------------------
# Waypoint-arrival frames
# ---------------------------------------------------------------------------


def test_waypoint_arrival_frames_match_path_anchors():
    m, p = _three_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    tl = evaluate_animated_state(m, p, frame_range=fr)
    # Path has 3 waypoints with equal duration → anchors at
    # 0, ~50, 100.
    assert tl.waypoint_arrival_frames[0] == 0
    assert tl.waypoint_arrival_frames[-1] == 99
    assert len(tl.waypoint_arrival_frames) == 3


def test_waypoint_arrival_frames_starts_with_start_frame():
    m, p = _two_wp_mission()
    fr = BakeRange(start_frame=24, end_frame=120, fps=24)
    tl = evaluate_animated_state(m, p, frame_range=fr)
    assert tl.waypoint_arrival_frames[0] == 24


# ---------------------------------------------------------------------------
# Sync markers
# ---------------------------------------------------------------------------


def test_sync_markers_default_includes_waypoint_arrivals():
    m, p = _three_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    tl = evaluate_animated_state(m, p, frame_range=fr)
    # waypoint_arrival_markers=True by default.
    assert set(tl.waypoint_arrival_frames).issubset(set(tl.sync_marker_frames))


def test_sync_markers_explicit_list_added():
    m, p = _three_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    cfg = AnimatedStateConfig(sync_markers=[10, 20, 30])
    tl = evaluate_animated_state(m, p, frame_range=fr, config=cfg)
    assert {10, 20, 30}.issubset(set(tl.sync_marker_frames))


def test_sync_markers_dedup_and_sorted():
    m, p = _two_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    cfg = AnimatedStateConfig(sync_markers=[50, 10, 50, 99])
    tl = evaluate_animated_state(m, p, frame_range=fr, config=cfg)
    assert tl.sync_marker_frames == sorted(set(tl.sync_marker_frames))


def test_sync_markers_disable_waypoint_default():
    m, p = _three_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    cfg = AnimatedStateConfig(sync_markers=[40], waypoint_arrival_markers=False)
    tl = evaluate_animated_state(m, p, frame_range=fr, config=cfg)
    assert tl.sync_marker_frames == [40]


def test_sync_marker_warning_when_too_many():
    m, p = _two_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    cfg = AnimatedStateConfig(sync_markers=list(range(100)))
    tl = evaluate_animated_state(m, p, frame_range=fr, config=cfg)
    assert any("sync markers scheduled" in w for w in tl.warnings)


def test_samples_carry_is_sync_marker_flag():
    m, p = _two_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    cfg = AnimatedStateConfig(sync_markers=[10, 50])
    tl = evaluate_animated_state(m, p, frame_range=fr, config=cfg)
    for s in tl.samples:
        if s.frame in (10, 50, 0, 99):  # explicit + endpoints
            assert s.is_sync_marker is True


# ---------------------------------------------------------------------------
# Epoch change frames
# ---------------------------------------------------------------------------


def test_epoch_change_frames_at_waypoint_granularity():
    """With three waypoints at distinct epochs, the change
    frames sit at the waypoint anchors (not every frame
    within a segment)."""
    m, p = _three_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    tl = evaluate_animated_state(m, p, frame_range=fr)
    # Three waypoint anchors → at most three epoch-change
    # frames (the first waypoint with no epoch is skipped).
    assert all(f in tl.waypoint_arrival_frames for f in tl.epoch_change_frames)
    assert len(tl.epoch_change_frames) <= 3


def test_no_epoch_change_when_no_epochs():
    m, p = _two_wp_mission(with_epochs=False)
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    tl = evaluate_animated_state(m, p, frame_range=fr)
    assert tl.epoch_change_frames == []


# ---------------------------------------------------------------------------
# FOV
# ---------------------------------------------------------------------------


def test_fov_propagates_to_keyframes_when_set():
    m, p = _two_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=10, fps=30)
    cfg = AnimatedStateConfig(fov_rad=math.radians(60))
    tl = evaluate_animated_state(m, p, frame_range=fr, config=cfg)
    for k in tl.keyframes:
        assert k.fov_rad == pytest.approx(math.radians(60))


def test_fov_absent_by_default():
    m, p = _two_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=10, fps=30)
    tl = evaluate_animated_state(m, p, frame_range=fr)
    for k in tl.keyframes:
        assert k.fov_rad is None


# ---------------------------------------------------------------------------
# Camera offset → navigator vs camera position split
# ---------------------------------------------------------------------------


def test_camera_offset_separates_nav_and_cam_positions():
    m, p = _two_wp_mission(with_offset=True)
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    cfg = AnimatedStateConfig(apply_camera_offset_to_navigator=True)
    tl = evaluate_animated_state(m, p, frame_range=fr, config=cfg)
    # Last frame: camera includes the offset (+2 on x); the
    # navigator position is the camera position minus the
    # offset.
    last = tl.samples[-1]
    assert last.camera_position[0] != last.navigator_position[0]


def test_camera_offset_disabled_keeps_positions_identical():
    m, p = _two_wp_mission(with_offset=True)
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    cfg = AnimatedStateConfig(apply_camera_offset_to_navigator=False)
    tl = evaluate_animated_state(m, p, frame_range=fr, config=cfg)
    for s in tl.samples:
        assert s.navigator_position == s.camera_position


# ---------------------------------------------------------------------------
# Single-frame read API
# ---------------------------------------------------------------------------


def test_evaluate_at_frame_clamps():
    m, p = _two_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    a = evaluate_at_frame(m, p, -10, frame_range=fr)
    b = evaluate_at_frame(m, p, 200, frame_range=fr)
    assert a.frame == 0
    assert b.frame == 99


def test_evaluate_at_frame_returns_none_for_empty_path():
    m = Mission()
    p = build_camera_path(m)
    assert evaluate_at_frame(m, p, 0) is None


def test_evaluate_at_seconds_aligns_with_evaluate_at_frame():
    m, p = _two_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=240, fps=30)
    a = evaluate_at_frame(m, p, 60, frame_range=fr)
    b = evaluate_at_seconds(m, p, 2.0, frame_range=fr)
    assert a.frame == b.frame
    assert a.camera_position == b.camera_position


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_animated_state_is_deterministic():
    m, p = _three_wp_mission()
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    cfg = AnimatedStateConfig(sync_markers=[15, 60])
    a = evaluate_animated_state(m, p, frame_range=fr, config=cfg)
    b = evaluate_animated_state(m, p, frame_range=fr, config=cfg)
    assert len(a.samples) == len(b.samples)
    for sa, sb in zip(a.samples, b.samples):
        assert sa.camera_position == sb.camera_position
        assert sa.rotation_hpb == sb.rotation_hpb
        assert sa.epoch_jd == sb.epoch_jd
    assert a.sync_marker_frames == b.sync_marker_frames
    assert a.epoch_change_frames == b.epoch_change_frames
