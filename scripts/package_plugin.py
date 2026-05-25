#!/usr/bin/env python3
"""v2.4 release-zip builder.

Walk the repository, copy plugin files into a staging
directory, exclude tests / cache / generated data / heavy
catalogs / hidden files, validate that every required file
is present, and zip the result.

Usage::

    python scripts/package_plugin.py
    python scripts/package_plugin.py --output dist/unav_pro-2.4.0.zip
    python scripts/package_plugin.py --staging /tmp/unav_stage --keep-staging

The output zip's name defaults to ``dist/unav_pro-<version>.zip``
where ``<version>`` is read from ``unav_pro/version.py``.

Determinism: the file list is sorted before zipping so the
package contents are byte-identical between runs (modulo
zip metadata timestamps).

Stdlib-only. Importable as a module: tests can call
``build_release_zip(...)`` directly.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence


REPO_ROOT: str = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)


# ---------------------------------------------------------------------------
# Inclusion + exclusion rules
# ---------------------------------------------------------------------------

#: Top-level paths the package always carries (relative to
#: the repo root). Globs are not supported here — the
#: include-list is intentionally explicit.
PACKAGE_INCLUDE: tuple = (
    "unav_pro",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "NOTICE.md",
    "RELEASE_NOTES_v2.4.md",
    "RELEASE_NOTES_v2.5.md",
    "RELEASE_NOTES_v3.0.md",
    "RELEASE_NOTES_v3.1.md",
    "RELEASE_NOTES_v3.2.md",
    "RELEASE_NOTES_v3.3.md",
    "RELEASE_NOTES_v3.4_INTERNAL_BETA.md",
    "RELEASE_NOTES_v3.45.md",
    "RELEASE_NOTES_v3.5_PUBLIC_ALPHA.md",
    "RELEASE_NOTES_v3.6.md",
    "RELEASE_NOTES_v3.7.md",
    "RELEASE_NOTES_v3.8.md",
    "RELEASE_NOTES_v3.9.md",
    "requirements-tools.txt",
    "samples/minimal_unav_demo",
    "samples/internal_beta_demo",
)

#: Top-level docs the package carries. Listed separately so
#: the script can log "X docs included" cleanly.
PACKAGE_DOCS: tuple = (
    "docs/INSTALL_C4D_2023_PLUS.md",
    "docs/QUICK_START.md",
    "docs/TROUBLESHOOTING.md",
    "docs/V2_4_RELEASE_PREP.md",
    "docs/PACKAGING.md",
    "docs/QA_CHECKLIST.md",
    "docs/KNOWN_LIMITATIONS.md",
    "docs/PLUGIN_LIFECYCLE.md",
    "docs/USER_MANUAL.md",
    "docs/ARTIST_QUICKSTART.md",
    "docs/TD_GUIDE.md",
    "docs/ROADMAP.md",
    "docs/V3_0_SCALABILITY_AND_STREAMING.md",
    "docs/LARGE_DATA_WORKFLOWS.md",
    "docs/SAFE_TASK_QUEUE_MODEL.md",
    "docs/QUERY_OPTIMIZATION.md",
    "docs/V3_1_PROJECT_WORKSPACES.md",
    "docs/SCENE_ORGANIZATION.md",
    "docs/MISSION_ASSET_MANAGEMENT.md",
    "docs/PROJECT_NOTES_SYSTEM.md",
    "docs/V3_2_DATA_INTEGRITY.md",
    "docs/DATA_PROVENANCE.md",
    "docs/DATA_VALIDATION_REPORTS.md",
    "docs/SCIENTIFIC_LIMITATIONS.md",
    "docs/V3_3_PRESENTATION_MODE.md",
    "docs/PRESENTATION_SEQUENCES.md",
    "docs/EDUCATIONAL_WORKFLOWS.md",
    "docs/PRESENTER_NOTES.md",
    "docs/V3_4_INTERNAL_BETA_CHECKLIST.md",
    "docs/V3_45_C4D_INTEGRATION_AUDIT.md",
    "docs/V3_45_NATIVE_C4D_WORKFLOW.md",
    "docs/UNDO_REDO_SUPPORT.md",
    "docs/OBJECT_MANAGER_STRUCTURE.md",
    "docs/MULTI_DOCUMENT_BEHAVIOR.md",
    "docs/PUBLIC_ALPHA_TESTING_GUIDE.md",
    "docs/ISSUE_REPORTING.md",
    "docs/FIRST_RUN_GUIDE.md",
    "docs/DATA_SOURCE_ATTRIBUTION.md",
    "docs/V3_6_PROCEDURAL_CINEMATIC_HELPERS.md",
    "docs/CAMERA_RIGS.md",
    "docs/CINEMATIC_FRAMING.md",
    "docs/ROUTE_BEAUTIFICATION.md",
    "docs/V3_7_ADVANCED_ASTRONOMICAL_QUERIES.md",
    "docs/QUERY_PRESETS.md",
    "docs/ROUTE_AWARE_QUERIES.md",
    "docs/EPOCH_AWARE_QUERY_LIMITATIONS.md",
    "docs/V3_8_EXHIBITION_WORKFLOWS.md",
    "docs/GUIDED_TOUR_CHAPTERS.md",
    "docs/AUDIENCE_MODE.md",
    "docs/PRESENTATION_TRANSITIONS.md",
    "docs/INTEGRATED_EXTERNAL_TOOLS.md",
    "docs/TOOLS_PYTHON_ENVIRONMENT.md",
    "docs/DATA_FETCH_UI_WORKFLOW.md",
    "docs/REQUIREMENTS_TOOLS.md",
    "docs/EXTERNAL_TOOLS_AUDIT.md",
)

#: Path-name parts that exclude any directory or file
#: containing them. Applied case-sensitively to every
#: relative path at copy time.
EXCLUDE_PATH_FRAGMENTS: tuple = (
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".github",
    ".venv",
    "build",
    "dist",
    "tests",
    "data/catalogs",
    "cache",
    "native",
)

#: File-extension exclusions (lowercased; matched with
#: ``.endswith``).
EXCLUDE_EXTENSIONS: tuple = (
    ".pyc", ".pyo", ".log", ".coverage",
    ".db", ".bin",
)

#: Plus a hard size cap on individual files. Anything larger
#: than this gets logged + skipped — if a 100MB Gaia chunk
#: lands in the staging copy by accident, the package never
#: ships it.
MAX_FILE_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB

#: Required-file allowlist the package must contain to be
#: considered valid. The validator runs after staging.
REQUIRED_FILES: tuple = (
    "unav_pro/__init__.py",
    "unav_pro/version.py",
    "unav_pro/unav_plugin.pyp",
    "unav_pro/core/__init__.py",
    "unav_pro/core/health_check.py",
    "unav_pro/core/state_manager.py",
    "unav_pro/data/__init__.py",
    "unav_pro/data/schema.py",
    "unav_pro/db/__init__.py",
    "unav_pro/voyage/__init__.py",
    "unav_pro/voyage/mission.py",
    "unav_pro/animation/__init__.py",
    "unav_pro/export/__init__.py",
    "unav_pro/c4d_objects/__init__.py",
    "unav_pro/ui/__init__.py",
    "unav_pro/core/issue_report.py",
    "unav_pro/core/first_run.py",
    "unav_pro/tools/__init__.py",
    "unav_pro/tools/tool_registry.py",
    "unav_pro/tools/python_env.py",
    "unav_pro/tools/tool_runner.py",
    "unav_pro/ui/tools_panel.py",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "NOTICE.md",
    "RELEASE_NOTES_v2.4.md",
    "RELEASE_NOTES_v2.5.md",
    "RELEASE_NOTES_v3.0.md",
    "RELEASE_NOTES_v3.1.md",
    "RELEASE_NOTES_v3.2.md",
    "RELEASE_NOTES_v3.3.md",
    "RELEASE_NOTES_v3.4_INTERNAL_BETA.md",
    "RELEASE_NOTES_v3.45.md",
    "RELEASE_NOTES_v3.5_PUBLIC_ALPHA.md",
    "RELEASE_NOTES_v3.6.md",
    "RELEASE_NOTES_v3.7.md",
    "RELEASE_NOTES_v3.8.md",
    "RELEASE_NOTES_v3.9.md",
    "requirements-tools.txt",
    "docs/INTEGRATED_EXTERNAL_TOOLS.md",
    "docs/TOOLS_PYTHON_ENVIRONMENT.md",
    "docs/DATA_FETCH_UI_WORKFLOW.md",
    "docs/REQUIREMENTS_TOOLS.md",
    "docs/INSTALL_C4D_2023_PLUS.md",
    "docs/QUICK_START.md",
    "docs/PUBLIC_ALPHA_TESTING_GUIDE.md",
    "docs/ISSUE_REPORTING.md",
    "docs/FIRST_RUN_GUIDE.md",
    "docs/DATA_SOURCE_ATTRIBUTION.md",
    "docs/V3_6_PROCEDURAL_CINEMATIC_HELPERS.md",
    "docs/CAMERA_RIGS.md",
    "docs/V3_7_ADVANCED_ASTRONOMICAL_QUERIES.md",
    "docs/EPOCH_AWARE_QUERY_LIMITATIONS.md",
    "docs/V3_8_EXHIBITION_WORKFLOWS.md",
    "docs/GUIDED_TOUR_CHAPTERS.md",
    "docs/USER_MANUAL.md",
    "docs/ARTIST_QUICKSTART.md",
    "docs/TD_GUIDE.md",
    "docs/ROADMAP.md",
    "docs/V3_0_SCALABILITY_AND_STREAMING.md",
    "docs/LARGE_DATA_WORKFLOWS.md",
    "docs/V3_1_PROJECT_WORKSPACES.md",
    "docs/SCENE_ORGANIZATION.md",
    "docs/V3_2_DATA_INTEGRITY.md",
    "docs/SCIENTIFIC_LIMITATIONS.md",
    "docs/V3_3_PRESENTATION_MODE.md",
    "docs/EDUCATIONAL_WORKFLOWS.md",
    "docs/V3_4_INTERNAL_BETA_CHECKLIST.md",
    "docs/V3_45_NATIVE_C4D_WORKFLOW.md",
    "docs/UNDO_REDO_SUPPORT.md",
    "docs/OBJECT_MANAGER_STRUCTURE.md",
    "docs/MULTI_DOCUMENT_BEHAVIOR.md",
    "samples/minimal_unav_demo/README.md",
    "samples/internal_beta_demo/README.md",
    "samples/internal_beta_demo/project_manifest.json",
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class PackageReport:
    """Outcome of one ``build_release_zip`` call.

    The CLI renders ``summary_line``; tests inspect every
    field directly.
    """

    success: bool = False
    zip_path: str = ""
    file_count: int = 0
    total_size_bytes: int = 0
    skipped: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)

    def summary_line(self) -> str:
        if not self.success:
            return (
                f"Package build FAILED — "
                f"{len(self.warnings)} warning(s), "
                f"{len(self.missing_required)} missing required file(s)."
            )
        kb = self.total_size_bytes / 1024.0
        return (
            f"Package OK: {self.zip_path} "
            f"({self.file_count} file(s), {kb:.1f} KB)."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _path_is_excluded(rel_path: str) -> bool:
    """Return True when ``rel_path`` should not appear in
    the staging copy. ``rel_path`` is relative to the repo
    root, with forward-slash separators."""
    norm = rel_path.replace(os.sep, "/")
    for fragment in EXCLUDE_PATH_FRAGMENTS:
        if fragment in norm.split("/"):
            return True
        # Multi-segment fragments (e.g. "data/catalogs") are
        # checked as substrings, anchored at a path
        # boundary.
        if "/" in fragment and (norm == fragment or norm.startswith(fragment + "/")):
            return True
    lower = norm.lower()
    for ext in EXCLUDE_EXTENSIONS:
        if lower.endswith(ext):
            return True
    # Hidden files / dirs.
    parts = norm.split("/")
    for p in parts:
        if p.startswith(".") and p not in (".", ".."):
            return True
    return False


def _collect_files(
    repo_root: str,
    *,
    include: Sequence[str],
    docs: Sequence[str],
) -> List[str]:
    """Walk every include + docs entry under ``repo_root``
    and return a sorted list of *relative* paths (with
    forward-slash separators) the package should carry."""
    out: set = set()
    for rel in list(include) + list(docs):
        abs_path = os.path.join(repo_root, rel)
        if os.path.isfile(abs_path):
            if not _path_is_excluded(rel):
                out.add(rel.replace(os.sep, "/"))
            continue
        if os.path.isdir(abs_path):
            for dirpath, dirnames, filenames in os.walk(abs_path):
                # Prune excluded subdirs in-place so os.walk
                # never recurses into them.
                pruned = []
                for d in list(dirnames):
                    sub_rel = os.path.relpath(
                        os.path.join(dirpath, d), repo_root,
                    ).replace(os.sep, "/")
                    if _path_is_excluded(sub_rel):
                        pruned.append(d)
                for d in pruned:
                    dirnames.remove(d)

                for fname in filenames:
                    full = os.path.join(dirpath, fname)
                    sub_rel = os.path.relpath(full, repo_root).replace(os.sep, "/")
                    if _path_is_excluded(sub_rel):
                        continue
                    out.add(sub_rel)
            continue
        # Path doesn't exist on disk — silently skipped; the
        # validator catches required-file misses later.
    return sorted(out)


def _stage_files(
    repo_root: str,
    rel_paths: Iterable[str],
    staging: str,
) -> tuple:
    """Copy each ``rel_path`` into ``staging`` preserving
    structure. Returns ``(written_paths, skipped_too_large)``.
    """
    written: List[str] = []
    skipped: List[str] = []
    for rel in rel_paths:
        src = os.path.join(repo_root, rel)
        if not os.path.isfile(src):
            continue
        try:
            size = os.path.getsize(src)
        except OSError:
            size = 0
        if size > MAX_FILE_SIZE_BYTES:
            skipped.append(f"{rel} ({size} bytes — exceeds {MAX_FILE_SIZE_BYTES})")
            continue
        dst = os.path.join(staging, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        written.append(rel)
    return written, skipped


def _validate_required(
    written: Sequence[str], required: Sequence[str],
) -> List[str]:
    """Return the list of required relative paths that are
    absent from ``written``."""
    written_set = {p.replace(os.sep, "/") for p in written}
    missing: List[str] = []
    for r in required:
        if r.replace(os.sep, "/") not in written_set:
            missing.append(r)
    return missing


def _zip_staging(staging: str, zip_path: str) -> int:
    """Zip every file under ``staging`` into ``zip_path``.
    Returns the total bytes written. Files are added in
    sorted order so the zip is reproducible."""
    os.makedirs(os.path.dirname(os.path.abspath(zip_path)) or ".", exist_ok=True)
    total = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(staging):
            dirnames.sort()
            for fname in sorted(filenames):
                src = os.path.join(dirpath, fname)
                arcname = os.path.relpath(src, staging).replace(os.sep, "/")
                zf.write(src, arcname=arcname)
                try:
                    total += os.path.getsize(src)
                except OSError:
                    pass
    return total


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_release_zip(
    *,
    repo_root: Optional[str] = None,
    output_zip: Optional[str] = None,
    staging: Optional[str] = None,
    keep_staging: bool = False,
    include: Optional[Sequence[str]] = None,
    docs: Optional[Sequence[str]] = None,
    required: Optional[Sequence[str]] = None,
) -> PackageReport:
    """Build a release zip. Pure-Python; tests use it
    directly.

    All arguments default to the repo-root values. ``output_zip``
    defaults to ``dist/unav_pro-<version>.zip``.
    """
    root = repo_root or REPO_ROOT
    inc = include if include is not None else PACKAGE_INCLUDE
    dcs = docs if docs is not None else PACKAGE_DOCS
    req = required if required is not None else REQUIRED_FILES

    # Resolve the version.
    version = _read_version(root)
    if output_zip is None:
        output_zip = os.path.join(root, "dist", f"unav_pro-{version}.zip")

    report = PackageReport(zip_path=os.path.abspath(output_zip))

    rel_paths = _collect_files(root, include=inc, docs=dcs)
    if not rel_paths:
        report.warnings.append(
            "no files matched the include/docs lists."
        )
        return report

    cleanup_staging = not keep_staging
    if staging is None:
        staging = tempfile.mkdtemp(prefix="unav_pro_pkg_")
    else:
        os.makedirs(staging, exist_ok=True)
        cleanup_staging = False  # the caller owns the dir

    try:
        written, skipped = _stage_files(root, rel_paths, staging)
        report.skipped.extend(skipped)
        if skipped:
            report.warnings.append(
                f"{len(skipped)} file(s) skipped (size cap)."
            )

        missing = _validate_required(written, req)
        if missing:
            report.missing_required = list(missing)
            report.warnings.append(
                f"{len(missing)} required file(s) missing — package "
                "will not be written."
            )
            return report

        report.total_size_bytes = _zip_staging(staging, output_zip)
        report.file_count = len(written)
        report.success = True
        return report
    finally:
        if cleanup_staging:
            try:
                shutil.rmtree(staging, ignore_errors=True)
            except OSError:
                pass


def _read_version(repo_root: str) -> str:
    """Read ``PLUGIN_VERSION`` from ``unav_pro/version.py``
    without importing the plugin (so the script works
    outside Cinema 4D)."""
    path = os.path.join(repo_root, "unav_pro", "version.py")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("PLUGIN_VERSION"):
                    # PLUGIN_VERSION: str = "2.4.0"
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        value = parts[1].strip()
                        if value.startswith('"') and value.endswith('"'):
                            return value[1:-1]
                        if value.startswith("'") and value.endswith("'"):
                            return value[1:-1]
    except OSError:
        pass
    return "0.0.0"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build a UNAV Pro release zip.",
    )
    p.add_argument(
        "--output", default=None,
        help="output zip path (default: dist/unav_pro-<version>.zip)",
    )
    p.add_argument(
        "--staging", default=None,
        help="staging directory (default: a fresh tempdir)",
    )
    p.add_argument(
        "--keep-staging", action="store_true",
        help="leave the staging directory in place after build",
    )
    p.add_argument(
        "--repo-root", default=REPO_ROOT,
        help="repository root (default: parent of this script)",
    )
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    report = build_release_zip(
        repo_root=args.repo_root,
        output_zip=args.output,
        staging=args.staging,
        keep_staging=args.keep_staging,
    )
    print(report.summary_line())
    for w in report.warnings:
        print(f"  ! {w}")
    for s in report.skipped:
        print(f"  - skipped: {s}")
    for m in report.missing_required:
        print(f"  - missing required: {m}")
    return 0 if report.success else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
