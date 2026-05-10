"""v2.5 documentation-suite sanity tests.

Doc files are part of the release contract: they're listed
in ``REQUIRED_FILES`` (see ``scripts/package_plugin.py``) and
ship inside the release zip. Tests assert the four new v2.5
docs exist on disk and contain the expected anchor sections,
so doc drift surfaces in CI rather than at QA time.
"""

from __future__ import annotations

import os

import pytest


_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_DOCS_DIR = os.path.join(_REPO_ROOT, "docs")


def _read(rel: str) -> str:
    path = os.path.join(_DOCS_DIR, rel)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Files exist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [
    "USER_MANUAL.md",
    "ARTIST_QUICKSTART.md",
    "TD_GUIDE.md",
    "ROADMAP.md",
    "QA_CHECKLIST.md",
])
def test_v25_doc_exists(name):
    assert os.path.isfile(os.path.join(_DOCS_DIR, name)), (
        f"missing doc: {name}"
    )


# ---------------------------------------------------------------------------
# USER_MANUAL.md
# ---------------------------------------------------------------------------


def test_user_manual_has_core_sections():
    text = _read("USER_MANUAL.md")
    for anchor in (
        "# UNAV Pro",
        "Install",
        "Mission",
        "Bake",
        "Export",
        "Troubleshoot",
    ):
        assert anchor in text, f"USER_MANUAL.md missing '{anchor}'"


# ---------------------------------------------------------------------------
# ARTIST_QUICKSTART.md
# ---------------------------------------------------------------------------


def test_artist_quickstart_walks_through_workflow():
    text = _read("ARTIST_QUICKSTART.md")
    for phrase in (
        "Install",
        "Sync",
        "Mission",
        "Bake",
        "Export",
    ):
        assert phrase in text, f"ARTIST_QUICKSTART.md missing '{phrase}'"


# ---------------------------------------------------------------------------
# TD_GUIDE.md
# ---------------------------------------------------------------------------


def test_td_guide_covers_pipeline_and_schemas():
    text = _read("TD_GUIDE.md")
    for phrase in (
        "schema",
        "pipeline",
        "performance",
        "export",
    ):
        # Match case-insensitively; TD doc uses sentence
        # capitalisation.
        assert phrase.lower() in text.lower(), (
            f"TD_GUIDE.md missing '{phrase}'"
        )


# ---------------------------------------------------------------------------
# ROADMAP.md
# ---------------------------------------------------------------------------


def test_roadmap_has_required_sections():
    text = _read("ROADMAP.md")
    for anchor in (
        "Implemented",
        "Planned",
        "Optional",
        "Explicitly out of scope",
    ):
        assert anchor in text, f"ROADMAP.md missing '{anchor}'"


def test_roadmap_excludes_renderer_and_bridge():
    """The boundary-restating section must explicitly call
    out renderer + RelativityRender + sockets/IPC as out of
    scope so the contract can't quietly drift."""
    text = _read("ROADMAP.md")
    assert "Render engine" in text or "render engine" in text
    assert "RelativityRender" in text
    assert "Sockets" in text or "IPC" in text


# ---------------------------------------------------------------------------
# QA_CHECKLIST.md
# ---------------------------------------------------------------------------


def test_qa_checklist_has_manual_install_section():
    text = _read("QA_CHECKLIST.md")
    # The v2.5 update added a "Manual end-to-end install
    # test" section walking through the eight artist steps.
    for phrase in (
        "Install from package",
        "Load sample",
        "Sync visible sector",
        "Inspect metadata",
        "Create mission",
        "Bake timeline",
        "Export package",
        "Reload plugin",
    ):
        assert phrase in text, (
            f"QA_CHECKLIST.md missing manual step '{phrase}'"
        )
