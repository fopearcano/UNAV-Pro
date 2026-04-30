"""Tests for the v1.4 ``voyage.mission_manager``."""

from __future__ import annotations

import os

import pytest

from voyage.mission import Mission, MissionWaypoint
from voyage.mission_manager import (
    MISSIONS_INDEX_FILENAME,
    MissionManager,
    waypoint_from_object,
    waypoints_from_bookmarks,
)


def _make_mission(title: str = "M") -> Mission:
    return Mission(
        title=title,
        waypoints=[
            MissionWaypoint(kind="object", uid="x:1"),
            MissionWaypoint(kind="object", uid="x:2"),
        ],
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_persists_and_lists(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    a = _make_mission("Alpha")
    mgr.create(a)
    assert len(mgr) == 1
    assert mgr.get(a.mission_id) is a
    listed = mgr.list_all()
    assert len(listed) == 1
    assert listed[0].title == "Alpha"


def test_create_writes_files(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    a = _make_mission()
    mgr.create(a)
    assert os.path.isfile(os.path.join(tmp_path, MISSIONS_INDEX_FILENAME))
    assert os.path.isfile(os.path.join(tmp_path, f"{a.mission_id}.json"))


def test_create_duplicate_id_raises(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    a = _make_mission()
    mgr.create(a)
    with pytest.raises(ValueError):
        mgr.create(a)


def test_update_mutates_persisted_file(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    a = _make_mission()
    mgr.create(a)
    a.title = "Renamed"
    mgr.update(a)

    mgr2 = MissionManager(missions_dir=str(tmp_path))
    reloaded = mgr2.get(a.mission_id)
    assert reloaded is not None
    assert reloaded.title == "Renamed"


def test_update_unknown_id_raises(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    with pytest.raises(KeyError):
        mgr.update(_make_mission())


def test_delete_removes_file_and_index(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    a = _make_mission()
    mgr.create(a)
    assert mgr.delete(a.mission_id) is True
    assert mgr.get(a.mission_id) is None
    assert not os.path.isfile(os.path.join(tmp_path, f"{a.mission_id}.json"))


def test_delete_unknown_id_returns_false(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    assert mgr.delete("nope") is False


def test_move_reorders_index(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    a = _make_mission("A")
    b = _make_mission("B")
    c = _make_mission("C")
    mgr.create(a); mgr.create(b); mgr.create(c)
    assert [m.title for m in mgr.list_all()] == ["A", "B", "C"]
    assert mgr.move(0, 2) is True
    assert [m.title for m in mgr.list_all()] == ["B", "C", "A"]


# ---------------------------------------------------------------------------
# Reload / persistence
# ---------------------------------------------------------------------------


def test_reload_picks_up_new_files(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    a = _make_mission("Alpha")
    mgr.create(a)
    # Spawn a fresh manager — should see what the first wrote.
    mgr2 = MissionManager(missions_dir=str(tmp_path))
    assert len(mgr2) == 1
    assert mgr2.get(a.mission_id).title == "Alpha"


def test_reload_skips_corrupt_files(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{not valid json", encoding="utf-8")
    mgr = MissionManager(missions_dir=str(tmp_path))
    assert len(mgr) == 0


def test_reload_handles_missing_dir(tmp_path):
    nope = tmp_path / "does_not_exist"
    mgr = MissionManager(missions_dir=str(nope))
    assert len(mgr) == 0


# ---------------------------------------------------------------------------
# Import / export
# ---------------------------------------------------------------------------


def test_export_then_import_roundtrips(tmp_path):
    src = MissionManager(missions_dir=str(tmp_path / "src"))
    a = _make_mission("Alpha")
    src.create(a)
    export_path = str(tmp_path / "alpha.json")
    assert src.export_mission(a.mission_id, export_path) is True

    dst = MissionManager(missions_dir=str(tmp_path / "dst"))
    imported = dst.import_mission(export_path)
    assert imported is not None
    assert imported.title == "Alpha"


def test_import_assigns_fresh_id_on_collision(tmp_path):
    a = _make_mission("Alpha")
    mgr = MissionManager(missions_dir=str(tmp_path))
    mgr.create(a)
    export_path = str(tmp_path / "alpha.json")
    mgr.export_mission(a.mission_id, export_path)
    re_imported = mgr.import_mission(export_path)
    assert re_imported is not None
    assert re_imported.mission_id != a.mission_id
    assert len(mgr) == 2


def test_import_missing_file_returns_none(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    assert mgr.import_mission(str(tmp_path / "no.json")) is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_waypoints_from_bookmarks_filters_empty():
    out = waypoints_from_bookmarks(["abc", "", "def"])
    assert len(out) == 2
    assert out[0].kind == "bookmark"
    assert out[0].bookmark_id == "abc"


def test_waypoint_from_object_carries_caches():
    wp = waypoint_from_object(
        uid="x:1", catalog_source="Gaia DR3", object_type="star",
        epoch_jd=2451545.0, duration_seconds=2.5,
    )
    assert wp.kind == "object"
    assert wp.catalog_source == "Gaia DR3"
    assert wp.epoch_jd == 2451545.0
    assert wp.duration_seconds == 2.5
