#!/usr/bin/env python3
"""v2.4 one-script test runner.

Walks every ``test_*.py`` under ``unav_pro/tests/`` via
pytest and prints a short summary the release-engineering
checklist consumes.

Usage::

    python scripts/run_tests.py                     # full suite
    python scripts/run_tests.py --filter v22        # only v2.2 tests
    python scripts/run_tests.py --quiet             # minimal output

The runner classifies tests by filename prefix so the
summary tells the artist "state tests OK, animation tests
OK, export tests OK" instead of one giant pass/fail count.

Stdlib + pytest. Uses ``pytest.main`` rather than spawning
subprocesses so the runner works inside packaged builds.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Sequence


REPO_ROOT: str = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
TESTS_DIR: str = os.path.join(REPO_ROOT, "unav_pro", "tests")


#: Test categories the runner reports separately. Each entry
#: is ``(label, prefix)`` — files in ``unav_pro/tests/``
#: whose basename starts with ``prefix`` belong to the
#: category. Files not matching any prefix go into ``other``.
TEST_CATEGORIES: tuple = (
    ("state",        "test_v17"),
    ("animation",    "test_v22"),
    ("voyage",       "test_v14"),
    ("knowledge",    "test_knowledge"),
    ("overlays",     "test_v20"),
    ("science",      "test_v21"),
    ("export",       "test_v23"),
    ("v18",          "test_v18"),
    ("v19",          "test_v19"),
    ("release",      "test_v24"),
)


@dataclass
class CategoryReport:
    label: str
    files: List[str] = field(default_factory=list)


@dataclass
class RunReport:
    """Aggregate run report. The runner returns this so
    tests can drive the runner pure-Python and assert the
    field shapes."""

    categories: List[CategoryReport] = field(default_factory=list)
    other_files: List[str] = field(default_factory=list)
    total_files: int = 0
    pytest_exit_code: int = -1

    def summary_line(self) -> str:
        if self.pytest_exit_code == 0:
            return f"All {self.total_files} test file(s) passed."
        return f"Tests FAILED (pytest exit code {self.pytest_exit_code})."


def _categorise(test_files: Sequence[str]) -> RunReport:
    """Bucket ``test_files`` (basenames) into categories.
    Pure helper; tests use this directly without spawning
    pytest."""
    rpt = RunReport()
    for label, _prefix in TEST_CATEGORIES:
        rpt.categories.append(CategoryReport(label=label))
    for fname in sorted(test_files):
        bucketed = False
        for cat, (_, prefix) in zip(rpt.categories, TEST_CATEGORIES):
            if fname.startswith(prefix):
                cat.files.append(fname)
                bucketed = True
                break
        if not bucketed:
            rpt.other_files.append(fname)
    rpt.total_files = sum(len(c.files) for c in rpt.categories) + len(rpt.other_files)
    return rpt


def list_test_files(tests_dir: str = TESTS_DIR) -> List[str]:
    """Return every ``test_*.py`` basename under
    ``tests_dir`` (sorted, unique)."""
    if not os.path.isdir(tests_dir):
        return []
    out: List[str] = []
    for fname in sorted(os.listdir(tests_dir)):
        if fname.startswith("test_") and fname.endswith(".py"):
            out.append(fname)
    return out


def categorise_tests(tests_dir: str = TESTS_DIR) -> RunReport:
    """Top-level categorisation entry. Doesn't run any
    tests; tests use this to assert the bucket layout."""
    return _categorise(list_test_files(tests_dir))


def render_summary(report: RunReport) -> str:
    lines: List[str] = ["=== UNAV Pro test runner ==="]
    lines.append(report.summary_line())
    lines.append("")
    for cat in report.categories:
        if cat.files:
            lines.append(f"  {cat.label:14}: {len(cat.files)} file(s)")
    if report.other_files:
        lines.append(f"  {'other':14}: {len(report.other_files)} file(s)")
    return "\n".join(lines)


def _run_pytest(
    tests_dir: str,
    *,
    filter_str: Optional[str] = None,
    quiet: bool = False,
) -> int:
    try:
        import pytest
    except ImportError:
        print(
            "ERROR: pytest is not installed. "
            "Install it via 'pip install pytest' to run the tests."
        )
        return 2
    args: List[str] = [tests_dir]
    if quiet:
        args.append("-q")
    if filter_str:
        args.extend(["-k", filter_str])
    return int(pytest.main(args))


def run(
    *,
    tests_dir: str = TESTS_DIR,
    filter_str: Optional[str] = None,
    quiet: bool = False,
) -> RunReport:
    """Run the suite + return a report."""
    report = categorise_tests(tests_dir)
    report.pytest_exit_code = _run_pytest(
        tests_dir, filter_str=filter_str, quiet=quiet,
    )
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="UNAV Pro test runner.")
    p.add_argument(
        "--filter", default=None,
        help="-k filter passed straight through to pytest.",
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="silence pytest's per-test dot output.",
    )
    p.add_argument(
        "--tests-dir", default=TESTS_DIR,
        help="override the tests directory.",
    )
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    report = run(
        tests_dir=args.tests_dir,
        filter_str=args.filter,
        quiet=args.quiet,
    )
    print(render_summary(report))
    return report.pytest_exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
