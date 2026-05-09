"""v2.3 export package — directory + manifest.

A package is a folder on disk with a fixed layout:

    UNAV_Export/
      manifest.json
      missions/
      routes/
      timelines/
      camera_paths/
      datasets/
      summaries/
      docs/

The manifest is a small JSON document that describes what the
package contains, what plugin version produced it, and what
coordinate convention / units were in force at export time.

Pure-Python; no Cinema 4D dependency. Tests drive this module
directly.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Format version + layout
# ---------------------------------------------------------------------------

#: Stable schema version for the package manifest. Bumped
#: when the on-disk layout changes; downstream readers can
#: refuse newer versions.
PACKAGE_MANIFEST_VERSION: int = 1

#: Default top-level directory name. The dialog uses it when
#: the artist hasn't picked a different name.
DEFAULT_PACKAGE_NAME: str = "UNAV_Export"

#: The fixed sub-directory layout. Every package built by the
#: v2.3 builder has these directories (some may be empty when
#: the artist's input doesn't carry that asset class).
PACKAGE_SUBDIRS: tuple = (
    "missions",
    "routes",
    "timelines",
    "camera_paths",
    "datasets",
    "summaries",
    "docs",
)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class PackageManifest:
    """Top-level metadata document.

    Stamped with the v2.3 schema version, the export
    timestamp, the plugin version, the coordinate convention
    in force at export, and a manifest of every asset
    written. Tests assert the round-trip; the package
    builder writes ``manifest.json`` from this struct.
    """

    manifest_version: int = PACKAGE_MANIFEST_VERSION
    exported_at_iso: str = field(default_factory=_now_iso)
    plugin_version: str = ""
    coordinate_convention: str = "C4D world units, Y-up"
    units: Dict[str, str] = field(default_factory=lambda: {
        "position": "C4D_world_units",
        "rotation": "radians_HPB",
        "fov": "radians_horizontal",
        "epoch": "julian_date",
        "time": "seconds",
    })
    package_name: str = DEFAULT_PACKAGE_NAME
    notes: str = ""
    active_datasets: List[str] = field(default_factory=list)
    included_assets: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest_version": int(self.manifest_version),
            "exported_at_iso": self.exported_at_iso,
            "plugin_version": self.plugin_version,
            "coordinate_convention": self.coordinate_convention,
            "units": dict(self.units),
            "package_name": self.package_name,
            "notes": self.notes,
            "active_datasets": list(self.active_datasets),
            "included_assets": {
                k: list(v) for k, v in self.included_assets.items()
            },
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=indent)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "PackageManifest":
        d = d or {}
        return cls(
            manifest_version=int(d.get("manifest_version") or PACKAGE_MANIFEST_VERSION),
            exported_at_iso=str(d.get("exported_at_iso") or _now_iso()),
            plugin_version=str(d.get("plugin_version") or ""),
            coordinate_convention=str(
                d.get("coordinate_convention") or "C4D world units, Y-up"
            ),
            units=dict(d.get("units") or {}),
            package_name=str(d.get("package_name") or DEFAULT_PACKAGE_NAME),
            notes=str(d.get("notes") or ""),
            active_datasets=[
                str(x) for x in (d.get("active_datasets") or []) if str(x)
            ],
            included_assets={
                str(k): [str(v) for v in (vs or [])]
                for k, vs in (d.get("included_assets") or {}).items()
            },
        )


@dataclass
class PackageBuildReport:
    """Aggregate result of ``build_export_package``."""

    package_root: str = ""
    files_written: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    manifest_path: str = ""
    success: bool = True

    def add_file(self, path: str) -> None:
        self.files_written.append(path)

    def render_text(self) -> str:
        lines: List[str] = []
        lines.append(
            f"Package: {self.package_root} "
            f"({len(self.files_written)} file(s) written)."
        )
        if self.manifest_path:
            lines.append(f"Manifest: {self.manifest_path}")
        for w in self.warnings:
            lines.append(f"  ! {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


@dataclass
class PackagePayload:
    """Caller-supplied bag of assets the builder writes into
    the package directory.

    Each field is a ``{filename: contents}`` mapping. The
    builder writes them under the corresponding subdirectory
    (``missions/``, ``routes/``, etc.). Filenames are
    relative; absolute paths trigger a validation error.
    """

    missions: Dict[str, str] = field(default_factory=dict)
    routes: Dict[str, str] = field(default_factory=dict)
    timelines: Dict[str, str] = field(default_factory=dict)
    camera_paths: Dict[str, str] = field(default_factory=dict)
    datasets: Dict[str, str] = field(default_factory=dict)
    summaries: Dict[str, str] = field(default_factory=dict)
    docs: Dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not any((
            self.missions, self.routes, self.timelines,
            self.camera_paths, self.datasets, self.summaries,
            self.docs,
        ))

    def asset_map(self) -> Dict[str, Dict[str, str]]:
        """Mapping of subdir → contents. Used by the builder
        to walk every asset class in one pass."""
        return {
            "missions": self.missions,
            "routes": self.routes,
            "timelines": self.timelines,
            "camera_paths": self.camera_paths,
            "datasets": self.datasets,
            "summaries": self.summaries,
            "docs": self.docs,
        }


def build_export_package(
    package_root: str,
    payload: PackagePayload,
    *,
    manifest: Optional[PackageManifest] = None,
    allow_existing: bool = True,
) -> PackageBuildReport:
    """v2.3 package builder.

    Creates the directory layout under ``package_root``,
    writes every asset in ``payload``, then writes the
    manifest. All writes go through the v1.7
    ``safe_write_json`` helper for atomicity.

    The builder is fail-closed: if any path validation
    issue surfaces, the report's ``success`` flag is
    ``False`` and partial state is left as-is for the artist
    to inspect.
    """
    from core.config import safe_write_json
    from .export_validation import (
        validate_no_duplicate_filenames,
        validate_writable_directory,
        validate_manifest,
    )

    report = PackageBuildReport(package_root=str(package_root))
    if payload is None:
        payload = PackagePayload()

    # Pre-flight: directory.
    dir_check = validate_writable_directory(
        str(package_root), allow_existing=allow_existing,
    )
    if dir_check.has_errors():
        report.success = False
        report.warnings.extend(
            f"{i.code}: {i.detail}" for i in dir_check.errors()
        )
        return report
    for issue in dir_check.warnings():
        report.warnings.append(f"{issue.code}: {issue.detail}")

    # Pre-flight: filename uniqueness within each subdir.
    all_paths: List[str] = []
    for subdir, contents in payload.asset_map().items():
        for relname in contents.keys():
            if os.path.isabs(relname):
                report.success = False
                report.warnings.append(
                    f"asset filename is absolute: "
                    f"{subdir}/{relname}"
                )
                continue
            all_paths.append(os.path.join(subdir, relname))
    dup_check = validate_no_duplicate_filenames(all_paths)
    if dup_check.has_errors():
        report.success = False
        report.warnings.extend(
            f"{i.code}: {i.detail}" for i in dup_check.errors()
        )
        return report

    # Materialise the directory tree.
    try:
        os.makedirs(package_root, exist_ok=True)
        for subdir in PACKAGE_SUBDIRS:
            os.makedirs(os.path.join(package_root, subdir), exist_ok=True)
    except OSError as exc:
        report.success = False
        report.warnings.append(f"could not create directories: {exc}")
        return report

    # Write the assets.
    final_manifest = manifest or PackageManifest()
    for subdir, contents in payload.asset_map().items():
        if not contents:
            continue
        final_manifest.included_assets.setdefault(subdir, [])
        for relname, body in contents.items():
            full = os.path.join(package_root, subdir, relname)
            written = safe_write_json(full, body)
            if written is None:
                report.success = False
                report.warnings.append(
                    f"failed to write {subdir}/{relname}"
                )
                continue
            report.add_file(full)
            final_manifest.included_assets[subdir].append(relname)

    # Validate the manifest before writing it.
    manifest_check = validate_manifest(final_manifest.to_dict())
    if manifest_check.has_errors():
        report.success = False
        for issue in manifest_check.errors():
            report.warnings.append(
                f"manifest invalid: {issue.code}: {issue.detail}"
            )
        return report

    manifest_path = os.path.join(package_root, "manifest.json")
    written = safe_write_json(manifest_path, final_manifest.to_json())
    if written is None:
        report.success = False
        report.warnings.append("failed to write manifest.json")
    else:
        report.manifest_path = manifest_path
        report.add_file(manifest_path)

    return report


def read_export_package(package_root: str) -> Optional[PackageManifest]:
    """Read just the manifest from an export package directory.
    Returns ``None`` when the directory or manifest is missing
    / corrupt."""
    if not package_root:
        return None
    manifest_path = os.path.join(str(package_root), "manifest.json")
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            return PackageManifest.from_dict(json.load(fh))
    except (OSError, ValueError, TypeError):
        return None
