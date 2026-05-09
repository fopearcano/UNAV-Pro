"""v2.3 export-validation pre-flight checks.

Pure-Python validators that the export manager runs before
materialising any file. Each validator returns a list of
``ValidationIssue`` records — empty list means "all good".

The export manager is fail-closed by convention: a validation
issue with severity ``error`` aborts the export; ``warning``
issues are logged but the export proceeds.

No Cinema 4D dependency. Tested without the host.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

SEVERITY_ERROR: str = "error"
SEVERITY_WARNING: str = "warning"
SEVERITY_INFO: str = "info"

SEVERITIES: tuple = (SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO)


@dataclass
class ValidationIssue:
    """One pre-flight finding.

    ``severity`` is one of ``SEVERITIES``; ``code`` is a
    short stable identifier the dialog can key off; ``detail``
    is a human-readable string the dialog log surfaces."""

    severity: str = SEVERITY_INFO
    code: str = ""
    detail: str = ""

    def is_error(self) -> bool:
        return self.severity == SEVERITY_ERROR

    def is_warning(self) -> bool:
        return self.severity == SEVERITY_WARNING


@dataclass
class ValidationReport:
    """Aggregate of validator findings.

    The export manager fails closed on any ``error``-severity
    issue; ``warning`` issues are logged but allowed.
    """

    issues: List[ValidationIssue] = field(default_factory=list)

    def has_errors(self) -> bool:
        return any(i.is_error() for i in self.issues)

    def has_warnings(self) -> bool:
        return any(i.is_warning() for i in self.issues)

    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.is_error()]

    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.is_warning()]

    def render_text(self) -> str:
        if not self.issues:
            return "Validation: all clear."
        lines: List[str] = []
        for issue in self.issues:
            mark = (
                "[ERR]" if issue.is_error()
                else "[!!]" if issue.is_warning()
                else "[..]"
            )
            lines.append(f"{mark} {issue.code}: {issue.detail}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Path / filesystem checks
# ---------------------------------------------------------------------------


def validate_writable_path(
    path: str, *, allow_overwrite: bool = False,
) -> ValidationReport:
    """v2.3 path-pre-flight. Checks that:

    * the path is non-empty,
    * the parent directory exists or can be created,
    * the file (when present) can be replaced if
      ``allow_overwrite=True``; otherwise the existing file
      raises an error.
    """
    rpt = ValidationReport()
    if not path or not str(path).strip():
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_ERROR,
            code="empty_path",
            detail="export path is empty.",
        ))
        return rpt
    abs_path = os.path.abspath(str(path))
    parent = os.path.dirname(abs_path)
    if parent and not os.path.isdir(parent):
        # If we can't even create the parent, that's an
        # error; we test by attempting ``os.makedirs`` with
        # ``exist_ok=True`` later. Here we just flag the
        # missing-parent case as a warning so the manager
        # logs it.
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_WARNING,
            code="missing_parent",
            detail=f"parent directory does not exist: {parent}",
        ))
    if os.path.exists(abs_path):
        if not allow_overwrite:
            rpt.issues.append(ValidationIssue(
                severity=SEVERITY_ERROR,
                code="overwrite_refused",
                detail=(
                    f"file already exists: {abs_path} "
                    "(set allow_overwrite=True to replace)."
                ),
            ))
        elif not os.path.isfile(abs_path):
            rpt.issues.append(ValidationIssue(
                severity=SEVERITY_ERROR,
                code="not_a_file",
                detail=(
                    f"path exists but is not a regular file: "
                    f"{abs_path}"
                ),
            ))
    return rpt


def validate_writable_directory(
    path: str, *, allow_existing: bool = True,
) -> ValidationReport:
    """v2.3 directory-pre-flight. Used by the export-package
    builder.

    When ``allow_existing=False``, the directory must not
    already exist; existing → error.
    """
    rpt = ValidationReport()
    if not path or not str(path).strip():
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_ERROR,
            code="empty_path",
            detail="export directory path is empty.",
        ))
        return rpt
    abs_path = os.path.abspath(str(path))
    if os.path.exists(abs_path):
        if not os.path.isdir(abs_path):
            rpt.issues.append(ValidationIssue(
                severity=SEVERITY_ERROR,
                code="not_a_directory",
                detail=(
                    f"path exists but is not a directory: {abs_path}"
                ),
            ))
        elif not allow_existing:
            rpt.issues.append(ValidationIssue(
                severity=SEVERITY_ERROR,
                code="directory_exists",
                detail=(
                    f"directory already exists: {abs_path} "
                    "(set allow_existing=True to write into it)."
                ),
            ))
        else:
            rpt.issues.append(ValidationIssue(
                severity=SEVERITY_INFO,
                code="directory_exists",
                detail=f"writing into existing directory: {abs_path}",
            ))
    return rpt


# ---------------------------------------------------------------------------
# Mission / route / camera-path validators
# ---------------------------------------------------------------------------


def validate_mission_for_export(mission) -> ValidationReport:
    """Lightweight mission validator. Catches the common
    failure modes the dialog should surface before the
    artist clicks Export."""
    rpt = ValidationReport()
    if mission is None:
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_ERROR,
            code="no_mission",
            detail="no mission supplied.",
        ))
        return rpt
    if not getattr(mission, "title", None):
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_WARNING,
            code="missing_title",
            detail="mission has no title.",
        ))
    waypoints = list(getattr(mission, "waypoints", None) or ())
    if len(waypoints) == 0:
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_WARNING,
            code="empty_waypoints",
            detail="mission has zero waypoints.",
        ))
    # Count waypoints whose position can't be resolved.
    unresolved = 0
    for wp in waypoints:
        if not getattr(wp, "is_path_contributing", lambda: True)():
            continue
        if not getattr(wp, "has_c4d_position", lambda: False)():
            unresolved += 1
    if unresolved:
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_WARNING,
            code="unresolved_waypoints",
            detail=(
                f"{unresolved} path-contributing waypoint(s) "
                "have no cached C4D position; downstream camera "
                "path / animation exports will skip them."
            ),
        ))
    return rpt


def validate_camera_path_for_export(path) -> ValidationReport:
    """Validate a built camera path before camera-exchange
    export."""
    rpt = ValidationReport()
    if path is None:
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_ERROR,
            code="no_path",
            detail="no camera path supplied.",
        ))
        return rpt
    is_empty = getattr(path, "is_empty", lambda: True)
    if is_empty():
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_ERROR,
            code="empty_path",
            detail="camera path is empty (no resolved waypoints).",
        ))
        return rpt
    waypoint_count = getattr(path, "waypoint_count", lambda: 0)()
    if waypoint_count < 2:
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_WARNING,
            code="single_waypoint_path",
            detail=(
                "camera path has only one waypoint; the export "
                "will produce a static pose."
            ),
        ))
    return rpt


def validate_dataset_registry(registry) -> ValidationReport:
    """Validate the active dataset registry."""
    rpt = ValidationReport()
    if registry is None:
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_WARNING,
            code="no_registry",
            detail="no dataset registry supplied; summary will be empty.",
        ))
        return rpt
    entries = list(getattr(registry, "entries", None) or ())
    if not entries:
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_WARNING,
            code="empty_registry",
            detail="dataset registry has no entries.",
        ))
        return rpt
    enabled = [e for e in entries if getattr(e, "enabled", False)]
    if not enabled:
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_INFO,
            code="no_enabled_datasets",
            detail="no enabled datasets; the summary will list registered datasets only.",
        ))
    return rpt


# ---------------------------------------------------------------------------
# Manifest validator
# ---------------------------------------------------------------------------


REQUIRED_MANIFEST_FIELDS: tuple = (
    "manifest_version", "exported_at_iso", "plugin_version",
    "coordinate_convention", "units",
)


def validate_manifest(manifest: dict) -> ValidationReport:
    """v2.3 manifest integrity check. Used by the export
    package builder; tests exercise this directly to assert
    the manifest schema."""
    rpt = ValidationReport()
    if not isinstance(manifest, dict):
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_ERROR,
            code="manifest_not_dict",
            detail="manifest top-level must be a JSON object.",
        ))
        return rpt
    for key in REQUIRED_MANIFEST_FIELDS:
        if key not in manifest:
            rpt.issues.append(ValidationIssue(
                severity=SEVERITY_ERROR,
                code="missing_manifest_field",
                detail=f"manifest missing required field: {key}",
            ))
    # Soft-checks.
    assets = manifest.get("included_assets") or {}
    if not isinstance(assets, dict):
        rpt.issues.append(ValidationIssue(
            severity=SEVERITY_WARNING,
            code="manifest_assets_not_object",
            detail="manifest 'included_assets' should be a JSON object.",
        ))
    return rpt


# ---------------------------------------------------------------------------
# Filename collision check
# ---------------------------------------------------------------------------


def validate_no_duplicate_filenames(
    paths: Iterable[str],
) -> ValidationReport:
    """Catch duplicate output paths within a single package
    export. Each ``paths`` entry must be unique (case-
    insensitive on case-insensitive filesystems is a v2.x
    concern; v2.3 does case-sensitive comparison for
    determinism)."""
    rpt = ValidationReport()
    seen = set()
    for raw in paths:
        if not raw:
            continue
        norm = os.path.normpath(str(raw))
        if norm in seen:
            rpt.issues.append(ValidationIssue(
                severity=SEVERITY_ERROR,
                code="duplicate_filename",
                detail=f"duplicate export filename: {norm}",
            ))
            continue
        seen.add(norm)
    return rpt
