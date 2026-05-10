"""v3.1 project-manifest tests."""

from __future__ import annotations

import json
import os

import pytest

from project.project_manifest import (
    PROJECT_MANIFEST_FILENAME,
    PROJECT_MANIFEST_SCHEMA_VERSION,
    DatasetReference,
    ManifestError,
    MissionReference,
    OverlaySettingsRef,
    ProjectManifest,
    RouteReference,
    ScienceSettingsRef,
    TimelineReference,
    _is_safe_relpath,
    load_manifest,
    save_manifest,
)


# ---------------------------------------------------------------------------
# _is_safe_relpath
# ---------------------------------------------------------------------------


def test_safe_relpath_accepts_workspace_relative():
    assert _is_safe_relpath("missions/foo.json")
    assert _is_safe_relpath("datasets/gaia.jsonl")


def test_safe_relpath_rejects_absolute():
    assert not _is_safe_relpath("/etc/passwd")
    # Windows-style "C:\foo" is only flagged as absolute on
    # Windows; the workspace-relative check on Linux doesn't
    # see the colon as special. The forward-slash absolute
    # check above is the universal guarantee.


def test_safe_relpath_rejects_traversal():
    assert not _is_safe_relpath("../foo")
    assert not _is_safe_relpath("missions/../../foo")


def test_safe_relpath_rejects_empty():
    assert not _is_safe_relpath("")


# ---------------------------------------------------------------------------
# DatasetReference
# ---------------------------------------------------------------------------


def test_dataset_reference_round_trip():
    ref = DatasetReference(
        name="Gaia DR3", path="datasets/gaia.db",
        enabled=True, role="primary",
    )
    rt = DatasetReference.from_dict(ref.to_dict())
    assert rt.name == ref.name
    assert rt.path == ref.path
    assert rt.enabled is True


def test_dataset_reference_validates_path():
    ref = DatasetReference(name="bad", path="/etc/passwd")
    errs = ref.validate()
    assert any("workspace-relative" in e for e in errs)


def test_dataset_reference_validates_empty_name():
    ref = DatasetReference(name="", path="datasets/x.jsonl")
    errs = ref.validate()
    assert any("name is empty" in e for e in errs)


# ---------------------------------------------------------------------------
# MissionReference
# ---------------------------------------------------------------------------


def test_mission_reference_round_trip():
    ref = MissionReference(
        mission_id="m-1", path="missions/m-1.json",
        title="My Mission", tags=["solar"],
    )
    rt = MissionReference.from_dict(ref.to_dict())
    assert rt.mission_id == "m-1"
    assert rt.tags == ["solar"]


def test_mission_reference_rejects_absolute_path():
    ref = MissionReference(mission_id="m1", path="/abs/path.json")
    errs = ref.validate()
    assert any("workspace-relative" in e for e in errs)


# ---------------------------------------------------------------------------
# RouteReference / TimelineReference
# ---------------------------------------------------------------------------


def test_route_reference_round_trip():
    ref = RouteReference(name="r1", path="routes/r1.json", notes="x")
    rt = RouteReference.from_dict(ref.to_dict())
    assert rt.name == "r1"
    assert rt.notes == "x"


def test_timeline_reference_validates_fps():
    ref = TimelineReference(name="t1", path="timelines/t1.json", fps=0)
    errs = ref.validate()
    assert any("fps must be > 0" in e for e in errs)


def test_timeline_reference_default_fps_is_24():
    ref = TimelineReference(name="t1", path="timelines/t1.json")
    assert ref.fps == 24.0


# ---------------------------------------------------------------------------
# ProjectManifest
# ---------------------------------------------------------------------------


def test_manifest_default_is_empty_but_valid():
    m = ProjectManifest()
    assert m.validate() == []
    assert m.schema_version == PROJECT_MANIFEST_SCHEMA_VERSION


def test_manifest_round_trip_via_json():
    m = ProjectManifest(
        project_name="Demo",
        plugin_version="3.1.0",
        scale_mode="parsec_to_cm",
    )
    m.datasets.append(DatasetReference(name="Gaia", path="datasets/g.db"))
    m.missions.append(
        MissionReference(mission_id="m", path="missions/m.json"),
    )
    rt = ProjectManifest.from_json(m.to_json())
    assert rt.project_name == "Demo"
    assert rt.plugin_version == "3.1.0"
    assert len(rt.datasets) == 1
    assert len(rt.missions) == 1


def test_manifest_rejects_newer_schema_version():
    payload = {"schema_version": 999}
    with pytest.raises(ManifestError):
        ProjectManifest.from_dict(payload)


def test_manifest_handles_missing_optional_fields():
    payload = {"schema_version": 1}
    m = ProjectManifest.from_dict(payload)
    assert m.project_name == "Untitled UNAV Project"
    assert m.datasets == []


def test_manifest_validate_flags_duplicate_dataset_names():
    m = ProjectManifest()
    m.datasets.append(DatasetReference(name="Gaia", path="datasets/a.db"))
    m.datasets.append(DatasetReference(name="Gaia", path="datasets/b.db"))
    errs = m.validate()
    assert any("duplicate dataset name" in e for e in errs)


def test_manifest_validate_flags_duplicate_mission_ids():
    m = ProjectManifest()
    m.missions.append(MissionReference(mission_id="x", path="missions/a.json"))
    m.missions.append(MissionReference(mission_id="x", path="missions/b.json"))
    errs = m.validate()
    assert any("duplicate mission_id" in e for e in errs)


def test_manifest_find_helpers():
    m = ProjectManifest()
    m.datasets.append(DatasetReference(name="Gaia", path="datasets/g.db"))
    m.missions.append(MissionReference(mission_id="m", path="missions/m.json"))
    assert m.find_dataset("Gaia") is not None
    assert m.find_dataset("nope") is None
    assert m.find_mission("m") is not None
    assert m.find_mission("nope") is None


def test_manifest_overlays_and_science_round_trip():
    m = ProjectManifest()
    m.overlays = OverlaySettingsRef(settings={"show_grid": True})
    m.science_layers = ScienceSettingsRef(
        settings={"show_distance_shells": True},
    )
    rt = ProjectManifest.from_json(m.to_json())
    assert rt.overlays.settings == {"show_grid": True}
    assert rt.science_layers.settings == {"show_distance_shells": True}


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def test_save_and_load_manifest(tmp_path):
    m = ProjectManifest(project_name="WS", plugin_version="3.1.0")
    path = tmp_path / "project_manifest.json"
    save_manifest(m, str(path))
    assert path.is_file()
    rt = load_manifest(str(path))
    assert rt.project_name == "WS"
    assert rt.created_at_iso  # stamped on save
    assert rt.updated_at_iso


def test_save_manifest_rejects_invalid(tmp_path):
    m = ProjectManifest()
    m.datasets.append(DatasetReference(name="bad", path="/abs/path"))
    with pytest.raises(ManifestError):
        save_manifest(m, str(tmp_path / "manifest.json"))


def test_load_manifest_missing_file(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(str(tmp_path / "nope.json"))


def test_load_manifest_bad_json(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("not json", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(str(p))


def test_save_writes_atomically(tmp_path):
    """A save + immediate load should not fail; write is via
    temp+rename so no partial file exists if a crash
    happens mid-write. Black-box: just check the file
    exists and parses cleanly."""
    m = ProjectManifest()
    path = tmp_path / "manifest.json"
    save_manifest(m, str(path))
    contents = path.read_text(encoding="utf-8")
    json.loads(contents)  # no exception → valid JSON
    # No leftover .tmp file.
    assert not (tmp_path / "manifest.json.tmp").exists()


def test_manifest_filename_constant():
    assert PROJECT_MANIFEST_FILENAME == "project_manifest.json"
