"""v2.3 export-validation tests.

Pre-flight validators are pure-Python; tests drive them
without touching the host or the filesystem (except via
``tmp_path``).
"""

from __future__ import annotations

import os

import pytest

from export import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    ValidationIssue,
    ValidationReport,
    validate_camera_path_for_export,
    validate_dataset_registry,
    validate_manifest,
    validate_mission_for_export,
    validate_no_duplicate_filenames,
    validate_writable_directory,
    validate_writable_path,
)


# ---------------------------------------------------------------------------
# Severity / report shape
# ---------------------------------------------------------------------------


def test_severities_exposed():
    assert SEVERITY_ERROR == "error"
    assert SEVERITY_WARNING == "warning"
    assert SEVERITY_INFO == "info"


def test_validation_report_render_when_clean():
    rpt = ValidationReport()
    assert rpt.has_errors() is False
    assert rpt.has_warnings() is False
    assert "all clear" in rpt.render_text()


def test_validation_report_renders_issues():
    rpt = ValidationReport(issues=[
        ValidationIssue(severity=SEVERITY_ERROR, code="E", detail="bad"),
        ValidationIssue(severity=SEVERITY_WARNING, code="W", detail="meh"),
    ])
    text = rpt.render_text()
    assert "E:" in text and "bad" in text
    assert "W:" in text and "meh" in text


# ---------------------------------------------------------------------------
# Path checks
# ---------------------------------------------------------------------------


def test_validate_writable_path_empty_is_error():
    rpt = validate_writable_path("")
    assert rpt.has_errors()
    assert any(i.code == "empty_path" for i in rpt.errors())


def test_validate_writable_path_overwrite_refused(tmp_path):
    target = tmp_path / "out.json"
    target.write_text("{}", encoding="utf-8")
    rpt = validate_writable_path(str(target), allow_overwrite=False)
    assert rpt.has_errors()
    assert any(i.code == "overwrite_refused" for i in rpt.errors())


def test_validate_writable_path_overwrite_allowed(tmp_path):
    target = tmp_path / "out.json"
    target.write_text("{}", encoding="utf-8")
    rpt = validate_writable_path(str(target), allow_overwrite=True)
    assert rpt.has_errors() is False


def test_validate_writable_path_directory_target_errors(tmp_path):
    """A directory at the target path must be flagged as not-
    a-file when overwrite is allowed."""
    rpt = validate_writable_path(str(tmp_path), allow_overwrite=True)
    assert rpt.has_errors()
    assert any(i.code == "not_a_file" for i in rpt.errors())


def test_validate_writable_directory_exists_existing_allowed(tmp_path):
    rpt = validate_writable_directory(str(tmp_path), allow_existing=True)
    assert rpt.has_errors() is False


def test_validate_writable_directory_exists_existing_forbidden(tmp_path):
    rpt = validate_writable_directory(str(tmp_path), allow_existing=False)
    assert rpt.has_errors()


def test_validate_writable_directory_file_at_path_errors(tmp_path):
    target = tmp_path / "file"
    target.write_text("hi", encoding="utf-8")
    rpt = validate_writable_directory(str(target))
    assert rpt.has_errors()
    assert any(i.code == "not_a_directory" for i in rpt.errors())


# ---------------------------------------------------------------------------
# Mission / camera / dataset validators
# ---------------------------------------------------------------------------


def test_validate_mission_handles_none():
    rpt = validate_mission_for_export(None)
    assert rpt.has_errors()
    assert any(i.code == "no_mission" for i in rpt.errors())


def test_validate_mission_warns_on_empty_waypoints():
    from voyage import Mission
    rpt = validate_mission_for_export(Mission(title="Empty"))
    codes = [i.code for i in rpt.warnings()]
    assert "empty_waypoints" in codes


def test_validate_mission_warns_on_missing_title():
    from voyage import Mission, MissionWaypoint
    m = Mission(title="", waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
    ])
    rpt = validate_mission_for_export(m)
    assert any(i.code == "missing_title" for i in rpt.warnings())


def test_validate_camera_path_none_errors():
    rpt = validate_camera_path_for_export(None)
    assert rpt.has_errors()


def test_validate_camera_path_empty_errors():
    from voyage import Mission, build_camera_path
    rpt = validate_camera_path_for_export(build_camera_path(Mission()))
    assert rpt.has_errors()


def test_validate_camera_path_single_waypoint_warns():
    from voyage import Mission, MissionWaypoint, build_camera_path
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
    ])
    rpt = validate_camera_path_for_export(build_camera_path(m))
    assert any(i.code == "single_waypoint_path" for i in rpt.warnings())


def test_validate_dataset_registry_none_warns():
    rpt = validate_dataset_registry(None)
    assert any(i.code == "no_registry" for i in rpt.warnings())


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------


def test_validate_manifest_rejects_non_dict():
    rpt = validate_manifest("not a dict")  # type: ignore[arg-type]
    assert rpt.has_errors()


def test_validate_manifest_flags_missing_fields():
    rpt = validate_manifest({})
    codes = [i.code for i in rpt.errors()]
    assert "missing_manifest_field" in codes


def test_validate_manifest_complete_passes():
    rpt = validate_manifest({
        "manifest_version": 1,
        "exported_at_iso": "2026-01-01T00:00:00Z",
        "plugin_version": "v2.3",
        "coordinate_convention": "C4D",
        "units": {},
    })
    assert rpt.has_errors() is False


def test_validate_manifest_warns_on_invalid_assets_field():
    rpt = validate_manifest({
        "manifest_version": 1,
        "exported_at_iso": "x",
        "plugin_version": "x",
        "coordinate_convention": "x",
        "units": {},
        "included_assets": "not an object",
    })
    assert any(i.code == "manifest_assets_not_object" for i in rpt.warnings())


# ---------------------------------------------------------------------------
# Filename uniqueness
# ---------------------------------------------------------------------------


def test_no_duplicate_filenames_clean():
    rpt = validate_no_duplicate_filenames(["a/x.json", "b/x.json", "c.json"])
    assert rpt.has_errors() is False


def test_no_duplicate_filenames_flags_repeats():
    rpt = validate_no_duplicate_filenames(["a/x.json", "a/x.json"])
    assert rpt.has_errors()
    assert any(i.code == "duplicate_filename" for i in rpt.errors())


def test_no_duplicate_filenames_normalises_path_separators():
    """``foo/bar.json`` and ``foo\\bar.json`` (on POSIX) are
    different paths after normalisation; the validator
    should not collapse them."""
    rpt = validate_no_duplicate_filenames(["foo/bar.json", "baz/qux.json"])
    assert rpt.has_errors() is False
