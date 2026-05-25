# UNAV Pro — UI Experience Audit

A snapshot of the dialog UX as of the v3.9.x UI-experience pass, the
problems found, and what this pass changed vs. left as documented
target state.

> Scope note: this was a **UX/UI pass**, not a feature pass. No core
> capabilities were added. The Cinema 4D `GeDialog` layout can only be
> visually verified inside the host, so changes that can't be unit- or
> source-tested were made conservatively and the full target IA is
> captured here + in `UI_TAB_STRUCTURE.md` as the build spec.

## Method

- Read `ui/main_dialog.py` (≈3.2k lines), `ui/main_command.py`, and
  every panel module (`dataset_manager`, `diagnostics_panel`,
  `tools_panel`, `search_panel`, `route_panel`, `mission_panel`,
  `bookmarks_panel`, `metadata_panel`, `cinematic_panel`,
  `presentation_panel`, `exhibition_panel`, `advanced_query_panel`).
- Inspected window sizing, scroll behaviour, tab structure, button
  naming, status/log formatting, and destructive-action handling.

## Current structure (before this pass)

The **main dialog** is a single vertical stack wrapped in a
`ScrollGroupBegin` (added in *fix-ui-window-vertical-scaling*):

1. Workflow hint strip
2. Display (color mode, size, brightness)
3. Safety (cap + override)
4. Visible Sector (sync + auto-sync + debug cone)
5. Render Mode
6. Native Point Viewer (experimental)
7. Time Navigator
8. Actions grid (14 buttons incl. Dataset Manager…, External Tools…,
   Diagnostics…)
9. Status Log
10. Route Planner
11. Metadata Inspector
12. A `TabGroup` with **5** tabs: Search, Bookmarks, Navigation,
    Missions, Overlays

Several workflows live in **separate async dialogs**: Dataset Manager,
Diagnostics, External Tools.

## Findings

| # | Area | Finding |
| --- | --- | --- |
| F1 | Window size | Opened at 720×640; spec target ~900×700. |
| F2 | Scroll | Vertical scroll already present (good); kept. |
| F3 | Tab order | Tabs were Search→Bookmarks→Navigation→Missions→Overlays, not workflow-ordered. Navigator/Search are the daily-driver tabs and should lead. |
| F4 | IA breadth | The intended 10-section IA (Home/Dataset/Navigator/Search/Voyage/Animation/Overlays/Tools/Diagnostics/Settings) wasn't expressed anywhere as a single source of truth. |
| F5 | Missions tab overload | The "Missions" tab crams route, mission, waypoints, playback, baking, animation, export, templates, and analytics into one very tall tab. |
| F6 | No Home/dashboard | No at-a-glance view of version / workspace / datasets / navigator / sector / mission / health. |
| F7 | Status formatting | Status strings were ad-hoc per panel; no shared OK/WARN/ERROR/MISSING vocabulary. |
| F8 | Log readability | Solid since *fix-log-newline-formatting* (Python-side `LogBuffer`); reused here. |
| F9 | Destructive actions | Clear Scene, Reset Preferences, Clear Route, Clear Log, Delete Mission, Clear Keyframes, Remove Dataset ran with **no confirmation**. |
| F10 | Tools clarity | External tools are a separate window (good) but should be unambiguously labelled as *external Python*, not C4D-runtime. |

## What this pass changed (live)

- **F1** — default window size → **900×700** (`main_command.py`).
- **F3** — in-dialog tab strip reordered to **Navigator → Search →
  Bookmarks → Missions → Overlays** (widget ids unchanged).
- **F7** — shared status vocabulary + formatters in
  `ui/ui_helpers.py` (`[OK]`/`[WARN]`/`[ERROR]`/`[MISSING]`/
  `[DISABLED]`).
- **F9** — destructive actions now confirm via
  `ui/confirmations.py` (`confirm_destructive(...)`) wired into Clear
  Scene, Clear Route, Reset Preferences, Clear Log, Delete Mission,
  Clear Keyframes (main dialog) and Remove Dataset (Dataset Manager).
- **F10** — External Tools panel already marks tools as external
  (`integrated-external-tools-ui`); reaffirmed in docs + the tab
  summary.

## What this pass added as foundation (tested)

- `ui/tab_registry.py` — the canonical, workflow-ordered 10-tab IA as
  data (order + uniqueness validated by tests). This is the build spec
  for **F4/F5** so a future layout refactor builds the strip from one
  list.
- `ui/ui_helpers.py` — pure formatters + c4d widget builders
  (`add_section_title`, `add_status_label`, `add_warning_box`,
  `add_button_row`, `add_path_selector`, `add_compact_separator`,
  `append_log_line`).
- `ui/home_dashboard.py` — pure `build_dashboard_text(DashboardState)`
  composing the **F6** Home dashboard from injected state.
- `ui/confirmations.py` — the destructive-action registry.

## Deliberately deferred

A full physical re-layout of the live `GeDialog` into ten discrete tabs
(moving the flat groups into per-tab builders) was **not** done blind in
this pass — it can't be visually verified outside Cinema 4D and risks
the 3.1k-line layout + the test suite. It is fully specified in
`UI_TAB_STRUCTURE.md`; the registry + helpers + dashboard make that
refactor mechanical when it's done in-host with visual QA.

## Acceptance check

| Criterion | Status |
| --- | --- |
| UI compact + resizable | [OK] 900×700 default, resizable, scrolls |
| Long panels scroll | [OK] outer vertical ScrollGroup |
| Tabs follow workflow | [OK] live reorder + canonical registry |
| Core actions easy to find | [OK] Actions grid + Home dashboard model + primary actions list |
| Logs readable | [OK] `LogBuffer`, one entry per line |
| External tools clear | [OK] separate window, labelled external Python |
| Destructive actions guarded | [OK] `confirm_destructive` on all listed actions |
| No new core features | [OK] formatting / layout / guards only |
