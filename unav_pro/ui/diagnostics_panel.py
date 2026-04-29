"""Diagnostics dialog — a stand-alone window for the **Diagnostics**
tab of UNAV Pro.

Layout:

  * One read-only multi-line text panel showing the environment
    snapshot + recent log records.
  * A level filter combo (ALL / DEBUG / INFO / WARNING / ERROR).
  * Three buttons: **Refresh**, **Copy Diagnostics**, **Open Log
    Folder**.

The pure-CPython controller lives in this module too (separate
class) so unit tests can drive the gather + format path without a
host. The c4d-bound dialog is a thin shell over the controller.
"""

from __future__ import annotations

from typing import Any, Optional

try:
    import c4d  # type: ignore
    from c4d import gui, storage  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    gui = None  # type: ignore
    storage = None  # type: ignore
    _C4D_AVAILABLE = False

from core.config import UnavConfig, load_config
from core.dataset_registry import DatasetRegistry, default_registry_path
from core.logger import (
    LEVELS,
    format_diagnostics,
    gather_environment,
    install_ring_buffer,
    log_folder,
    recent_logs,
)
from core.logging_util import get_logger
from core.metadata_lookup import default_lookup

_log = get_logger("ui.diagnostics_panel")

# Widget IDs.
_ID_GROUP_HEADER = 100
_ID_COMBO_LEVEL = 101
_ID_GROUP_PANEL = 200
_ID_PANEL = 201
_ID_GROUP_BUTTONS = 300
_ID_BTN_REFRESH = 301
_ID_BTN_COPY = 302
_ID_BTN_OPEN_LOG_DIR = 303
_ID_BTN_CLEAR = 304
_COMBO_BASE = 1_000_010

_LEVEL_OPTIONS = (
    ("All levels", None),
    ("Debug",   "DEBUG"),
    ("Info",    "INFO"),
    ("Warning", "WARNING"),
    ("Error",   "ERROR"),
)

assert tuple(t for _l, t in _LEVEL_OPTIONS if t is not None) == LEVELS


# ---------------------------------------------------------------------------
# Controller (pure CPython, fully testable)
# ---------------------------------------------------------------------------


class DiagnosticsController:
    """Composes the environment snapshot + recent logs into a
    single multi-line text block.

    Live instances of the registry / lookup / config can be passed
    in for tests; in production the dialog leaves them as ``None``
    and the controller resolves them lazily from the standard
    lookup paths.
    """

    def __init__(
        self,
        registry: Optional[DatasetRegistry] = None,
        lookup: Optional[Any] = None,
        config: Optional[UnavConfig] = None,
    ):
        # Make sure the ring buffer is attached so refresh() picks up
        # log records from anywhere in the plugin.
        install_ring_buffer()
        self.registry = registry
        self.lookup = lookup
        self.config = config

    # ------------------------------------------------------------ resolvers
    def _resolve_registry(self) -> Optional[DatasetRegistry]:
        if self.registry is not None:
            return self.registry
        try:
            return DatasetRegistry.load(default_registry_path())
        except Exception:  # noqa: BLE001 — defensive
            _log.exception("DiagnosticsController: registry load failed")
            return None

    def _resolve_lookup(self):
        if self.lookup is not None:
            return self.lookup
        try:
            return default_lookup()
        except Exception:  # noqa: BLE001
            return None

    def _resolve_config(self) -> UnavConfig:
        if self.config is not None:
            return self.config
        try:
            return load_config()
        except Exception:  # noqa: BLE001
            return UnavConfig()

    # ------------------------------------------------------------- snapshot
    def snapshot(
        self,
        level: Optional[str] = None,
        recent_limit: Optional[int] = 200,
    ) -> str:
        """Build the full diagnostics text. Filters log records by
        ``level`` (None = all)."""
        env = gather_environment(
            config=self._resolve_config(),
            registry=self._resolve_registry(),
            lookup=self._resolve_lookup(),
        )
        records = recent_logs(level=level, limit=recent_limit)
        return format_diagnostics(env, records)


# ---------------------------------------------------------------------------
# C4D dialog
# ---------------------------------------------------------------------------


if _C4D_AVAILABLE:

    class UnavDiagnosticsDialog(gui.GeDialog):
        """Stand-alone Diagnostics window."""

        TITLE = "UNAV Pro — Diagnostics"
        controller: Optional[DiagnosticsController] = None

        def CreateLayout(self) -> bool:
            self.SetTitle(self.TITLE)

            # Header row: level filter combo.
            self.GroupBegin(
                _ID_GROUP_HEADER, c4d.BFH_SCALEFIT, cols=2, rows=1,
                title="Filter",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Log level")
            self.AddComboBox(_ID_COMBO_LEVEL, c4d.BFH_SCALEFIT)
            for i, (label, _token) in enumerate(_LEVEL_OPTIONS):
                self.AddChild(_ID_COMBO_LEVEL, _COMBO_BASE + i, label)
            self.SetInt32(_ID_COMBO_LEVEL, _COMBO_BASE)
            self.GroupEnd()

            # Diagnostics text panel.
            self.GroupBegin(
                _ID_GROUP_PANEL, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                cols=1, rows=1, title="Diagnostics",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddMultiLineEditText(
                _ID_PANEL,
                c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                inith=420,
                style=c4d.DR_MULTILINE_READONLY | c4d.DR_MULTILINE_MONOSPACED,
            )
            self.GroupEnd()

            # Buttons row.
            self.GroupBegin(
                _ID_GROUP_BUTTONS, c4d.BFH_SCALEFIT, cols=4, rows=1,
                title="Actions",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddButton(_ID_BTN_REFRESH, c4d.BFH_SCALEFIT, name="Refresh")
            self.AddButton(_ID_BTN_COPY, c4d.BFH_SCALEFIT, name="Copy Diagnostics")
            self.AddButton(_ID_BTN_OPEN_LOG_DIR, c4d.BFH_SCALEFIT, name="Open Log Folder")
            self.AddButton(_ID_BTN_CLEAR, c4d.BFH_SCALEFIT, name="Clear Recent Logs")
            self.GroupEnd()
            return True

        def InitValues(self) -> bool:
            if self.controller is None:
                self.controller = DiagnosticsController()
            self._refresh()
            return True

        # ------------------------------------------------------- refresh
        def _selected_level(self) -> Optional[str]:
            try:
                idx = int(self.GetInt32(_ID_COMBO_LEVEL))
            except Exception:
                return None
            pos = max(0, idx - _COMBO_BASE)
            pos = min(pos, len(_LEVEL_OPTIONS) - 1)
            return _LEVEL_OPTIONS[pos][1]

        def _refresh(self) -> None:
            text = self.controller.snapshot(level=self._selected_level())
            self.SetString(_ID_PANEL, text)

        # ------------------------------------------------------- commands
        def Command(self, mid: int, msg) -> bool:
            try:
                if mid == _ID_BTN_REFRESH or mid == _ID_COMBO_LEVEL:
                    self._refresh()
                elif mid == _ID_BTN_COPY:
                    payload = self.controller.snapshot(level=self._selected_level())
                    try:
                        c4d.CopyStringToClipboard(payload)
                        self.SetString(_ID_PANEL, payload)  # ensure parity
                    except Exception:  # noqa: BLE001
                        _log.exception("Copy diagnostics failed")
                elif mid == _ID_BTN_OPEN_LOG_DIR:
                    folder = log_folder()
                    if folder:
                        try:
                            storage.GeExecuteFile(folder)
                        except Exception:  # noqa: BLE001
                            _log.exception("Open log folder failed")
                elif mid == _ID_BTN_CLEAR:
                    from core.logger import clear_recent_logs

                    clear_recent_logs()
                    self._refresh()
            except Exception as exc:  # noqa: BLE001 — UI boundary
                _log.exception("DiagnosticsDialog command %s failed", mid)
                self.SetString(_ID_PANEL, f"ERROR: {exc!r}")
            return True

else:  # pragma: no cover — non-C4D import path

    class UnavDiagnosticsDialog:  # type: ignore[no-redef]
        TITLE = "UNAV Pro — Diagnostics"
        controller = None

        def __init__(self, *_args, **_kwargs):
            raise RuntimeError(
                "UnavDiagnosticsDialog can only be instantiated inside Cinema 4D."
            )
