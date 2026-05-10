"""v3.5 package-manifest tests.

Asserts the v3.5 release zip contains the public-alpha
artefacts (LICENSE, NOTICE, the new docs) and excludes
generated / cache / dist directories.
"""

from __future__ import annotations

import os
import sys

import pytest


_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from package_plugin import (  # noqa: E402
    EXCLUDE_PATH_FRAGMENTS,
    PACKAGE_DOCS,
    PACKAGE_INCLUDE,
    REQUIRED_FILES,
    _collect_files,
    _path_is_excluded,
    build_release_zip,
)


# ---------------------------------------------------------------------------
# License + attribution wired into the package
# ---------------------------------------------------------------------------


def test_package_include_carries_license():
    assert "LICENSE" in PACKAGE_INCLUDE


def test_package_include_carries_notice():
    assert "NOTICE.md" in PACKAGE_INCLUDE


def test_package_include_carries_v35_release_notes():
    assert "RELEASE_NOTES_v3.5_PUBLIC_ALPHA.md" in PACKAGE_INCLUDE


def test_required_files_carries_license():
    assert "LICENSE" in REQUIRED_FILES


def test_required_files_carries_notice():
    assert "NOTICE.md" in REQUIRED_FILES


def test_required_files_carries_v35_release_notes():
    assert "RELEASE_NOTES_v3.5_PUBLIC_ALPHA.md" in REQUIRED_FILES


def test_required_files_carries_first_run_guide():
    assert "docs/FIRST_RUN_GUIDE.md" in REQUIRED_FILES


def test_required_files_carries_issue_reporting():
    assert "docs/ISSUE_REPORTING.md" in REQUIRED_FILES


def test_required_files_carries_public_alpha_guide():
    assert "docs/PUBLIC_ALPHA_TESTING_GUIDE.md" in REQUIRED_FILES


def test_required_files_carries_data_attribution():
    assert "docs/DATA_SOURCE_ATTRIBUTION.md" in REQUIRED_FILES


def test_required_files_carries_issue_report_module():
    assert "unav_pro/core/issue_report.py" in REQUIRED_FILES


def test_required_files_carries_first_run_module():
    assert "unav_pro/core/first_run.py" in REQUIRED_FILES


def test_package_docs_carries_v35_docs():
    expected = {
        "docs/PUBLIC_ALPHA_TESTING_GUIDE.md",
        "docs/ISSUE_REPORTING.md",
        "docs/FIRST_RUN_GUIDE.md",
        "docs/DATA_SOURCE_ATTRIBUTION.md",
    }
    assert expected.issubset(set(PACKAGE_DOCS))


# ---------------------------------------------------------------------------
# Excluded fragments
# ---------------------------------------------------------------------------


def test_exclude_path_fragments_excludes_dist():
    assert "dist" in EXCLUDE_PATH_FRAGMENTS


def test_exclude_path_fragments_excludes_cache():
    assert "cache" in EXCLUDE_PATH_FRAGMENTS


def test_exclude_path_fragments_excludes_data_catalogs():
    assert "data/catalogs" in EXCLUDE_PATH_FRAGMENTS


def test_path_is_excluded_for_dist():
    assert _path_is_excluded("dist/unav_pro-3.4.5.zip")


def test_path_is_excluded_for_cache():
    assert _path_is_excluded("cache/gaia/something.jsonl")


def test_path_is_excluded_for_pycache():
    assert _path_is_excluded("unav_pro/__pycache__/foo.pyc")


def test_path_is_excluded_for_pyc_extension():
    assert _path_is_excluded("foo.pyc")


# ---------------------------------------------------------------------------
# _collect_files end-to-end
# ---------------------------------------------------------------------------


def test_collect_files_includes_license():
    rels = _collect_files(_REPO_ROOT, include=PACKAGE_INCLUDE, docs=PACKAGE_DOCS)
    assert "LICENSE" in rels


def test_collect_files_includes_notice():
    rels = _collect_files(_REPO_ROOT, include=PACKAGE_INCLUDE, docs=PACKAGE_DOCS)
    assert "NOTICE.md" in rels


def test_collect_files_excludes_dist_zips():
    rels = _collect_files(_REPO_ROOT, include=PACKAGE_INCLUDE, docs=PACKAGE_DOCS)
    assert not any(r.startswith("dist/") for r in rels)


def test_collect_files_includes_data_attribution():
    rels = _collect_files(_REPO_ROOT, include=PACKAGE_INCLUDE, docs=PACKAGE_DOCS)
    assert "docs/DATA_SOURCE_ATTRIBUTION.md" in rels


def test_collect_files_includes_internal_beta_demo():
    rels = _collect_files(_REPO_ROOT, include=PACKAGE_INCLUDE, docs=PACKAGE_DOCS)
    # The bundled samples ship as part of the public alpha.
    assert any(
        r.startswith("samples/internal_beta_demo/") for r in rels
    )


# ---------------------------------------------------------------------------
# build_release_zip end-to-end
# ---------------------------------------------------------------------------


def test_build_release_zip_includes_license(tmp_path):
    import zipfile
    output = str(tmp_path / "test.zip")
    report = build_release_zip(repo_root=_REPO_ROOT, output_zip=output)
    assert report.success, report.summary_line()
    with zipfile.ZipFile(output) as zf:
        names = set(zf.namelist())
    assert "LICENSE" in names
    assert "NOTICE.md" in names
    assert "RELEASE_NOTES_v3.5_PUBLIC_ALPHA.md" in names
    assert "docs/DATA_SOURCE_ATTRIBUTION.md" in names


def test_build_release_zip_excludes_dist_directory(tmp_path):
    import zipfile
    output = str(tmp_path / "test.zip")
    build_release_zip(repo_root=_REPO_ROOT, output_zip=output)
    with zipfile.ZipFile(output) as zf:
        names = zf.namelist()
    assert not any(n.startswith("dist/") for n in names)


def test_build_release_zip_succeeds_with_v35_required_files(tmp_path):
    output = str(tmp_path / "test.zip")
    report = build_release_zip(repo_root=_REPO_ROOT, output_zip=output)
    assert report.success
    assert not report.missing_required


# ---------------------------------------------------------------------------
# Sample demos available
# ---------------------------------------------------------------------------


def test_minimal_demo_exists():
    assert os.path.isdir(
        os.path.join(_REPO_ROOT, "samples", "minimal_unav_demo"),
    )


def test_internal_beta_demo_exists():
    assert os.path.isdir(
        os.path.join(_REPO_ROOT, "samples", "internal_beta_demo"),
    )
