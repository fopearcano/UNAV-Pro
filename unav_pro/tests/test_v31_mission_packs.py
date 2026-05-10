"""v3.1 mission-pack tests."""

from __future__ import annotations

import json

import pytest

from project import (
    COLLISION_STRATEGIES,
    MissionPack,
    MissionPackError,
    build_pack_from_missions,
    import_pack,
    read_pack,
    write_pack,
)
from voyage import Mission, MissionWaypoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_mission(mission_id: str, title: str = "M") -> Mission:
    m = Mission(title=title)
    m.mission_id = mission_id
    m.waypoints.append(MissionWaypoint(
        kind="coordinate", label="origin",
        x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
    ))
    return m


# ---------------------------------------------------------------------------
# Build / round-trip
# ---------------------------------------------------------------------------


def test_build_pack_from_missions():
    pack = build_pack_from_missions(
        [_mk_mission("a"), _mk_mission("b")],
        pack_name="My Pack",
        description="d",
    )
    assert pack.pack_name == "My Pack"
    assert len(pack.missions) == 2
    ids = [m["mission_id"] for m in pack.missions]
    assert "a" in ids and "b" in ids


def test_build_pack_rejects_empty_name():
    with pytest.raises(ValueError):
        build_pack_from_missions(
            [_mk_mission("a")], pack_name="   ",
        )


def test_build_pack_rejects_non_mission_inputs():
    with pytest.raises(TypeError):
        build_pack_from_missions(["not a mission"], pack_name="X")


def test_pack_round_trips_via_json():
    pack = build_pack_from_missions(
        [_mk_mission("a"), _mk_mission("b")], pack_name="X",
    )
    rt = MissionPack.from_json(pack.to_json())
    assert rt.pack_name == "X"
    assert len(rt.missions) == 2


def test_pack_rejects_newer_schema():
    payload = {"schema_version": 999, "missions": []}
    with pytest.raises(MissionPackError):
        MissionPack.from_dict(payload)


def test_pack_handles_missing_optional_fields():
    pack = MissionPack.from_dict({"missions": []})
    assert pack.pack_name == "Untitled Pack"


def test_pack_filters_non_dict_entries():
    pack = MissionPack.from_dict({
        "missions": [
            {"mission_id": "a"},
            "not a mission",
            None,
            {"mission_id": "b"},
        ],
    })
    assert len(pack.missions) == 2


def test_pack_rejects_non_object_payload():
    with pytest.raises(MissionPackError):
        MissionPack.from_dict([])  # type: ignore[arg-type]


def test_pack_from_json_rejects_garbage():
    with pytest.raises(MissionPackError):
        MissionPack.from_json("{not json")


# ---------------------------------------------------------------------------
# Disk I/O
# ---------------------------------------------------------------------------


def test_write_and_read_pack(tmp_path):
    pack = build_pack_from_missions(
        [_mk_mission("a")], pack_name="P",
    )
    path = str(tmp_path / "p.unavpack.json")
    write_pack(pack, path)
    rt = read_pack(path)
    assert rt.pack_name == "P"
    assert len(rt.missions) == 1


def test_read_pack_missing_file_raises(tmp_path):
    with pytest.raises(MissionPackError):
        read_pack(str(tmp_path / "missing.json"))


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------


class _FakeStore:
    """Stand-in for MissionManager. Tests verify the
    importer's interaction with create / update without
    touching the real on-disk manager."""

    def __init__(self):
        self.missions = {}

    def create(self, mission):
        if mission.mission_id in self.missions:
            raise ValueError(f"duplicate {mission.mission_id}")
        self.missions[mission.mission_id] = mission

    def update(self, mission):
        if mission.mission_id not in self.missions:
            raise KeyError(mission.mission_id)
        self.missions[mission.mission_id] = mission


def test_import_pack_skip_strategy():
    store = _FakeStore()
    store.create(_mk_mission("a", title="orig"))
    pack = build_pack_from_missions(
        [_mk_mission("a", title="new"), _mk_mission("b")],
        pack_name="P",
    )
    report = import_pack(
        pack,
        existing_ids=list(store.missions.keys()),
        mission_factory=Mission.from_dict,
        create_callback=store.create,
        on_collision="skip",
    )
    assert report.imported == ["b"]
    assert "a" in report.skipped
    assert store.missions["a"].title == "orig"


def test_import_pack_replace_strategy():
    store = _FakeStore()
    store.create(_mk_mission("a", title="orig"))
    pack = build_pack_from_missions(
        [_mk_mission("a", title="new")], pack_name="P",
    )
    report = import_pack(
        pack,
        existing_ids=list(store.missions.keys()),
        mission_factory=Mission.from_dict,
        create_callback=store.create,
        update_callback=store.update,
        on_collision="replace",
    )
    assert report.replaced == ["a"]
    assert store.missions["a"].title == "new"


def test_import_pack_rename_strategy():
    store = _FakeStore()
    store.create(_mk_mission("a"))
    pack = build_pack_from_missions(
        [_mk_mission("a", title="copy")], pack_name="P",
    )
    report = import_pack(
        pack,
        existing_ids=list(store.missions.keys()),
        mission_factory=Mission.from_dict,
        create_callback=store.create,
        on_collision="rename",
    )
    assert len(report.renamed) == 1
    old_id, new_id = report.renamed[0]
    assert old_id == "a"
    assert new_id != "a"
    assert new_id in store.missions


def test_import_pack_replace_requires_callback():
    pack = build_pack_from_missions([_mk_mission("a")], pack_name="P")
    with pytest.raises(ValueError):
        import_pack(
            pack,
            existing_ids=["a"],
            mission_factory=Mission.from_dict,
            create_callback=lambda m: None,
            on_collision="replace",
        )


def test_import_pack_rejects_unknown_strategy():
    pack = build_pack_from_missions([_mk_mission("a")], pack_name="P")
    with pytest.raises(ValueError):
        import_pack(
            pack,
            existing_ids=[],
            mission_factory=Mission.from_dict,
            create_callback=lambda m: None,
            on_collision="merge",
        )


def test_import_pack_collects_factory_errors():
    pack = MissionPack(pack_name="P", missions=[
        {"mission_id": "x", "schema_version": 999},  # forces from_dict to fail
    ])

    def bad_factory(d):
        raise ValueError("bad mission")

    report = import_pack(
        pack,
        existing_ids=[],
        mission_factory=bad_factory,
        create_callback=lambda m: None,
        on_collision="skip",
    )
    assert report.errors


def test_import_pack_skips_missions_without_id():
    pack = MissionPack(pack_name="P", missions=[
        {"foo": "bar"},  # no mission_id
    ])

    class FactoryReturnsObjectWithoutId:
        mission_id = ""

    def factory(d):
        return FactoryReturnsObjectWithoutId()

    report = import_pack(
        pack,
        existing_ids=[],
        mission_factory=factory,
        create_callback=lambda m: None,
        on_collision="skip",
    )
    assert any("mission_id" in e for e in report.errors)


def test_import_report_summary():
    store = _FakeStore()
    pack = build_pack_from_missions(
        [_mk_mission("a"), _mk_mission("b")], pack_name="P",
    )
    report = import_pack(
        pack,
        existing_ids=[],
        mission_factory=Mission.from_dict,
        create_callback=store.create,
        on_collision="skip",
    )
    s = report.short_summary()
    assert "imported=2" in s


def test_collision_strategies_constant():
    assert set(COLLISION_STRATEGIES) == {"skip", "replace", "rename"}
