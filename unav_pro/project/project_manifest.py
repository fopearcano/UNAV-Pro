"""v3.1 project manifest.

The manifest is the single source of truth for an UNAV Pro
workspace. It lives at ``<workspace>/project_manifest.json``
and tracks:

* The plugin version that wrote it (forward / backward
  compatibility).
* The project's coordinate scale + active datasets.
* References to missions, routes, timelines (filenames
  *relative* to the workspace root, never absolute).
* Snapshots of the overlay + science-layer settings.
* Free-form notes / metadata the artist wants alongside
  the project.

Everything is **pure stdlib + JSON-serialisable**; no
Cinema 4D imports. The c4d-bound dialog reads / writes
through this layer.

Schema policy:

* The ``schema_version`` integer bumps when the on-disk
  shape changes incompatibly. v3.1 ships ``v=1``.
* Loaders accept missing fields (defaulted) but reject
  unknown ``schema_version`` values fail-closed.
* Every reference is a workspace-relative path. The loader
  rejects absolute paths so a workspace stays portable
  across machines.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


#: Filename the manifest lives under inside the workspace.
PROJECT_MANIFEST_FILENAME: str = "project_manifest.json"

#: Schema-version integer the v3.1 codebase writes + accepts.
PROJECT_MANIFEST_SCHEMA_VERSION: int = 1


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ManifestError(ValueError):
    """Raised when manifest I/O or validation fails."""


# ---------------------------------------------------------------------------
# Reference dataclasses
# ---------------------------------------------------------------------------


def _is_safe_relpath(p: str) -> bool:
    """A path is workspace-safe iff it is non-empty,
    relative, and does not climb above the workspace root.

    This is a lexical check (no filesystem touches), so it
    is portable across OSes and safe to call on a manifest
    coming from another machine.
    """
    if not p:
        return False
    s = str(p).replace("\\", "/")
    if s.startswith("/"):
        return False
    if os.path.isabs(s):
        return False
    parts = [x for x in s.split("/") if x]
    if any(p == ".." for p in parts):
        return False
    return True


@dataclass
class DatasetReference:
    """One entry in the manifest's ``datasets`` list.

    ``path`` is workspace-relative — typically
    ``"datasets/<entry-name>.jsonl"`` or
    ``"datasets/<entry-name>.db"``. Index data, when
    present, lives next to the catalog; ``index_dir`` is
    advisory.
    """

    name: str
    path: str
    enabled: bool = True
    namespace: bool = True
    role: str = "primary"
    index_dir: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DatasetReference":
        return cls(
            name=str(d.get("name", "")).strip(),
            path=str(d.get("path", "")).strip(),
            enabled=bool(d.get("enabled", True)),
            namespace=bool(d.get("namespace", True)),
            role=str(d.get("role", "primary")),
            index_dir=(d.get("index_dir") or None),
            notes=str(d.get("notes", "") or ""),
        )

    def validate(self) -> List[str]:
        errs: List[str] = []
        if not self.name:
            errs.append("dataset reference: name is empty")
        if not _is_safe_relpath(self.path):
            errs.append(
                f"dataset reference '{self.name}': path '{self.path}' "
                "is not a workspace-relative path"
            )
        if self.index_dir is not None and not _is_safe_relpath(self.index_dir):
            errs.append(
                f"dataset reference '{self.name}': index_dir "
                f"'{self.index_dir}' is not a workspace-relative path"
            )
        return errs


@dataclass
class MissionReference:
    """Pointer to a mission JSON inside the workspace."""

    mission_id: str
    path: str
    title: str = ""
    tags: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "path": self.path,
            "title": self.title,
            "tags": list(self.tags),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MissionReference":
        return cls(
            mission_id=str(d.get("mission_id", "")).strip(),
            path=str(d.get("path", "")).strip(),
            title=str(d.get("title", "") or ""),
            tags=[str(t) for t in (d.get("tags") or [])],
            notes=str(d.get("notes", "") or ""),
        )

    def validate(self) -> List[str]:
        errs: List[str] = []
        if not self.mission_id:
            errs.append("mission reference: mission_id is empty")
        if not _is_safe_relpath(self.path):
            errs.append(
                f"mission reference '{self.mission_id}': path "
                f"'{self.path}' is not a workspace-relative path"
            )
        return errs


@dataclass
class RouteReference:
    """Pointer to a route JSON inside the workspace."""

    name: str
    path: str
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RouteReference":
        return cls(
            name=str(d.get("name", "")).strip(),
            path=str(d.get("path", "")).strip(),
            notes=str(d.get("notes", "") or ""),
        )

    def validate(self) -> List[str]:
        errs: List[str] = []
        if not self.name:
            errs.append("route reference: name is empty")
        if not _is_safe_relpath(self.path):
            errs.append(
                f"route reference '{self.name}': path '{self.path}' "
                "is not a workspace-relative path"
            )
        return errs


@dataclass
class TimelineReference:
    """Pointer to a baked timeline JSON inside the workspace."""

    name: str
    path: str
    frames: int = 0
    fps: float = 24.0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TimelineReference":
        return cls(
            name=str(d.get("name", "")).strip(),
            path=str(d.get("path", "")).strip(),
            frames=int(d.get("frames", 0) or 0),
            fps=float(d.get("fps", 24.0) or 24.0),
            notes=str(d.get("notes", "") or ""),
        )

    def validate(self) -> List[str]:
        errs: List[str] = []
        if not self.name:
            errs.append("timeline reference: name is empty")
        if not _is_safe_relpath(self.path):
            errs.append(
                f"timeline reference '{self.name}': path '{self.path}' "
                "is not a workspace-relative path"
            )
        if self.frames < 0:
            errs.append(
                f"timeline reference '{self.name}': frames must be >= 0"
            )
        if self.fps <= 0:
            errs.append(
                f"timeline reference '{self.name}': fps must be > 0"
            )
        return errs


@dataclass
class OverlaySettingsRef:
    """Snapshot of the v2.0 overlay settings the project
    uses. Stored verbatim as a dict so we don't have to
    cross-import the procedural package at the manifest
    layer."""

    settings: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"settings": dict(self.settings)}

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "OverlaySettingsRef":
        if not d:
            return cls()
        s = d.get("settings") or {}
        if not isinstance(s, dict):
            return cls()
        return cls(settings=dict(s))


@dataclass
class ScienceSettingsRef:
    """Snapshot of the v2.1 science-layer settings."""

    settings: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"settings": dict(self.settings)}

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "ScienceSettingsRef":
        if not d:
            return cls()
        s = d.get("settings") or {}
        if not isinstance(s, dict):
            return cls()
        return cls(settings=dict(s))


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


@dataclass
class ProjectManifest:
    """Top-level manifest persisted at
    ``<workspace>/project_manifest.json``.

    The manifest is **declarative**: it describes what the
    workspace contains and how the project is configured.
    The actual files (catalogs, mission JSONs, route JSONs)
    live in the workspace subdirectories; the manifest
    references them by relative path.

    All fields default to safe empty values so a freshly
    created workspace can be saved before any data is added.
    """

    schema_version: int = PROJECT_MANIFEST_SCHEMA_VERSION

    project_name: str = "Untitled UNAV Project"
    project_description: str = ""

    # Versioning + provenance.
    plugin_version: str = ""
    created_at_iso: str = ""
    updated_at_iso: str = ""

    # Coordinate scale and the navigator's last-known scale
    # mode. Stored so the dialog can render a status line
    # ("scale: 1 pc = 100 C4D units") without having to
    # walk the scene.
    scale_mode: str = "parsec_to_cm"

    # Active dataset references.
    datasets: List[DatasetReference] = field(default_factory=list)

    # Mission / route / timeline references.
    missions: List[MissionReference] = field(default_factory=list)
    routes: List[RouteReference] = field(default_factory=list)
    timelines: List[TimelineReference] = field(default_factory=list)

    # Overlay + science-layer settings snapshots.
    overlays: OverlaySettingsRef = field(default_factory=OverlaySettingsRef)
    science_layers: ScienceSettingsRef = field(default_factory=ScienceSettingsRef)

    # Free-form metadata the dialog can populate; not
    # interpreted by the manifest layer itself.
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ---------------------------------------------------- timestamps
    def touch(self) -> None:
        """Stamp ``updated_at_iso`` to the current UTC time
        in ISO-8601 'YYYY-MM-DDTHH:MM:SS' form."""
        self.updated_at_iso = _now_iso()

    # ---------------------------------------------------- (de)serialisation
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "project_name": self.project_name,
            "project_description": self.project_description,
            "plugin_version": self.plugin_version,
            "created_at_iso": self.created_at_iso,
            "updated_at_iso": self.updated_at_iso,
            "scale_mode": self.scale_mode,
            "datasets": [d.to_dict() for d in self.datasets],
            "missions": [m.to_dict() for m in self.missions],
            "routes": [r.to_dict() for r in self.routes],
            "timelines": [t.to_dict() for t in self.timelines],
            "overlays": self.overlays.to_dict(),
            "science_layers": self.science_layers.to_dict(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "ProjectManifest":
        if not isinstance(d, dict):
            raise ManifestError("manifest payload is not an object")
        version = d.get("schema_version", PROJECT_MANIFEST_SCHEMA_VERSION)
        try:
            version_i = int(version)
        except (TypeError, ValueError) as exc:
            raise ManifestError(
                f"manifest schema_version not an integer: {version!r}",
            ) from exc
        if version_i > PROJECT_MANIFEST_SCHEMA_VERSION:
            raise ManifestError(
                f"manifest schema_version {version_i} is newer than "
                f"this build understands "
                f"({PROJECT_MANIFEST_SCHEMA_VERSION}). Upgrade the "
                "plugin or save the manifest from this build first."
            )
        out = cls(
            schema_version=version_i,
            project_name=str(d.get("project_name", "")).strip()
            or "Untitled UNAV Project",
            project_description=str(d.get("project_description", "") or ""),
            plugin_version=str(d.get("plugin_version", "") or ""),
            created_at_iso=str(d.get("created_at_iso", "") or ""),
            updated_at_iso=str(d.get("updated_at_iso", "") or ""),
            scale_mode=str(d.get("scale_mode", "parsec_to_cm") or "parsec_to_cm"),
            datasets=[
                DatasetReference.from_dict(x)
                for x in (d.get("datasets") or [])
                if isinstance(x, dict)
            ],
            missions=[
                MissionReference.from_dict(x)
                for x in (d.get("missions") or [])
                if isinstance(x, dict)
            ],
            routes=[
                RouteReference.from_dict(x)
                for x in (d.get("routes") or [])
                if isinstance(x, dict)
            ],
            timelines=[
                TimelineReference.from_dict(x)
                for x in (d.get("timelines") or [])
                if isinstance(x, dict)
            ],
            overlays=OverlaySettingsRef.from_dict(d.get("overlays")),
            science_layers=ScienceSettingsRef.from_dict(d.get("science_layers")),
            metadata=(
                dict(d.get("metadata") or {})
                if isinstance(d.get("metadata"), dict)
                else {}
            ),
        )
        return out

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=False,
        )

    @classmethod
    def from_json(cls, text: str) -> "ProjectManifest":
        try:
            d = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"manifest JSON parse failed: {exc}") from exc
        return cls.from_dict(d)

    # ---------------------------------------------------- validation
    def validate(self) -> List[str]:
        """Return a list of validation errors. Empty list ⇒
        the manifest is internally consistent and safe to
        persist. Does not touch the filesystem."""
        errs: List[str] = []
        if self.schema_version != PROJECT_MANIFEST_SCHEMA_VERSION:
            errs.append(
                f"schema_version is {self.schema_version}; this build "
                f"writes {PROJECT_MANIFEST_SCHEMA_VERSION}. Re-saving "
                "will upgrade."
            )
        for d in self.datasets:
            errs.extend(d.validate())
        for m in self.missions:
            errs.extend(m.validate())
        for r in self.routes:
            errs.extend(r.validate())
        for t in self.timelines:
            errs.extend(t.validate())
        # Duplicate-name checks across reference families.
        seen: Dict[str, str] = {}
        for d in self.datasets:
            key = f"dataset:{d.name}"
            if key in seen:
                errs.append(f"duplicate dataset name: {d.name}")
            seen[key] = d.path
        for m in self.missions:
            key = f"mission:{m.mission_id}"
            if key in seen:
                errs.append(f"duplicate mission_id: {m.mission_id}")
            seen[key] = m.path
        for r in self.routes:
            key = f"route:{r.name}"
            if key in seen:
                errs.append(f"duplicate route name: {r.name}")
            seen[key] = r.path
        for t in self.timelines:
            key = f"timeline:{t.name}"
            if key in seen:
                errs.append(f"duplicate timeline name: {t.name}")
            seen[key] = t.path
        return errs

    # ---------------------------------------------------- helpers
    def find_mission(self, mission_id: str) -> Optional[MissionReference]:
        for m in self.missions:
            if m.mission_id == mission_id:
                return m
        return None

    def find_dataset(self, name: str) -> Optional[DatasetReference]:
        for d in self.datasets:
            if d.name == name:
                return d
        return None


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def _safe_write_json(path: str, payload: Dict[str, Any]) -> None:
    """Atomic write: temp file in the same directory, then
    rename. Mirrors the v0.x ``safe_write_json`` pattern.
    """
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def save_manifest(manifest: ProjectManifest, path: str) -> None:
    """Validate + atomically write ``manifest`` to ``path``.

    Stamps ``updated_at_iso`` before writing. Validation
    errors raise ``ManifestError``.
    """
    errs = manifest.validate()
    if errs:
        raise ManifestError(
            "manifest failed validation:\n  - " + "\n  - ".join(errs),
        )
    if not manifest.created_at_iso:
        manifest.created_at_iso = _now_iso()
    manifest.touch()
    _safe_write_json(path, manifest.to_dict())


def load_manifest(path: str) -> ProjectManifest:
    """Read + parse + validate a manifest from ``path``.

    Raises ``ManifestError`` on missing file, parse failure,
    or schema-version mismatch.
    """
    if not os.path.isfile(path):
        raise ManifestError(f"manifest not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return ProjectManifest.from_json(text)
