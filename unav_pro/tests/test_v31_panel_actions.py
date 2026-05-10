"""v3.1 panel-action tests.

The panel-action layer is the pure-Python facade the
dialog's *Project* panel calls. Tests here drive the
facade with no UI involved.
"""

from __future__ import annotations

import os

import pytest

from project import (
    PanelActionError,
    PROJECT_MANIFEST_FILENAME,
    create_workspace_action,
    export_path_for_action,
    open_folder_action_path,
    open_workspace_action,
    save_workspace_action,
    summary_action,
    workspace_export_subdir,
)


# ---------------------------------------------------------------------------
# create / open / save
# ---------------------------------------------------------------------------


def test_create_action_builds_workspace(tmp_path):
    ws = create_workspace_action(
        str(tmp_path / "P"),
        project_name="X", plugin_version="3.1.0",
    )
    assert ws.manifest.project_name == "X"
    assert os.path.isfile(os.path.join(ws.root, PROJECT_MANIFEST_FILENAME))


def test_create_action_rejects_blank_path(tmp_path):
    with pytest.raises(PanelActionError):
        create_workspace_action("")


def test_create_action_translates_workspace_error(tmp_path):
    create_workspace_action(str(tmp_path / "P"))
    with pytest.raises(PanelActionError):
        create_workspace_action(str(tmp_path / "P"))


def test_open_action_opens_existing(tmp_path):
    create_workspace_action(str(tmp_path / "P"), project_name="Demo")
    ws = open_workspace_action(str(tmp_path / "P"))
    assert ws.manifest.project_name == "Demo"


def test_open_action_rejects_blank_path():
    with pytest.raises(PanelActionError):
        open_workspace_action("")


def test_open_action_missing_workspace_raises(tmp_path):
    with pytest.raises(PanelActionError):
        open_workspace_action(str(tmp_path / "missing"))


def test_save_action_persists(tmp_path):
    ws = create_workspace_action(str(tmp_path / "P"), project_name="A")
    ws.manifest.project_name = "B"
    save_workspace_action(ws)
    fresh = open_workspace_action(ws.root)
    assert fresh.manifest.project_name == "B"


def test_save_action_no_workspace_raises():
    with pytest.raises(PanelActionError):
        save_workspace_action(None)


# ---------------------------------------------------------------------------
# Summary / folder
# ---------------------------------------------------------------------------


def test_summary_action_returns_summary(tmp_path):
    ws = create_workspace_action(str(tmp_path / "P"))
    s = summary_action(ws)
    assert s.workspace_root == ws.root


def test_summary_action_no_workspace_raises():
    with pytest.raises(PanelActionError):
        summary_action(None)


def test_open_folder_returns_root(tmp_path):
    ws = create_workspace_action(str(tmp_path / "P"))
    assert open_folder_action_path(ws) == ws.root


def test_open_folder_no_workspace_raises():
    with pytest.raises(PanelActionError):
        open_folder_action_path(None)


# ---------------------------------------------------------------------------
# Export integration
# ---------------------------------------------------------------------------


def test_workspace_export_subdir_returns_root_when_blank(tmp_path):
    ws = create_workspace_action(str(tmp_path / "P"))
    target = workspace_export_subdir(ws)
    assert os.path.isdir(target)
    assert os.path.normpath(target) == os.path.normpath(ws.exports_dir())


def test_workspace_export_subdir_creates_subpath(tmp_path):
    ws = create_workspace_action(str(tmp_path / "P"))
    target = workspace_export_subdir(ws, subdir="cinematic_v1")
    assert os.path.isdir(target)
    assert "cinematic_v1" in target


def test_workspace_export_subdir_rejects_absolute(tmp_path):
    ws = create_workspace_action(str(tmp_path / "P"))
    with pytest.raises(PanelActionError):
        workspace_export_subdir(ws, subdir="/etc/passwd")


def test_workspace_export_subdir_rejects_traversal(tmp_path):
    ws = create_workspace_action(str(tmp_path / "P"))
    with pytest.raises(PanelActionError):
        workspace_export_subdir(ws, subdir="../escape")


def test_workspace_export_subdir_no_workspace_raises():
    with pytest.raises(PanelActionError):
        workspace_export_subdir(None)


def test_export_path_for_action_resolves_filename(tmp_path):
    ws = create_workspace_action(str(tmp_path / "P"))
    p = export_path_for_action(ws, "camera_path.json")
    assert p.endswith("camera_path.json")
    assert os.path.dirname(p) == os.path.normpath(ws.exports_dir())


def test_export_path_for_action_rejects_separators(tmp_path):
    ws = create_workspace_action(str(tmp_path / "P"))
    with pytest.raises(PanelActionError):
        export_path_for_action(ws, "subdir/file.json")


def test_export_path_for_action_rejects_empty_filename(tmp_path):
    ws = create_workspace_action(str(tmp_path / "P"))
    with pytest.raises(PanelActionError):
        export_path_for_action(ws, "")


def test_export_path_with_subdir(tmp_path):
    ws = create_workspace_action(str(tmp_path / "P"))
    p = export_path_for_action(ws, "f.json", subdir="cinematic")
    assert "cinematic" in p
    assert os.path.dirname(os.path.dirname(p)) == os.path.normpath(ws.exports_dir())
