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
_ID_BTN_DIAGNOSTICS = 7005
_ID_GROUP_SAFETY = 8000
_ID_SAFETY_STATUS = 8001
_ID_NUM_SAFETY_CAP = 8002
_ID_CHK_FULL_OVERRIDE = 8003
_ID_BTN_SAFETY_REFRESH = 8004
_ID_GROUP_WORKFLOW = 9000
_ID_WORKFLOW_HINT = 9001

# v0.7 — Render Mode controls (live in their own strip below the
# Visible Sector group so the selector is reachable without dropping
# into the Diagnostics tab).
_ID_GROUP_RENDER = 9100
_ID_COMBO_RENDER_MODE = 9101
_ID_RENDER_STATS = 9102
_RENDER_COMBO_BASE = 9200

# v0.9 — Native Point Viewer bridge controls.
_ID_GROUP_NATIVE = 9300
_ID_BTN_NATIVE_EXPORT = 9301
_ID_BTN_NATIVE_RELOAD = 9302
_ID_BTN_NATIVE_TOGGLE = 9303
_ID_NATIVE_STATUS = 9304

# v0.6 — UX layer: search, bookmarks, navigation controller.
_ID_GROUP_TABS = 10000
_ID_TAB_SEARCH = 10100
_ID_SEARCH_INPUT = 10101
_ID_SEARCH_SOURCE = 10102
_ID_SEARCH_TYPE = 10103
_ID_BTN_SEARCH_GO = 10104
_ID_SEARCH_PANEL = 10105
_ID_SEARCH_INDEX = 10106
_ID_BTN_SEARCH_FOCUS = 10107
_ID_BTN_SEARCH_LOCK = 10108
_ID_BTN_SEARCH_BOOKMARK = 10109
_ID_TAB_BOOKMARKS = 10200
_ID_BOOKMARKS_PANEL = 10201
_ID_BOOKMARKS_INDEX = 10202
_ID_BTN_BOOKMARK_FOCUS = 10203
_ID_BTN_BOOKMARK_REMOVE = 10204
_ID_BTN_BOOKMARK_REFRESH = 10205
_ID_BTN_BOOKMARK_CAPTURE = 10206
_ID_TAB_NAVIGATION = 10300
_ID_NAV_STEP_PC = 10301
_ID_NAV_ACCEL = 10302
_ID_BTN_NAV_FORWARD = 10303
_ID_BTN_NAV_BACKWARD = 10304
_ID_BTN_NAV_LOCK = 10305
_ID_BTN_NAV_UNLOCK = 10306
_ID_NAV_STATUS = 10307


if _C4D_AVAILABLE:

    class UnavMainDialog(gui.GeDialog):
        """Main control panel for UNAV Pro (MVP)."""

        TITLE = "Universal Navigator Pro"

        def CreateLayout(self) -> bool:
            self.SetTitle(self.TITLE)

            # Workflow hint — read-only strip at the top guiding the
            # user through the five v0.2 sector-streaming steps.
            self.GroupBegin(
                _ID_GROUP_WORKFLOW, c4d.BFH_SCALEFIT, cols=1, rows=1,
                title="Workflow",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddStaticText(
                _ID_WORKFLOW_HINT, c4d.BFH_SCALEFIT,
                name="(workflow status)",
            )
            self.GroupEnd()

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

            # Safety strip — always visible so the user knows the cap
            # and the active mode at a glance.
            self.GroupBegin(
                _ID_GROUP_SAFETY, c4d.BFH_SCALEFIT, cols=2, rows=2,
                title="Safety",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddStaticText(_ID_SAFETY_STATUS, c4d.BFH_SCALEFIT, name="(safety status)")
            self.AddButton(_ID_BTN_SAFETY_REFRESH, c4d.BFH_RIGHT, name="Refresh")
            self.AddStaticText(0, c4d.BFH_LEFT, name="Max generated objects")
            self.AddEditNumberArrows(_ID_NUM_SAFETY_CAP, c4d.BFH_SCALEFIT)
            self.SetInt32(
                _ID_NUM_SAFETY_CAP, 100_000, min=0, max=10_000_000, step=1000,
            )
            self.AddCheckbox(
                _ID_CHK_FULL_OVERRIDE, c4d.BFH_LEFT, initw=0, inith=0,
                name="Allow Full Catalog (override navigator + cap)",
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

            # Render Mode (v0.7).
            from core.render_mode import RENDER_MODE_LABELS

            self.GroupBegin(
                _ID_GROUP_RENDER, c4d.BFH_SCALEFIT, cols=2, rows=2,
                title="Render Mode",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Backend")
            self.AddComboBox(_ID_COMBO_RENDER_MODE, c4d.BFH_SCALEFIT)
            for i, (label, _token) in enumerate(RENDER_MODE_LABELS):
                self.AddChild(
                    _ID_COMBO_RENDER_MODE, _RENDER_COMBO_BASE + i, label,
                )
            self.SetInt32(_ID_COMBO_RENDER_MODE, _RENDER_COMBO_BASE)
            self.AddStaticText(
                _ID_RENDER_STATS, c4d.BFH_SCALEFIT,
                name="(no backend stats yet)",
            )
            self.GroupEnd()

            # Native Point Viewer bridge (v0.9).
            self.GroupBegin(
                _ID_GROUP_NATIVE, c4d.BFH_SCALEFIT, cols=3, rows=2,
                title="Native Point Viewer (Experimental)",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddButton(
                _ID_BTN_NATIVE_EXPORT, c4d.BFH_SCALEFIT,
                name="Export Visible Sector (Binary)",
            )
            self.AddButton(
                _ID_BTN_NATIVE_RELOAD, c4d.BFH_SCALEFIT,
                name="Reload Native Viewer",
            )
            self.AddButton(
                _ID_BTN_NATIVE_TOGGLE, c4d.BFH_SCALEFIT,
                name="Toggle Native Viewer Mode",
            )
            self.AddStaticText(
                _ID_NATIVE_STATUS, c4d.BFH_SCALEFIT,
                name="(native viewer: not loaded)",
            )
            self.GroupEnd()

            # Buttons grid.
            self.GroupBegin(
                _ID_GROUP_BUTTONS, c4d.BFH_SCALEFIT, cols=2, rows=8,
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
            self.AddButton(_ID_BTN_DIAGNOSTICS, c4d.BFH_SCALEFIT, name="Diagnostics…")
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

            # v0.6 — UX layer tabs: Search / Bookmarks / Navigation.
            # Lives under the existing controls so the working
            # sector-streaming flow is unaffected. Other planned tabs
            # (Dataset / Navigator / Route / Diagnostics) currently
            # live as their own groups above; a future polish pass
            # may consolidate every group under TabGroupBegin (see
            # docs/V0_6_NAVIGATOR_UX.md §4).
            try:
                self.TabGroupBegin(
                    _ID_GROUP_TABS,
                    c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                )
                self._build_search_tab()
                self._build_bookmarks_tab()
                self._build_navigation_tab()
                self.GroupEnd()
            except Exception:  # noqa: BLE001 — UI boundary
                _log.exception("v0.6 tab group failed to build")
            return True

        # The most recent inspection so "Copy Metadata JSON" has
        # something to copy without re-reading the selection.
        _last_inspection = None

        # Live route state. Shared between every "Route Planner"
        # button so adds, clears, and rebuilds operate on the same
        # waypoint list.
        _route = None

        # v0.6 — UX layer state.
        _search_outcome = None
        _bookmarks = None
        _target_lock = None
        _nav_controller = None

        # v0.9 — Native Point Viewer toggle remembers the last
        # non-native render-mode choice so Toggle flips back to it.
        _previous_render_mode_token = None

        # ------------------------------------------------- v0.6 tab builders

        def _build_search_tab(self) -> None:
            self.GroupBegin(
                _ID_TAB_SEARCH, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                cols=1, rows=4, title="Search",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            # Query row
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Find")
            self.AddEditText(_ID_SEARCH_INPUT, c4d.BFH_SCALEFIT)
            self.AddEditText(_ID_SEARCH_SOURCE, c4d.BFH_SCALEFIT)
            self.AddButton(_ID_BTN_SEARCH_GO, c4d.BFH_RIGHT, name="Search")
            self.GroupEnd()
            self.AddMultiLineEditText(
                _ID_SEARCH_PANEL,
                c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                inith=160,
                style=c4d.DR_MULTILINE_READONLY | c4d.DR_MULTILINE_MONOSPACED,
            )
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Pick #")
            self.AddEditNumberArrows(_ID_SEARCH_INDEX, c4d.BFH_SCALEFIT)
            self.SetInt32(_ID_SEARCH_INDEX, 0, min=0, max=9999, step=1)
            self.AddButton(_ID_BTN_SEARCH_FOCUS, c4d.BFH_SCALEFIT, name="Focus")
            self.AddButton(_ID_BTN_SEARCH_LOCK, c4d.BFH_SCALEFIT, name="Lock Target")
            self.GroupEnd()
            self.AddButton(
                _ID_BTN_SEARCH_BOOKMARK, c4d.BFH_SCALEFIT,
                name="Add Selected Result to Bookmarks",
            )
            self.GroupEnd()

        def _build_bookmarks_tab(self) -> None:
            self.GroupBegin(
                _ID_TAB_BOOKMARKS, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                cols=1, rows=3, title="Bookmarks",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddMultiLineEditText(
                _ID_BOOKMARKS_PANEL,
                c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                inith=160,
                style=c4d.DR_MULTILINE_READONLY | c4d.DR_MULTILINE_MONOSPACED,
            )
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Pick #")
            self.AddEditNumberArrows(_ID_BOOKMARKS_INDEX, c4d.BFH_SCALEFIT)
            self.SetInt32(_ID_BOOKMARKS_INDEX, 0, min=0, max=9999, step=1)
            self.AddButton(_ID_BTN_BOOKMARK_FOCUS, c4d.BFH_SCALEFIT, name="Focus")
            self.AddButton(_ID_BTN_BOOKMARK_REMOVE, c4d.BFH_SCALEFIT, name="Remove")
            self.GroupEnd()
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=2, rows=1)
            self.AddButton(
                _ID_BTN_BOOKMARK_CAPTURE, c4d.BFH_SCALEFIT,
                name="Capture Navigator Position",
            )
            self.AddButton(
                _ID_BTN_BOOKMARK_REFRESH, c4d.BFH_SCALEFIT, name="Reload",
            )
            self.GroupEnd()
            self.GroupEnd()

        def _build_navigation_tab(self) -> None:
            self.GroupBegin(
                _ID_TAB_NAVIGATION, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                cols=1, rows=4, title="Navigation",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Step (pc)")
            self.AddEditNumberArrows(_ID_NAV_STEP_PC, c4d.BFH_SCALEFIT)
            self.SetFloat(_ID_NAV_STEP_PC, 1.0, min=1e-6, max=1e6, step=0.1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Acceleration")
            self.AddEditNumberArrows(_ID_NAV_ACCEL, c4d.BFH_SCALEFIT)
            self.SetFloat(_ID_NAV_ACCEL, 1.0, min=0.01, max=1000.0, step=0.5)
            self.GroupEnd()
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddButton(_ID_BTN_NAV_BACKWARD, c4d.BFH_SCALEFIT, name="Step Backward")
            self.AddButton(_ID_BTN_NAV_FORWARD, c4d.BFH_SCALEFIT, name="Step Forward")
            self.AddButton(_ID_BTN_NAV_LOCK, c4d.BFH_SCALEFIT, name="Lock Selected as Target")
            self.AddButton(_ID_BTN_NAV_UNLOCK, c4d.BFH_SCALEFIT, name="Unlock Target")
            self.GroupEnd()
            self.AddStaticText(
                _ID_NAV_STATUS, c4d.BFH_SCALEFIT,
                name="(navigation status)",
            )
            self.GroupEnd()

        def InitValues(self) -> bool:
            from core.bookmarks import load_bookmarks
            from core.navigation_controller import NavigationController
            from core.route import Route
            from ui.bookmarks_panel import empty_panel_text as bm_empty
            from ui.bookmarks_panel import render as bm_render
            from ui.metadata_panel import empty_panel_text
            from ui.search_panel import empty_panel_text as search_empty

            self._append_log(f"{self.TITLE} ready.")
            self.SetString(_ID_META_PANEL, empty_panel_text())
            self._route = Route()
            from ui.route_panel import empty_panel_text as rt_empty
            self.SetString(_ID_RT_PANEL, rt_empty())
            self._refresh_safety_status()
            self._refresh_workflow_hint()

            # v0.6 panel defaults.
            try:
                self.SetString(_ID_SEARCH_PANEL, search_empty())
            except Exception:  # noqa: BLE001
                pass
            self._bookmarks = load_bookmarks()
            try:
                self.SetString(
                    _ID_BOOKMARKS_PANEL,
                    bm_render(self._bookmarks) if len(self._bookmarks)
                    else bm_empty(),
                )
            except Exception:  # noqa: BLE001
                pass
            self._nav_controller = NavigationController()
            try:
                self.SetString(_ID_NAV_STATUS, "(no target locked)")
            except Exception:  # noqa: BLE001
                pass
            # v0.9 — surface the native-viewer status the moment the
            # dialog opens; the bridge file may exist from a prior
            # session.
            try:
                self._refresh_native_status()
            except Exception:  # noqa: BLE001
                pass
            return True

        def _refresh_workflow_hint(self) -> None:
            """Set the top workflow strip to the current step."""
            try:
                from c4d import documents  # type: ignore

                from c4d_objects.navigation_null import find_navigator
                from c4d_objects.point_cloud_builder import find_visible_sector
                from core.dataset_registry import (
                    DatasetRegistry, default_registry_path,
                )
                from core.sector_streaming import workflow_step

                doc = documents.GetActiveDocument()
                registry = DatasetRegistry.load(default_registry_path())
                enabled = registry.enabled_entries()
                indexed = any(e.is_indexed for e in enabled)
                has_nav = doc is not None and find_navigator(doc) is not None
                visible = 0
                if doc is not None:
                    sector = find_visible_sector(doc)
                    if sector is not None:
                        ch = sector.GetDown()
                        while ch is not None:
                            visible += 1
                            ch = ch.GetNext()
                _step, hint = workflow_step(
                    enabled_dataset_count=len(enabled),
                    any_dataset_indexed=indexed,
                    has_navigator=has_nav,
                    visible_sector_count=visible,
                )
                self.SetString(_ID_WORKFLOW_HINT, hint)
            except Exception:  # noqa: BLE001 — UI boundary
                _log.exception("Workflow hint refresh failed")
                self.SetString(_ID_WORKFLOW_HINT, "(workflow status unavailable)")

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
                            safety_limits=self._read_safety_limits(),
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
                            render_mode=self._read_render_mode(),
                        )
                    )
                    self._refresh_render_stats()
                elif mid == _ID_COMBO_RENDER_MODE:
                    self._on_render_mode_changed()
                elif mid == _ID_BTN_NATIVE_EXPORT:
                    self._append_log(
                        mock_actions.export_visible_sector_binary(
                            encoding=self._read_encoding(),
                        )
                    )
                    self._refresh_native_status()
                elif mid == _ID_BTN_NATIVE_RELOAD:
                    self._append_log(mock_actions.reload_native_viewer())
                    self._refresh_native_status()
                elif mid == _ID_BTN_NATIVE_TOGGLE:
                    self._do_toggle_native_viewer_mode()
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
                elif mid == _ID_BTN_DIAGNOSTICS:
                    self._do_open_diagnostics()
                elif mid == _ID_BTN_SAFETY_REFRESH or mid == _ID_NUM_SAFETY_CAP \
                        or mid == _ID_CHK_FULL_OVERRIDE:
                    self._refresh_safety_status()
                elif mid == _ID_BTN_CLEAR_LOG:
                    self.SetString(_ID_LOG, "")
                # v0.6 — search / bookmarks / navigation handlers.
                elif mid == _ID_BTN_SEARCH_GO:
                    self._do_search()
                elif mid == _ID_BTN_SEARCH_FOCUS:
                    self._do_search_focus()
                elif mid == _ID_BTN_SEARCH_LOCK:
                    self._do_search_lock()
                elif mid == _ID_BTN_SEARCH_BOOKMARK:
                    self._do_search_bookmark()
                elif mid == _ID_BTN_BOOKMARK_FOCUS:
                    self._do_bookmark_focus()
                elif mid == _ID_BTN_BOOKMARK_REMOVE:
                    self._do_bookmark_remove()
                elif mid == _ID_BTN_BOOKMARK_REFRESH:
                    self._do_bookmark_refresh()
                elif mid == _ID_BTN_BOOKMARK_CAPTURE:
                    self._do_bookmark_capture()
                elif mid == _ID_BTN_NAV_FORWARD:
                    self._do_nav_step(direction=1)
                elif mid == _ID_BTN_NAV_BACKWARD:
                    self._do_nav_step(direction=-1)
                elif mid == _ID_BTN_NAV_LOCK:
                    self._do_nav_lock()
                elif mid == _ID_BTN_NAV_UNLOCK:
                    self._do_nav_unlock()
            except Exception as exc:  # noqa: BLE001 — UI boundary handler
                _log.exception("Dialog command %s failed", mid)
                self._append_log(f"ERROR: {exc!r}")
            # The workflow hint depends on the registry, the
            # navigator, and the visible-sector count — any of which
            # an action might have just changed.
            self._refresh_workflow_hint()
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
            from core.render_mode import RENDER_MODE_POINT_CLOUD
            from ui.metadata_panel import (
                STATUS_FOUND_FULL,
                inspect_active_selection,
                point_cloud_panel_text,
                point_cloud_search_hint,
            )

            result = inspect_active_selection()
            self._last_inspection = result
            mode = self._read_render_mode()
            # Under Point Cloud Mode, per-object selection does not
            # resolve to a uid: route the artist to the v0.6 Search
            # tab via the dedicated hint instead of showing a
            # confused "marker only" panel.
            if (
                mode == RENDER_MODE_POINT_CLOUD
                and result.status != STATUS_FOUND_FULL
            ):
                self.SetString(_ID_META_PANEL, point_cloud_panel_text())
                self._append_log(point_cloud_search_hint())
                return
            self.SetString(_ID_META_PANEL, result.display_text)
            self._append_log(result.status_line)

        # --- v0.7 Render Mode helpers ---------------------------------

        def _read_render_mode(self) -> str:
            from core.render_mode import (
                DEFAULT_RENDER_MODE, RENDER_MODE_LABELS,
            )
            try:
                combo_idx = int(self.GetInt32(_ID_COMBO_RENDER_MODE))
            except Exception:  # noqa: BLE001
                return DEFAULT_RENDER_MODE
            mode_pos = max(0, combo_idx - _RENDER_COMBO_BASE)
            mode_pos = min(mode_pos, len(RENDER_MODE_LABELS) - 1)
            return RENDER_MODE_LABELS[mode_pos][1]

        def _refresh_render_stats(self) -> None:
            """Pull the most recent backend stats off ``mock_actions``
            (the sync writes them onto the registry's last result)
            and surface a one-line summary in the Render Mode strip."""
            try:
                from core.mock_actions import last_render_stats
                stats = last_render_stats()
            except Exception:  # noqa: BLE001
                stats = None
            if stats is None:
                self.SetString(
                    _ID_RENDER_STATS, "(no backend stats yet)",
                )
                return
            self.SetString(_ID_RENDER_STATS, stats.short_summary())

        def _on_render_mode_changed(self) -> None:
            from core.render_mode import (
                capabilities_for, validate_mode,
            )
            mode = validate_mode(self._read_render_mode())
            caps = capabilities_for(mode)
            self._append_log(
                f"Render Mode: switched to {caps.name} — "
                f"{caps.short_summary()}"
            )

        # --- v0.9 Native Viewer helpers -------------------------------

        def _refresh_native_status(self) -> None:
            """Pull the most recent status the native plugin wrote
            and surface a one-line summary in the Native bridge
            strip. When the native plugin is not loaded, the dialog
            says so plainly."""
            from core.native_bridge import read_status
            try:
                status = read_status()
            except Exception:  # noqa: BLE001 — UI boundary
                self.SetString(
                    _ID_NATIVE_STATUS,
                    "(native viewer: status read failed)",
                )
                return
            if status is None:
                self.SetString(
                    _ID_NATIVE_STATUS,
                    "(native viewer: no status file — Python fallback)",
                )
                return
            self.SetString(_ID_NATIVE_STATUS, status.short_summary())

        def _do_toggle_native_viewer_mode(self) -> None:
            """Flip the Render Mode combo between the user's last
            non-native choice and Native Point Viewer."""
            from core.render_mode import (
                DEFAULT_RENDER_MODE,
                RENDER_MODE_LABELS,
                RENDER_MODE_NATIVE_VIEWER,
            )
            current = self._read_render_mode()
            if current == RENDER_MODE_NATIVE_VIEWER:
                target = (
                    self._previous_render_mode_token
                    or DEFAULT_RENDER_MODE
                )
            else:
                self._previous_render_mode_token = current
                target = RENDER_MODE_NATIVE_VIEWER
            for i, (_label, token) in enumerate(RENDER_MODE_LABELS):
                if token == target:
                    self.SetInt32(
                        _ID_COMBO_RENDER_MODE, _RENDER_COMBO_BASE + i,
                    )
                    break
            self._on_render_mode_changed()
            self._append_log(
                mock_actions.native_viewer_status()
            )
            self._refresh_native_status()

        # --- Route panel handlers ----------------------------------

        # --- Safety helpers --------------------------------------------

        def _read_safety_limits(self):
            from core.safety import SafetyLimits

            try:
                cap = int(self.GetInt32(_ID_NUM_SAFETY_CAP))
                override = bool(self.GetBool(_ID_CHK_FULL_OVERRIDE))
            except Exception:  # noqa: BLE001
                return SafetyLimits()
            try:
                return SafetyLimits(
                    max_generated_objects=max(0, cap),
                    allow_full_catalog=override,
                )
            except ValueError:
                return SafetyLimits()

        def _refresh_safety_status(self) -> None:
            from core.logger import _count_visible_sector_children
            from core.safety import status_line

            limits = self._read_safety_limits()
            generated = None
            try:
                generated = _count_visible_sector_children()
            except Exception:  # noqa: BLE001
                pass
            self.SetString(_ID_SAFETY_STATUS, status_line(limits, generated))

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

        # --- v0.6 Search / Bookmarks / Navigation -----------------

        def _refresh_bookmarks_panel(self) -> None:
            from ui.bookmarks_panel import empty_panel_text as bm_empty
            from ui.bookmarks_panel import render as bm_render
            try:
                self.SetString(
                    _ID_BOOKMARKS_PANEL,
                    bm_render(self._bookmarks) if len(self._bookmarks)
                    else bm_empty(),
                )
            except Exception:  # noqa: BLE001
                pass

        def _do_search(self) -> None:
            from ui.search_panel import run_search
            try:
                text = self.GetString(_ID_SEARCH_INPUT) or ""
                source = (self.GetString(_ID_SEARCH_SOURCE) or "").strip() or None
            except Exception:  # noqa: BLE001
                text, source = "", None
            outcome = run_search(text, catalog_source_filter=source)
            self._search_outcome = outcome
            try:
                self.SetString(_ID_SEARCH_PANEL, outcome.panel_text)
            except Exception:  # noqa: BLE001
                pass
            self._append_log(outcome.status_line)

        def _selected_search_result(self):
            from ui.search_panel import selected_result
            if self._search_outcome is None:
                return None
            try:
                idx = int(self.GetInt32(_ID_SEARCH_INDEX))
            except Exception:  # noqa: BLE001
                idx = 0
            return selected_result(self._search_outcome, idx)

        def _do_search_focus(self) -> None:
            from core.target_lock import acquire_target
            from core.metadata_lookup import default_lookup
            r = self._selected_search_result()
            if r is None:
                self._append_log("Search Focus: pick a result first.")
                return
            try:
                from c4d import documents  # type: ignore
            except ImportError:
                self._append_log("Search Focus: Cinema 4D not available.")
                return
            doc = documents.GetActiveDocument()
            if doc is None:
                self._append_log("Search Focus: no active document.")
                return
            from c4d_objects.navigation_null import find_navigator
            nav = find_navigator(doc)
            if nav is None:
                self._append_log("Search Focus: no UNAV_Navigator in scene.")
                return
            lock = acquire_target(r.uid, default_lookup())
            if lock is None or not lock.is_resolved:
                self._append_log(
                    f"Search Focus: '{r.display_label()}' not resolvable; "
                    "load the matching dataset."
                )
                return
            doc.StartUndo()
            try:
                doc.AddUndo(c4d.UNDOTYPE_CHANGE, nav)
                mg = nav.GetMg()
                mg.off = c4d.Vector(*lock.position_c4d)
                nav.SetMg(mg)
            finally:
                doc.EndUndo()
            c4d.EventAdd()
            self._append_log(
                f"Search Focus: navigator → '{lock.label}'."
            )

        def _do_search_lock(self) -> None:
            from core.target_lock import acquire_target
            from core.metadata_lookup import default_lookup
            r = self._selected_search_result()
            if r is None:
                self._append_log("Lock Target: pick a result first.")
                return
            lock = acquire_target(r.uid, default_lookup())
            if lock is None or not lock.is_resolved:
                self._append_log(
                    f"Lock Target: '{r.display_label()}' not resolvable."
                )
                return
            self._target_lock = lock
            try:
                self.SetString(
                    _ID_NAV_STATUS,
                    f"Locked on '{lock.label}' [{lock.uid}]",
                )
            except Exception:  # noqa: BLE001
                pass
            self._append_log(f"Lock Target: locked on '{lock.label}'.")

        def _do_search_bookmark(self) -> None:
            from ui.bookmarks_panel import add_search_result
            r = self._selected_search_result()
            if r is None:
                self._append_log("Bookmark: pick a search result first.")
                return
            _ok, status = add_search_result(self._bookmarks, r)
            self._append_log(status)
            self._refresh_bookmarks_panel()

        def _selected_bookmark(self):
            try:
                idx = int(self.GetInt32(_ID_BOOKMARKS_INDEX))
            except Exception:  # noqa: BLE001
                idx = 0
            if 0 <= idx < len(self._bookmarks):
                return self._bookmarks.bookmarks[idx]
            return None

        def _do_bookmark_focus(self) -> None:
            from ui.bookmarks_panel import focus_pose_for
            bm = self._selected_bookmark()
            if bm is None:
                self._append_log("Bookmark Focus: pick a bookmark first.")
                return
            pose = focus_pose_for(bm)
            self._append_log(pose.status_line)
            if not pose.is_resolved:
                return
            try:
                from c4d import documents  # type: ignore
            except ImportError:
                self._append_log("Bookmark Focus: Cinema 4D not available.")
                return
            doc = documents.GetActiveDocument()
            if doc is None:
                self._append_log("Bookmark Focus: no active document.")
                return
            from c4d_objects.navigation_null import find_navigator
            nav = find_navigator(doc)
            if nav is None:
                self._append_log("Bookmark Focus: no UNAV_Navigator in scene.")
                return
            doc.StartUndo()
            try:
                doc.AddUndo(c4d.UNDOTYPE_CHANGE, nav)
                mg = nav.GetMg()
                mg.off = c4d.Vector(*pose.position_c4d)
                nav.SetMg(mg)
            finally:
                doc.EndUndo()
            c4d.EventAdd()

        def _do_bookmark_remove(self) -> None:
            from ui.bookmarks_panel import remove
            bm = self._selected_bookmark()
            if bm is None:
                self._append_log("Bookmark Remove: pick a bookmark first.")
                return
            _ok, status = remove(self._bookmarks, bm.id)
            self._append_log(status)
            self._refresh_bookmarks_panel()

        def _do_bookmark_refresh(self) -> None:
            from core.bookmarks import load_bookmarks
            self._bookmarks = load_bookmarks()
            self._append_log(
                f"Bookmarks: reloaded ({len(self._bookmarks)} entries)."
            )
            self._refresh_bookmarks_panel()

        def _do_bookmark_capture(self) -> None:
            try:
                from c4d import documents  # type: ignore
            except ImportError:
                self._append_log("Capture Position: Cinema 4D not available.")
                return
            from c4d_objects.navigation_null import find_navigator
            from ui.bookmarks_panel import add_coordinate
            doc = documents.GetActiveDocument()
            if doc is None:
                self._append_log("Capture Position: no active document.")
                return
            nav = find_navigator(doc)
            if nav is None:
                self._append_log(
                    "Capture Position: no UNAV_Navigator in scene."
                )
                return
            off = nav.GetMg().off
            label = f"Pos {len(self._bookmarks) + 1}"
            _ok, status = add_coordinate(
                self._bookmarks,
                (float(off.x), float(off.y), float(off.z)),
                label,
            )
            self._append_log(status)
            self._refresh_bookmarks_panel()

        def _read_step_speed(self):
            from core.navigation_controller import StepSpeed
            try:
                step_pc = float(self.GetFloat(_ID_NAV_STEP_PC))
                accel = float(self.GetFloat(_ID_NAV_ACCEL))
            except Exception:  # noqa: BLE001
                return StepSpeed()
            try:
                return StepSpeed(step_distance_pc=step_pc, acceleration=accel)
            except ValueError:
                return StepSpeed()

        def _do_nav_step(self, direction: int) -> None:
            from core.navigation_controller import step_position
            from data.schema import SCALE_MODES
            try:
                from c4d import documents  # type: ignore
            except ImportError:
                self._append_log("Step: Cinema 4D not available.")
                return
            from c4d_objects.navigation_null import find_navigator
            doc = documents.GetActiveDocument()
            if doc is None:
                self._append_log("Step: no active document.")
                return
            nav = find_navigator(doc)
            if nav is None:
                self._append_log("Step: no UNAV_Navigator in scene.")
                return
            speed = self._read_step_speed()
            self._nav_controller.speed = speed
            mg = nav.GetMg()
            # Forward = local -Z transformed by navigator orientation.
            forward_c4d = (mg.v3 * -1.0)
            # Convert step from pc → C4D units via the active scale.
            scale = SCALE_MODES.get("pc", 1.0)
            current_pc = (
                float(mg.off.x) / scale,
                float(mg.off.y) / scale,
                float(mg.off.z) / scale,
            )
            forward = (
                float(forward_c4d.x), float(forward_c4d.y), float(forward_c4d.z),
            )
            new_pc = step_position(current_pc, forward, speed, direction=direction)
            new_c4d = (
                new_pc[0] * scale, new_pc[1] * scale, new_pc[2] * scale,
            )
            doc.StartUndo()
            try:
                doc.AddUndo(c4d.UNDOTYPE_CHANGE, nav)
                mg.off = c4d.Vector(*new_c4d)
                nav.SetMg(mg)
            finally:
                doc.EndUndo()
            c4d.EventAdd()
            tag = "forward" if direction >= 0 else "backward"
            self._append_log(
                f"Step {tag}: {speed.effective_step_pc:.3g} pc."
            )
            try:
                self.SetString(
                    _ID_NAV_STATUS,
                    f"At ({new_c4d[0]:.3g}, {new_c4d[1]:.3g}, {new_c4d[2]:.3g})",
                )
            except Exception:  # noqa: BLE001
                pass

        def _do_nav_lock(self) -> None:
            from core.target_lock import acquire_target
            from core.metadata_lookup import default_lookup
            try:
                from c4d import documents  # type: ignore
            except ImportError:
                self._append_log("Lock: Cinema 4D not available.")
                return
            from c4d_objects.point_cloud_builder import (
                MARKER_KEY_UID, _read_marker,
            )
            doc = documents.GetActiveDocument()
            if doc is None:
                self._append_log("Lock: no active document.")
                return
            sel = doc.GetActiveObject()
            if sel is None:
                self._append_log("Lock: nothing selected.")
                return
            marker = _read_marker(sel)
            if marker is None:
                self._append_log("Lock: selection is not a UNAV object.")
                return
            uid = str(marker.get(MARKER_KEY_UID) or "")
            if not uid:
                self._append_log("Lock: selected UNAV object carries no uid.")
                return
            lock = acquire_target(uid, default_lookup())
            if lock is None or not lock.is_resolved:
                self._append_log("Lock: target not resolvable in lookup.")
                return
            self._target_lock = lock
            try:
                self.SetString(
                    _ID_NAV_STATUS,
                    f"Locked on '{lock.label}' [{lock.uid}]",
                )
            except Exception:  # noqa: BLE001
                pass
            self._append_log(f"Lock: locked on '{lock.label}'.")

        def _do_nav_unlock(self) -> None:
            self._target_lock = None
            try:
                self.SetString(_ID_NAV_STATUS, "(no target locked)")
            except Exception:  # noqa: BLE001
                pass
            self._append_log("Unlock: target cleared.")

        # The dataset manager dialog is async and persistent: we
        # keep one instance per session so re-clicking the menu
        # reuses the same window.
        _dataset_dialog = None
        _diagnostics_dialog = None

        def _do_open_diagnostics(self) -> None:
            from core.plugin_ids import PLUGIN_ID_DIAGNOSTICS_DIALOG
            from ui.diagnostics_panel import UnavDiagnosticsDialog

            if self._diagnostics_dialog is None:
                self._diagnostics_dialog = UnavDiagnosticsDialog()
            opened = self._diagnostics_dialog.Open(
                dlgtype=c4d.DLG_TYPE_ASYNC,
                pluginid=PLUGIN_ID_DIAGNOSTICS_DIALOG,
                defaultw=620, defaulth=620,
            )
            self._append_log(
                "Diagnostics: opened." if opened
                else "Diagnostics: could not open window."
            )

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
