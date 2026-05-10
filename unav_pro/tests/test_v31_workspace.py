"""v3.1 workspace tests."""

from __future__ import annotations

import os

import pytest

from project import (
    DEFAULT_WORKSPACE_SUBDIRS,
    DatasetReference,
    MissionReference,
    PROJECT_MANIFEST_FILENAME,
    RouteReference,
    TimelineReference,
    Workspace,
    WorkspaceError,
    create_workspace,
    open_workspace,
)


# ---------------------------------------------------------------------------
# create_workspace
# ---------------------------------------------------------------------------


def test_create_workspace_makes_full_tree(tmp_path):
    root = str(tmp_path / "MyProject")
    ws = create_workspace(root, project_name="My Demo")
    assert os.path.isdir(root)
    for sub in DEFAULT_WORKSPACE_SUBDIRS:
        assert os.path.isdir(os.path.join(root, sub))
    assert os.path.isfile(os.path.join(root, PROJECT_MANIFEST_FILENAME))
    assert ws.manifest.project_name == "My Demo"


def test_create_workspace_refuses_existing_manifest(tmp_path):
    root = str(tmp_path / "P")
    create_workspace(root)
    with pytest.raises(WorkspaceError):
        create_workspace(root)


def test_create_workspace_overwrite_replaces_manifest(tmp_path):
    root = str(tmp_path / "P")
    create_workspace(root, project_name="A")
    ws2 = create_workspace(root, project_name="B", overwrite=True)
    assert ws2.manifest.project_name == "B"


def test_create_workspace_stores_plugin_version(tmp_path):
    ws = create_workspace(
        str(tmp_path / "P"), plugin_version="3.1.0",
    )
    assert ws.manifest.plugin_version == "3.1.0"


# ---------------------------------------------------------------------------
# open_workspace
# ---------------------------------------------------------------------------


def test_open_existing_workspace(tmp_path):
    root = str(tmp_path / "P")
    created = create_workspace(root, project_name="X")
    opened = open_workspace(root)
    assert opened.manifest.project_name == "X"
    assert opened.root == created.root


def test_open_workspace_missing_dir(tmp_path):
    with pytest.raises(WorkspaceError):
        open_workspace(str(tmp_path / "does-not-exist"))


def test_open_workspace_missing_manifest(tmp_path):
    root = tmp_path / "no-manifest"
    root.mkdir()
    with pytest.raises(WorkspaceError):
        open_workspace(str(root))


# ---------------------------------------------------------------------------
# subdir helpers
# ---------------------------------------------------------------------------


def test_workspace_subdir_helpers(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    assert ws.datasets_dir().endswith("datasets")
    assert ws.cache_dir().endswith("cache")
    assert ws.missions_dir().endswith("missions")
    assert ws.routes_dir().endswith("routes")
    assert ws.exports_dir().endswith("exports")
    assert ws.overlays_dir().endswith("overlays")
    assert ws.timelines_dir().endswith("timelines")
    assert ws.notes_dir().endswith("notes")


def test_workspace_subdir_rejects_unknown(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    with pytest.raises(WorkspaceError):
        ws.subdir("not-a-real-subdir")


# ---------------------------------------------------------------------------
# absolute / relative path helpers
# ---------------------------------------------------------------------------


def test_absolute_path_resolves_relative(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    abs_path = ws.absolute_path("missions/foo.json")
    assert os.path.normpath(abs_path) == os.path.normpath(
        os.path.join(ws.root, "missions", "foo.json"),
    )


def test_absolute_path_refuses_absolute(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    with pytest.raises(WorkspaceError):
        ws.absolute_path("/etc/passwd")


def test_absolute_path_refuses_traversal(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    with pytest.raises(WorkspaceError):
        ws.absolute_path("../escape.txt")


def test_relative_path_round_trip(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    abs_path = ws.absolute_path("missions/foo.json")
    rel = ws.relative_path(abs_path)
    assert rel == "missions/foo.json"


def test_relative_path_refuses_outside(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    outside = str(tmp_path / "elsewhere" / "x.txt")
    with pytest.raises(WorkspaceError):
        ws.relative_path(outside)


# ---------------------------------------------------------------------------
# add_* / remove_* references
# ---------------------------------------------------------------------------


def test_add_mission_reference(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    ws.add_mission(MissionReference(
        mission_id="m1", path="missions/m1.json",
    ))
    assert ws.manifest.find_mission("m1") is not None


def test_add_mission_rejects_duplicate(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    ws.add_mission(MissionReference(mission_id="m1", path="missions/m1.json"))
    with pytest.raises(WorkspaceError):
        ws.add_mission(MissionReference(
            mission_id="m1", path="missions/m1.json",
        ))


def test_add_dataset_rejects_invalid_path(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    with pytest.raises(WorkspaceError):
        ws.add_dataset(DatasetReference(name="bad", path="/abs/x.db"))


def test_add_route_and_timeline(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    ws.add_route(RouteReference(name="r1", path="routes/r1.json"))
    ws.add_timeline(TimelineReference(
        name="t1", path="timelines/t1.json", frames=120, fps=24.0,
    ))
    assert len(ws.manifest.routes) == 1
    assert len(ws.manifest.timelines) == 1


def test_remove_mission_returns_false_when_missing(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    assert ws.remove_mission("missing") is False


def test_remove_mission_drops_existing(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    ws.add_mission(MissionReference(mission_id="x", path="missions/x.json"))
    assert ws.remove_mission("x") is True
    assert ws.manifest.find_mission("x") is None


# ---------------------------------------------------------------------------
# save / reload
# ---------------------------------------------------------------------------


def test_save_persists_manifest_changes(tmp_path):
    ws = create_workspace(str(tmp_path / "P"), project_name="Old")
    ws.manifest.project_name = "New"
    ws.save()
    rt = open_workspace(ws.root)
    assert rt.manifest.project_name == "New"


def test_reload_picks_up_external_changes(tmp_path):
    """Simulate an external editor changing the manifest."""
    ws = create_workspace(str(tmp_path / "P"), project_name="A")
    # Edit on disk via a fresh open + save.
    other = open_workspace(ws.root)
    other.manifest.project_name = "B"
    other.save()
    ws.reload()
    assert ws.manifest.project_name == "B"


# ---------------------------------------------------------------------------
# is_intact / list_present_subdirs
# ---------------------------------------------------------------------------


def test_is_intact_after_create(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    assert ws.is_intact() is True


def test_is_intact_returns_false_when_subdir_missing(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    os.rmdir(ws.cache_dir())
    assert ws.is_intact() is False


def test_ensure_structure_recreates_missing(tmp_path):
    ws = create_workspace(str(tmp_path / "P"))
    os.rmdir(ws.cache_dir())
    created = ws.ensure_structure()
    assert "cache" in created
    assert ws.is_intact() is True


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


def test_summary_renders_basic_lines(tmp_path):
    ws = create_workspace(str(tmp_path / "P"), project_name="Demo")
    ws.add_mission(MissionReference(mission_id="m", path="missions/m.json"))
    ws.add_dataset(DatasetReference(name="ds", path="datasets/d.db"))
    s = ws.summary()
    assert s.project_name == "Demo"
    assert s.mission_count == 1
    assert s.dataset_count == 1
    text = s.render()
    assert "Demo" in text
    assert "Missions: 1" in text


def test_summary_counts_notes(tmp_path):
    from project import NotesStore
    ws = create_workspace(str(tmp_path / "P"))
    store = NotesStore(ws.notes_dir())
    store.write_project_note("Hello")
    assert ws.summary().notes_count == 1
