"""Main UNAV Pro dialog.

A simple ``GeDialog`` with four action buttons and a multiline status log.
All button handlers delegate to ``core.mock_actions`` and append the
returned status to the log area. The dialog is intentionally
self-contained so it can be reasoned about and tested in isolation; it
does not touch the active document directly in this MVP.
"""

from __future__ import annotations

try:
    import c4d  # type: ignore
    from c4d import gui  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    gui = None  # type: ignore
    _C4D_AVAILABLE = False

from core import mock_actions
from core.logging_util import get_logger

_log = get_logger("ui.main_dialog")

# Local widget IDs. Kept in a small range to avoid colliding with C4D's
# standard symbol IDs.
_ID_GROUP_BUTTONS = 1000
_ID_BTN_LOAD = 1001
_ID_BTN_NULL = 1002
_ID_BTN_CLOUD = 1003
_ID_BTN_CLEAR = 1004
_ID_BTN_APPLY_FILTER = 1005
_ID_BTN_REGENERATE = 1006
_ID_GROUP_LOG = 2000
_ID_LOG = 2001
_ID_BTN_CLEAR_LOG = 2002


if _C4D_AVAILABLE:

    class UnavMainDialog(gui.GeDialog):
        """Main control panel for UNAV Pro (MVP)."""

        TITLE = "Universal Navigator Pro"

        def CreateLayout(self) -> bool:
            self.SetTitle(self.TITLE)

            # Buttons grid.
            self.GroupBegin(
                _ID_GROUP_BUTTONS, c4d.BFH_SCALEFIT, cols=2, rows=3,
                title="Actions",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddButton(_ID_BTN_LOAD, c4d.BFH_SCALEFIT, name="Load Dataset")
            self.AddButton(_ID_BTN_NULL, c4d.BFH_SCALEFIT, name="Create Navigation Null")
            self.AddButton(_ID_BTN_CLOUD, c4d.BFH_SCALEFIT, name="Generate Point Cloud")
            self.AddButton(_ID_BTN_CLEAR, c4d.BFH_SCALEFIT, name="Clear Scene")
            self.AddButton(_ID_BTN_APPLY_FILTER, c4d.BFH_SCALEFIT, name="Apply View Filter")
            self.AddButton(_ID_BTN_REGENERATE, c4d.BFH_SCALEFIT, name="Regenerate Visible Field")
            self.GroupEnd()

            # Status log.
            self.GroupBegin(
                _ID_GROUP_LOG, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                cols=1, rows=2, title="Status Log",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddMultiLineEditText(
                _ID_LOG,
                c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                inith=160,
                style=c4d.DR_MULTILINE_READONLY | c4d.DR_MULTILINE_MONOSPACED,
            )
            self.AddButton(_ID_BTN_CLEAR_LOG, c4d.BFH_RIGHT, name="Clear Log")
            self.GroupEnd()
            return True

        def InitValues(self) -> bool:
            self._append_log(f"{self.TITLE} ready.")
            return True

        def Command(self, mid: int, msg) -> bool:
            try:
                if mid == _ID_BTN_LOAD:
                    self._append_log(mock_actions.load_dataset())
                elif mid == _ID_BTN_NULL:
                    self._append_log(mock_actions.create_navigation_null())
                elif mid == _ID_BTN_CLOUD:
                    self._append_log(mock_actions.generate_point_cloud())
                elif mid == _ID_BTN_CLEAR:
                    self._append_log(mock_actions.clear_scene())
                elif mid == _ID_BTN_APPLY_FILTER:
                    self._append_log(mock_actions.apply_view_filter())
                elif mid == _ID_BTN_REGENERATE:
                    self._append_log(mock_actions.regenerate_visible_field())
                elif mid == _ID_BTN_CLEAR_LOG:
                    self.SetString(_ID_LOG, "")
            except Exception as exc:  # noqa: BLE001 — UI boundary handler
                _log.exception("Dialog command %s failed", mid)
                self._append_log(f"ERROR: {exc!r}")
            return True

        # --- helpers ---------------------------------------------------

        def _append_log(self, line: str) -> None:
            current = self.GetString(_ID_LOG) or ""
            new_text = (current + line + "\n") if current else (line + "\n")
            self.SetString(_ID_LOG, new_text)

else:  # pragma: no cover — non-C4D import path

    class UnavMainDialog:  # type: ignore[no-redef]
        """Stub used when ``c4d`` is not importable.

        Exists so that tests and tooling can import this module outside of
        Cinema 4D without raising. Instantiating it raises a clear error.
        """

        TITLE = "Universal Navigator Pro"

        def __init__(self, *_args, **_kwargs):
            raise RuntimeError(
                "UnavMainDialog can only be instantiated inside Cinema 4D."
            )
