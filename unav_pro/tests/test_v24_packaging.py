"""v2.4 packaging-script tests.

The packaging script lives at ``scripts/package_plugin.py``.
Tests import it directly (the script is importable) and
drive ``build_release_zip`` against a synthetic repo.
"""

from __future__ import annotations

import os
import sys
import zipfile

import pytest

# The packaging script lives in scripts/. Add it to the
# import path the same way the source repo's tests already
# add unav_pro/.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from package_plugin import (  # noqa: E402
    EXCLUDE_EXTENSIONS,
    EXCLUDE_PATH_FRAGMENTS,
    MAX_FILE_SIZE_BYTES,
    PACKAGE_DOCS,
    PACKAGE_INCLUDE,
    REQUIRED_FILES,
    PackageReport,
    _collect_files,
    _path_is_excluded,
    _read_version,
    build_release_zip,
)


# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------


def test_required_files_includes_version_module():
    assert "unav_pro/version.py" in REQUIRED_FILES


def test_required_files_includes_health_check():
    assert "unav_pro/core/health_check.py" in REQUIRED_FILES


def test_required_files_includes_install_doc():
    assert "docs/INSTALL_C4D_2023_PLUS.md" in REQUIRED_FILES
    assert "docs/QUICK_START.md" in REQUIRED_FILES


def test_required_files_includes_release_notes():
    assert "RELEASE_NOTES_v2.4.md" in REQUIRED_FILES


def test_required_files_includes_sample_demo_readme():
    assert "samples/minimal_unav_demo/README.md" in REQUIRED_FILES


def test_exclude_path_fragments_block_tests_and_caches():
    """Caches, tests, and generated data must never ship."""
    expected = {"__pycache__", ".pytest_cache", "tests",
                "cache", "data/catalogs", "native"}
    assert expected.issubset(set(EXCLUDE_PATH_FRAGMENTS))


def test_exclude_extensions_cover_common_artifacts():
    expected = {".pyc", ".pyo", ".log", ".coverage", ".db", ".bin"}
    assert expected.issubset(set(EXCLUDE_EXTENSIONS))


def test_max_file_size_is_reasonable():
    """5 MB is the v2.4 baseline; bumping it is a code
    change that must come with a release-notes entry."""
    assert 1 * 1024 * 1024 <= MAX_FILE_SIZE_BYTES <= 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# _path_is_excluded
# ---------------------------------------------------------------------------


def test_path_excluded_for_pycache():
    assert _path_is_excluded("unav_pro/__pycache__/foo.pyc")


def test_path_excluded_for_test_dir():
    assert _path_is_excluded("unav_pro/tests/test_foo.py")


def test_path_excluded_for_cache_dir():
    assert _path_is_excluded("cache/gaia_chunk.jsonl")


def test_path_excluded_for_data_catalogs():
    assert _path_is_excluded("data/catalogs/gaia_dr3.jsonl")


def test_path_excluded_for_pyc_extension():
    assert _path_is_excluded("foo.pyc")
    assert _path_is_excluded("FOO.PYC")  # case-insensitive ext check


def test_path_excluded_for_hidden_file():
    assert _path_is_excluded(".gitignore")
    assert _path_is_excluded("docs/.DS_Store")


def test_normal_path_not_excluded():
    assert not _path_is_excluded("unav_pro/version.py")
    assert not _path_is_excluded("docs/QUICK_START.md")
    assert not _path_is_excluded("samples/minimal_unav_demo/catalog.jsonl")


# ---------------------------------------------------------------------------
# _read_version
# ---------------------------------------------------------------------------


def test_read_version_finds_canonical_string():
    version = _read_version(_REPO_ROOT)
    assert version != "0.0.0"
    assert version.startswith("2.4")


def test_read_version_returns_zero_on_missing_repo(tmp_path):
    """Missing version.py → fallback rather than crash."""
    assert _read_version(str(tmp_path)) == "0.0.0"


# ---------------------------------------------------------------------------
# _collect_files
# ---------------------------------------------------------------------------


def test_collect_files_includes_version_module():
    rels = _collect_files(_REPO_ROOT, include=PACKAGE_INCLUDE, docs=PACKAGE_DOCS)
    assert "unav_pro/version.py" in rels


def test_collect_files_excludes_tests():
    rels = _collect_files(_REPO_ROOT, include=PACKAGE_INCLUDE, docs=PACKAGE_DOCS)
    assert not any(r.startswith("unav_pro/tests/") for r in rels)


def test_collect_files_excludes_pycache():
    rels = _collect_files(_REPO_ROOT, include=PACKAGE_INCLUDE, docs=PACKAGE_DOCS)
    assert not any("__pycache__" in r for r in rels)


def test_collect_files_includes_sample_demo():
    rels = _collect_files(_REPO_ROOT, include=PACKAGE_INCLUDE, docs=PACKAGE_DOCS)
    assert "samples/minimal_unav_demo/catalog.jsonl" in rels
    assert "samples/minimal_unav_demo/mission.json" in rels
    assert "samples/minimal_unav_demo/README.md" in rels


def test_collect_files_includes_required_docs():
    rels = _collect_files(_REPO_ROOT, include=PACKAGE_INCLUDE, docs=PACKAGE_DOCS)
    for required_doc in (
        "docs/INSTALL_C4D_2023_PLUS.md",
        "docs/QUICK_START.md",
        "docs/TROUBLESHOOTING.md",
    ):
        assert required_doc in rels


# ---------------------------------------------------------------------------
# build_release_zip end-to-end
# ---------------------------------------------------------------------------


def test_build_release_zip_succeeds(tmp_path):
    output = str(tmp_path / "test.zip")
    report = build_release_zip(
        repo_root=_REPO_ROOT, output_zip=output,
    )
    assert report.success is True, report.summary_line()
    assert os.path.isfile(output)
    assert report.file_count > 0
    assert not report.missing_required


def test_build_release_zip_excludes_test_files(tmp_path):
    output = str(tmp_path / "test.zip")
    build_release_zip(repo_root=_REPO_ROOT, output_zip=output)
    with zipfile.ZipFile(output) as zf:
        names = zf.namelist()
    assert not any(n.startswith("unav_pro/tests/") for n in names)
    assert not any("__pycache__" in n for n in names)
    assert not any(n.startswith("cache/") for n in names)
    assert not any(n.startswith("data/catalogs/") for n in names)


def test_build_release_zip_carries_required_files(tmp_path):
    output = str(tmp_path / "test.zip")
    build_release_zip(repo_root=_REPO_ROOT, output_zip=output)
    with zipfile.ZipFile(output) as zf:
        names = set(zf.namelist())
    for required in REQUIRED_FILES:
        assert required in names, f"missing {required}"


def test_build_release_zip_filename_matches_version(tmp_path):
    """When ``output_zip`` is omitted, the default name
    embeds the live version."""
    # We can't test the default location (it points at the
    # repo's dist/) without polluting the repo. We just
    # verify the version is reachable.
    version = _read_version(_REPO_ROOT)
    assert version.startswith("2.4")


def test_build_release_zip_with_synthetic_repo(tmp_path):
    """Build a tiny synthetic repo + verify the script
    handles include / exclude rules + the required-file
    check end-to-end."""
    fake_root = tmp_path / "fake_repo"
    (fake_root / "unav_pro" / "core").mkdir(parents=True)
    (fake_root / "unav_pro" / "__init__.py").write_text("", encoding="utf-8")
    (fake_root / "unav_pro" / "version.py").write_text(
        'PLUGIN_VERSION: str = "9.9.9"\n', encoding="utf-8",
    )
    (fake_root / "README.md").write_text("# Fake", encoding="utf-8")

    fake_required = ("README.md", "unav_pro/version.py", "unav_pro/__init__.py")
    fake_include = ("unav_pro", "README.md")
    output = str(tmp_path / "fake.zip")
    report = build_release_zip(
        repo_root=str(fake_root),
        output_zip=output,
        include=fake_include,
        docs=(),
        required=fake_required,
    )
    assert report.success
    with zipfile.ZipFile(output) as zf:
        names = set(zf.namelist())
    assert "README.md" in names
    assert "unav_pro/version.py" in names


def test_build_release_zip_refuses_when_required_missing(tmp_path):
    fake_root = tmp_path / "broken_repo"
    fake_root.mkdir()
    (fake_root / "README.md").write_text("# Fake", encoding="utf-8")
    output = str(tmp_path / "broken.zip")
    report = build_release_zip(
        repo_root=str(fake_root),
        output_zip=output,
        include=("README.md",),
        docs=(),
        required=("README.md", "unav_pro/version.py"),
    )
    assert report.success is False
    assert "unav_pro/version.py" in report.missing_required
    assert not os.path.exists(output)


def test_build_release_zip_skips_oversized_files(tmp_path, monkeypatch):
    """A file larger than the size cap is logged + skipped."""
    fake_root = tmp_path / "huge_repo"
    fake_root.mkdir()
    huge = fake_root / "big.bin.txt"
    huge.write_bytes(b"x" * (MAX_FILE_SIZE_BYTES + 1024))
    (fake_root / "README.md").write_text("# Fake", encoding="utf-8")
    output = str(tmp_path / "huge.zip")
    report = build_release_zip(
        repo_root=str(fake_root),
        output_zip=output,
        include=("README.md", "big.bin.txt"),
        docs=(),
        required=("README.md",),
    )
    # README is required + present → success.
    assert report.success
    # The huge file is in the skipped list.
    assert any("big.bin.txt" in s for s in report.skipped)
    with zipfile.ZipFile(output) as zf:
        assert "big.bin.txt" not in zf.namelist()


# ---------------------------------------------------------------------------
# PackageReport rendering
# ---------------------------------------------------------------------------


def test_package_report_summary_success_format():
    rep = PackageReport(success=True, zip_path="/tmp/x.zip",
                        file_count=5, total_size_bytes=2048)
    assert "Package OK" in rep.summary_line()


def test_package_report_summary_failure_format():
    rep = PackageReport(success=False,
                        warnings=["foo"], missing_required=["bar"])
    assert "FAILED" in rep.summary_line()
