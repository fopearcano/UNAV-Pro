"""v2.3 export pipeline tests — single-format + package
exports, camera exchange, dataset summary."""

from __future__ import annotations

import json
import os

import pytest

from c4d_objects.timeline_keys import BakeRange
from export import (
    CAMERA_EXCHANGE_VERSION,
    DATASET_SUMMARY_VERSION,
    DEFAULT_PACKAGE_NAME,
    EXPORT_FORMATS,
    FORMAT_CAMERA_PATH_JSON,
    FORMAT_DATASET_SUMMARY_JSON,
    FORMAT_MISSION_JSON,
    FORMAT_ROUTE_JSON,
    FORMAT_ROUTE_MARKDOWN,
    FORMAT_SCIENCE_LAYER_JSON,
    FORMAT_TIMELINE_KEYFRAMES_JSON,
    FORMAT_WAYPOINT_CSV,
    PACKAGE_MANIFEST_VERSION,
    PACKAGE_SUBDIRS,
    ExportSettings,
    PackageBuildSettings,
    PackageManifest,
    PackagePayload,
    build_camera_exchange_from_keyframes,
    build_camera_exchange_from_mission,
    build_camera_exchange_from_timeline,
    build_dataset_summary,
    build_export_package,
    export_one,
    export_package,
    list_export_formats,
    read_export_package,
    write_camera_exchange,
)
from voyage import Mission, MissionWaypoint, build_camera_path


def _two_wp_mission():
    return Mission(title="Test", waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        label="A"),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
                        label="B"),
    ])


# ---------------------------------------------------------------------------
# Format registry
# ---------------------------------------------------------------------------


def test_export_formats_constant_includes_every_dialog_format():
    expected = {
        FORMAT_MISSION_JSON, FORMAT_ROUTE_JSON, FORMAT_WAYPOINT_CSV,
        FORMAT_ROUTE_MARKDOWN, FORMAT_CAMERA_PATH_JSON,
        FORMAT_TIMELINE_KEYFRAMES_JSON, FORMAT_SCIENCE_LAYER_JSON,
        FORMAT_DATASET_SUMMARY_JSON,
    }
    assert set(EXPORT_FORMATS) == expected


def test_list_export_formats_returns_label_and_extension():
    rows = list_export_formats()
    names = {r["name"] for r in rows}
    assert names == set(EXPORT_FORMATS)
    for r in rows:
        assert r["label"]
        assert r["extension"].startswith(".")


# ---------------------------------------------------------------------------
# Single-format export
# ---------------------------------------------------------------------------


def test_export_mission_writes_json(tmp_path):
    target = str(tmp_path / "mission.json")
    res = export_one(FORMAT_MISSION_JSON, target,
                     mission=_two_wp_mission())
    assert res.success is True
    assert os.path.isfile(target)
    with open(target, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["title"] == "Test"


def test_export_unknown_format_fails_closed(tmp_path):
    target = str(tmp_path / "x.json")
    res = export_one("nonsense", target)
    assert res.success is False
    assert any(i.code == "unknown_format" for i in res.validation.errors())


def test_export_overwrite_refused_by_default(tmp_path):
    target = str(tmp_path / "mission.json")
    export_one(FORMAT_MISSION_JSON, target, mission=_two_wp_mission())
    res = export_one(FORMAT_MISSION_JSON, target, mission=_two_wp_mission())
    assert res.success is False
    assert any(i.code == "overwrite_refused" for i in res.validation.errors())


def test_export_overwrite_allowed_when_flag_set(tmp_path):
    target = str(tmp_path / "mission.json")
    export_one(FORMAT_MISSION_JSON, target, mission=_two_wp_mission())
    res = export_one(
        FORMAT_MISSION_JSON, target, mission=_two_wp_mission(),
        settings=ExportSettings(allow_overwrite=True),
    )
    assert res.success is True


def test_export_waypoint_csv(tmp_path):
    target = str(tmp_path / "wp.csv")
    res = export_one(FORMAT_WAYPOINT_CSV, target, mission=_two_wp_mission())
    assert res.success is True
    text = open(target, encoding="utf-8").read()
    # Header + 2 rows.
    assert "label" in text.splitlines()[0]
    assert "A" in text


def test_export_route_markdown(tmp_path):
    target = str(tmp_path / "route.md")
    res = export_one(FORMAT_ROUTE_MARKDOWN, target,
                     mission=_two_wp_mission())
    assert res.success is True
    assert open(target, encoding="utf-8").read().startswith("# Test")


def test_export_camera_path(tmp_path):
    target = str(tmp_path / "cam.json")
    m = _two_wp_mission()
    p = build_camera_path(m)
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    res = export_one(FORMAT_CAMERA_PATH_JSON, target,
                     mission=m, camera_path=p, frame_range=fr,
                     settings=ExportSettings(plugin_version="v2.3"))
    assert res.success is True
    payload = json.load(open(target, encoding="utf-8"))
    assert payload["schema_version"] == CAMERA_EXCHANGE_VERSION
    assert payload["fps"] == 30
    assert len(payload["records"]) == 100
    assert payload["plugin_version"] == "v2.3"


def test_export_camera_path_validates_empty_path(tmp_path):
    """Empty camera path → validation error, no file."""
    target = str(tmp_path / "cam.json")
    m = Mission()
    p = build_camera_path(m)
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    res = export_one(FORMAT_CAMERA_PATH_JSON, target,
                     mission=m, camera_path=p, frame_range=fr)
    assert res.success is False
    assert any(i.code == "empty_path" for i in res.validation.errors())
    assert not os.path.exists(target)


def test_export_dataset_summary(tmp_path):
    summary = build_dataset_summary(plugin_version="v2.3")
    target = str(tmp_path / "summary.json")
    res = export_one(FORMAT_DATASET_SUMMARY_JSON, target, summary=summary)
    assert res.success is True
    payload = json.load(open(target, encoding="utf-8"))
    assert payload["schema_version"] == DATASET_SUMMARY_VERSION


def test_export_writer_exception_caught(tmp_path):
    """If the writer raises, the export reports the error in
    the validation report rather than letting the exception
    escape."""
    # Force a writer failure by handing a non-Mission object
    # to the camera-path writer (the camera_exchange builder
    # will raise during ``mission.title`` access).
    target = str(tmp_path / "x.json")

    class _Broken:  # not a Mission; missing required attrs
        pass

    res = export_one(FORMAT_MISSION_JSON, target, mission=_Broken())
    assert res.success is False
    # Either pre-flight catches it (no_mission missing title etc.) or
    # the writer raises and writer_exception is logged.
    codes = [i.code for i in res.validation.errors()]
    assert codes  # at least one error reported


# ---------------------------------------------------------------------------
# Camera exchange
# ---------------------------------------------------------------------------


def test_camera_exchange_record_count_matches_frame_count():
    m = _two_wp_mission()
    p = build_camera_path(m)
    fr = BakeRange(start_frame=0, end_frame=99, fps=30)
    doc = build_camera_exchange_from_mission(m, p, frame_range=fr)
    assert doc.frame_count == 100
    assert len(doc.records) == 100


def test_camera_exchange_carries_units():
    doc = build_camera_exchange_from_mission(
        _two_wp_mission(), build_camera_path(_two_wp_mission()),
        frame_range=BakeRange(start_frame=0, end_frame=10, fps=30),
    )
    assert "position" in doc.units
    assert "rotation" in doc.units


def test_camera_exchange_from_keyframes():
    from c4d_objects.timeline_keys import KeyframeRecord
    fr = BakeRange(start_frame=10, end_frame=19, fps=10)
    keys = [
        KeyframeRecord(frame=i, position=(i, 0.0, 0.0),
                        rotation_hpb=(0.0, 0.0, 0.0))
        for i in range(10, 20)
    ]
    doc = build_camera_exchange_from_keyframes(
        keys, frame_range=fr, mission_title="Custom",
    )
    assert doc.fps == 10
    assert doc.start_frame == 10
    assert len(doc.records) == 10
    assert doc.records[0].seconds == 0.0
    assert doc.records[-1].seconds == pytest.approx(0.9)


def test_camera_exchange_atomic_write(tmp_path):
    doc = build_camera_exchange_from_mission(
        _two_wp_mission(), build_camera_path(_two_wp_mission()),
        frame_range=BakeRange(start_frame=0, end_frame=10, fps=30),
    )
    target = str(tmp_path / "cam.json")
    written = write_camera_exchange(doc, target)
    assert written == target
    assert os.path.isfile(target)


def test_camera_exchange_round_trips_through_dict():
    doc = build_camera_exchange_from_mission(
        _two_wp_mission(), build_camera_path(_two_wp_mission()),
        frame_range=BakeRange(start_frame=0, end_frame=4, fps=30),
    )
    rt = json.loads(doc.to_json())
    assert rt["fps"] == 30
    assert len(rt["records"]) == 5


# ---------------------------------------------------------------------------
# Dataset summary
# ---------------------------------------------------------------------------


def test_dataset_summary_default_is_empty():
    s = build_dataset_summary()
    assert s.dataset_count == 0
    assert s.enabled_dataset_count == 0
    assert s.datasets == []
    assert s.notes  # at least the "registry not supplied" note


def test_dataset_summary_aggregates_objects():
    class _Obj:
        def __init__(self, src, typ):
            self.catalog_source = src
            self.object_type = typ
            self.cartesian_x = self.cartesian_y = self.cartesian_z = 0.0
    rows = [
        _Obj("Gaia DR3", "star"),
        _Obj("Gaia DR3", "star"),
        _Obj("SDSS", "galaxy"),
    ]
    s = build_dataset_summary(objects=rows)
    assert s.object_count_estimate == 3
    assert s.sources["Gaia DR3"] == 2
    assert s.sources["SDSS"] == 1


def test_dataset_summary_round_trip_json():
    s = build_dataset_summary(plugin_version="v2.3")
    payload = json.loads(s.to_json())
    assert payload["schema_version"] == DATASET_SUMMARY_VERSION
    assert payload["plugin_version"] == "v2.3"


# ---------------------------------------------------------------------------
# Package builder
# ---------------------------------------------------------------------------


def test_package_default_name_constant():
    assert DEFAULT_PACKAGE_NAME == "UNAV_Export"


def test_package_subdirs_match_spec():
    expected = {
        "missions", "routes", "timelines", "camera_paths",
        "datasets", "summaries", "docs",
    }
    assert set(PACKAGE_SUBDIRS) == expected


def test_package_creates_directory_layout(tmp_path):
    payload = PackagePayload(
        missions={"m.json": '{"title":"x"}'},
        camera_paths={"c.json": '{"records":[]}'},
    )
    rep = build_export_package(str(tmp_path / "pkg"), payload)
    assert rep.success is True
    for sub in PACKAGE_SUBDIRS:
        assert os.path.isdir(os.path.join(tmp_path, "pkg", sub))
    assert os.path.isfile(os.path.join(tmp_path, "pkg", "manifest.json"))


def test_package_manifest_lists_only_written_assets(tmp_path):
    payload = PackagePayload(
        missions={"m.json": '{"title":"x"}'},
    )
    rep = build_export_package(str(tmp_path / "pkg"), payload)
    assert rep.success is True
    manifest = read_export_package(str(tmp_path / "pkg"))
    assert "missions" in manifest.included_assets
    assert "m.json" in manifest.included_assets["missions"]
    # Empty asset classes are absent.
    assert "routes" not in manifest.included_assets


def test_package_refuses_absolute_filename(tmp_path):
    payload = PackagePayload(
        missions={"/tmp/abs.json": "{}"},
    )
    rep = build_export_package(str(tmp_path / "pkg"), payload)
    assert rep.success is False
    assert any("absolute" in w for w in rep.warnings)


def test_package_existing_directory_allowed_by_default(tmp_path):
    target = tmp_path / "pkg"
    target.mkdir()
    rep = build_export_package(str(target), PackagePayload(
        missions={"m.json": "{}"},
    ))
    assert rep.success is True


def test_package_existing_directory_forbidden_when_flag_set(tmp_path):
    target = tmp_path / "pkg"
    target.mkdir()
    rep = build_export_package(
        str(target), PackagePayload(missions={"m.json": "{}"}),
        allow_existing=False,
    )
    assert rep.success is False


def test_package_manifest_is_valid_v23(tmp_path):
    rep = build_export_package(
        str(tmp_path / "pkg"),
        PackagePayload(missions={"m.json": "{}"}),
        manifest=PackageManifest(plugin_version="v2.3"),
    )
    assert rep.success is True
    manifest = read_export_package(str(tmp_path / "pkg"))
    assert manifest.manifest_version == PACKAGE_MANIFEST_VERSION
    assert manifest.plugin_version == "v2.3"


def test_package_manifest_round_trip():
    m = PackageManifest(
        plugin_version="v2.3",
        active_datasets=["Gaia DR3", "SDSS"],
        included_assets={"missions": ["m.json"]},
    )
    rt = PackageManifest.from_dict(m.to_dict())
    assert rt.plugin_version == "v2.3"
    assert rt.active_datasets == ["Gaia DR3", "SDSS"]
    assert rt.included_assets == {"missions": ["m.json"]}


def test_high_level_export_package_writes_manifest(tmp_path):
    rep = export_package(
        str(tmp_path / "pkg"),
        missions=[_two_wp_mission()],
        active_dataset_names=["Gaia DR3"],
        settings=PackageBuildSettings(plugin_version="v2.3"),
    )
    assert rep.success is True
    manifest = read_export_package(str(tmp_path / "pkg"))
    assert manifest.active_datasets == ["Gaia DR3"]
    assert "missions" in manifest.included_assets


def test_read_export_package_missing_returns_none(tmp_path):
    assert read_export_package(str(tmp_path / "nope")) is None


def test_read_export_package_corrupt_returns_none(tmp_path):
    target = tmp_path / "pkg"
    target.mkdir()
    (target / "manifest.json").write_text("not valid", encoding="utf-8")
    assert read_export_package(str(target)) is None


# ---------------------------------------------------------------------------
# Filename hygiene (private helper, exercised via package)
# ---------------------------------------------------------------------------


def test_package_safe_filename_replaces_invalid_chars(tmp_path):
    """Mission titles containing path separators should be
    sanitised to safe filenames."""
    m = _two_wp_mission()
    m.title = "Bad/Name:Here"
    rep = export_package(
        str(tmp_path / "pkg"), missions=[m],
        settings=PackageBuildSettings(plugin_version="v2.3"),
    )
    assert rep.success is True
    manifest = read_export_package(str(tmp_path / "pkg"))
    written = manifest.included_assets.get("missions") or []
    assert written
    # Original characters must be replaced.
    for name in written:
        assert "/" not in name
        assert ":" not in name
