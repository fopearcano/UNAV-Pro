"""Main menu command: opens the UNAV Pro dialog window.

This module wires a ``CommandData`` plugin into Cinema 4D's plugin menu.
The command is registered by ``unav_plugin.pyp``; this file only defines
the class. We keep the dialog instance on the class so re-invoking the
command re-uses the same window rather than spawning duplicates.
"""

from __future__ import annotations

try:
    import c4d  # type: ignore
    from c4d import plugins  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover
    c4d = None  # type: ignore
    plugins = None  # type: ignore
    _C4D_AVAILABLE = False

from core.logging_util import get_logger
from core.plugin_ids import PLUGIN_ID_MAIN_COMMAND, PLUGIN_ID_MAIN_DIALOG
from ui.main_dialog import UnavMainDialog

_log = get_logger("ui.main_command")


if _C4D_AVAILABLE:

    class UnavMainCommand(plugins.CommandData):
        """Menu command that opens the main UNAV Pro dialog."""

        _dialog: "UnavMainDialog | None" = None

        def Execute(self, doc) -> bool:
            try:
                if self._dialog is None:
                    self._dialog = UnavMainDialog()
                # Default size sized for laptop-class screens
                # (~1366×768). The dialog wraps its content in a
                # vertical ScrollGroup (see ui/main_dialog.py +
                # docs/UI_LAYOUT_NOTES.md), so the window stays
                # resizable in both directions and never forces
                # the user to make the host taller than the
                # screen.
                return bool(
                    self._dialog.Open(
                        dlgtype=c4d.DLG_TYPE_ASYNC,
                        pluginid=PLUGIN_ID_MAIN_DIALOG,
                        defaultw=720,
                        defaulth=640,
                    )
                )
            except Exception as exc:  # noqa: BLE001 — boundary handler
                _log.exception("Failed to open main dialog: %s", exc)
                return False

        def RestoreLayout(self, sec_ref) -> bool:
            try:
                if self._dialog is None:
                    self._dialog = UnavMainDialog()
                return bool(
                    self._dialog.Restore(
                        pluginid=PLUGIN_ID_MAIN_DIALOG, secret=sec_ref
                    )
                )
            except Exception as exc:  # noqa: BLE001
                _log.exception("Failed to restore main dialog layout: %s", exc)
                return False


    def register() -> bool:
        """Register the command with C4D's plugin system."""
        ok = plugins.RegisterCommandPlugin(
            id=PLUGIN_ID_MAIN_COMMAND,
            str="Universal Navigator Pro",
            info=0,
            help="Open the UNAV Pro control panel.",
            dat=UnavMainCommand(),
            icon=None,
        )
        if ok:
            _log.info("Registered main command (id=%s).", PLUGIN_ID_MAIN_COMMAND)
        else:
            _log.error("Failed to register main command (id=%s).", PLUGIN_ID_MAIN_COMMAND)
        return bool(ok)

else:  # pragma: no cover — non-C4D import path

    class UnavMainCommand:  # type: ignore[no-redef]
        pass

    def register() -> bool:  # type: ignore[no-redef]
        _log.warning("c4d module not available; skipping command registration.")
        return False
