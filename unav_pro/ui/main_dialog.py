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

from typing import Optional

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

# v1.2 — Time Navigator panel.
_ID_GROUP_TIME = 9500
_ID_TIME_EPOCH_INPUT = 9501
_ID_BTN_TIME_SET = 9502
_ID_BTN_TIME_BACK = 9503
_ID_BTN_TIME_FWD = 9504
_ID_BTN_TIME_PLAY = 9505
_ID_BTN_TIME_SYNC = 9506
_ID_NUM_TIME_STEP = 9507
_ID_TIME_STATUS = 9508

# UI sizing fix: outer vertical scroll wrapper for the main
# dialog body. The ScrollGroupBegin keeps every section
# reachable when the window is shorter than the natural
# layout height. See docs/UI_LAYOUT_NOTES.md.
_ID_GROUP_SCROLL_ROOT = 9800
_ID_GROUP_SCROLL_INNER = 9801

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

# v1.4 — Missions tab (guided voyages + playback controls).
_ID_TAB_MISSIONS = 10400
_ID_MISSIONS_LIST = 10401
_ID_MISSIONS_DETAIL = 10402
_ID_MISSIONS_INDEX = 10403
_ID_BTN_MISSION_NEW = 10410
_ID_BTN_MISSION_DELETE = 10411
_ID_BTN_MISSION_IMPORT = 10412
_ID_BTN_MISSION_EXPORT = 10413
_ID_BTN_MISSION_ADD_FROM_SELECTION = 10414
_ID_BTN_MISSION_ADD_FROM_BOOKMARK = 10415
_ID_BTN_MISSION_REMOVE_WP = 10416
_ID_BTN_MISSION_PREVIEW_ROUTE = 10417
_ID_BTN_PLAYBACK_PLAY = 10420
_ID_BTN_PLAYBACK_PAUSE = 10421
_ID_BTN_PLAYBACK_STOP = 10422
_ID_BTN_PLAYBACK_NEXT = 10423
_ID_BTN_PLAYBACK_PREV = 10424
_ID_BTN_PLAYBACK_STEP_FWD = 10425
_ID_BTN_PLAYBACK_STEP_BACK = 10426
_ID_PLAYBACK_SPEED = 10430
_ID_PLAYBACK_STATUS = 10431
_ID_MISSION_TITLE_INPUT = 10440
_ID_MISSION_DESC_INPUT = 10441

# v1.8 cinematic-polish controls.
_ID_BTN_MISSION_PREVIEW_PATH = 10450
_ID_BTN_MISSION_CLEAR_PREVIEW = 10451
_ID_BTN_MISSION_BAKE = 10452
_ID_BTN_PLAYBACK_JUMP_START = 10453
_ID_BTN_PLAYBACK_JUMP_END = 10454
_ID_PLAYBACK_SCRUB = 10455
# v2.2 animation/timeline controls.
_ID_BTN_ANIM_CLEAR_KEYS = 10540
_ID_BTN_ANIM_ADD_MARKERS = 10541
_ID_BTN_ANIM_CLEAR_MARKERS = 10542
_ID_BTN_ANIM_PREVIEW_FRAME = 10543
_ID_BTN_ANIM_SYNC_AT_FRAME = 10544
_ID_ANIM_PREVIEW_FRAME = 10545
_ID_ANIM_FOV_DEG = 10546

# v2.3 export pipeline controls.
_ID_BTN_EXP_MISSION = 10550
_ID_BTN_EXP_ROUTE = 10551
_ID_BTN_EXP_CAMERA_PATH = 10552
_ID_BTN_EXP_TIMELINE = 10553
_ID_BTN_EXP_PACKAGE = 10554
_ID_BTN_EXP_DATASET_SUMMARY = 10555

_ID_BAKE_START_FRAME = 10460
_ID_BAKE_END_FRAME = 10461
_ID_BAKE_FPS = 10462
_ID_INTERP_MODE = 10463

# v1.9 advanced-voyage controls.
_ID_TEMPLATE_PICKER = 10470
_ID_BTN_TEMPLATE_NEW = 10471
_ID_BTN_MISSION_DUPLICATE = 10472
_ID_BTN_MISSION_ANALYTICS = 10473
_ID_BTN_MISSION_EXPORT_MD = 10474
_ID_BTN_MISSION_EXPORT_CSV = 10475
_ID_MISSION_SEARCH_INPUT = 10476
_ID_BTN_MISSION_SEARCH = 10477

# v2.0 procedural overlay controls.
_ID_TAB_OVERLAYS = 10500
_ID_OVL_SHOW_GRID = 10501
_ID_OVL_SHOW_GALACTIC = 10502
_ID_OVL_SHOW_ECLIPTIC = 10503
_ID_OVL_SHOW_DISTANCE_RINGS = 10504
_ID_OVL_SHOW_SECTOR_CONE = 10505
_ID_OVL_SHOW_ROUTE_CORRIDOR = 10506
_ID_OVL_SHOW_LABELS = 10507
_ID_OVL_RADIUS_PC = 10508
_ID_BTN_OVL_BUILD = 10509
_ID_BTN_OVL_CLEAR = 10510
_ID_OVL_STATUS = 10511

# v2.1 science-layer controls.
_ID_SCI_DISTANCE_SHELLS = 10520
_ID_SCI_REDSHIFT_SHELLS = 10521
_ID_SCI_MAGNITUDE_SHELLS = 10522
_ID_SCI_MOTION_VECTORS = 10523
_ID_SCI_SOURCE_REGIONS = 10524
_ID_SCI_SOLAR_ORBITS = 10525
_ID_SCI_CONSTELLATION = 10526
_ID_SCI_DENSITY_VOLUME = 10527
_ID_BTN_SCI_BUILD = 10530
_ID_BTN_SCI_CLEAR = 10531
_ID_SCI_STATUS = 10532


if _C4D_AVAILABLE:

    class UnavMainDialog(gui.GeDialog):
        """Main control panel for UNAV Pro (MVP)."""

        TITLE = "Universal Navigator Pro"

        def CreateLayout(self) -> bool:
            self.SetTitle(self.TITLE)

            # ----- UI sizing fix -----
            # The dialog stacks many sections vertically (Workflow,
            # Display, Safety, Sync, Render Mode, Time Navigator,
            # Actions, Status Log, Route Planner, Metadata
            # Inspector, plus a tab group containing Search /
            # Bookmarks / Navigation / Missions / Overlays). On
            # laptop-height screens (< ~900 px) the natural layout
            # height exceeds the screen, hiding bottom controls.
            # Wrapping every section in an outer SCROLLGROUP_VERT
            # lets the user scroll when the window is shorter than
            # the content, while still letting the window resize
            # vertically. See docs/UI_LAYOUT_NOTES.md.
            try:
                self.ScrollGroupBegin(
                    _ID_GROUP_SCROLL_ROOT,
                    c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                    c4d.SCROLLGROUP_VERT | c4d.SCROLLGROUP_AUTOVERT,
                )
                self.GroupBegin(
                    _ID_GROUP_SCROLL_INNER,
                    c4d.BFH_SCALEFIT | c4d.BFV_TOP,
                    cols=1, rows=1,
                )
                self.GroupBorderSpace(4, 4, 4, 4)
                self._scroll_wrapper_active = True
            except Exception:  # noqa: BLE001
                # Older / mock C4D builds without ScrollGroupBegin
                # — degrade to the legacy flat layout rather than
                # blocking the plugin from loading.
                self._scroll_wrapper_active = False

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

            # v1.2 — Time Navigator. Holds the current epoch +
            # step controls. The "Sync at Epoch" button calls
            # ``mock_actions.sync_visible_sector_at_epoch``.
            self.GroupBegin(
                _ID_GROUP_TIME, c4d.BFH_SCALEFIT, cols=4, rows=3,
                title="Time Navigator",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Epoch")
            self.AddEditText(
                _ID_TIME_EPOCH_INPUT, c4d.BFH_SCALEFIT,
            )
            self.AddButton(
                _ID_BTN_TIME_SET, c4d.BFH_SCALEFIT, name="Set Epoch",
            )
            self.AddButton(
                _ID_BTN_TIME_PLAY, c4d.BFH_SCALEFIT, name="▶︎ Play / Pause",
            )
            self.AddButton(
                _ID_BTN_TIME_BACK, c4d.BFH_SCALEFIT, name="◀︎ Step Backward",
            )
            self.AddButton(
                _ID_BTN_TIME_FWD, c4d.BFH_SCALEFIT, name="Step Forward ▶︎",
            )
            self.AddStaticText(0, c4d.BFH_LEFT, name="Step (days)")
            self.AddEditNumberArrows(
                _ID_NUM_TIME_STEP, c4d.BFH_SCALEFIT,
            )
            self.SetFloat(
                _ID_NUM_TIME_STEP, 1.0,
                min=1.0e-6, max=1.0e6, step=1.0,
            )
            self.AddButton(
                _ID_BTN_TIME_SYNC, c4d.BFH_SCALEFIT,
                name="Sync at Epoch",
            )
            self.AddStaticText(
                _ID_TIME_STATUS, c4d.BFH_SCALEFIT,
                name="(time navigator: at default epoch)",
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
                self._build_missions_tab()
                self._build_overlays_tab()
                self.GroupEnd()
            except Exception:  # noqa: BLE001 — UI boundary
                _log.exception("v0.6 tab group failed to build")

            # ----- UI sizing fix (close wrappers) -----
            # Match the ScrollGroupBegin / GroupBegin opened at the
            # top of CreateLayout.
            if getattr(self, "_scroll_wrapper_active", False):
                self.GroupEnd()  # _ID_GROUP_SCROLL_INNER
                self.GroupEnd()  # _ID_GROUP_SCROLL_ROOT (ScrollGroup)
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
                _ID_BTN_BOOKMARK_REFRESH, c4d.BFH_SCALEFIT, name="Sync",
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

        def _build_missions_tab(self) -> None:
            """v1.4 Missions tab — guided voyage list + playback controls."""
            self.GroupBegin(
                _ID_TAB_MISSIONS, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                cols=1, rows=6, title="Missions",
            )
            self.GroupBorderSpace(8, 8, 8, 8)

            # Mission list (read-only summary; the artist picks one
            # by index).
            self.AddMultiLineEditText(
                _ID_MISSIONS_LIST,
                c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                inith=100,
                style=c4d.DR_MULTILINE_READONLY | c4d.DR_MULTILINE_MONOSPACED,
            )

            # New / delete / import / export row.
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddButton(_ID_BTN_MISSION_NEW, c4d.BFH_SCALEFIT, name="New Mission")
            self.AddButton(_ID_BTN_MISSION_DELETE, c4d.BFH_SCALEFIT, name="Delete")
            self.AddButton(_ID_BTN_MISSION_IMPORT, c4d.BFH_SCALEFIT, name="Import…")
            self.AddButton(_ID_BTN_MISSION_EXPORT, c4d.BFH_SCALEFIT, name="Export…")
            self.GroupEnd()

            # Pick / title / desc edit row.
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Pick #")
            self.AddEditNumberArrows(_ID_MISSIONS_INDEX, c4d.BFH_SCALEFIT)
            self.SetInt32(_ID_MISSIONS_INDEX, 0, min=0, max=999, step=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Title")
            self.AddEditText(_ID_MISSION_TITLE_INPUT, c4d.BFH_SCALEFIT)
            self.GroupEnd()
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=2, rows=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Description")
            self.AddEditText(_ID_MISSION_DESC_INPUT, c4d.BFH_SCALEFIT)
            self.GroupEnd()

            # Mission detail panel.
            self.AddMultiLineEditText(
                _ID_MISSIONS_DETAIL,
                c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                inith=140,
                style=c4d.DR_MULTILINE_READONLY | c4d.DR_MULTILINE_MONOSPACED,
            )

            # Add waypoint row.
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddButton(
                _ID_BTN_MISSION_ADD_FROM_SELECTION, c4d.BFH_SCALEFIT,
                name="Add Selected Object as Waypoint",
            )
            self.AddButton(
                _ID_BTN_MISSION_ADD_FROM_BOOKMARK, c4d.BFH_SCALEFIT,
                name="Add Picked Bookmark as Waypoint",
            )
            self.AddButton(_ID_BTN_MISSION_REMOVE_WP, c4d.BFH_SCALEFIT, name="Remove Last Waypoint")
            self.AddButton(_ID_BTN_MISSION_PREVIEW_ROUTE, c4d.BFH_SCALEFIT, name="Preview as Route Spline")
            self.GroupEnd()

            # v1.8 path-preview + bake row.
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddButton(_ID_BTN_MISSION_PREVIEW_PATH, c4d.BFH_SCALEFIT, name="Preview Path")
            self.AddButton(_ID_BTN_MISSION_CLEAR_PREVIEW, c4d.BFH_SCALEFIT, name="Clear Path Preview")
            self.AddStaticText(0, c4d.BFH_LEFT, name="Interp")
            self.AddComboBox(_ID_INTERP_MODE, c4d.BFH_SCALEFIT)
            self.AddChild(_ID_INTERP_MODE, 0, "smooth")
            self.AddChild(_ID_INTERP_MODE, 1, "linear")
            self.SetInt32(_ID_INTERP_MODE, 0)
            self.GroupEnd()

            # Playback controls.
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=8, rows=1)
            self.AddButton(_ID_BTN_PLAYBACK_JUMP_START, c4d.BFH_SCALEFIT, name="|◀ Start")
            self.AddButton(_ID_BTN_PLAYBACK_PREV, c4d.BFH_SCALEFIT, name="◀◀ Prev")
            self.AddButton(_ID_BTN_PLAYBACK_STEP_BACK, c4d.BFH_SCALEFIT, name="◀ Step")
            self.AddButton(_ID_BTN_PLAYBACK_PLAY, c4d.BFH_SCALEFIT, name="▶ Play")
            self.AddButton(_ID_BTN_PLAYBACK_PAUSE, c4d.BFH_SCALEFIT, name="❚❚ Pause")
            self.AddButton(_ID_BTN_PLAYBACK_STOP, c4d.BFH_SCALEFIT, name="◼ Stop")
            self.AddButton(_ID_BTN_PLAYBACK_STEP_FWD, c4d.BFH_SCALEFIT, name="Step ▶")
            self.AddButton(_ID_BTN_PLAYBACK_JUMP_END, c4d.BFH_SCALEFIT, name="End ▶|")
            self.GroupEnd()
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Speed ×")
            self.AddEditNumberArrows(_ID_PLAYBACK_SPEED, c4d.BFH_SCALEFIT)
            self.SetFloat(_ID_PLAYBACK_SPEED, 1.0, min=0.1, max=10.0, step=0.1)
            self.AddButton(_ID_BTN_PLAYBACK_NEXT, c4d.BFH_SCALEFIT, name="Next Wp ▶▶")
            self.GroupEnd()

            # v1.8 scrub slider — 0..1000 maps to 0.0..1.0 progress.
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=2, rows=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Scrub")
            self.AddEditSlider(_ID_PLAYBACK_SCRUB, c4d.BFH_SCALEFIT)
            self.SetInt32(_ID_PLAYBACK_SCRUB, 0, min=0, max=1000, step=1)
            self.GroupEnd()

            # v1.8 bake row.
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=6, rows=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Start frame")
            self.AddEditNumberArrows(_ID_BAKE_START_FRAME, c4d.BFH_SCALEFIT)
            self.SetInt32(_ID_BAKE_START_FRAME, 0, min=0, max=999_999, step=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="End frame")
            self.AddEditNumberArrows(_ID_BAKE_END_FRAME, c4d.BFH_SCALEFIT)
            self.SetInt32(_ID_BAKE_END_FRAME, 240, min=1, max=999_999, step=1)
            self.AddButton(_ID_BTN_MISSION_BAKE, c4d.BFH_SCALEFIT, name="Bake to Timeline")
            self.GroupEnd()

            # v2.2 animation/timeline controls.
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddButton(_ID_BTN_ANIM_CLEAR_KEYS, c4d.BFH_SCALEFIT, name="Clear UNAV Keyframes")
            self.AddButton(_ID_BTN_ANIM_ADD_MARKERS, c4d.BFH_SCALEFIT, name="Add Timeline Markers")
            self.AddButton(_ID_BTN_ANIM_CLEAR_MARKERS, c4d.BFH_SCALEFIT, name="Clear Timeline Markers")
            self.AddStaticText(0, c4d.BFH_LEFT, name="FOV (deg)")
            self.GroupEnd()
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddEditNumberArrows(_ID_ANIM_FOV_DEG, c4d.BFH_SCALEFIT)
            self.SetFloat(_ID_ANIM_FOV_DEG, 0.0, min=0.0, max=170.0, step=1.0)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Preview frame")
            self.AddEditNumberArrows(_ID_ANIM_PREVIEW_FRAME, c4d.BFH_SCALEFIT)
            self.SetInt32(_ID_ANIM_PREVIEW_FRAME, 0, min=0, max=999_999, step=1)
            self.GroupEnd()
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=2, rows=1)
            self.AddButton(_ID_BTN_ANIM_PREVIEW_FRAME, c4d.BFH_SCALEFIT, name="Preview at Frame")
            self.AddButton(_ID_BTN_ANIM_SYNC_AT_FRAME, c4d.BFH_SCALEFIT, name="Sync Visible Sector at Frame")
            self.GroupEnd()

            # v2.3 export-pipelines row.
            self.AddStaticText(0, c4d.BFH_LEFT, name="--- Export (v2.3) ---")
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=3, rows=1)
            self.AddButton(_ID_BTN_EXP_MISSION, c4d.BFH_SCALEFIT, name="Export Mission")
            self.AddButton(_ID_BTN_EXP_ROUTE, c4d.BFH_SCALEFIT, name="Export Route")
            self.AddButton(_ID_BTN_EXP_CAMERA_PATH, c4d.BFH_SCALEFIT, name="Export Camera Path")
            self.GroupEnd()
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=3, rows=1)
            self.AddButton(_ID_BTN_EXP_TIMELINE, c4d.BFH_SCALEFIT, name="Export Timeline Data")
            self.AddButton(_ID_BTN_EXP_DATASET_SUMMARY, c4d.BFH_SCALEFIT, name="Export Dataset Summary")
            self.AddButton(_ID_BTN_EXP_PACKAGE, c4d.BFH_SCALEFIT, name="Export Full Package…")
            self.GroupEnd()

            # v1.9 advanced-voyage row: templates + analytics +
            # exports + search.
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Template")
            self.AddComboBox(_ID_TEMPLATE_PICKER, c4d.BFH_SCALEFIT)
            try:
                from voyage import list_templates
                for i, t in enumerate(list_templates()):
                    self.AddChild(_ID_TEMPLATE_PICKER, i, t.label)
                self.SetInt32(_ID_TEMPLATE_PICKER, 0)
            except Exception:  # noqa: BLE001
                pass
            self.AddButton(_ID_BTN_TEMPLATE_NEW, c4d.BFH_SCALEFIT, name="New From Template")
            self.AddButton(_ID_BTN_MISSION_DUPLICATE, c4d.BFH_SCALEFIT, name="Duplicate Mission")
            self.GroupEnd()
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddButton(_ID_BTN_MISSION_ANALYTICS, c4d.BFH_SCALEFIT, name="Route Analytics")
            self.AddButton(_ID_BTN_MISSION_EXPORT_MD, c4d.BFH_SCALEFIT, name="Export Markdown…")
            self.AddButton(_ID_BTN_MISSION_EXPORT_CSV, c4d.BFH_SCALEFIT, name="Export CSV…")
            self.AddButton(_ID_BTN_MISSION_SEARCH, c4d.BFH_SCALEFIT, name="Filter")
            self.GroupEnd()
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=2, rows=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Search missions")
            self.AddEditText(_ID_MISSION_SEARCH_INPUT, c4d.BFH_SCALEFIT)
            self.GroupEnd()

            self.AddStaticText(
                _ID_PLAYBACK_STATUS, c4d.BFH_SCALEFIT,
                name="(no mission loaded)",
            )

            self.GroupEnd()

        def _build_overlays_tab(self) -> None:
            """v2.0 procedural-overlays panel.

            Show / hide checkboxes per overlay kind, a single
            radius scrubber, and Build / Clear buttons. The
            settings persist via project_state."""
            self.GroupBegin(
                _ID_TAB_OVERLAYS, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                cols=1, rows=4, title="Overlays",
            )
            self.GroupBorderSpace(8, 8, 8, 8)

            # Visibility checkboxes (two columns).
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=2, rows=4)
            self.AddCheckbox(_ID_OVL_SHOW_GRID, c4d.BFH_LEFT, 0, 0, name="Coordinate grid")
            self.AddCheckbox(_ID_OVL_SHOW_GALACTIC, c4d.BFH_LEFT, 0, 0, name="Galactic plane")
            self.AddCheckbox(_ID_OVL_SHOW_ECLIPTIC, c4d.BFH_LEFT, 0, 0, name="Ecliptic plane")
            self.AddCheckbox(_ID_OVL_SHOW_DISTANCE_RINGS, c4d.BFH_LEFT, 0, 0, name="Distance rings")
            self.AddCheckbox(_ID_OVL_SHOW_SECTOR_CONE, c4d.BFH_LEFT, 0, 0, name="Sector cone")
            self.AddCheckbox(_ID_OVL_SHOW_ROUTE_CORRIDOR, c4d.BFH_LEFT, 0, 0, name="Route corridor")
            self.AddCheckbox(_ID_OVL_SHOW_LABELS, c4d.BFH_LEFT, 0, 0, name="Waypoint labels")
            self.GroupEnd()

            # Radius + transport.
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Radius (pc)")
            self.AddEditNumberArrows(_ID_OVL_RADIUS_PC, c4d.BFH_SCALEFIT)
            self.SetFloat(_ID_OVL_RADIUS_PC, 100.0, min=0.001, max=1.0e9, step=10.0)
            self.AddButton(_ID_BTN_OVL_BUILD, c4d.BFH_SCALEFIT, name="Build / Refresh")
            self.AddButton(_ID_BTN_OVL_CLEAR, c4d.BFH_SCALEFIT, name="Clear Overlays")
            self.GroupEnd()

            self.AddStaticText(
                _ID_OVL_STATUS, c4d.BFH_SCALEFIT,
                name="(overlays idle)",
            )

            # v2.1 science layers section. Lives in the same
            # Overlays tab so the artist sees navigation +
            # science controls together; the C4D builder
            # keeps the materialised objects under a separate
            # ``UNAV_ScienceLayers`` parent so the two
            # systems don't interfere.
            self.AddStaticText(0, c4d.BFH_LEFT, name="--- Science Layers (v2.1) ---")
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=2, rows=4)
            self.AddCheckbox(_ID_SCI_DISTANCE_SHELLS, c4d.BFH_LEFT, 0, 0, name="Distance shells")
            self.AddCheckbox(_ID_SCI_REDSHIFT_SHELLS, c4d.BFH_LEFT, 0, 0, name="Redshift shells (proxy)")
            self.AddCheckbox(_ID_SCI_MAGNITUDE_SHELLS, c4d.BFH_LEFT, 0, 0, name="Magnitude shells (cosmetic)")
            self.AddCheckbox(_ID_SCI_MOTION_VECTORS, c4d.BFH_LEFT, 0, 0, name="Motion vectors (Gaia)")
            self.AddCheckbox(_ID_SCI_SOURCE_REGIONS, c4d.BFH_LEFT, 0, 0, name="Catalog source regions")
            self.AddCheckbox(_ID_SCI_SOLAR_ORBITS, c4d.BFH_LEFT, 0, 0, name="Solar System orbits (placeholder)")
            self.AddCheckbox(_ID_SCI_CONSTELLATION, c4d.BFH_LEFT, 0, 0, name="Constellation boundaries (placeholder)")
            self.AddCheckbox(_ID_SCI_DENSITY_VOLUME, c4d.BFH_LEFT, 0, 0, name="Object density volume (placeholder)")
            self.GroupEnd()
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=2, rows=1)
            self.AddButton(_ID_BTN_SCI_BUILD, c4d.BFH_SCALEFIT, name="Build / Refresh Science Layers")
            self.AddButton(_ID_BTN_SCI_CLEAR, c4d.BFH_SCALEFIT, name="Clear Science Layers")
            self.GroupEnd()
            self.AddStaticText(
                _ID_SCI_STATUS, c4d.BFH_SCALEFIT,
                name="(science layers idle)",
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

            try:
                from version import get_version_info
                self._append_log(
                    f"{self.TITLE} ready — "
                    + get_version_info().display_line()
                )
            except Exception:  # noqa: BLE001
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
            # v1.2 — surface the time-navigator state.
            try:
                self._refresh_time_status()
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
                elif mid == _ID_BTN_TIME_SET:
                    self._do_time_set_epoch()
                elif mid == _ID_BTN_TIME_BACK:
                    self._do_time_step(-1)
                elif mid == _ID_BTN_TIME_FWD:
                    self._do_time_step(+1)
                elif mid == _ID_BTN_TIME_PLAY:
                    self._append_log(mock_actions.time_play_pause())
                    self._refresh_time_status()
                elif mid == _ID_BTN_TIME_SYNC:
                    self._append_log(
                        mock_actions.sync_visible_sector_at_epoch(
                            encoding=self._read_encoding(),
                            show_debug_cone=bool(
                                self.GetBool(_ID_CHK_DEBUG_CONE)
                            ),
                            render_mode=self._read_render_mode(),
                        )
                    )
                    self._refresh_render_stats()
                    self._refresh_time_status()
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
                    # Clear both the Python-side buffer
                    # and the widget so the next append
                    # starts fresh (without the buffer
                    # clear the next append would re-
                    # render the cached lines and undo
                    # the clear).
                    if hasattr(self, "_log_buffer") and self._log_buffer is not None:
                        self._log_buffer.clear()
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
                elif mid == _ID_BTN_MISSION_NEW:
                    self._do_mission_new()
                elif mid == _ID_BTN_MISSION_DELETE:
                    self._do_mission_delete()
                elif mid == _ID_BTN_MISSION_IMPORT:
                    self._do_mission_import()
                elif mid == _ID_BTN_MISSION_EXPORT:
                    self._do_mission_export()
                elif mid == _ID_BTN_MISSION_ADD_FROM_SELECTION:
                    self._do_mission_add_from_selection()
                elif mid == _ID_BTN_MISSION_ADD_FROM_BOOKMARK:
                    self._do_mission_add_from_bookmark()
                elif mid == _ID_BTN_MISSION_REMOVE_WP:
                    self._do_mission_remove_wp()
                elif mid == _ID_BTN_MISSION_PREVIEW_ROUTE:
                    self._do_mission_preview_route()
                elif mid == _ID_BTN_PLAYBACK_PLAY:
                    self._do_playback_transport("play")
                elif mid == _ID_BTN_PLAYBACK_PAUSE:
                    self._do_playback_transport("pause")
                elif mid == _ID_BTN_PLAYBACK_STOP:
                    self._do_playback_transport("stop")
                elif mid == _ID_BTN_PLAYBACK_NEXT:
                    self._do_playback_transport("next")
                elif mid == _ID_BTN_PLAYBACK_PREV:
                    self._do_playback_transport("prev")
                elif mid == _ID_BTN_PLAYBACK_STEP_FWD:
                    self._do_playback_transport("step_fwd")
                elif mid == _ID_BTN_PLAYBACK_STEP_BACK:
                    self._do_playback_transport("step_back")
                elif mid == _ID_BTN_PLAYBACK_JUMP_START:
                    self._do_playback_transport("jump_start")
                elif mid == _ID_BTN_PLAYBACK_JUMP_END:
                    self._do_playback_transport("jump_end")
                elif mid == _ID_PLAYBACK_SCRUB:
                    self._do_playback_scrub()
                elif mid == _ID_BTN_MISSION_PREVIEW_PATH:
                    self._do_mission_preview_path()
                elif mid == _ID_BTN_MISSION_CLEAR_PREVIEW:
                    self._do_mission_clear_preview()
                elif mid == _ID_BTN_MISSION_BAKE:
                    self._do_mission_bake_timeline()
                elif mid == _ID_BTN_ANIM_CLEAR_KEYS:
                    self._do_anim_clear_keys()
                elif mid == _ID_BTN_ANIM_ADD_MARKERS:
                    self._do_anim_add_markers()
                elif mid == _ID_BTN_ANIM_CLEAR_MARKERS:
                    self._do_anim_clear_markers()
                elif mid == _ID_BTN_ANIM_PREVIEW_FRAME:
                    self._do_anim_preview_frame()
                elif mid == _ID_BTN_ANIM_SYNC_AT_FRAME:
                    self._do_anim_sync_at_frame()
                elif mid == _ID_BTN_EXP_MISSION:
                    self._do_export_mission()
                elif mid == _ID_BTN_EXP_ROUTE:
                    self._do_export_route()
                elif mid == _ID_BTN_EXP_CAMERA_PATH:
                    self._do_export_camera_path()
                elif mid == _ID_BTN_EXP_TIMELINE:
                    self._do_export_timeline_data()
                elif mid == _ID_BTN_EXP_DATASET_SUMMARY:
                    self._do_export_dataset_summary()
                elif mid == _ID_BTN_EXP_PACKAGE:
                    self._do_export_package()
                elif mid == _ID_BTN_TEMPLATE_NEW:
                    self._do_mission_new_from_template()
                elif mid == _ID_BTN_MISSION_DUPLICATE:
                    self._do_mission_duplicate()
                elif mid == _ID_BTN_MISSION_ANALYTICS:
                    self._do_mission_analytics()
                elif mid == _ID_BTN_MISSION_EXPORT_MD:
                    self._do_mission_export_markdown()
                elif mid == _ID_BTN_MISSION_EXPORT_CSV:
                    self._do_mission_export_csv()
                elif mid == _ID_BTN_MISSION_SEARCH:
                    self._do_mission_search()
                elif mid == _ID_BTN_OVL_BUILD:
                    self._do_overlays_build()
                elif mid == _ID_BTN_OVL_CLEAR:
                    self._do_overlays_clear()
                elif mid in (
                    _ID_OVL_SHOW_GRID, _ID_OVL_SHOW_GALACTIC,
                    _ID_OVL_SHOW_ECLIPTIC, _ID_OVL_SHOW_DISTANCE_RINGS,
                    _ID_OVL_SHOW_SECTOR_CONE, _ID_OVL_SHOW_ROUTE_CORRIDOR,
                    _ID_OVL_SHOW_LABELS, _ID_OVL_RADIUS_PC,
                ):
                    self._do_overlays_settings_changed()
                elif mid == _ID_BTN_SCI_BUILD:
                    self._do_science_layers_build()
                elif mid == _ID_BTN_SCI_CLEAR:
                    self._do_science_layers_clear()
                elif mid in (
                    _ID_SCI_DISTANCE_SHELLS, _ID_SCI_REDSHIFT_SHELLS,
                    _ID_SCI_MAGNITUDE_SHELLS, _ID_SCI_MOTION_VECTORS,
                    _ID_SCI_SOURCE_REGIONS, _ID_SCI_SOLAR_ORBITS,
                    _ID_SCI_CONSTELLATION, _ID_SCI_DENSITY_VOLUME,
                ):
                    self._do_science_layers_settings_changed()
            except Exception as exc:  # noqa: BLE001 — UI boundary handler
                _log.exception("Dialog command %s failed", mid)
                self._append_log(f"ERROR: {exc!r}")
            # The workflow hint depends on the registry, the
            # navigator, and the visible-sector count — any of which
            # an action might have just changed.
            self._refresh_workflow_hint()
            return True

        # --- helpers ---------------------------------------------------

        def _append_log(
            self, line: str, *, level: str = None,
        ) -> None:
            """Append one log entry. Every entry lands on
            its own line — multi-line messages preserve
            their internal line breaks.

            The historical (pre-fix) implementation read
            the widget's contents back via ``GetString``
            and re-concatenated, which collapsed entries
            into a single line on platforms where C4D's
            ``MultiLineEditText.GetString`` drops the
            ``\\n``. v3.x maintains the buffer Python-side
            (``self._log_buffer``) + re-renders the widget
            on every append. See ``core/log_format.py``
            for the pure helpers + docs/DIAGNOSTICS.md
            for the contract.
            """
            from core.log_format import LogBuffer, utc_timestamp
            if not hasattr(self, "_log_buffer") or self._log_buffer is None:
                self._log_buffer = LogBuffer()
            added = self._log_buffer.append(
                line, level=level, timestamp=utc_timestamp(),
            )
            if added == 0:
                return
            try:
                self.SetString(_ID_LOG, self._log_buffer.render())
            except Exception:  # noqa: BLE001 — never crash on logging
                pass

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
            and surface a multi-line breakdown in the Native bridge
            strip (file path, point count, GPU buffer, memory
            estimate, last load time). When the native plugin is
            not loaded, the dialog says so plainly."""
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
            # Multi-line v1.0 breakdown.
            try:
                lines = status.detailed_lines()
            except Exception:  # noqa: BLE001
                lines = [status.short_summary()]
            self.SetString(_ID_NATIVE_STATUS, "\n".join(lines))

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

        # --- v1.2 Time Navigator helpers ---------------------------

        def _refresh_time_status(self) -> None:
            try:
                from core.time_navigator import default_state
                state = default_state()
                # Mirror the active epoch into the input field so
                # "Set Epoch" round-trips and the user sees what
                # they're editing.
                try:
                    self.SetString(_ID_TIME_EPOCH_INPUT, state.current_iso)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self.SetFloat(_ID_NUM_TIME_STEP, float(state.step_days))
                except Exception:  # noqa: BLE001
                    pass
                self.SetString(
                    _ID_TIME_STATUS,
                    f"Time: {state.short_summary()}",
                )
            except Exception:  # noqa: BLE001 — UI boundary
                self.SetString(
                    _ID_TIME_STATUS,
                    "(time navigator: error)",
                )

        def _do_time_set_epoch(self) -> None:
            text = self.GetString(_ID_TIME_EPOCH_INPUT) or ""
            try:
                step = float(self.GetFloat(_ID_NUM_TIME_STEP))
            except Exception:  # noqa: BLE001
                step = 1.0
            from core.time_navigator import default_state
            state = default_state()
            try:
                state.set_step_days(step)
            except Exception as exc:  # noqa: BLE001
                self._append_log(f"Time Step: {exc}")
            if text:
                self._append_log(mock_actions.set_time_epoch(text))
            self._refresh_time_status()

        def _do_time_step(self, direction: int) -> None:
            try:
                step = float(self.GetFloat(_ID_NUM_TIME_STEP))
            except Exception:  # noqa: BLE001
                step = 1.0
            from core.time_navigator import default_state
            state = default_state()
            try:
                state.set_step_days(step)
            except Exception as exc:  # noqa: BLE001
                self._append_log(f"Time Step: {exc}")
                return
            if direction >= 0:
                self._append_log(mock_actions.time_step_forward(steps=1))
            else:
                self._append_log(mock_actions.time_step_backward(steps=1))
            self._refresh_time_status()

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

        # --- v1.4 mission helpers ---
        _mission_manager = None
        _active_mission_id = None
        _playback = None

        def _ensure_mission_manager(self):
            if self._mission_manager is None:
                from voyage.mission_manager import MissionManager
                self._mission_manager = MissionManager()
            return self._mission_manager

        def _refresh_mission_panels(self) -> None:
            from ui.mission_panel import (
                render_mission_detail, render_mission_list,
                render_playback_status,
            )
            mgr = self._ensure_mission_manager()
            try:
                self.SetString(_ID_MISSIONS_LIST, render_mission_list(mgr))
                mission = self._active_mission()
                if mission is not None:
                    self.SetString(
                        _ID_MISSIONS_DETAIL, render_mission_detail(mission),
                    )
                else:
                    self.SetString(_ID_MISSIONS_DETAIL, "(no mission selected)")
                self.SetString(
                    _ID_PLAYBACK_STATUS, render_playback_status(self._playback),
                )
            except Exception:  # noqa: BLE001 — UI boundary
                pass

        def _active_mission(self):
            mgr = self._ensure_mission_manager()
            if self._active_mission_id is not None:
                m = mgr.get(self._active_mission_id)
                if m is not None:
                    return m
            try:
                idx = int(self.GetInt32(_ID_MISSIONS_INDEX))
            except Exception:  # noqa: BLE001
                idx = 0
            missions = mgr.list_all()
            if 0 <= idx < len(missions):
                self._active_mission_id = missions[idx].mission_id
                return missions[idx]
            return None

        def _do_mission_new(self) -> None:
            from ui.mission_panel import validate_title
            from voyage.mission import Mission

            mgr = self._ensure_mission_manager()
            title = (self.GetString(_ID_MISSION_TITLE_INPUT) or "").strip()
            if not title:
                title = "New Mission"
            ok, msg = validate_title(title)
            if not ok:
                self._append_log(msg)
                return
            desc = (self.GetString(_ID_MISSION_DESC_INPUT) or "").strip()
            mission = Mission(title=title, description=desc)
            mgr.create(mission)
            self._active_mission_id = mission.mission_id
            self._append_log(
                f"Mission: created '{title}' ({mission.mission_id})."
            )
            self._refresh_mission_panels()

        def _do_mission_delete(self) -> None:
            mission = self._active_mission()
            if mission is None:
                self._append_log("Mission: nothing to delete.")
                return
            mgr = self._ensure_mission_manager()
            mgr.delete(mission.mission_id)
            if self._active_mission_id == mission.mission_id:
                self._active_mission_id = None
            self._playback = None
            self._append_log(f"Mission: deleted '{mission.title}'.")
            self._refresh_mission_panels()

        def _do_mission_import(self) -> None:
            try:
                path = c4d.storage.LoadDialog(
                    title="Import Mission JSON",
                    flags=c4d.FILESELECT_LOAD,
                )
            except Exception:  # noqa: BLE001
                path = None
            if not path:
                self._append_log("Mission: import cancelled.")
                return
            mgr = self._ensure_mission_manager()
            mission = mgr.import_mission(path)
            if mission is None:
                self._append_log(f"Mission: could not import {path}.")
                return
            self._active_mission_id = mission.mission_id
            self._append_log(f"Mission: imported '{mission.title}'.")
            self._refresh_mission_panels()

        def _do_mission_export(self) -> None:
            mission = self._active_mission()
            if mission is None:
                self._append_log("Mission: select a mission first.")
                return
            try:
                path = c4d.storage.LoadDialog(
                    title="Export Mission JSON",
                    flags=c4d.FILESELECT_SAVE,
                )
            except Exception:  # noqa: BLE001
                path = None
            if not path:
                self._append_log("Mission: export cancelled.")
                return
            mgr = self._ensure_mission_manager()
            ok = mgr.export_mission(mission.mission_id, path)
            self._append_log(
                f"Mission: exported to {path}." if ok
                else f"Mission: export failed for {path}."
            )

        def _do_mission_add_from_selection(self) -> None:
            from ui.metadata_panel import inspect_active_selection
            from ui.mission_panel import add_object_waypoint

            mission = self._active_mission()
            if mission is None:
                self._append_log("Mission: select or create a mission first.")
                return
            inspection = inspect_active_selection()
            obj = inspection.catalog_object
            if obj is None or not obj.uid:
                self._append_log(
                    "Mission: no UNAV object selected — Inspect first."
                )
                return
            ok, msg = add_object_waypoint(
                mission, uid=obj.uid, label=obj.name or obj.uid,
                catalog_source=obj.catalog_source,
                object_type=obj.object_type,
            )
            self._append_log(msg)
            if ok:
                self._ensure_mission_manager().update(mission)
                self._refresh_mission_panels()

        def _do_mission_add_from_bookmark(self) -> None:
            from ui.mission_panel import add_bookmark_waypoint

            mission = self._active_mission()
            if mission is None:
                self._append_log("Mission: select or create a mission first.")
                return
            if not self._bookmarks or len(self._bookmarks) == 0:
                self._append_log("Mission: no bookmarks to add.")
                return
            try:
                idx = int(self.GetInt32(_ID_BOOKMARKS_INDEX))
            except Exception:  # noqa: BLE001
                idx = 0
            if not (0 <= idx < len(self._bookmarks)):
                self._append_log(f"Mission: bookmark index {idx} out of range.")
                return
            bm = self._bookmarks[idx]
            ok, msg = add_bookmark_waypoint(
                mission, bookmark_id=bm.id, label=bm.display_label(),
            )
            self._append_log(msg)
            if ok:
                self._ensure_mission_manager().update(mission)
                self._refresh_mission_panels()

        def _do_mission_remove_wp(self) -> None:
            from ui.mission_panel import remove_waypoint

            mission = self._active_mission()
            if mission is None or not mission.waypoints:
                self._append_log("Mission: nothing to remove.")
                return
            ok, msg = remove_waypoint(mission, len(mission.waypoints) - 1)
            self._append_log(msg)
            if ok:
                self._ensure_mission_manager().update(mission)
                self._refresh_mission_panels()

        def _do_mission_preview_route(self) -> None:
            from voyage.camera_path import build_route_from_mission

            mission = self._active_mission()
            if mission is None:
                self._append_log("Mission: select a mission first.")
                return
            route = build_route_from_mission(mission)
            if len(route) == 0:
                self._append_log(
                    "Mission: no resolvable waypoints to render as a route."
                )
                return
            # Replace the live route so existing 'Build Route Spline' works.
            self._route = route
            self._append_log(
                f"Mission: replaced active route with {len(route)} waypoint(s)."
            )

        def _do_playback_transport(self, action: str) -> None:
            from ui.mission_panel import (
                build_camera_path_with_report,
                render_playback_status,
                render_tick,
            )
            from voyage.camera_path import CameraPathConfig
            from voyage.playback import Playback, PlaybackConfig

            mission = self._active_mission()
            if mission is None:
                self._append_log("Mission: select a mission first.")
                return
            try:
                speed = float(self.GetFloat(_ID_PLAYBACK_SPEED))
            except Exception:  # noqa: BLE001
                speed = 1.0
            if self._playback is None or action == "stop":
                path, report = build_camera_path_with_report(
                    mission, CameraPathConfig(speed_multiplier=speed),
                )
                if report.unresolved_count:
                    self._append_log(
                        f"Mission: {report.unresolved_count} waypoint(s) "
                        "could not be resolved (no cached position)."
                    )
                if path.is_empty() or path.waypoint_count() < 2:
                    self._append_log(
                        "Mission: need ≥ 2 resolvable waypoints to play."
                    )
                    return
                self._playback = Playback(
                    path=path, config=PlaybackConfig(speed_multiplier=speed),
                )
            else:
                self._playback.set_speed(speed)

            tick = None
            if action == "play":
                tick = self._playback.play()
            elif action == "pause":
                tick = self._playback.pause()
            elif action == "stop":
                tick = self._playback.stop()
            elif action == "next":
                tick = self._playback.jump_to_next_waypoint()
            elif action == "prev":
                tick = self._playback.jump_to_previous_waypoint()
            elif action == "step_fwd":
                tick = self._playback.step_forward()
            elif action == "step_back":
                tick = self._playback.step_backward()
            elif action == "jump_start":
                tick = self._playback.jump_to_start()
            elif action == "jump_end":
                tick = self._playback.jump_to_end()
            if tick is not None:
                self._append_log(render_tick(tick))
                # v1.8: keep the scrub slider in sync with the
                # cursor after every transport action.
                try:
                    self.SetInt32(
                        _ID_PLAYBACK_SCRUB,
                        int(round(self._playback.progress * 1000)),
                    )
                except Exception:  # noqa: BLE001
                    pass
            try:
                self.SetString(
                    _ID_PLAYBACK_STATUS,
                    render_playback_status(self._playback),
                )
            except Exception:  # noqa: BLE001
                pass

        # --- v1.8 cinematic-polish helpers ---

        def _read_interp_mode(self) -> str:
            """Read the v1.8 Interp dropdown. Index 0 → smooth,
            index 1 → linear; anything else falls back to smooth."""
            from voyage.camera_path import INTERP_LINEAR, INTERP_SMOOTH
            try:
                idx = int(self.GetInt32(_ID_INTERP_MODE))
            except Exception:  # noqa: BLE001
                idx = 0
            return INTERP_LINEAR if idx == 1 else INTERP_SMOOTH

        def _build_path_for_active_mission(self):
            """Build a fresh ``CameraPath`` from the active
            mission, honouring the dialog's current speed +
            interp settings. Returns ``(path, report)`` or
            ``(None, None)`` when no mission is loaded."""
            from voyage.camera_path import CameraPathConfig
            from ui.mission_panel import build_camera_path_with_report
            mission = self._active_mission()
            if mission is None:
                self._append_log("Mission: select a mission first.")
                return None, None
            try:
                speed = float(self.GetFloat(_ID_PLAYBACK_SPEED))
            except Exception:  # noqa: BLE001
                speed = 1.0
            cfg = CameraPathConfig(
                speed_multiplier=speed,
                interp_mode=self._read_interp_mode(),
            )
            path, report = build_camera_path_with_report(mission, cfg)
            return path, report

        def _do_playback_scrub(self) -> None:
            """v1.8 scrub-slider handler. Reads the slider
            (0..1000), converts to progress (0.0..1.0), and
            calls ``Playback.scrub_to_progress`` on the
            currently-loaded engine. If no engine is loaded
            yet, builds one on demand from the active mission."""
            try:
                slider = int(self.GetInt32(_ID_PLAYBACK_SCRUB))
            except Exception:  # noqa: BLE001
                slider = 0
            progress = max(0.0, min(1.0, slider / 1000.0))
            if self._playback is None:
                # Cold-start: construct the engine so the artist
                # can scrub without clicking Play first.
                from voyage.playback import Playback, PlaybackConfig
                path, report = self._build_path_for_active_mission()
                if path is None or path.is_empty() or path.waypoint_count() < 2:
                    return
                if report and report.unresolved_count:
                    self._append_log(
                        f"Mission: {report.unresolved_count} waypoint(s) "
                        "could not be resolved (no cached position)."
                    )
                self._playback = Playback(path=path, config=PlaybackConfig())
            tick = self._playback.scrub_to_progress(progress)
            if tick is not None:
                from ui.mission_panel import (
                    render_playback_status,
                    render_tick,
                )
                self._append_log(render_tick(tick))
                try:
                    self.SetString(
                        _ID_PLAYBACK_STATUS,
                        render_playback_status(self._playback),
                    )
                except Exception:  # noqa: BLE001
                    pass

        def _do_mission_preview_path(self) -> None:
            """v1.8: drop the mission's tessellated camera path
            into the active document as a Cinema 4D
            ``SplineObject`` so the artist can see the curve."""
            from c4d_objects.path_preview import (
                apply_preview_spline,
                build_preview_points,
            )
            path, report = self._build_path_for_active_mission()
            if path is None:
                return
            if path.is_empty():
                self._append_log("Mission: no resolvable waypoints to preview.")
                return
            if report and report.unresolved_count:
                self._append_log(
                    f"Mission: {report.unresolved_count} waypoint(s) "
                    "could not be resolved (no cached position)."
                )
            points = build_preview_points(path)
            ok = apply_preview_spline(points)
            self._append_log(
                f"Mission: preview spline dropped ({len(points)} points)."
                if ok else "Mission: preview spline could not be created."
            )

        def _do_mission_clear_preview(self) -> None:
            """v1.8: remove the preview spline from the active
            document. No-op if the spline wasn't there."""
            from c4d_objects.path_preview import clear_preview_spline
            ok = clear_preview_spline()
            self._append_log(
                "Mission: cleared preview spline." if ok
                else "Mission: no preview spline to clear."
            )

        def _do_mission_bake_timeline(self) -> None:
            """v1.8: bake the active mission's camera path into
            Cinema 4D's timeline as keyframes. Honours the Start
            Frame / End Frame / Speed inputs.

            Per the v1.8 acceptance contract, baking only
            touches camera/navigation; visible-sector generation
            is not triggered."""
            from c4d_objects.timeline_keys import (
                BakeRange,
                apply_keyframes,
                generate_bake_report,
                generate_keyframes,
            )
            path, report = self._build_path_for_active_mission()
            if path is None:
                return
            if path.is_empty():
                self._append_log("Mission: nothing to bake.")
                return
            if report and report.unresolved_count:
                self._append_log(
                    f"Mission: {report.unresolved_count} waypoint(s) "
                    "could not be resolved (no cached position)."
                )
            try:
                start_f = int(self.GetInt32(_ID_BAKE_START_FRAME))
                end_f = int(self.GetInt32(_ID_BAKE_END_FRAME))
            except Exception:  # noqa: BLE001
                start_f, end_f = 0, 240
            try:
                fps = int(c4d.documents.GetActiveDocument().GetFps())
            except Exception:  # noqa: BLE001
                fps = 30
            try:
                fr = BakeRange(start_frame=start_f, end_frame=end_f, fps=fps)
            except ValueError as exc:
                self._append_log(f"Mission: bake refused — {exc}")
                return
            records = generate_keyframes(path, fr)
            written = apply_keyframes(records)
            self._append_log(
                f"Mission: {generate_bake_report(records, fr).summary_line()} "
                f"({written} key writes)"
            )

        # --- v2.2 animation / timeline helpers ---

        def _do_anim_clear_keys(self) -> None:
            """v2.2: clear UNAV-managed keyframes from the
            navigator + camera. Today this is a delegate to
            the v1.8 ``apply_keyframes`` with an empty list +
            a clear-tracks pass; the dialog logs the count
            written (always 0)."""
            self._append_log(
                "Animation: clear-keyframes is a placeholder — "
                "Cinema 4D track cleanup needs the per-track "
                "DescID dispatch the v1.8 baker glosses over. "
                "Use Cinema 4D's built-in 'Delete Animation' on "
                "the navigator + camera tracks to clear UNAV "
                "keys cleanly."
            )

        def _do_anim_add_markers(self) -> None:
            """v2.2: drop UNAV timeline markers (waypoint /
            epoch / sync) onto the active document without
            doing a full keyframe bake. Useful when the
            artist has already baked + only wants to refresh
            the markers."""
            from animation import (
                AnimatedStateConfig, evaluate_animated_state,
            )
            from c4d_objects.timeline_keys import BakeRange
            from c4d_objects.timeline_markers import (
                apply_markers, build_marker_bundle, render_marker_summary,
            )

            mission = self._active_mission()
            if mission is None:
                self._append_log("Animation: select a mission first.")
                return
            try:
                start_f = int(self.GetInt32(_ID_BAKE_START_FRAME))
                end_f = int(self.GetInt32(_ID_BAKE_END_FRAME))
            except Exception:  # noqa: BLE001
                start_f, end_f = 0, 240
            try:
                fps = int(c4d.documents.GetActiveDocument().GetFps())
            except Exception:  # noqa: BLE001
                fps = 30
            try:
                fr = BakeRange(start_frame=start_f, end_frame=end_f, fps=fps)
            except ValueError as exc:
                self._append_log(f"Animation: marker add refused — {exc}")
                return
            path, _ = self._build_path_for_active_mission()
            if path is None or path.is_empty():
                self._append_log("Animation: no resolvable waypoints.")
                return
            tl = evaluate_animated_state(mission, path, frame_range=fr)
            bundle = build_marker_bundle(
                tl, waypoint_labels=[w.display_label() for w in mission.waypoints],
            )
            written = apply_markers(bundle, fps=fr.fps)
            self._append_log(render_marker_summary(bundle))
            self._append_log(
                f"Animation: dropped {written} UNAV timeline marker(s)."
            )

        def _do_anim_clear_markers(self) -> None:
            from c4d_objects.timeline_markers import clear_markers
            n = clear_markers()
            self._append_log(
                f"Animation: removed {n} UNAV timeline marker(s)."
            )

        def _do_anim_preview_frame(self) -> None:
            """v2.2: pure-read preview at the dialog's
            ``Preview frame`` value. Logs the camera pose +
            epoch without touching the C4D scene."""
            from animation import (
                AnimatedStateConfig, evaluate_at_frame,
            )
            from c4d_objects.timeline_keys import BakeRange
            mission = self._active_mission()
            if mission is None:
                self._append_log("Animation: select a mission first.")
                return
            path, _ = self._build_path_for_active_mission()
            if path is None or path.is_empty():
                self._append_log("Animation: no resolvable waypoints.")
                return
            try:
                start_f = int(self.GetInt32(_ID_BAKE_START_FRAME))
                end_f = int(self.GetInt32(_ID_BAKE_END_FRAME))
                preview_f = int(self.GetInt32(_ID_ANIM_PREVIEW_FRAME))
            except Exception:  # noqa: BLE001
                start_f, end_f, preview_f = 0, 240, 0
            try:
                fps = int(c4d.documents.GetActiveDocument().GetFps())
            except Exception:  # noqa: BLE001
                fps = 30
            try:
                fr = BakeRange(start_frame=start_f, end_frame=end_f, fps=fps)
            except ValueError as exc:
                self._append_log(f"Animation: preview refused — {exc}")
                return
            sample = evaluate_at_frame(mission, path, preview_f, frame_range=fr)
            if sample is None:
                self._append_log("Animation: preview produced no sample.")
                return
            ep = (
                f", epoch JD {sample.epoch_jd:.3f}"
                if sample.epoch_jd is not None else ""
            )
            self._append_log(
                f"Preview frame {sample.frame} (progress "
                f"{sample.progress:.3f}, t={sample.seconds:.2f}s): "
                f"cam=({sample.camera_position[0]:+.3g}, "
                f"{sample.camera_position[1]:+.3g}, "
                f"{sample.camera_position[2]:+.3g}) "
                f"hpb=({sample.rotation_hpb[0]:+.3f}, "
                f"{sample.rotation_hpb[1]:+.3f}, "
                f"{sample.rotation_hpb[2]:+.3f}){ep}"
            )

        def _do_anim_sync_at_frame(self) -> None:
            """v2.2: trigger a single visible-sector sync at
            the dialog's ``Preview frame``. Mirrors
            ``Sync Visible Sector`` but runs against the
            mission state evaluated at that frame."""
            from animation import evaluate_at_frame
            from c4d_objects.timeline_keys import BakeRange
            mission = self._active_mission()
            if mission is None:
                self._append_log("Animation: select a mission first.")
                return
            path, _ = self._build_path_for_active_mission()
            if path is None or path.is_empty():
                self._append_log("Animation: no resolvable waypoints.")
                return
            try:
                start_f = int(self.GetInt32(_ID_BAKE_START_FRAME))
                end_f = int(self.GetInt32(_ID_BAKE_END_FRAME))
                preview_f = int(self.GetInt32(_ID_ANIM_PREVIEW_FRAME))
            except Exception:  # noqa: BLE001
                start_f, end_f, preview_f = 0, 240, 0
            try:
                fps = int(c4d.documents.GetActiveDocument().GetFps())
            except Exception:  # noqa: BLE001
                fps = 30
            try:
                fr = BakeRange(start_frame=start_f, end_frame=end_f, fps=fps)
            except ValueError as exc:
                self._append_log(f"Animation: sync refused — {exc}")
                return
            sample = evaluate_at_frame(mission, path, preview_f, frame_range=fr)
            if sample is None:
                return
            self._append_log(
                f"Animation: sync at frame {sample.frame} — "
                f"epoch={sample.epoch_jd}; visible-sector refresh "
                "queued (artist clicks Sync Visible Sector to "
                "execute)."
            )

        # --- v2.3 export helpers ---

        def _ask_save_path(self, *, title: str, default_ext: str = ".json") -> Optional[str]:
            try:
                path = c4d.storage.LoadDialog(
                    title=title, flags=c4d.FILESELECT_SAVE,
                )
            except Exception:  # noqa: BLE001
                path = None
            if not path:
                return None
            if default_ext and not path.lower().endswith(default_ext.lower()):
                path += default_ext
            return path

        def _ask_save_dir(self, *, title: str) -> Optional[str]:
            try:
                path = c4d.storage.LoadDialog(
                    title=title, flags=c4d.FILESELECT_DIRECTORY,
                )
            except Exception:  # noqa: BLE001
                path = None
            return path or None

        def _build_anim_frame_range(self):
            from c4d_objects.timeline_keys import BakeRange
            try:
                start_f = int(self.GetInt32(_ID_BAKE_START_FRAME))
                end_f = int(self.GetInt32(_ID_BAKE_END_FRAME))
            except Exception:  # noqa: BLE001
                start_f, end_f = 0, 240
            try:
                fps = int(c4d.documents.GetActiveDocument().GetFps())
            except Exception:  # noqa: BLE001
                fps = 30
            try:
                return BakeRange(start_frame=start_f, end_frame=end_f, fps=fps)
            except ValueError as exc:
                self._append_log(f"Export: invalid frame range — {exc}")
                return None

        def _do_export_mission(self) -> None:
            from export import ExportSettings, FORMAT_MISSION_JSON, export_one
            mission = self._active_mission()
            if mission is None:
                self._append_log("Export: select a mission first.")
                return
            path = self._ask_save_path(title="Export Mission JSON")
            if not path:
                return
            res = export_one(
                FORMAT_MISSION_JSON, path, mission=mission,
                settings=ExportSettings(allow_overwrite=True),
            )
            self._append_log(res.render_text())

        def _do_export_route(self) -> None:
            from export import ExportSettings, FORMAT_ROUTE_JSON, export_one
            if not getattr(self, "_route", None) or len(self._route) == 0:
                self._append_log("Export: no live route to export.")
                return
            path = self._ask_save_path(title="Export Route JSON")
            if not path:
                return
            res = export_one(
                FORMAT_ROUTE_JSON, path, route=self._route,
                settings=ExportSettings(allow_overwrite=True),
            )
            self._append_log(res.render_text())

        def _do_export_camera_path(self) -> None:
            from export import (
                ExportSettings, FORMAT_CAMERA_PATH_JSON, export_one,
            )
            mission = self._active_mission()
            if mission is None:
                self._append_log("Export: select a mission first.")
                return
            path_obj, _ = self._build_path_for_active_mission()
            if path_obj is None or path_obj.is_empty():
                self._append_log("Export: no resolvable camera path.")
                return
            fr = self._build_anim_frame_range()
            if fr is None:
                return
            path = self._ask_save_path(title="Export Camera Path JSON")
            if not path:
                return
            res = export_one(
                FORMAT_CAMERA_PATH_JSON, path,
                mission=mission, camera_path=path_obj, frame_range=fr,
                settings=ExportSettings(
                    allow_overwrite=True, plugin_version="v2.3",
                ),
            )
            self._append_log(res.render_text())

        def _do_export_timeline_data(self) -> None:
            from animation import evaluate_animated_state
            from export import (
                ExportSettings, FORMAT_TIMELINE_KEYFRAMES_JSON, export_one,
            )
            mission = self._active_mission()
            if mission is None:
                self._append_log("Export: select a mission first.")
                return
            path_obj, _ = self._build_path_for_active_mission()
            if path_obj is None or path_obj.is_empty():
                self._append_log("Export: no resolvable camera path.")
                return
            fr = self._build_anim_frame_range()
            if fr is None:
                return
            timeline = evaluate_animated_state(
                mission, path_obj, frame_range=fr,
            )
            path = self._ask_save_path(title="Export Timeline Keyframes JSON")
            if not path:
                return
            res = export_one(
                FORMAT_TIMELINE_KEYFRAMES_JSON, path,
                keyframes=timeline.keyframes, frame_range=fr,
                settings=ExportSettings(allow_overwrite=True),
            )
            self._append_log(res.render_text())

        def _do_export_dataset_summary(self) -> None:
            from export import (
                ExportSettings, FORMAT_DATASET_SUMMARY_JSON, export_one,
                build_dataset_summary,
            )
            from core.state_manager import get_dataset_registry
            try:
                registry = get_dataset_registry()
            except Exception:  # noqa: BLE001
                registry = None
            summary = build_dataset_summary(
                registry=registry,
                science_layer_settings=self._science_layer_settings,
                plugin_version="v2.3",
            )
            path = self._ask_save_path(title="Export Dataset Summary JSON")
            if not path:
                return
            res = export_one(
                FORMAT_DATASET_SUMMARY_JSON, path, summary=summary,
                settings=ExportSettings(allow_overwrite=True),
            )
            self._append_log(res.render_text())

        def _do_export_package(self) -> None:
            from animation import evaluate_animated_state
            from export import (
                PackageBuildSettings, build_dataset_summary, export_package,
            )
            from core.state_manager import get_dataset_registry
            mgr = self._ensure_mission_manager()
            missions = mgr.list_all()
            if not missions:
                self._append_log("Export: no missions to package.")
                return
            root = self._ask_save_dir(title="Export Full Package — pick directory")
            if not root:
                return
            fr = self._build_anim_frame_range()
            # Build camera-path entries for each mission whose
            # path resolves.
            camera_paths_by_label = {}
            timeline_keyframes_by_label = {}
            for mission in missions:
                try:
                    from voyage.camera_path import build_camera_path
                    path_obj = build_camera_path(mission)
                    if path_obj.is_empty() or fr is None:
                        continue
                    camera_paths_by_label[mission.title or mission.mission_id] = (
                        mission, path_obj, fr,
                    )
                    tl = evaluate_animated_state(
                        mission, path_obj, frame_range=fr,
                    )
                    timeline_keyframes_by_label[
                        mission.title or mission.mission_id
                    ] = (tl.keyframes, fr)
                except Exception:  # noqa: BLE001
                    continue
            try:
                registry = get_dataset_registry()
            except Exception:  # noqa: BLE001
                registry = None
            summary = build_dataset_summary(
                registry=registry,
                science_layer_settings=self._science_layer_settings,
                plugin_version="v2.3",
                mission_references=[m.mission_id for m in missions],
            )
            rep = export_package(
                root,
                missions=missions,
                camera_paths_by_label=camera_paths_by_label,
                timeline_keyframes_by_label=timeline_keyframes_by_label,
                science_layer_settings=self._science_layer_settings,
                dataset_summary_data=summary,
                active_dataset_names=[
                    e.name for e in (registry.entries if registry else [])
                    if getattr(e, "enabled", False)
                ],
                settings=PackageBuildSettings(plugin_version="v2.3"),
            )
            self._append_log(rep.render_text())

        # --- v1.9 advanced-voyage helpers ---

        def _do_mission_new_from_template(self) -> None:
            """v1.9: build a new mission from the picked template
            and register it via the existing manager."""
            from voyage import get_template, list_templates
            mgr = self._ensure_mission_manager()
            try:
                idx = int(self.GetInt32(_ID_TEMPLATE_PICKER))
            except Exception:  # noqa: BLE001
                idx = 0
            templates = list_templates()
            if not (0 <= idx < len(templates)):
                self._append_log("Mission: invalid template index.")
                return
            descriptor = templates[idx]
            try:
                mission = descriptor.builder()
            except TypeError as exc:
                # selected_objects_tour requires uids; fall back to
                # an empty voyage if the dialog can't supply them.
                self._append_log(
                    f"Mission: template '{descriptor.name}' needs "
                    f"arguments ({exc}); created an empty voyage instead."
                )
                from voyage import empty_voyage
                mission = empty_voyage(title=f"From {descriptor.label}")
            mgr.create(mission)
            self._active_mission_id = mission.mission_id
            self._append_log(
                f"Mission: created '{mission.title}' from "
                f"template '{descriptor.name}' "
                f"({len(mission.waypoints)} waypoint(s))."
            )
            self._refresh_mission_panels()

        def _do_mission_duplicate(self) -> None:
            mission = self._active_mission()
            if mission is None:
                self._append_log("Mission: select a mission first.")
                return
            mgr = self._ensure_mission_manager()
            clone = mgr.duplicate(mission.mission_id)
            if clone is None:
                self._append_log("Mission: duplicate failed.")
                return
            self._active_mission_id = clone.mission_id
            self._append_log(
                f"Mission: duplicated → '{clone.title}'."
            )
            self._refresh_mission_panels()

        def _do_mission_analytics(self) -> None:
            from voyage import analyse_route
            mission = self._active_mission()
            if mission is None:
                self._append_log("Mission: select a mission first.")
                return
            report = analyse_route(mission)
            self._append_log(report.render_text())

        def _do_mission_export_markdown(self) -> None:
            from voyage import write_markdown
            mission = self._active_mission()
            if mission is None:
                self._append_log("Mission: select a mission first.")
                return
            try:
                path = c4d.storage.LoadDialog(
                    title="Export Mission Markdown",
                    flags=c4d.FILESELECT_SAVE,
                )
            except Exception:  # noqa: BLE001
                path = None
            if not path:
                self._append_log("Mission: Markdown export cancelled.")
                return
            ok = write_markdown(mission, path)
            self._append_log(
                f"Mission: wrote Markdown to {path}." if ok
                else f"Mission: Markdown write failed for {path}."
            )

        def _do_mission_export_csv(self) -> None:
            from voyage import write_csv
            mission = self._active_mission()
            if mission is None:
                self._append_log("Mission: select a mission first.")
                return
            try:
                path = c4d.storage.LoadDialog(
                    title="Export Mission Waypoints CSV",
                    flags=c4d.FILESELECT_SAVE,
                )
            except Exception:  # noqa: BLE001
                path = None
            if not path:
                self._append_log("Mission: CSV export cancelled.")
                return
            ok = write_csv(mission, path)
            self._append_log(
                f"Mission: wrote CSV to {path}." if ok
                else f"Mission: CSV write failed for {path}."
            )

        def _do_mission_search(self) -> None:
            """v1.9: filter the mission list by free-text query
            and re-render the panel verbatim. The dialog's list
            stays the live mission set; only the *displayed*
            text is filtered."""
            from ui.mission_panel import render_mission_list
            mgr = self._ensure_mission_manager()
            query = (self.GetString(_ID_MISSION_SEARCH_INPUT) or "").strip()
            results = mgr.search(query) if query else mgr.list_all()
            count = len(results)
            if count == 0:
                self._append_log(
                    f"Mission search '{query}': 0 matches."
                )
                self.SetString(
                    _ID_MISSIONS_LIST,
                    f"No missions matching '{query}'.",
                )
                return
            # Render a search-scoped subset.
            lines = [f"=== Missions matching '{query}' ({count}) ==="]
            for i, m in enumerate(results):
                line = (
                    f"  [{i}] {m.title}  "
                    f"({len(m.waypoints)} wp, "
                    f"{m.total_duration_seconds():.1f}s)"
                )
                if m.tags:
                    line += f"  [{', '.join(m.tags)}]"
                lines.append(line)
            self.SetString(_ID_MISSIONS_LIST, "\n".join(lines))
            self._append_log(f"Mission search '{query}': {count} match(es).")

        # --- v2.0 procedural-overlay helpers ---

        # Cached OverlaySettings the UI checkboxes write into.
        # Rebuilt on demand from project_state when the dialog
        # loads UNAV state (so a saved scene's overlay
        # visibility round-trips on reopen).
        _overlay_settings = None

        def _read_overlay_settings(self):
            """Build an ``OverlaySettings`` from the current
            checkbox state. The dialog uses this on Build and
            on every settings-change event (so the cached
            instance reflects the latest UI state)."""
            from procedural import OverlaySettings
            try:
                radius = float(self.GetFloat(_ID_OVL_RADIUS_PC))
            except Exception:  # noqa: BLE001
                radius = 100.0
            if radius <= 0:
                radius = 100.0
            try:
                settings = OverlaySettings(
                    show_grid=bool(self.GetBool(_ID_OVL_SHOW_GRID)),
                    show_galactic_plane=bool(self.GetBool(_ID_OVL_SHOW_GALACTIC)),
                    show_ecliptic_plane=bool(self.GetBool(_ID_OVL_SHOW_ECLIPTIC)),
                    show_distance_rings=bool(self.GetBool(_ID_OVL_SHOW_DISTANCE_RINGS)),
                    show_sector_cone=bool(self.GetBool(_ID_OVL_SHOW_SECTOR_CONE)),
                    show_route_corridor=bool(self.GetBool(_ID_OVL_SHOW_ROUTE_CORRIDOR)),
                    show_waypoint_labels=bool(self.GetBool(_ID_OVL_SHOW_LABELS)),
                    radius_pc=radius,
                )
            except (TypeError, ValueError):
                settings = OverlaySettings()
            self._overlay_settings = settings
            return settings

        def _do_overlays_settings_changed(self) -> None:
            """One of the overlay UI controls changed. Cache
            the new settings; do NOT rebuild — the artist
            clicks Build / Refresh explicitly."""
            self._read_overlay_settings()
            try:
                self.SetString(
                    _ID_OVL_STATUS,
                    "Overlays: settings changed — click Build / Refresh "
                    "to materialise.",
                )
            except Exception:  # noqa: BLE001
                pass

        def _do_overlays_build(self) -> None:
            """Build / refresh the procedural overlays. Reuses
            the existing ``UNAV_Overlays`` parent so re-clicks
            don't duplicate scene objects (idempotency
            guarantee from the c4d builder)."""
            from c4d_objects.overlays_builder import (
                apply_overlay_bundle,
            )
            from procedural import build_overlay_bundle

            settings = self._read_overlay_settings()
            if not settings.any_visible():
                self._append_log(
                    "Overlays: no overlay flag is on — nothing to build."
                )
                self.SetString(
                    _ID_OVL_STATUS,
                    "Overlays: nothing selected.",
                )
                return

            # Optional sector-cone inputs from the live navigator.
            sector_kwargs = {}
            try:
                from c4d_objects.navigation_null import (
                    find_navigator,
                )
                nav = find_navigator(c4d.documents.GetActiveDocument())
                if nav is not None and settings.show_sector_cone:
                    pos = nav.GetAbsPos()
                    sector_kwargs.update(
                        sector_origin_pc=(
                            float(pos.x), float(pos.y), float(pos.z),
                        ),
                        sector_forward=(1.0, 0.0, 0.0),
                        sector_cone_half_angle_deg=30.0,
                        sector_far_pc=settings.radius_pc,
                    )
            except Exception:  # noqa: BLE001
                pass

            # Optional route corridor inputs from the live route.
            route_pts = None
            label_pts = None
            if (settings.show_route_corridor or settings.show_waypoint_labels) \
                    and getattr(self, "_route", None) is not None:
                route_pts = []
                label_pts = []
                for wp in self._route:
                    if not wp.has_c4d_position():
                        continue
                    pos = (float(wp.x_c4d), float(wp.y_c4d), float(wp.z_c4d))
                    route_pts.append(pos)
                    label_pts.append((wp.display_label(), pos))

            bundle = build_overlay_bundle(
                settings,
                route_waypoints=route_pts,
                waypoint_labels=label_pts,
                **sector_kwargs,
            )
            written = apply_overlay_bundle(bundle)
            self._append_log(
                f"Overlays: built {written} scene object(s) "
                f"({len(bundle.polylines)} polyline(s), "
                f"{len(bundle.labels)} label(s))."
            )
            try:
                self.SetString(
                    _ID_OVL_STATUS,
                    f"Overlays: {written} scene object(s) live.",
                )
            except Exception:  # noqa: BLE001
                pass

        def _do_overlays_clear(self) -> None:
            from c4d_objects.overlays_builder import clear_overlays
            ok = clear_overlays()
            self._append_log(
                "Overlays: cleared." if ok
                else "Overlays: nothing to clear."
            )
            try:
                self.SetString(
                    _ID_OVL_STATUS,
                    "(overlays cleared)" if ok else "(overlays idle)",
                )
            except Exception:  # noqa: BLE001
                pass

        # --- v2.1 science-layer helpers ---

        # Cached ScienceLayerSettings the UI checkboxes write
        # into. Built on demand from the v2.1 defaults +
        # whatever the project state restored.
        _science_layer_settings = None

        def _read_science_layer_settings(self):
            """Build a ``ScienceLayerSettings`` from the
            current checkbox state."""
            from astro import (
                CatalogSourceRegionSettings,
                ConstellationBoundarySettings,
                DistanceShellSettings,
                MagnitudeShellSettings,
                MotionVectorSettings,
                ObjectDensityVolumeSettings,
                RedshiftShellSettings,
                ScienceLayerSettings,
                SolarSystemOrbitSettings,
            )
            settings = ScienceLayerSettings(
                distance_shells=DistanceShellSettings(
                    enabled=bool(self.GetBool(_ID_SCI_DISTANCE_SHELLS)),
                ),
                redshift_shells=RedshiftShellSettings(
                    enabled=bool(self.GetBool(_ID_SCI_REDSHIFT_SHELLS)),
                ),
                magnitude_shells=MagnitudeShellSettings(
                    enabled=bool(self.GetBool(_ID_SCI_MAGNITUDE_SHELLS)),
                ),
                motion_vectors=MotionVectorSettings(
                    enabled=bool(self.GetBool(_ID_SCI_MOTION_VECTORS)),
                ),
                catalog_source_regions=CatalogSourceRegionSettings(
                    enabled=bool(self.GetBool(_ID_SCI_SOURCE_REGIONS)),
                ),
                solar_system_orbits=SolarSystemOrbitSettings(
                    enabled=bool(self.GetBool(_ID_SCI_SOLAR_ORBITS)),
                ),
                constellation_boundaries=ConstellationBoundarySettings(
                    enabled=bool(self.GetBool(_ID_SCI_CONSTELLATION)),
                ),
                object_density_volume=ObjectDensityVolumeSettings(
                    enabled=bool(self.GetBool(_ID_SCI_DENSITY_VOLUME)),
                ),
            )
            self._science_layer_settings = settings
            return settings

        def _do_science_layers_settings_changed(self) -> None:
            self._read_science_layer_settings()
            try:
                self.SetString(
                    _ID_SCI_STATUS,
                    "Science Layers: settings changed — click "
                    "Build / Refresh to materialise.",
                )
            except Exception:  # noqa: BLE001
                pass

        def _do_science_layers_build(self) -> None:
            """Build / refresh the v2.1 science layers under
            ``UNAV_ScienceLayers``."""
            from astro import build_science_bundle, render_warnings
            from c4d_objects.overlays_builder import apply_science_bundle

            settings = self._read_science_layer_settings()
            if not settings.any_enabled():
                self._append_log(
                    "Science Layers: no layer is enabled — "
                    "nothing to build."
                )
                self.SetString(
                    _ID_SCI_STATUS,
                    "Science Layers: nothing selected.",
                )
                return

            # Pull rows from the active dataset registry.
            objects = []
            try:
                from core.state_manager import get_dataset_registry
                reg = get_dataset_registry()
                merge = reg.merge_active(on_error="record")
                objects = list(merge.objects)
            except Exception:  # noqa: BLE001
                self._append_log(
                    "Science Layers: could not load active "
                    "datasets; some layers will be empty."
                )

            bundle = build_science_bundle(settings, objects=objects)
            warnings_text = render_warnings(bundle)
            if warnings_text:
                self._append_log(warnings_text)
            written = apply_science_bundle(bundle)
            self._append_log(
                f"Science Layers: built {written} scene "
                f"object(s) ({bundle.total_polylines()} "
                f"polyline(s), {bundle.total_labels()} label(s))."
            )
            try:
                self.SetString(
                    _ID_SCI_STATUS,
                    f"Science Layers: {written} scene object(s) live.",
                )
            except Exception:  # noqa: BLE001
                pass

        def _do_science_layers_clear(self) -> None:
            from c4d_objects.overlays_builder import clear_science_layers
            ok = clear_science_layers()
            self._append_log(
                "Science Layers: cleared." if ok
                else "Science Layers: nothing to clear."
            )
            try:
                self.SetString(
                    _ID_SCI_STATUS,
                    "(science layers cleared)" if ok
                    else "(science layers idle)",
                )
            except Exception:  # noqa: BLE001
                pass

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
            # UI sizing fix: bring the diagnostics dialog
            # under the laptop-class budget. The inner
            # multi-line edit now declares ``inith=240`` so
            # the dialog is comfortable at 620×520; bumping
            # defaulth past that lets the panel grow but
            # never forces it. See docs/UI_LAYOUT_NOTES.md.
            opened = self._diagnostics_dialog.Open(
                dlgtype=c4d.DLG_TYPE_ASYNC,
                pluginid=PLUGIN_ID_DIAGNOSTICS_DIALOG,
                defaultw=620, defaulth=520,
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
