"""Tests for the v1.4 ``voyage.mission`` data model."""

from __future__ import annotations

import json

import pytest

from voyage.mission import (
    MAX_WAYPOINTS_PER_MISSION,
    MISSION_SCHEMA_VERSION,
    Mission,
    MissionWaypoint,
)


# ---------------------------------------------------------------------------
# MissionWaypoint validation
# ---------------------------------------------------------------------------


def test_object_waypoint_requires_uid():
    with pytest.raises(ValueError):
        MissionWaypoint(kind="object")


def test_coordinate_waypoint_requires_position():
    with pytest.raises(ValueError):
        MissionWaypoint(kind="coordinate")


def test_named_waypoint_requires_label_or_position():
    with pytest.raises(ValueError):
        MissionWaypoint(kind="named")
    # OK with a label.
    MissionWaypoint(kind="named", label="Sgr A*")


def test_bookmark_waypoint_requires_id():
    with pytest.raises(ValueError):
        MissionWaypoint(kind="bookmark")


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        MissionWaypoint(kind="alien", label="x")


def test_orientation_quat_must_be_4_tuple():
    with pytest.raises(ValueError):
        MissionWaypoint(
            kind="object", uid="x:1",
            orientation_quat=(1.0, 0.0, 0.0),  # 3-tuple
        )


def test_duration_must_be_positive():
    with pytest.raises(ValueError):
        MissionWaypoint(kind="object", uid="x:1", duration_seconds=0.0)


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def _full_mission() -> Mission:
    return Mission(
        title="Inner Solar System Tour",
        description="A weekly fly-through of the inner planets.",
        tags=["solar-system", "demo"],
        waypoints=[
            MissionWaypoint(
                kind="object", uid="jpl:Mars:2026",
                label="Mars 2026",
                duration_seconds=3.0, epoch_jd=2461041.5,
                notes="closest approach",
            ),
            MissionWaypoint(
                kind="bookmark", bookmark_id="abc123",
                label="Earth",
                orientation_quat=(1.0, 0.0, 0.0, 0.0),
            ),
            MissionWaypoint(
                kind="coordinate",
                x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
                label="lookout",
            ),
        ],
    )


def test_mission_round_trips_through_json():
    a = _full_mission()
    b = Mission.from_json(a.to_json())
    assert b.title == a.title
    assert b.description == a.description
    assert b.tags == a.tags
    assert len(b.waypoints) == 3
    assert b.waypoints[0].uid == "jpl:Mars:2026"
    assert b.waypoints[0].epoch_jd == 2461041.5
    assert b.waypoints[1].bookmark_id == "abc123"
    assert b.waypoints[1].orientation_quat == (1.0, 0.0, 0.0, 0.0)
    assert b.waypoints[2].x_c4d == 10.0


def test_mission_to_dict_carries_schema_version():
    m = _full_mission()
    d = m.to_dict()
    assert d["schema_version"] == MISSION_SCHEMA_VERSION


def test_mission_from_json_handles_garbage():
    m = Mission.from_json("not valid json")
    assert isinstance(m, Mission)
    assert len(m.waypoints) == 0


def test_mission_from_dict_drops_unrecoverable_waypoints():
    raw = {
        "title": "Half-broken",
        "waypoints": [
            {"kind": "object", "uid": "x:1"},
            {"kind": "object"},  # missing uid → dropped
            {"kind": "coordinate", "x_c4d": 0.0, "y_c4d": 0.0, "z_c4d": 0.0},
        ],
    }
    m = Mission.from_dict(raw)
    assert len(m.waypoints) == 2


# ---------------------------------------------------------------------------
# Ordering / mutation
# ---------------------------------------------------------------------------


def test_mission_add_grows_list():
    m = Mission()
    m.add(MissionWaypoint(kind="object", uid="x:1"))
    m.add(MissionWaypoint(kind="object", uid="x:2"))
    assert len(m) == 2


def test_mission_move_reorders():
    m = _full_mission()
    assert m.waypoints[0].uid == "jpl:Mars:2026"
    assert m.move(0, 2) is True
    assert m.waypoints[2].uid == "jpl:Mars:2026"


def test_mission_move_clamps_out_of_range_dst():
    m = _full_mission()
    assert m.move(0, 1000) is True
    assert m.waypoints[-1].uid == "jpl:Mars:2026"


def test_mission_remove_at_returns_dropped_waypoint():
    m = _full_mission()
    dropped = m.remove_at(0)
    assert dropped.uid == "jpl:Mars:2026"
    assert len(m) == 2


def test_mission_remove_at_out_of_range_returns_none():
    m = Mission()
    assert m.remove_at(0) is None


def test_mission_replace_at():
    m = _full_mission()
    new_wp = MissionWaypoint(kind="object", uid="x:replacement")
    old = m.replace_at(0, new_wp)
    assert old.uid == "jpl:Mars:2026"
    assert m.waypoints[0].uid == "x:replacement"


def test_mission_max_waypoints_enforced():
    m = Mission()
    for i in range(MAX_WAYPOINTS_PER_MISSION):
        m.add(MissionWaypoint(kind="object", uid=f"x:{i}"))
    assert len(m) == MAX_WAYPOINTS_PER_MISSION
    with pytest.raises(ValueError):
        m.add(MissionWaypoint(kind="object", uid="overflow"))


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------


def test_total_duration_sums_waypoints():
    m = Mission(waypoints=[
        MissionWaypoint(kind="object", uid="a", duration_seconds=2.0),
        MissionWaypoint(kind="object", uid="b", duration_seconds=3.5),
    ])
    assert m.total_duration_seconds() == pytest.approx(5.5)


def test_epoch_range_returns_min_max_or_none():
    m = Mission(waypoints=[
        MissionWaypoint(kind="object", uid="a", epoch_jd=2451545.0),
        MissionWaypoint(kind="object", uid="b"),  # no epoch
        MissionWaypoint(kind="object", uid="c", epoch_jd=2461041.5),
    ])
    lo, hi = m.epoch_range()
    assert lo == pytest.approx(2451545.0)
    assert hi == pytest.approx(2461041.5)


def test_epoch_range_none_when_no_waypoint_has_epoch():
    m = Mission(waypoints=[
        MissionWaypoint(kind="object", uid="a"),
    ])
    assert m.epoch_range() is None
