"""v3.1 notes system.

Lightweight markdown / plain-text notes scoped to a
workspace. Three kinds of notes:

* **Project notes** — one free-form file at
  ``notes/project.md``.
* **Mission notes** — one file per mission at
  ``notes/missions/<mission_id>.md``.
* **Dataset notes** — one file per dataset at
  ``notes/datasets/<dataset-name>.md``.

Notes are **artist-owned** plain text. The plugin reads /
writes them but never interprets the body — only the
*filename* gives a note its scope.

The store is fully unit-testable without a workspace
instance: every API takes the notes-root absolute path.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


NOTE_KIND_PROJECT: str = "project"
NOTE_KIND_MISSION: str = "mission"
NOTE_KIND_DATASET: str = "dataset"

#: Filename for the workspace-level note.
PROJECT_NOTE_FILENAME: str = "project.md"

_MISSIONS_SUBDIR: str = "missions"
_DATASETS_SUBDIR: str = "datasets"

_VALID_KINDS: Tuple[str, ...] = (
    NOTE_KIND_PROJECT, NOTE_KIND_MISSION, NOTE_KIND_DATASET,
)


# ---------------------------------------------------------------------------
# Filename safety
# ---------------------------------------------------------------------------


_SAFE_PATTERN = re.compile(r"[^A-Za-z0-9._\-]+")


def _safe_filename(stem: str) -> str:
    """Map a free-form id to a filesystem-safe filename
    stem. Non-alphanumeric runs collapse to ``_``; leading /
    trailing dots and underscores are stripped; an empty
    result becomes ``_``."""
    s = _SAFE_PATTERN.sub("_", str(stem or "")).strip("._")
    if not s:
        s = "_"
    return s


def relative_path_for_note(kind: str, scope_id: Optional[str] = None) -> str:
    """Return the workspace-relative path for a note of
    the given ``kind`` (and ``scope_id`` for mission /
    dataset notes). Pure helper — does not touch the
    filesystem.

    The returned path always uses forward slashes so it
    is portable across OSes. Always rooted at ``notes/``.
    """
    if kind not in _VALID_KINDS:
        raise ValueError(f"unknown note kind: {kind!r}")
    if kind == NOTE_KIND_PROJECT:
        return f"notes/{PROJECT_NOTE_FILENAME}"
    if not scope_id:
        raise ValueError(
            f"note kind {kind!r} requires a scope_id"
        )
    safe = _safe_filename(scope_id)
    sub = _MISSIONS_SUBDIR if kind == NOTE_KIND_MISSION else _DATASETS_SUBDIR
    return f"notes/{sub}/{safe}.md"


# ---------------------------------------------------------------------------
# Note entry
# ---------------------------------------------------------------------------


@dataclass
class NoteEntry:
    """One note read from the store. ``path`` is the
    absolute path on disk."""

    kind: str
    scope_id: Optional[str]
    body: str
    path: str = ""
    last_modified_iso: str = ""

    def short_summary(self) -> str:
        scope = self.scope_id or "(workspace)"
        first_line = ""
        for line in self.body.splitlines():
            if line.strip():
                first_line = line.strip()
                break
        suffix = f" — {first_line[:60]}" if first_line else ""
        return f"[{self.kind}:{scope}] {len(self.body)} chars{suffix}"


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


class NotesStore:
    """File-backed notes for one workspace's ``notes/``
    directory.

    The constructor takes the **absolute** path to the
    notes root (e.g. ``Workspace.notes_dir()``). The store
    creates the kind-specific subdirectories on demand;
    reading from a missing directory returns ``None`` /
    empty list rather than raising.
    """

    def __init__(self, notes_root: str) -> None:
        self._root = os.path.abspath(notes_root)

    # ---------------------------------------------------- properties
    @property
    def root(self) -> str:
        return self._root

    @property
    def project_note_path(self) -> str:
        return os.path.join(self._root, PROJECT_NOTE_FILENAME)

    def mission_note_path(self, mission_id: str) -> str:
        return os.path.join(
            self._root, _MISSIONS_SUBDIR,
            f"{_safe_filename(mission_id)}.md",
        )

    def dataset_note_path(self, dataset_name: str) -> str:
        return os.path.join(
            self._root, _DATASETS_SUBDIR,
            f"{_safe_filename(dataset_name)}.md",
        )

    # ---------------------------------------------------- write
    def write_project_note(self, body: str) -> NoteEntry:
        path = self.project_note_path
        return self._write_note(
            kind=NOTE_KIND_PROJECT, scope_id=None,
            body=body, path=path,
        )

    def write_mission_note(self, mission_id: str, body: str) -> NoteEntry:
        if not mission_id:
            raise ValueError("mission_id is required")
        path = self.mission_note_path(mission_id)
        return self._write_note(
            kind=NOTE_KIND_MISSION, scope_id=mission_id,
            body=body, path=path,
        )

    def write_dataset_note(self, dataset_name: str, body: str) -> NoteEntry:
        if not dataset_name:
            raise ValueError("dataset_name is required")
        path = self.dataset_note_path(dataset_name)
        return self._write_note(
            kind=NOTE_KIND_DATASET, scope_id=dataset_name,
            body=body, path=path,
        )

    def _write_note(
        self, *, kind: str, scope_id: Optional[str],
        body: str, path: str,
    ) -> NoteEntry:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        text = body if body.endswith("\n") or not body else body + "\n"
        # Atomic temp+rename so a crash mid-write doesn't
        # truncate the previous note.
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
        return NoteEntry(
            kind=kind,
            scope_id=scope_id,
            body=text,
            path=path,
            last_modified_iso=_utc_iso(),
        )

    # ---------------------------------------------------- read
    def read_project_note(self) -> Optional[NoteEntry]:
        return self._read(
            path=self.project_note_path,
            kind=NOTE_KIND_PROJECT, scope_id=None,
        )

    def read_mission_note(self, mission_id: str) -> Optional[NoteEntry]:
        if not mission_id:
            return None
        return self._read(
            path=self.mission_note_path(mission_id),
            kind=NOTE_KIND_MISSION, scope_id=mission_id,
        )

    def read_dataset_note(self, dataset_name: str) -> Optional[NoteEntry]:
        if not dataset_name:
            return None
        return self._read(
            path=self.dataset_note_path(dataset_name),
            kind=NOTE_KIND_DATASET, scope_id=dataset_name,
        )

    def _read(
        self, *, path: str, kind: str, scope_id: Optional[str],
    ) -> Optional[NoteEntry]:
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                body = fh.read()
        except OSError:
            return None
        try:
            mtime = os.path.getmtime(path)
            stamp = time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.gmtime(mtime),
            )
        except OSError:
            stamp = ""
        return NoteEntry(
            kind=kind, scope_id=scope_id,
            body=body, path=path,
            last_modified_iso=stamp,
        )

    # ---------------------------------------------------- delete
    def delete_mission_note(self, mission_id: str) -> bool:
        path = self.mission_note_path(mission_id)
        return self._delete(path)

    def delete_dataset_note(self, dataset_name: str) -> bool:
        path = self.dataset_note_path(dataset_name)
        return self._delete(path)

    def delete_project_note(self) -> bool:
        return self._delete(self.project_note_path)

    def _delete(self, path: str) -> bool:
        if not os.path.isfile(path):
            return False
        try:
            os.remove(path)
            return True
        except OSError:
            return False

    # ---------------------------------------------------- enumerate
    def list_notes(self) -> List[NoteEntry]:
        """Return every note currently on disk, in
        deterministic order (project → missions →
        datasets, alphabetic within each scope).

        Reads every file's body so the diagnostics panel
        can render a summary; for a directory of hundreds
        of notes consider ``list_summaries`` (lazy) once
        we add it. v3.1 notes are typically small enough
        that eager reads are fine.
        """
        out: List[NoteEntry] = []
        proj = self.read_project_note()
        if proj is not None:
            out.append(proj)
        missions_root = os.path.join(self._root, _MISSIONS_SUBDIR)
        if os.path.isdir(missions_root):
            for fname in sorted(os.listdir(missions_root)):
                if not fname.lower().endswith(".md"):
                    continue
                scope_id = fname[:-3]
                entry = self._read(
                    path=os.path.join(missions_root, fname),
                    kind=NOTE_KIND_MISSION, scope_id=scope_id,
                )
                if entry is not None:
                    out.append(entry)
        datasets_root = os.path.join(self._root, _DATASETS_SUBDIR)
        if os.path.isdir(datasets_root):
            for fname in sorted(os.listdir(datasets_root)):
                if not fname.lower().endswith(".md"):
                    continue
                scope_id = fname[:-3]
                entry = self._read(
                    path=os.path.join(datasets_root, fname),
                    kind=NOTE_KIND_DATASET, scope_id=scope_id,
                )
                if entry is not None:
                    out.append(entry)
        return out

    def count(self) -> int:
        """Number of notes currently on disk. Cheap walk
        (no body reads)."""
        n = 0
        for sub in (".", _MISSIONS_SUBDIR, _DATASETS_SUBDIR):
            target = os.path.join(self._root, sub) if sub != "." else self._root
            if not os.path.isdir(target):
                continue
            for fname in os.listdir(target):
                if fname.lower().endswith((".md", ".txt")):
                    if sub == "." and fname not in (PROJECT_NOTE_FILENAME,):
                        continue
                    n += 1
        return n

    # ---------------------------------------------------- aggregation
    def annotation_summary(self) -> str:
        """Render a multi-line markdown summary of every
        note in the store. Used by the dialog's
        ``Project → Notes → Summary`` action."""
        entries = self.list_notes()
        if not entries:
            return "(no notes recorded)"
        lines: List[str] = ["# Project Notes Summary", ""]
        for e in entries:
            scope = e.scope_id or "(workspace)"
            lines.append(f"## [{e.kind}] {scope}")
            if e.last_modified_iso:
                lines.append(f"*Updated: {e.last_modified_iso}*")
            lines.append("")
            body = e.body.strip()
            if body:
                lines.append(body)
            else:
                lines.append("*(empty note)*")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
