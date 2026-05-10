"""v3.5 release-artifact tests.

Asserts the public-alpha repo carries the artefacts a
first-time visitor expects: LICENSE, NOTICE.md, the
v3.5 release notes, the three v3.5 docs, the
DATA_SOURCE_ATTRIBUTION reference.
"""

from __future__ import annotations

import os

import pytest


_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def _path(rel: str) -> str:
    return os.path.join(_REPO_ROOT, rel)


# ---------------------------------------------------------------------------
# License + attribution
# ---------------------------------------------------------------------------


def test_license_file_present():
    assert os.path.isfile(_path("LICENSE"))


def test_license_is_apache_2():
    with open(_path("LICENSE"), encoding="utf-8") as fh:
        text = fh.read()
    assert "Apache License" in text
    assert "Version 2.0" in text


def test_notice_file_present():
    assert os.path.isfile(_path("NOTICE.md"))


def test_notice_mentions_apache_2():
    with open(_path("NOTICE.md"), encoding="utf-8") as fh:
        text = fh.read()
    assert "Apache License" in text
    assert "LICENSE" in text


def test_notice_mentions_data_sources():
    with open(_path("NOTICE.md"), encoding="utf-8") as fh:
        text = fh.read()
    for source in ("Gaia", "SDSS", "DESI", "JPL Horizons"):
        assert source in text, f"NOTICE missing '{source}'"


def test_notice_says_no_data_redistributed():
    with open(_path("NOTICE.md"), encoding="utf-8") as fh:
        # Strip Markdown emphasis so "does **not**
        # redistribute" still matches the substring check.
        text = fh.read().lower().replace("*", "")
    assert (
        "does not redistribute" in text
        or "do not redistribute" in text
        or "not redistributed" in text
    )


# ---------------------------------------------------------------------------
# Required v3.5 docs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relpath", [
    "RELEASE_NOTES_v3.5_PUBLIC_ALPHA.md",
    "docs/PUBLIC_ALPHA_TESTING_GUIDE.md",
    "docs/ISSUE_REPORTING.md",
    "docs/FIRST_RUN_GUIDE.md",
    "docs/DATA_SOURCE_ATTRIBUTION.md",
])
def test_required_v35_doc_present(relpath):
    assert os.path.isfile(_path(relpath)), f"missing {relpath}"


# ---------------------------------------------------------------------------
# Release-notes content
# ---------------------------------------------------------------------------


def test_release_notes_mention_apache_2():
    with open(_path("RELEASE_NOTES_v3.5_PUBLIC_ALPHA.md"),
              encoding="utf-8") as fh:
        text = fh.read()
    assert "Apache" in text


def test_release_notes_list_known_limitations():
    with open(_path("RELEASE_NOTES_v3.5_PUBLIC_ALPHA.md"),
              encoding="utf-8") as fh:
        text = fh.read()
    assert "Known limitations" in text
    assert "Auto Sync" in text


def test_release_notes_warn_about_rendering_scope():
    with open(_path("RELEASE_NOTES_v3.5_PUBLIC_ALPHA.md"),
              encoding="utf-8") as fh:
        text = fh.read()
    assert "No rendering" in text or "not a renderer" in text.lower()


def test_release_notes_describe_install():
    with open(_path("RELEASE_NOTES_v3.5_PUBLIC_ALPHA.md"),
              encoding="utf-8") as fh:
        text = fh.read()
    assert "Installation" in text
    assert "Cinema 4D" in text


# ---------------------------------------------------------------------------
# README banner
# ---------------------------------------------------------------------------


def test_readme_has_public_alpha_banner():
    with open(_path("README.md"), encoding="utf-8") as fh:
        text = fh.read()
    assert "Public Alpha" in text
    assert "Reporting issues" in text


def test_readme_links_data_attribution():
    with open(_path("README.md"), encoding="utf-8") as fh:
        text = fh.read()
    assert "DATA_SOURCE_ATTRIBUTION.md" in text


def test_readme_links_license():
    with open(_path("README.md"), encoding="utf-8") as fh:
        text = fh.read()
    assert "LICENSE" in text


def test_readme_describes_apache_2():
    with open(_path("README.md"), encoding="utf-8") as fh:
        text = fh.read()
    assert "Apache 2.0" in text
