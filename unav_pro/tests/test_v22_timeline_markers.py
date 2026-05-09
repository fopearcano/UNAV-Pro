"""v2.2 timeline-marker tests.

Pure-Python data-layer coverage. The c4d-bound applier is
exercised by the dialog at runtime; tests cover the
``MarkerRecord`` / ``MarkerBundle`` shape, the build helper,
and the no-c4d safety path.
"""

from __future__ import annotations

import pytest

from animation import (
    AnimatedStateConfig,
    AnimatedTimeline,
    evaluate_animated_state,
)
from c4d_objects.timeline_keys import BakeRange
from c4d_objects.timeline_markers import (
    KIND_EPOCH,
    KIND_SCIENCE,
    KIND_SYNC,
    KIND_WAYPOINT,
    MARKER_KINDS,
    MAX_MARKERS_PER_BAKE,
    UNAV_MARKER_PREFIX,
    MarkerBundle,
    MarkerRecord,
    apply_markers,
    build_marker_bundle,
    clear_markers,
    render_marker_summary,
)
from voyage import Mission, MissionWaypoint, build_camera_path


def _three_wp_timeline(*, sync_markers=None, with_epochs=True):
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        label="A", duration_seconds=2.0,
                        epoch_jd=2451545.0 if with_epochs else None),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
                        label="B", duration_seconds=2.0,
                        epoch_jd=2461041.5 if with_epochs else None),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=10.0, z_c4d=0.0,
                        label="C", duration_seconds=2.0),
    ])
    p = build_camera_path(m)
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    cfg = AnimatedStateConfig(sync_markers=sync_markers or [])
    return m, p, fr, evaluate_animated_state(m, p, frame_range=fr, config=cfg)


# ---------------------------------------------------------------------------
# MarkerRecord
# ---------------------------------------------------------------------------


def test_marker_kinds_match():
    assert set(MARKER_KINDS) == {KIND_WAYPOINT, KIND_EPOCH, KIND_SYNC, KIND_SCIENCE}


def test_marker_record_display_name_uses_prefix():
    rec = MarkerRecord(frame=10, kind=KIND_WAYPOINT, label="Earth")
    assert rec.display_name().startswith(UNAV_MARKER_PREFIX)
    assert "waypoint" in rec.display_name()
    assert "Earth" in rec.display_name()


def test_marker_record_default_label_falls_back_to_kind():
    rec = MarkerRecord(frame=0, kind=KIND_SYNC)
    assert "sync" in rec.display_name()


# ---------------------------------------------------------------------------
# build_marker_bundle
# ---------------------------------------------------------------------------


def test_build_marker_bundle_includes_waypoint_per_arrival():
    _, _, _, tl = _three_wp_timeline()
    bundle = build_marker_bundle(tl)
    waypoint_records = bundle.by_kind(KIND_WAYPOINT)
    assert len(waypoint_records) == len(tl.waypoint_arrival_frames)


def test_build_marker_bundle_uses_provided_waypoint_labels():
    _, _, _, tl = _three_wp_timeline()
    bundle = build_marker_bundle(tl, waypoint_labels=["Alpha", "Beta", "Gamma"])
    labels = [r.label for r in bundle.by_kind(KIND_WAYPOINT)]
    assert labels[:3] == ["Alpha", "Beta", "Gamma"]


def test_build_marker_bundle_falls_back_to_default_label():
    _, _, _, tl = _three_wp_timeline()
    bundle = build_marker_bundle(tl, waypoint_labels=["Alpha"])
    labels = [r.label for r in bundle.by_kind(KIND_WAYPOINT)]
    # First label honoured, rest get default.
    assert labels[0] == "Alpha"
    assert all("waypoint #" in l for l in labels[1:])


def test_build_marker_bundle_includes_epoch_changes():
    _, _, _, tl = _three_wp_timeline(with_epochs=True)
    bundle = build_marker_bundle(tl)
    epoch_records = bundle.by_kind(KIND_EPOCH)
    assert len(epoch_records) == len(tl.epoch_change_frames)


def test_build_marker_bundle_includes_sync_markers():
    _, _, _, tl = _three_wp_timeline(sync_markers=[10, 50])
    bundle = build_marker_bundle(tl)
    sync_records = bundle.by_kind(KIND_SYNC)
    # waypoint arrivals are also sync markers by default.
    assert len(sync_records) == len(tl.sync_marker_frames)


def test_build_marker_bundle_includes_science_layer_frames():
    _, _, _, tl = _three_wp_timeline()
    bundle = build_marker_bundle(tl, science_layer_frames=[20, 40, 60])
    sci_records = bundle.by_kind(KIND_SCIENCE)
    assert len(sci_records) == 3
    assert [r.frame for r in sci_records] == [20, 40, 60]


def test_build_marker_bundle_caps_records():
    """Forcing a tiny synthetic timeline with too many science
    layer frames should trip the cap warning."""
    tl = AnimatedTimeline()
    bundle = build_marker_bundle(
        tl, science_layer_frames=list(range(MAX_MARKERS_PER_BAKE + 50)),
    )
    assert len(bundle.records) == MAX_MARKERS_PER_BAKE
    assert any("capped" in w for w in bundle.warnings)


# ---------------------------------------------------------------------------
# render_marker_summary
# ---------------------------------------------------------------------------


def test_render_marker_summary_lists_kinds_with_counts():
    _, _, _, tl = _three_wp_timeline(sync_markers=[10])
    bundle = build_marker_bundle(tl)
    text = render_marker_summary(bundle)
    assert "waypoint" in text
    assert "sync" in text


def test_render_marker_summary_for_empty_bundle():
    text = render_marker_summary(MarkerBundle())
    assert "No timeline markers" in text


# ---------------------------------------------------------------------------
# C4D applier — pure-Python fallback
# ---------------------------------------------------------------------------


def test_apply_markers_no_c4d_returns_zero():
    _, _, _, tl = _three_wp_timeline()
    bundle = build_marker_bundle(tl)
    assert apply_markers(bundle) == 0


def test_apply_markers_empty_bundle_no_c4d_returns_zero():
    assert apply_markers(MarkerBundle()) == 0


def test_clear_markers_no_c4d_returns_zero():
    assert clear_markers() == 0


# ---------------------------------------------------------------------------
# Idempotency — bundle structure is stable
# ---------------------------------------------------------------------------


def test_bundle_build_is_deterministic():
    _, _, _, tl = _three_wp_timeline(sync_markers=[10, 50])
    a = build_marker_bundle(tl, waypoint_labels=["Alpha", "Beta", "Gamma"])
    b = build_marker_bundle(tl, waypoint_labels=["Alpha", "Beta", "Gamma"])
    assert len(a.records) == len(b.records)
    for ra, rb in zip(a.records, b.records):
        assert ra.frame == rb.frame
        assert ra.kind == rb.kind
        assert ra.display_name() == rb.display_name()
