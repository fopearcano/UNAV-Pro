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
_ID_BTN_INSPECT = 1007
_ID_BTN_COPY_META = 1008
_ID_GROUP_LOG = 2000
_ID_LOG = 2001
_ID_BTN_CLEAR_LOG = 2002
_ID_GROUP_META = 3000
_ID_META_PANEL = 3001
_ID_GROUP_VISUAL = 4000
_ID_COMBO_COLOR_MODE = 4001
_ID_NUM_SIZE_SCALE = 4002
_ID_NUM_BRIGHTNESS_SCALE = 4003
# Combo-box items live in a private id range; offset from the combo id.
_COMBO_BASE = 4100
_ID_GROUP_SYNC = 5000
_ID_BTN_SYNC = 5001
_ID_CHK_AUTO_SYNC = 5002
_ID_CHK_DEBUG_CONE = 5003
_ID_GROUP_ROUTE = 6000
_ID_BTN_RT_ADD = 6001
_ID_BTN_RT_CLEAR = 6002
_ID_BTN_RT_SPLINE = 6003
_ID_BTN_RT_FOCUS = 6004
_ID_RT_PANEL = 6005
_ID_BTN_DATASET_MGR = 7001
_ID_BTN_SAVE_STATE = 7002
_ID_BTN_LOAD_STATE = 7003
_ID_BTN_RESET_PREFS = 7004


if _C4D_AVAILABLE:

    class UnavMainDialog(gui.GeDialog):
        """Main control panel for UNAV Pro (MVP)."""

        TITLE = "Universal Navigator Pro"

        def CreateLayout(self) -> bool:
            self.SetTitle(self.TITLE)

            # Visual encoding controls.
            from core.visual_encoding import COLOR_MODE_LABELS

            self.GroupBegin(
                _ID_GROUP_VISUAL, c4d.BFH_SCALEFIT, cols=2, rows=3,
                title="Display",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Color mode")
            self.AddComboBox(_ID_COMBO_COLOR_MODE, c4d.BFH_SCALEFIT)
            for i, (label, _token) in enumerate(COLOR_MODE_LABELS):
                self.AddChild(_ID_COMBO_COLOR_MODE, _COMBO_BASE + i, label)
            self.SetInt32(_ID_COMBO_COLOR_MODE, _COMBO_BASE)  # default = first

            self.AddStaticText(0, c4d.BFH_LEFT, name="Size scale")
            self.AddEditNumberArrows(_ID_NUM_SIZE_SCALE, c4d.BFH_SCALEFIT)
            self.SetFloat(
                _ID_NUM_SIZE_SCALE, 1.0, min=0.01, max=100.0, step=0.1,
            )

            self.AddStaticText(0, c4d.BFH_LEFT, name="Brightness scale")
            self.AddEditNumberArrows(_ID_NUM_BRIGHTNESS_SCALE, c4d.BFH_SCALEFIT)
            self.SetFloat(
                _ID_NUM_BRIGHTNESS_SCALE, 1.0, min=0.01, max=100.0, step=0.1,
            )
            self.GroupEnd()

            # Sync controls (lives between Display and the action grid
            # because Sync Visible Sector is the workflow primary).
            self.GroupBegin(
                _ID_GROUP_SYNC, c4d.BFH_SCALEFIT, cols=3, rows=1,
                title="Visible Sector",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddButton(_ID_BTN_SYNC, c4d.BFH_SCALEFIT, name="Sync Visible Sector")
            self.AddCheckbox(
                _ID_CHK_AUTO_SYNC, c4d.BFH_LEFT, initw=0, inith=0,
                name="Auto Sync",
            )
            self.AddCheckbox(
                _ID_CHK_DEBUG_CONE, c4d.BFH_LEFT, initw=0, inith=0,
                name="Show Debug Cone",
            )
            self.GroupEnd()

            # Buttons grid.
            self.GroupBegin(
                _ID_GROUP_BUTTONS, c4d.BFH_SCALEFIT, cols=2, rows=7,
                title="Actions",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddButton(_ID_BTN_LOAD, c4d.BFH_SCALEFIT, name="Load Dataset")
            self.AddButton(_ID_BTN_NULL, c4d.BFH_SCALEFIT, name="Create Navigation Null")
            self.AddButton(_ID_BTN_CLOUD, c4d.BFH_SCALEFIT, name="Generate Point Cloud")
            self.AddButton(_ID_BTN_CLEAR, c4d.BFH_SCALEFIT, name="Clear Scene")
            self.AddButton(_ID_BTN_APPLY_FILTER, c4d.BFH_SCALEFIT, name="Apply View Filter")
            self.AddButton(_ID_BTN_REGENERATE, c4d.BFH_SCALEFIT, name="Regenerate Visible Field")
            self.AddButton(_ID_BTN_INSPECT, c4d.BFH_SCALEFIT, name="Inspect Selected Object")
            self.AddButton(_ID_BTN_COPY_META, c4d.BFH_SCALEFIT, name="Copy Metadata JSON")
            self.AddButton(_ID_BTN_DATASET_MGR, c4d.BFH_SCALEFIT, name="Dataset Manager…")
            self.AddButton(_ID_BTN_SAVE_STATE, c4d.BFH_SCALEFIT, name="Save UNAV State")
            self.AddButton(_ID_BTN_LOAD_STATE, c4d.BFH_SCALEFIT, name="Load UNAV State")
            self.AddButton(_ID_BTN_RESET_PREFS, c4d.BFH_SCALEFIT, name="Reset Preferences")
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
                inith=140,
                style=c4d.DR_MULTILINE_READONLY | c4d.DR_MULTILINE_MONOSPACED,
            )
            self.AddButton(_ID_BTN_CLEAR_LOG, c4d.BFH_RIGHT, name="Clear Log")
            self.GroupEnd()

            # Route planner.
            self.GroupBegin(
                _ID_GROUP_ROUTE, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                cols=1, rows=2, title="Route Planner",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddMultiLineEditText(
                _ID_RT_PANEL,
                c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                inith=140,
                style=c4d.DR_MULTILINE_READONLY | c4d.DR_MULTILINE_MONOSPACED,
            )
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddButton(_ID_BTN_RT_ADD, c4d.BFH_SCALEFIT, name="Add Selected Object as Waypoint")
            self.AddButton(_ID_BTN_RT_CLEAR, c4d.BFH_SCALEFIT, name="Clear Route")
            self.AddButton(_ID_BTN_RT_SPLINE, c4d.BFH_SCALEFIT, name="Build Route Spline")
            self.AddButton(_ID_BTN_RT_FOCUS, c4d.BFH_SCALEFIT, name="Focus Navigator on Waypoint")
            self.GroupEnd()
            self.GroupEnd()

            # Metadata inspection panel.
            self.GroupBegin(
                _ID_GROUP_META, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                cols=1, rows=1, title="Metadata Inspector",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddMultiLineEditText(
                _ID_META_PANEL,
                c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                inith=240,
                style=c4d.DR_MULTILINE_READONLY | c4d.DR_MULTILINE_MONOSPACED,
            )
            self.GroupEnd()
            return True

        # The most recent inspection so "Copy Metadata JSON" has
        # something to copy without re-reading the selection.
        _last_inspection = None

        # Live route state. Shared between every "Route Planner"
        # button so adds, clears, and rebuilds operate on the same
        # waypoint list.
        _route = None

        def InitValues(self) -> bool:
            from core.route import Route
            from ui.metadata_panel import empty_panel_text
            from ui.route_panel import empty_panel_text as rt_empty

            self._append_log(f"{self.TITLE} ready.")
            self.SetString(_ID_META_PANEL, empty_panel_text())
            self._route = Route()
            self.SetString(_ID_RT_PANEL, rt_empty())
            return True

        def Command(self, mid: int, msg) -> bool:
            try:
                if mid == _ID_BTN_LOAD:
                    self._append_log(mock_actions.load_dataset())
                elif mid == _ID_BTN_NULL:
                    self._append_log(mock_actions.create_navigation_null())
                elif mid == _ID_BTN_CLOUD:
                    self._append_log(
                        mock_actions.generate_point_cloud(
                            encoding=self._read_encoding(),
                        )
                    )
                elif mid == _ID_BTN_CLEAR:
                    self._append_log(mock_actions.clear_scene())
                elif mid == _ID_BTN_APPLY_FILTER:
                    self._append_log(mock_actions.apply_view_filter())
                elif mid == _ID_BTN_REGENERATE:
                    self._append_log(
                        mock_actions.regenerate_visible_field(
                            encoding=self._read_encoding(),
                        )
                    )
                elif mid == _ID_BTN_SYNC:
                    self._append_log(
                        mock_actions.sync_visible_sector(
                            encoding=self._read_encoding(),
                            show_debug_cone=bool(
                                self.GetBool(_ID_CHK_DEBUG_CONE)
                            ),
                        )
                    )
                elif mid == _ID_CHK_AUTO_SYNC:
                    self._append_log(
                        "Auto Sync: not yet implemented; "
                        "click Sync Visible Sector manually."
                    )
                elif mid == _ID_CHK_DEBUG_CONE:
                    show = bool(self.GetBool(_ID_CHK_DEBUG_CONE))
                    self._append_log(mock_actions.toggle_debug_cone(show))
                elif mid == _ID_BTN_INSPECT:
                    self._do_inspect()
                elif mid == _ID_BTN_COPY_META:
                    self._do_copy_metadata()
                elif mid == _ID_BTN_RT_ADD:
                    self._do_route_add()
                elif mid == _ID_BTN_RT_CLEAR:
                    self._do_route_clear()
                elif mid == _ID_BTN_RT_SPLINE:
                    self._do_route_spline()
                elif mid == _ID_BTN_RT_FOCUS:
                    self._do_route_focus()
                elif mid == _ID_BTN_DATASET_MGR:
                    self._do_open_dataset_manager()
                elif mid == _ID_BTN_SAVE_STATE:
                    self._append_log(
                        mock_actions.save_unav_state(
                            route=self._route,
                            encoding=self._read_encoding(),
                        )
                    )
                elif mid == _ID_BTN_LOAD_STATE:
                    self._append_log(mock_actions.load_unav_state())
                elif mid == _ID_BTN_RESET_PREFS:
                    self._append_log(mock_actions.reset_preferences())
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

        def _read_encoding(self):
            """Snapshot the current dropdown + scale values into a
            ``VisualEncodingParams`` instance. Out-of-range values
            (or a missing host) fall back to defaults."""
            from core.visual_encoding import (
                COLOR_MODE_LABELS,
                VisualEncodingParams,
            )
            try:
                combo_idx = int(self.GetInt32(_ID_COMBO_COLOR_MODE))
                size_scale = float(self.GetFloat(_ID_NUM_SIZE_SCALE))
                brightness_scale = float(self.GetFloat(_ID_NUM_BRIGHTNESS_SCALE))
            except Exception:  # noqa: BLE001 — never fail at the UI boundary
                return VisualEncodingParams()
            mode_pos = max(0, combo_idx - _COMBO_BASE)
            mode_pos = min(mode_pos, len(COLOR_MODE_LABELS) - 1)
            color_mode = COLOR_MODE_LABELS[mode_pos][1]
            try:
                return VisualEncodingParams(
                    color_mode=color_mode,
                    size_scale=size_scale if size_scale > 0 else 1.0,
                    brightness_scale=brightness_scale if brightness_scale > 0 else 1.0,
                )
            except ValueError:
                return VisualEncodingParams()

        def _do_inspect(self) -> None:
            from ui.metadata_panel import inspect_active_selection

            result = inspect_active_selection()
            self._last_inspection = result
            self.SetString(_ID_META_PANEL, result.display_text)
            self._append_log(result.status_line)

        # --- Route panel handlers ----------------------------------

        def _refresh_route_panel(self) -> None:
            from ui.route_panel import panel_text

            try:
                self.SetString(_ID_RT_PANEL, panel_text(self._route))
            except Exception as exc:  # noqa: BLE001
                _log.exception("Failed to render route panel")
                self.SetString(_ID_RT_PANEL, f"(could not render route: {exc})")

        def _do_route_add(self) -> None:
            try:
                from c4d import documents  # type: ignore
            except ImportError:
                self._append_log("Add Waypoint: Cinema 4D not available.")
                return
            from ui.route_panel import add_selected_as_waypoint

            doc = documents.GetActiveDocument()
            if doc is None:
                self._append_log("Add Waypoint: no active document.")
                return
            _wp, status = add_selected_as_waypoint(doc, self._route)
            self._append_log(status)
            self._refresh_route_panel()

        def _do_route_clear(self) -> None:
            try:
                from c4d import documents  # type: ignore
            except ImportError:
                self._append_log("Clear Route: Cinema 4D not available.")
                return
            from ui.route_panel import clear_route

            doc = documents.GetActiveDocument()
            self._append_log(clear_route(self._route, doc=doc))
            self._refresh_route_panel()

        def _do_route_spline(self) -> None:
            try:
                from c4d import documents  # type: ignore
            except ImportError:
                self._append_log("Build Route Spline: Cinema 4D not available.")
                return
            from ui.route_panel import build_route_spline

            doc = documents.GetActiveDocument()
            if doc is None:
                self._append_log("Build Route Spline: no active document.")
                return
            self._append_log(build_route_spline(doc, self._route))

        def _do_route_focus(self) -> None:
            try:
                from c4d import documents  # type: ignore
            except ImportError:
                self._append_log("Focus Navigator: Cinema 4D not available.")
                return
            from ui.route_panel import focus_navigator_on

            doc = documents.GetActiveDocument()
            if doc is None:
                self._append_log("Focus Navigator: no active document.")
                return
            self._append_log(focus_navigator_on(doc, self._route))

        # The dataset manager dialog is async and persistent: we
        # keep one instance per session so re-clicking the menu
        # reuses the same window.
        _dataset_dialog = None

        def _do_open_dataset_manager(self) -> None:
            from core.plugin_ids import PLUGIN_ID_DATASET_DIALOG
            from ui.dataset_manager import UnavDatasetDialog

            if self._dataset_dialog is None:
                self._dataset_dialog = UnavDatasetDialog()
            opened = self._dataset_dialog.Open(
                dlgtype=c4d.DLG_TYPE_ASYNC,
                pluginid=PLUGIN_ID_DATASET_DIALOG,
                defaultw=520, defaulth=520,
            )
            self._append_log(
                "Dataset Manager: opened." if opened
                else "Dataset Manager: could not open window."
            )

        def _do_copy_metadata(self) -> None:
            from ui.metadata_panel import (
                copy_to_clipboard,
                no_inspection_result,
            )

            result = self._last_inspection
            if result is None:
                self._append_log(no_inspection_result().status_line)
                return
            payload = result.clipboard_json
            if not payload or payload == "{}":
                self._append_log("Copy Metadata: no metadata to copy.")
                return
            ok = copy_to_clipboard(payload)
            if ok:
                self._append_log(
                    f"Copy Metadata: copied {len(payload)} chars to clipboard."
                )
            else:
                self._append_log("Copy Metadata: clipboard write refused by host.")

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
