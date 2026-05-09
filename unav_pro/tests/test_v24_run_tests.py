"""v2.4 test-runner categorisation tests.

Drive the runner's pure-Python helpers (``categorise_tests``,
``list_test_files``) without invoking pytest itself.
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

from run_tests import (  # noqa: E402
    TEST_CATEGORIES,
    CategoryReport,
    RunReport,
    _categorise,
    categorise_tests,
    list_test_files,
    render_summary,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_categories_cover_every_release():
    """The runner's category list is the v2.4 release-prep
    audit. New milestone? Add the bucket here."""
    labels = {label for label, _ in TEST_CATEGORIES}
    expected = {
        "state", "animation", "voyage", "knowledge",
        "overlays", "science", "export", "v18", "v19",
        "release",
    }
    assert expected.issubset(labels)


# ---------------------------------------------------------------------------
# Pure categorisation
# ---------------------------------------------------------------------------


def test_categorise_buckets_by_prefix():
    rpt = _categorise([
        "test_v17_stability.py",
        "test_v22_animated_state.py",
        "test_v24_version.py",
        "test_v24_health_check.py",
        "test_random_other.py",
    ])
    cats = {c.label: c.files for c in rpt.categories}
    assert "test_v17_stability.py" in cats["state"]
    assert "test_v22_animated_state.py" in cats["animation"]
    assert "test_v24_version.py" in cats["release"]
    assert "test_random_other.py" in rpt.other_files


def test_categorise_total_includes_other():
    rpt = _categorise([
        "test_v17_a.py", "test_random.py",
    ])
    assert rpt.total_files == 2


def test_categorise_returns_run_report_shape():
    rpt = _categorise([])
    assert isinstance(rpt, RunReport)
    assert rpt.total_files == 0
    assert all(isinstance(c, CategoryReport) for c in rpt.categories)


# ---------------------------------------------------------------------------
# list_test_files
# ---------------------------------------------------------------------------


def test_list_test_files_finds_real_tests():
    """The live tests directory contains a non-trivial set
    of test files."""
    here = os.path.dirname(os.path.abspath(__file__))
    files = list_test_files(here)
    assert "test_v24_run_tests.py" in files
    assert "test_v24_version.py" in files
    assert all(f.startswith("test_") for f in files)


def test_list_test_files_handles_missing_dir(tmp_path):
    """Pointing at a non-existent dir → empty list, no
    raise."""
    files = list_test_files(str(tmp_path / "nope"))
    assert files == []


def test_list_test_files_only_matches_test_prefix(tmp_path):
    (tmp_path / "test_real.py").write_text("", encoding="utf-8")
    (tmp_path / "helper.py").write_text("", encoding="utf-8")
    (tmp_path / "test_other.py").write_text("", encoding="utf-8")
    files = list_test_files(str(tmp_path))
    assert "test_real.py" in files
    assert "test_other.py" in files
    assert "helper.py" not in files


# ---------------------------------------------------------------------------
# Top-level categorise_tests
# ---------------------------------------------------------------------------


def test_categorise_tests_against_real_repo():
    here = os.path.dirname(os.path.abspath(__file__))
    rpt = categorise_tests(here)
    assert rpt.total_files >= 8  # at least: v17 / v18 / v19 / v20 / v21 / v22 / v23 / v24
    by_label = {c.label: len(c.files) for c in rpt.categories}
    # Sanity: at least the v24 bucket is non-empty.
    assert by_label.get("release", 0) >= 1


def test_render_summary_includes_label_lines():
    rpt = _categorise([
        "test_v17_a.py", "test_v22_b.py", "test_v24_c.py",
    ])
    text = render_summary(rpt)
    assert "state" in text
    assert "animation" in text
    assert "release" in text


def test_render_summary_handles_empty_input():
    text = render_summary(_categorise([]))
    assert "test runner" in text
