"""v3.1 Project-panel actions.

The dialog's *Project* panel surfaces six buttons:

* **Create Workspace…** — pick a directory + project
  name, build the tree, save the manifest.
* **Open Workspace…** — pick a directory, load the
  manifest.
* **Save Workspace** — persist the in-memory manifest.
* **Project Summary** — render the
  ``WorkspaceSummary``.
* **Open Project Folder** — reveal the workspace root
  in the host OS file browser.
* **Notes** — open the project notes file in the
  default editor.

This module is the **pure-Python facade** the dialog
calls. Each function takes plain inputs (paths, strings)
and returns plain outputs (``Workspace``, str). The
dialog handles the OS-level "show file dialog", "reveal
in Finder", "open in editor" parts.

Keeping the facade pure means tests exercise the
workspace lifecycle without faking any UI primitives.
"""

from __future__ import annotations

import os
from typing import Optional

from .notes import NotesStore
from .project_manifest import ManifestError
from .workspace import (
    WORKSPACE_SUBDIR_EXPORTS,
    Workspace,
    WorkspaceError,
    WorkspaceSummary,
    create_workspace,
    open_workspace,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PanelActionError(RuntimeError):
    """Raised when a panel action fails. Carries a short
    human-readable message the dialog renders in the
    status line."""


# ---------------------------------------------------------------------------
# Create / open / save
# ---------------------------------------------------------------------------


def create_workspace_action(
    root: str,
    *,
    project_name: str = "Untitled UNAV Project",
    project_description: str = "",
    plugin_version: str = "",
    overwrite: bool = False,
) -> Workspace:
    """Build a fresh workspace at ``root``. Wraps
    ``create_workspace`` and translates errors into
    ``PanelActionError`` so the dialog can rely on a
    single exception type."""
    if not root:
        raise PanelActionError("workspace path is empty")
    try:
        return create_workspace(
            root,
            project_name=project_name,
            project_description=project_description,
            plugin_version=plugin_version,
            overwrite=overwrite,
        )
    except (WorkspaceError, ManifestError, OSError) as exc:
        raise PanelActionError(f"create failed: {exc}") from exc


def open_workspace_action(root: str) -> Workspace:
    """Open the workspace at ``root``. Translates the
    underlying errors into a single ``PanelActionError``."""
    if not root:
        raise PanelActionError("workspace path is empty")
    try:
        return open_workspace(root)
    except (WorkspaceError, ManifestError, OSError) as exc:
        raise PanelActionError(f"open failed: {exc}") from exc


def save_workspace_action(workspace: Optional[Workspace]) -> None:
    """Persist the workspace's manifest. Raises
    ``PanelActionError`` when no workspace is active or
    the save fails."""
    if workspace is None:
        raise PanelActionError("no active workspace to save")
    try:
        workspace.save()
    except (WorkspaceError, ManifestError, OSError) as exc:
        raise PanelActionError(f"save failed: {exc}") from exc


def summary_action(workspace: Optional[Workspace]) -> WorkspaceSummary:
    """Render a ``WorkspaceSummary`` for the dialog's
    *Project Summary* button."""
    if workspace is None:
        raise PanelActionError("no active workspace")
    return workspace.summary()


# ---------------------------------------------------------------------------
# Folder / notes path helpers
# ---------------------------------------------------------------------------


def open_folder_action_path(workspace: Optional[Workspace]) -> str:
    """Return the absolute path the dialog should hand to
    the host OS's file browser. The dialog handles the
    actual reveal."""
    if workspace is None:
        raise PanelActionError("no active workspace")
    return workspace.root


def project_notes_path(workspace: Optional[Workspace]) -> str:
    """Return the absolute path to the project-level
    note file. Creates the notes directory if missing."""
    if workspace is None:
        raise PanelActionError("no active workspace")
    store = NotesStore(workspace.notes_dir())
    os.makedirs(store.root, exist_ok=True)
    return store.project_note_path


# ---------------------------------------------------------------------------
# Export integration
# ---------------------------------------------------------------------------


def workspace_export_subdir(
    workspace: Optional[Workspace],
    *,
    subdir: str = "",
) -> str:
    """Compute the absolute path inside the workspace
    where an export should land.

    When ``subdir`` is empty the function returns the
    workspace's ``exports/`` root. When ``subdir`` is
    set, it is appended (workspace-relative; absolute
    inputs are rejected to keep exports inside the tree).
    Creates the target directory.
    """
    if workspace is None:
        raise PanelActionError("no active workspace")
    if subdir and os.path.isabs(subdir):
        raise PanelActionError(
            f"export subdir must be workspace-relative: {subdir}"
        )
    base = workspace.exports_dir()
    target = os.path.normpath(os.path.join(base, subdir or ""))
    # Defensive: refuse to escape the workspace exports dir.
    base_abs = os.path.abspath(base)
    target_abs = os.path.abspath(target)
    if not (target_abs == base_abs or target_abs.startswith(base_abs + os.sep)):
        raise PanelActionError(
            f"export path escapes workspace exports: {subdir}"
        )
    os.makedirs(target_abs, exist_ok=True)
    return target_abs


def export_path_for_action(
    workspace: Optional[Workspace],
    filename: str,
    *,
    subdir: str = "",
) -> str:
    """Convenience: ``workspace_export_subdir`` joined with
    a filename. The dialog passes a default name like
    ``"camera_path.json"``; the helper returns the full
    path the export pipeline should write to."""
    if not filename:
        raise PanelActionError("filename is required")
    if os.path.isabs(filename) or "/" in filename or "\\" in filename:
        raise PanelActionError(
            f"filename must be a leaf name (no separators): {filename}"
        )
    base = workspace_export_subdir(workspace, subdir=subdir)
    return os.path.join(base, filename)
