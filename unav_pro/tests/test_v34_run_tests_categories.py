"""v3.4 test-runner category coverage.

Verify ``scripts/run_tests.py`` knows about every v3.x
test family. Catches the regression where a new
milestone's tests get bucketed into ``other``."""

from __future__ import annotations

import os
import sys


_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from run_tests import (  # noqa: E402
    TEST_CATEGORIES,
    categorise_tests,
)


def test_categories_cover_v34_beta():
    labels = {label for label, _ in TEST_CATEGORIES}
    expected = {
        "state", "animation", "voyage", "knowledge",
        "overlays", "science", "export",
        "v18", "v19", "release",
        "workflow", "scalability", "workspace",
        "integrity", "presentation", "beta",
    }
    assert expected.issubset(labels)


def test_categorise_real_tests_buckets_v33_correctly():
    here = os.path.dirname(os.path.abspath(__file__))
    rpt = categorise_tests(here)
    by_label = {c.label: len(c.files) for c in rpt.categories}
    # Every v3.x bucket should be non-empty.
    for label in (
        "scalability", "workspace", "integrity", "presentation",
    ):
        assert by_label.get(label, 0) >= 1, (
            f"category '{label}' has no test files"
        )


def test_v34_beta_bucket_has_files():
    here = os.path.dirname(os.path.abspath(__file__))
    rpt = categorise_tests(here)
    by_label = {c.label: len(c.files) for c in rpt.categories}
    # v3.4 ships 3+ test files.
    assert by_label.get("beta", 0) >= 3
