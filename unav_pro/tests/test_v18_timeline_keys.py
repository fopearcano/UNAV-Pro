"""v1.8 timeline-baking tests.

Pure-Python coverage of the keyframe generator + the
quaternion-to-HPB conversion. The c4d-bound applier is not
tested (it's a thin wrapper that no-ops outside Cinema 4D —
the dialog's bake button is the only caller).
"""

from __future__ import annotations

import math

import pytest

from c4d_objects.timeline_keys import (
    DEFAULT_FPS,
    MAX_FRAMES_FOR_BAKE,
    MIN_FRAMES_FOR_BAKE,
    BakeRange,
    BakeReport,
    KeyframeRecord,
    apply_keyframes,
    frame_to_progress,
    generate_bake_report,
    generate_keyframes,
    progress_to_frame,
    quaternion_to_hpb,
)
from voyage import Mission, MissionWaypoint, build_camera_path


def _two_wp_path():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=20.0, z_c4d=30.0),
    ])
    return build_camera_path(m)


# ---------------------------------------------------------------------------
# BakeRange validation
# ---------------------------------------------------------------------------


def test_bake_range_default():
    r = BakeRange()
    assert r.start_frame == 0
    assert r.fps == DEFAULT_FPS
    assert r.frame_count == 241


def test_bake_range_rejects_inverted_range():
    with pytest.raises(ValueError):
        BakeRange(start_frame=100, end_frame=50)


def test_bake_range_rejects_zero_fps():
    with pytest.raises(ValueError):
        BakeRange(fps=0)


def test_bake_range_rejects_too_narrow():
    with pytest.raises(ValueError):
        BakeRange(start_frame=10, end_frame=10)


def test_bake_range_rejects_too_wide():
    with pytest.raises(ValueError):
        BakeRange(start_frame=0, end_frame=MAX_FRAMES_FOR_BAKE + 5)


def test_bake_range_duration_seconds():
    r = BakeRange(start_frame=0, end_frame=119, fps=24)
    assert r.duration_seconds == pytest.approx(120.0 / 24.0)


# ---------------------------------------------------------------------------
# Frame mapping
# ---------------------------------------------------------------------------


def test_frame_to_progress_endpoints():
    r = BakeRange(start_frame=0, end_frame=100, fps=30)
    assert frame_to_progress(0, r) == 0.0
    assert frame_to_progress(100, r) == 1.0
    assert frame_to_progress(50, r) == pytest.approx(0.5)


def test_frame_to_progress_clamps():
    r = BakeRange(start_frame=0, end_frame=100, fps=30)
    assert frame_to_progress(-10, r) == 0.0
    assert frame_to_progress(200, r) == 1.0


def test_progress_to_frame_inverts_frame_to_progress():
    r = BakeRange(start_frame=10, end_frame=110, fps=30)
    assert progress_to_frame(0.0, r) == 10
    assert progress_to_frame(1.0, r) == 110
    assert progress_to_frame(0.5, r) == 60


# ---------------------------------------------------------------------------
# Keyframe generation
# ---------------------------------------------------------------------------


def test_generate_keyframes_count_matches_range():
    path = _two_wp_path()
    r = BakeRange(start_frame=0, end_frame=99, fps=30)
    records = generate_keyframes(path, r)
    assert len(records) == 100
    assert records[0].frame == 0
    assert records[-1].frame == 99


def test_generate_keyframes_endpoints_match_path_endpoints():
    path = _two_wp_path()
    r = BakeRange(start_frame=0, end_frame=99, fps=30)
    records = generate_keyframes(path, r)
    # First record is at path progress 0.
    assert records[0].position == pytest.approx((0.0, 0.0, 0.0))
    # Last record is at path progress 1.
    assert records[-1].position == pytest.approx((10.0, 20.0, 30.0))


def test_generate_keyframes_empty_path_returns_empty():
    records = generate_keyframes(build_camera_path(Mission()))
    assert records == []


def test_generate_keyframes_with_explicit_samples():
    path = _two_wp_path()
    r = BakeRange(start_frame=0, end_frame=99, fps=30)
    records = generate_keyframes(path, r, samples=10)
    assert len(records) == 10
    assert records[0].frame == 0
    assert records[-1].frame == 99


def test_generate_keyframes_is_deterministic():
    path = _two_wp_path()
    r = BakeRange(start_frame=0, end_frame=99, fps=30)
    a = generate_keyframes(path, r)
    b = generate_keyframes(path, r)
    for ra, rb in zip(a, b):
        assert ra.frame == rb.frame
        assert ra.position == rb.position
        assert ra.rotation_hpb == rb.rotation_hpb


def test_generate_keyframes_records_carry_frame_integers():
    path = _two_wp_path()
    r = BakeRange(start_frame=24, end_frame=120, fps=24)
    for record in generate_keyframes(path, r):
        assert isinstance(record.frame, int)
        assert 24 <= record.frame <= 120


def test_keyframe_carries_fov_when_requested():
    path = _two_wp_path()
    r = BakeRange(start_frame=0, end_frame=10, fps=30,
                  include_fov=True, fov_rad=math.radians(45))
    records = generate_keyframes(path, r)
    assert all(rec.fov_rad is not None for rec in records)
    assert records[0].fov_rad == pytest.approx(math.radians(45))


def test_keyframe_omits_fov_when_not_requested():
    path = _two_wp_path()
    r = BakeRange(start_frame=0, end_frame=10, fps=30, include_fov=False)
    records = generate_keyframes(path, r)
    assert all(rec.fov_rad is None for rec in records)


# ---------------------------------------------------------------------------
# Bake report
# ---------------------------------------------------------------------------


def test_bake_report_summary_line():
    path = _two_wp_path()
    r = BakeRange(start_frame=10, end_frame=29, fps=24)
    records = generate_keyframes(path, r)
    report = generate_bake_report(records, r)
    line = report.summary_line()
    assert "20" in line  # 20 records
    assert "[10..29]" in line
    assert "24 fps" in line


# ---------------------------------------------------------------------------
# Quaternion → HPB
# ---------------------------------------------------------------------------


def test_quaternion_identity_returns_zero_hpb():
    h, p, b = quaternion_to_hpb((1.0, 0.0, 0.0, 0.0))
    assert h == pytest.approx(0.0)
    assert p == pytest.approx(0.0)
    assert b == pytest.approx(0.0)


def test_quaternion_zero_returns_zero_hpb():
    """Defensive: a zero quaternion is malformed; the helper
    must not divide by zero."""
    h, p, b = quaternion_to_hpb((0.0, 0.0, 0.0, 0.0))
    assert (h, p, b) == (0.0, 0.0, 0.0)


def test_quaternion_to_hpb_returns_finite_for_random_unit():
    """Robustness: every unit quaternion must produce finite
    HPB values (no NaN, no inf)."""
    import math
    sqrt2 = 1.0 / math.sqrt(2.0)
    for q in (
        (sqrt2, sqrt2, 0.0, 0.0),
        (sqrt2, 0.0, sqrt2, 0.0),
        (sqrt2, 0.0, 0.0, sqrt2),
        (0.5, 0.5, 0.5, 0.5),
    ):
        h, p, b = quaternion_to_hpb(q)
        assert all(math.isfinite(v) for v in (h, p, b))


# ---------------------------------------------------------------------------
# Applier no-op when c4d missing
# ---------------------------------------------------------------------------


def test_apply_keyframes_no_c4d_returns_zero():
    """Outside Cinema 4D the applier must not raise. It returns
    0 written keys."""
    path = _two_wp_path()
    records = generate_keyframes(path, BakeRange(start_frame=0, end_frame=10))
    written = apply_keyframes(records)
    assert written == 0


def test_apply_keyframes_empty_records_returns_zero():
    written = apply_keyframes([])
    assert written == 0


# ---------------------------------------------------------------------------
# Missing-waypoint fallback (acceptance criterion)
# ---------------------------------------------------------------------------


def test_keyframes_resilient_to_unresolved_waypoints():
    """A mission with one unresolved object waypoint and one
    coordinate waypoint produces a path with only the
    coordinate waypoint. Keyframe generation should still
    work — every record carries the fallback's position."""
    m = Mission(waypoints=[
        MissionWaypoint(kind="object", uid="unknown:1"),  # unresolved
        MissionWaypoint(kind="coordinate", x_c4d=5.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=15.0, y_c4d=0.0, z_c4d=0.0),
    ])
    path = build_camera_path(m)
    records = generate_keyframes(
        path, BakeRange(start_frame=0, end_frame=20, fps=30),
    )
    assert len(records) == 21
    # Endpoints are the two coordinate waypoints.
    assert records[0].position == pytest.approx((5.0, 0.0, 0.0))
    assert records[-1].position == pytest.approx((15.0, 0.0, 0.0))
