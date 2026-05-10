"""v3.1 workspace: the on-disk directory layout for an
UNAV Pro project.

A workspace is a directory tree the artist owns, containing
the manifest plus organised subdirectories for datasets,
cache, missions, routes, exports, overlays, timelines, and
notes:

::

    UNAV_Project/
    ├── project_manifest.json
    ├── datasets/
    ├── cache/
    ├── missions/
    ├── routes/
    ├── exports/
    ├── overlays/
    ├── timelines/
    └── notes/

This module provides:

* ``create_workspace(root, *, project_name=...)`` — build
  the directory tree + write the initial manifest.
* ``open_workspace(root)`` — load the manifest from an
  existing tree.
* ``Workspace`` — the in-memory facade with helpers for
  listing missions, computing paths, reloading.

All paths the workspace returns are absolute and use the
host OS's separator. References inside the manifest stay
**workspace-relative** so a workspace stays portable.

Pure stdlib; no Cinema 4D imports.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .project_manifest import (
    PROJECT_MANIFEST_FILENAME,
    DatasetReference,
    ManifestError,
    MissionReference,
    OverlaySettingsRef,
    ProjectManifest,
    RouteReference,
    ScienceSettingsRef,
    TimelineReference,
    load_manifest,
    save_manifest,
)


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------


WORKSPACE_SUBDIR_DATASETS: str = "datasets"
WORKSPACE_SUBDIR_CACHE: str = "cache"
WORKSPACE_SUBDIR_MISSIONS: str = "missions"
WORKSPACE_SUBDIR_ROUTES: str = "routes"
WORKSPACE_SUBDIR_EXPORTS: str = "exports"
WORKSPACE_SUBDIR_OVERLAYS: str = "overlays"
WORKSPACE_SUBDIR_TIMELINES: str = "timelines"
WORKSPACE_SUBDIR_NOTES: str = "notes"

#: The eight subdirectories every workspace contains.
DEFAULT_WORKSPACE_SUBDIRS: Tuple[str, ...] = (
    WORKSPACE_SUBDIR_DATASETS,
    WORKSPACE_SUBDIR_CACHE,
    WORKSPACE_SUBDIR_MISSIONS,
    WORKSPACE_SUBDIR_ROUTES,
    WORKSPACE_SUBDIR_EXPORTS,
    WORKSPACE_SUBDIR_OVERLAYS,
    WORKSPACE_SUBDIR_TIMELINES,
    WORKSPACE_SUBDIR_NOTES,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WorkspaceError(RuntimeError):
    """Raised for workspace-level failures (missing
    directory, malformed manifest, refusal to overwrite)."""


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


@dataclass
class WorkspaceSummary:
    """Snapshot rendered by the dialog's *Project Summary*
    button. Pure data; the formatter lives below."""

    project_name: str = ""
    project_description: str = ""
    plugin_version: str = ""
    scale_mode: str = ""
    dataset_count: int = 0
    enabled_dataset_count: int = 0
    mission_count: int = 0
    route_count: int = 0
    timeline_count: int = 0
    workspace_root: str = ""
    notes_count: int = 0
    last_updated_iso: str = ""

    def render(self) -> str:
        lines: List[str] = []
        lines.append(f"Project: {self.project_name}")
        if self.project_description:
            lines.append(f"  '{self.project_description}'")
        lines.append(f"Workspace: {self.workspace_root}")
        if self.plugin_version:
            lines.append(f"Plugin version: {self.plugin_version}")
        if self.scale_mode:
            lines.append(f"Scale: {self.scale_mode}")
        lines.append(
            f"Datasets: {self.enabled_dataset_count} enabled / "
            f"{self.dataset_count} total"
        )
        lines.append(f"Missions: {self.mission_count}")
        lines.append(f"Routes:   {self.route_count}")
        lines.append(f"Timelines: {self.timeline_count}")
        lines.append(f"Notes:    {self.notes_count}")
        if self.last_updated_iso:
            lines.append(f"Last saved: {self.last_updated_iso}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------


class Workspace:
    """In-memory facade over a workspace directory tree.

    Construct via ``create_workspace`` or ``open_workspace``;
    the constructor is private-ish (it accepts a root + an
    already-validated manifest, which the helpers produce).

    The facade is intentionally **shallow** — it doesn't
    cache catalog rows, mission objects, or route objects.
    Heavy data lives in the existing v0.x subsystems
    (``DatasetRegistry``, ``MissionManager``, etc.); the
    workspace layer just hands them workspace-relative
    paths to read from / write to.
    """

    def __init__(self, root: str, manifest: ProjectManifest) -> None:
        self._root = os.path.abspath(root)
        self._manifest = manifest

    # ---------------------------------------------------- properties
    @property
    def root(self) -> str:
        return self._root

    @property
    def manifest(self) -> ProjectManifest:
        return self._manifest

    @property
    def manifest_path(self) -> str:
        return os.path.join(self._root, PROJECT_MANIFEST_FILENAME)

    # ---------------------------------------------------- subdirs
    def subdir(self, name: str) -> str:
        """Absolute path to a workspace subdirectory.

        ``name`` must be one of ``DEFAULT_WORKSPACE_SUBDIRS``
        — passing anything else raises ``WorkspaceError`` so
        typos can't write outside the documented layout."""
        if name not in DEFAULT_WORKSPACE_SUBDIRS:
            raise WorkspaceError(
                f"unknown workspace subdir: {name!r}; valid names: "
                + ", ".join(DEFAULT_WORKSPACE_SUBDIRS)
            )
        return os.path.join(self._root, name)

    def datasets_dir(self) -> str:
        return self.subdir(WORKSPACE_SUBDIR_DATASETS)

    def cache_dir(self) -> str:
        return self.subdir(WORKSPACE_SUBDIR_CACHE)

    def missions_dir(self) -> str:
        return self.subdir(WORKSPACE_SUBDIR_MISSIONS)

    def routes_dir(self) -> str:
        return self.subdir(WORKSPACE_SUBDIR_ROUTES)

    def exports_dir(self) -> str:
        return self.subdir(WORKSPACE_SUBDIR_EXPORTS)

    def overlays_dir(self) -> str:
        return self.subdir(WORKSPACE_SUBDIR_OVERLAYS)

    def timelines_dir(self) -> str:
        return self.subdir(WORKSPACE_SUBDIR_TIMELINES)

    def notes_dir(self) -> str:
        return self.subdir(WORKSPACE_SUBDIR_NOTES)

    # ---------------------------------------------------- path helpers
    def absolute_path(self, relpath: str) -> str:
        """Resolve a workspace-relative path to an absolute
        one. Refuses absolute inputs and ``..`` traversal so
        a malicious manifest can't escape the workspace."""
        if os.path.isabs(relpath):
            raise WorkspaceError(
                f"refusing absolute path inside workspace: {relpath}"
            )
        norm = os.path.normpath(relpath).replace("\\", "/")
        if norm.startswith("../") or norm == ".." or "/.." in norm:
            raise WorkspaceError(
                f"refusing path that climbs above workspace root: {relpath}"
            )
        return os.path.normpath(os.path.join(self._root, relpath))

    def relative_path(self, absolute: str) -> str:
        """Inverse of :meth:`absolute_path`. Returns a
        forward-slashed workspace-relative path. Raises if
        ``absolute`` is outside the workspace root."""
        try:
            rel = os.path.relpath(
                os.path.abspath(absolute), start=self._root,
            )
        except ValueError as exc:  # cross-drive on Windows
            raise WorkspaceError(
                f"cannot relativise {absolute} against workspace {self._root}"
            ) from exc
        rel = rel.replace("\\", "/")
        if rel.startswith("..") or os.path.isabs(rel):
            raise WorkspaceError(
                f"path is outside the workspace: {absolute}"
            )
        return rel

    # ---------------------------------------------------- mutation
    def reload(self) -> None:
        """Re-read the manifest from disk. Used after a
        cooperative external editor changed the file."""
        self._manifest = load_manifest(self.manifest_path)

    def save(self) -> None:
        """Persist the current manifest atomically."""
        save_manifest(self._manifest, self.manifest_path)

    # ---------------------------------------------------- references
    def add_dataset(self, ref: DatasetReference) -> DatasetReference:
        if self._manifest.find_dataset(ref.name) is not None:
            raise WorkspaceError(
                f"dataset already in manifest: {ref.name}"
            )
        errs = ref.validate()
        if errs:
            raise WorkspaceError(
                "dataset reference failed validation:\n  - "
                + "\n  - ".join(errs)
            )
        self._manifest.datasets.append(ref)
        return ref

    def add_mission(self, ref: MissionReference) -> MissionReference:
        if self._manifest.find_mission(ref.mission_id) is not None:
            raise WorkspaceError(
                f"mission already in manifest: {ref.mission_id}"
            )
        errs = ref.validate()
        if errs:
            raise WorkspaceError(
                "mission reference failed validation:\n  - "
                + "\n  - ".join(errs)
            )
        self._manifest.missions.append(ref)
        return ref

    def add_route(self, ref: RouteReference) -> RouteReference:
        for existing in self._manifest.routes:
            if existing.name == ref.name:
                raise WorkspaceError(
                    f"route already in manifest: {ref.name}"
                )
        errs = ref.validate()
        if errs:
            raise WorkspaceError(
                "route reference failed validation:\n  - "
                + "\n  - ".join(errs)
            )
        self._manifest.routes.append(ref)
        return ref

    def add_timeline(self, ref: TimelineReference) -> TimelineReference:
        for existing in self._manifest.timelines:
            if existing.name == ref.name:
                raise WorkspaceError(
                    f"timeline already in manifest: {ref.name}"
                )
        errs = ref.validate()
        if errs:
            raise WorkspaceError(
                "timeline reference failed validation:\n  - "
                + "\n  - ".join(errs)
            )
        self._manifest.timelines.append(ref)
        return ref

    def remove_mission(self, mission_id: str) -> bool:
        before = len(self._manifest.missions)
        self._manifest.missions = [
            m for m in self._manifest.missions
            if m.mission_id != mission_id
        ]
        return len(self._manifest.missions) != before

    def remove_dataset(self, name: str) -> bool:
        before = len(self._manifest.datasets)
        self._manifest.datasets = [
            d for d in self._manifest.datasets if d.name != name
        ]
        return len(self._manifest.datasets) != before

    # ---------------------------------------------------- structure
    def ensure_structure(self) -> List[str]:
        """Create any missing subdirectories. Returns the
        list of subdirectory names that were created (empty
        when the workspace was already complete)."""
        created: List[str] = []
        for sub in DEFAULT_WORKSPACE_SUBDIRS:
            target = os.path.join(self._root, sub)
            if not os.path.isdir(target):
                os.makedirs(target, exist_ok=True)
                created.append(sub)
        return created

    def list_present_subdirs(self) -> List[str]:
        """Subset of ``DEFAULT_WORKSPACE_SUBDIRS`` that
        exists on disk. Used by the diagnostics panel."""
        return [
            sub for sub in DEFAULT_WORKSPACE_SUBDIRS
            if os.path.isdir(os.path.join(self._root, sub))
        ]

    def is_intact(self) -> bool:
        """True iff the manifest exists + every default
        subdirectory exists."""
        if not os.path.isfile(self.manifest_path):
            return False
        return len(self.list_present_subdirs()) == len(DEFAULT_WORKSPACE_SUBDIRS)

    # ---------------------------------------------------- summary
    def summary(self) -> WorkspaceSummary:
        notes_root = self.notes_dir()
        notes_count = 0
        if os.path.isdir(notes_root):
            for _root, _dirs, files in os.walk(notes_root):
                notes_count += sum(
                    1 for f in files
                    if f.lower().endswith((".md", ".txt"))
                )
        return WorkspaceSummary(
            project_name=self._manifest.project_name,
            project_description=self._manifest.project_description,
            plugin_version=self._manifest.plugin_version,
            scale_mode=self._manifest.scale_mode,
            dataset_count=len(self._manifest.datasets),
            enabled_dataset_count=sum(
                1 for d in self._manifest.datasets if d.enabled
            ),
            mission_count=len(self._manifest.missions),
            route_count=len(self._manifest.routes),
            timeline_count=len(self._manifest.timelines),
            workspace_root=self._root,
            notes_count=notes_count,
            last_updated_iso=self._manifest.updated_at_iso,
        )

    def __repr__(self) -> str:
        return f"<Workspace root={self._root!r} manifest={self._manifest.project_name!r}>"


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def create_workspace(
    root: str,
    *,
    project_name: str = "Untitled UNAV Project",
    project_description: str = "",
    plugin_version: str = "",
    scale_mode: str = "parsec_to_cm",
    overwrite: bool = False,
) -> Workspace:
    """Create a fresh workspace directory tree at ``root``.

    Behaviour:

    * If ``root`` doesn't exist → it's created.
    * If ``root`` exists, is empty, has no manifest → fine.
    * If ``root`` already contains a manifest:
      * ``overwrite=False`` (default): raise
        ``WorkspaceError``. The artist must explicitly
        opt in to overwrite.
      * ``overwrite=True``: the existing manifest is
        replaced; existing data files are left intact.

    Returns the freshly opened ``Workspace`` instance with
    the manifest already saved to disk.
    """
    abs_root = os.path.abspath(root)
    _ensure_dir(abs_root)
    manifest_path = os.path.join(abs_root, PROJECT_MANIFEST_FILENAME)
    if os.path.isfile(manifest_path) and not overwrite:
        raise WorkspaceError(
            f"workspace already exists at {abs_root}; pass "
            "overwrite=True to replace its manifest"
        )
    for sub in DEFAULT_WORKSPACE_SUBDIRS:
        _ensure_dir(os.path.join(abs_root, sub))
    manifest = ProjectManifest(
        project_name=project_name,
        project_description=project_description,
        plugin_version=plugin_version,
        scale_mode=scale_mode,
    )
    save_manifest(manifest, manifest_path)
    return Workspace(abs_root, manifest)


def open_workspace(root: str) -> Workspace:
    """Open an existing workspace at ``root``. Raises
    ``WorkspaceError`` if the manifest is missing or
    malformed."""
    abs_root = os.path.abspath(root)
    if not os.path.isdir(abs_root):
        raise WorkspaceError(f"workspace directory does not exist: {abs_root}")
    manifest_path = os.path.join(abs_root, PROJECT_MANIFEST_FILENAME)
    if not os.path.isfile(manifest_path):
        raise WorkspaceError(
            f"no project_manifest.json in {abs_root}; this is not a "
            "v3.1 workspace"
        )
    try:
        manifest = load_manifest(manifest_path)
    except ManifestError as exc:
        raise WorkspaceError(f"manifest at {manifest_path} is invalid: {exc}") from exc
    return Workspace(abs_root, manifest)
