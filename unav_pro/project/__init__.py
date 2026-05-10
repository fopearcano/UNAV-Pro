"""UNAV Pro v3.1 project package.

The v3.1 project layer adds **workspace-based project
organisation** on top of the v0.1 → v3.0 stack. A workspace
is a directory tree the artist owns, containing the
manifest, datasets, cache, missions, routes, exports,
overlays, timelines, and notes for one production
project.

This package is **pure stdlib** at runtime; no Cinema 4D
dependency. Tests construct workspaces in ``tmp_path`` and
exercise every API without a host.

Modules:

* :mod:`unav_pro.project.project_manifest` — the manifest
  schema (``ProjectManifest``) + JSON I/O.
* :mod:`unav_pro.project.workspace` — the on-disk
  directory layout + create / open / save / summary
  helpers.
* :mod:`unav_pro.project.notes` — markdown-based notes
  system (project / mission / dataset notes).

The c4d-bound integration (the dialog's *Project* panel,
scene-hierarchy materialisation) lives elsewhere and reads
this package for the data shape.
"""

from __future__ import annotations

from .project_manifest import (
    PROJECT_MANIFEST_FILENAME,
    PROJECT_MANIFEST_SCHEMA_VERSION,
    DatasetReference,
    MissionReference,
    OverlaySettingsRef,
    ProjectManifest,
    RouteReference,
    ScienceSettingsRef,
    TimelineReference,
    load_manifest,
    save_manifest,
)
from .workspace import (
    DEFAULT_WORKSPACE_SUBDIRS,
    WORKSPACE_SUBDIR_CACHE,
    WORKSPACE_SUBDIR_DATASETS,
    WORKSPACE_SUBDIR_EXPORTS,
    WORKSPACE_SUBDIR_MISSIONS,
    WORKSPACE_SUBDIR_NOTES,
    WORKSPACE_SUBDIR_OVERLAYS,
    WORKSPACE_SUBDIR_ROUTES,
    WORKSPACE_SUBDIR_TIMELINES,
    Workspace,
    WorkspaceError,
    WorkspaceSummary,
    create_workspace,
    open_workspace,
)
from .notes import (
    NOTE_KIND_DATASET,
    NOTE_KIND_MISSION,
    NOTE_KIND_PROJECT,
    NoteEntry,
    NotesStore,
    relative_path_for_note,
)
from .mission_packs import (
    COLLISION_STRATEGIES,
    MISSION_PACK_SCHEMA_VERSION,
    ImportReport,
    MissionPack,
    MissionPackError,
    build_pack_from_missions,
    import_pack,
    read_pack,
    write_pack,
)
from .panel_actions import (
    PanelActionError,
    create_workspace_action,
    export_path_for_action,
    open_folder_action_path,
    open_workspace_action,
    save_workspace_action,
    summary_action,
    workspace_export_subdir,
)

__all__ = [
    # manifest
    "PROJECT_MANIFEST_FILENAME", "PROJECT_MANIFEST_SCHEMA_VERSION",
    "DatasetReference", "MissionReference", "RouteReference",
    "OverlaySettingsRef", "ScienceSettingsRef", "TimelineReference",
    "ProjectManifest", "load_manifest", "save_manifest",
    # workspace
    "Workspace", "WorkspaceError", "WorkspaceSummary",
    "create_workspace", "open_workspace",
    "DEFAULT_WORKSPACE_SUBDIRS",
    "WORKSPACE_SUBDIR_CACHE", "WORKSPACE_SUBDIR_DATASETS",
    "WORKSPACE_SUBDIR_EXPORTS", "WORKSPACE_SUBDIR_MISSIONS",
    "WORKSPACE_SUBDIR_NOTES", "WORKSPACE_SUBDIR_OVERLAYS",
    "WORKSPACE_SUBDIR_ROUTES", "WORKSPACE_SUBDIR_TIMELINES",
    # notes
    "NoteEntry", "NotesStore",
    "NOTE_KIND_DATASET", "NOTE_KIND_MISSION", "NOTE_KIND_PROJECT",
    "relative_path_for_note",
    # mission packs
    "MissionPack", "MissionPackError", "ImportReport",
    "MISSION_PACK_SCHEMA_VERSION", "COLLISION_STRATEGIES",
    "build_pack_from_missions", "import_pack",
    "read_pack", "write_pack",
    # panel actions
    "PanelActionError",
    "create_workspace_action", "open_workspace_action",
    "save_workspace_action", "summary_action",
    "open_folder_action_path", "export_path_for_action",
    "workspace_export_subdir",
]
