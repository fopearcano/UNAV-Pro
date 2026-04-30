"""Tests for the v1.4 ``ui.mission_panel`` formatters + helpers."""

from __future__ import annotations

import pytest

from ui.mission_panel import (
    add_bookmark_waypoint,
    add_coordinate_waypoint,
    add_object_waypoint,
    build_camera_path_with_report,
    remove_waypoint,
    render_mission_detail,
    render_mission_list,
    render_playback_status,
    render_tick,
    reorder_waypoint,
    validate_title,
)
from voyage.mission import Mission, MissionWaypoint
from voyage.mission_manager import MissionManager
from voyage.playback import Playback, make_playback


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_render_mission_list_empty(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    text = render_mission_list(mgr)
    assert "No missions yet" in text


def test_render_mission_list_shows_count(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    mgr.create(Mission(title="A"))
    mgr.create(Mission(title="B"))
    text = render_mission_list(mgr)
    assert "Missions (2)" in text
    assert "A" in text
    assert "B" in text


def test_render_mission_detail_lists_waypoints():
    m = Mission(title="Tour", waypoints=[
        MissionWaypoint(kind="object", uid="x:1", label="Star"),
    ])
    text = render_mission_detail(m)
    assert "Tour" in text
    assert "Star" in text
    assert "object" in text


def test_render_mission_detail_includes_epoch_range():
    m = Mission(waypoints=[
        MissionWaypoint(kind="object", uid="a", epoch_jd=2451545.0),
        MissionWaypoint(kind="object", uid="b", epoch_jd=2461041.5),
    ])
    text = render_mission_detail(m)
    assert "Epoch range" in text


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_title_rejects_empty():
    ok, msg = validate_title("")
    assert ok is False
    assert msg


def test_validate_title_accepts_normal():
    ok, msg = validate_title("My Mission")
    assert ok is True
    assert msg == ""


def test_validate_title_rejects_too_long():
    ok, _ = validate_title("x" * 250)
    assert ok is False


# ---------------------------------------------------------------------------
# Add / remove / reorder
# ---------------------------------------------------------------------------


def test_add_object_waypoint_appends():
    m = Mission()
    ok, msg = add_object_waypoint(m, uid="x:1")
    assert ok and "added" in msg
    assert len(m) == 1


def test_add_object_waypoint_rejects_empty_uid():
    m = Mission()
    ok, _ = add_object_waypoint(m, uid="")
    assert ok is False
    assert len(m) == 0


def test_add_bookmark_waypoint_appends():
    m = Mission()
    ok, _ = add_bookmark_waypoint(m, bookmark_id="abc")
    assert ok
    assert m.waypoints[0].kind == "bookmark"


def test_add_coordinate_waypoint_appends():
    m = Mission()
    ok, _ = add_coordinate_waypoint(m, x_c4d=1.0, y_c4d=2.0, z_c4d=3.0)
    assert ok
    assert m.waypoints[0].x_c4d == 1.0


def test_remove_waypoint_drops_by_index():
    m = Mission(waypoints=[
        MissionWaypoint(kind="object", uid="a"),
        MissionWaypoint(kind="object", uid="b"),
    ])
    ok, _ = remove_waypoint(m, 0)
    assert ok
    assert len(m) == 1
    assert m.waypoints[0].uid == "b"


def test_remove_waypoint_out_of_range():
    m = Mission()
    ok, _ = remove_waypoint(m, 0)
    assert ok is False


def test_reorder_waypoint_moves_in_place():
    m = Mission(waypoints=[
        MissionWaypoint(kind="object", uid="a"),
        MissionWaypoint(kind="object", uid="b"),
        MissionWaypoint(kind="object", uid="c"),
    ])
    ok, _ = reorder_waypoint(m, 0, 2)
    assert ok
    assert m.waypoints[2].uid == "a"


# ---------------------------------------------------------------------------
# Build report
# ---------------------------------------------------------------------------


def test_build_camera_path_with_report_counts_unresolved():
    m = Mission(waypoints=[
        MissionWaypoint(kind="object", uid="x:1"),  # no cached pos
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
    ])
    path, report = build_camera_path_with_report(m)
    assert report.unresolved_count == 1
    assert report.unresolved_indices == [0]
    assert report.resolved_count == 1


# ---------------------------------------------------------------------------
# Status rendering
# ---------------------------------------------------------------------------


def test_render_playback_status_idle():
    text = render_playback_status(None)
    assert "idle" in text


def test_render_playback_status_paused_after_step():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=1.0, y_c4d=0.0, z_c4d=0.0),
    ])
    pb = make_playback(m)
    pb.step_forward(n=2)
    text = render_playback_status(pb)
    assert "PAUSED" in text


def test_render_tick_includes_step():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="coordinate", x_c4d=1.0, y_c4d=0.0, z_c4d=0.0),
    ])
    pb = make_playback(m)
    tick = pb.step_forward(n=1)
    line = render_tick(tick)
    assert "step=1" in line
