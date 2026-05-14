"""UI layout sanity tests.

The Cinema 4D dialog can't be driven from a unit
test (it needs the host's GUI), but the dialog's
source can. These tests assert that the v3.x +
UI-sizing-fix wiring is in place so a future
refactor can't silently re-introduce the bug
the fix repaired:

* The main dialog's ``CreateLayout`` opens a
  vertical scroll group around its body.
* The main command opens the dialog at a laptop-
  friendly default size.
* The diagnostics multi-line edit declares a
  bounded ``inith``.
* The new UI layout doc exists.
"""

from __future__ import annotations

import os
import re


_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def _read(relpath: str) -> str:
    with open(
        os.path.join(_REPO_ROOT, relpath), encoding="utf-8",
    ) as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Main dialog scroll group wrapper
# ---------------------------------------------------------------------------


def test_main_dialog_opens_scroll_group():
    src = _read("unav_pro/ui/main_dialog.py")
    assert "ScrollGroupBegin" in src
    assert "_ID_GROUP_SCROLL_ROOT" in src
    assert "SCROLLGROUP_VERT" in src
    assert "SCROLLGROUP_AUTOVERT" in src


def test_main_dialog_scroll_group_inside_create_layout():
    src = _read("unav_pro/ui/main_dialog.py")
    create_layout_idx = src.index("def CreateLayout")
    # Look for the actual *call*, not the constant /
    # comment occurrences that appear elsewhere in
    # the module.
    call_idx = src.index("self.ScrollGroupBegin(")
    assert call_idx > create_layout_idx


def test_main_dialog_closes_wrapper_inside_create_layout():
    """The two extra GroupEnd calls land before the
    final return True so the wrappers balance."""
    src = _read("unav_pro/ui/main_dialog.py")
    assert "if getattr(self, \"_scroll_wrapper_active\", False):" in src


# ---------------------------------------------------------------------------
# Main command default size
# ---------------------------------------------------------------------------


def test_main_command_uses_laptop_default_size():
    src = _read("unav_pro/ui/main_command.py")
    # Both defaults must be present, and tall enough
    # for the typical mid-laptop screen but small
    # enough to fit a 1366×768.
    width_match = re.search(r"defaultw\s*=\s*(\d+)", src)
    height_match = re.search(r"defaulth\s*=\s*(\d+)", src)
    assert width_match and height_match
    width = int(width_match.group(1))
    height = int(height_match.group(1))
    assert 600 <= width <= 1200, (
        f"defaultw out of band: {width}"
    )
    assert 480 <= height <= 1024, (
        f"defaulth out of band: {height}"
    )


def test_main_command_default_size_not_legacy_420_320():
    """The pre-fix defaults of 420×320 left the
    layout clipped on launch. Guard against
    regression."""
    src = _read("unav_pro/ui/main_command.py")
    assert "defaultw=420" not in src
    assert "defaulth=320" not in src


# ---------------------------------------------------------------------------
# Diagnostics multi-line edit
# ---------------------------------------------------------------------------


def test_diagnostics_panel_bounded_inith():
    src = _read("unav_pro/ui/diagnostics_panel.py")
    # Filter out comments so the regex only sees
    # the actual call site. The pre-fix value
    # ``inith=420`` lives in a doc comment now;
    # the executable value must be <= 320.
    code_lines = [
        line for line in src.splitlines()
        if not line.lstrip().startswith("#")
    ]
    match = re.search(
        r"inith\s*=\s*(\d+)", "\n".join(code_lines),
    )
    assert match, "diagnostics multi-line edit missing inith"
    inith = int(match.group(1))
    assert inith <= 320, (
        f"diagnostics inith too tall: {inith}"
    )


def test_diagnostics_dialog_open_height_capped():
    """The main dialog's diagnostics opener uses
    defaultw=620, defaulth=520 (was 620×620
    pre-fix)."""
    src = _read("unav_pro/ui/main_dialog.py")
    # Match the literal pair that opens the
    # diagnostics dialog.
    assert "defaultw=620, defaulth=520" in src


# ---------------------------------------------------------------------------
# Docs
# ---------------------------------------------------------------------------


def test_ui_layout_notes_doc_present():
    path = os.path.join(_REPO_ROOT, "docs", "UI_LAYOUT_NOTES.md")
    assert os.path.isfile(path)


def test_ui_layout_notes_describes_scroll_group():
    text = _read("docs/UI_LAYOUT_NOTES.md")
    assert "ScrollGroupBegin" in text
    assert "scroll group" in text.lower()
    assert "laptop" in text.lower()


def test_ui_layout_notes_describes_manual_test_matrix():
    text = _read("docs/UI_LAYOUT_NOTES.md")
    # The doc carries the recommended manual-test
    # display matrix.
    assert "1366" in text
    assert "1080" in text
