# UNAV Pro — User Workflow Map

How the tabs map to the things people actually do. Each flow lists the
tab(s) involved and the order of operations. Tab order itself is in
`UI_TAB_STRUCTURE.md`.

## First run

1. **Home** — read the dashboard (everything `[MISSING]` at first).
2. **Home → Open Sample Demo** — loads the bundled minimal catalog so
   you have something to look at.
3. **Home → Create Navigator**, then **Sync Visible Sector**.
4. **Home → Run Health Check** — confirms the install is sound.

## Bring in real data

1. **Tools** — set the **external Python** (Python Environment
   section), then run a fetch (Gaia / JPL / SDSS / DESI). These run
   *outside* Cinema 4D; the panel streams their log.
   - or do it from the command line — see
     `docs/DATA_FETCH_UI_WORKFLOW.md`.
2. On success the catalog is offered to the **Dataset** registry (and
   an index is attached if the fetch built one).
3. **Dataset** — confirm it's `[OK]` / indexed / enabled, **Load Active
   Datasets**.

## Explore

1. **Navigator** — create/select the navigator, set the view cone,
   **Sync Visible Sector**.
2. **Search** — find an object; from the results: **Focus**,
   **Bookmark**, **Add to Route**, or **Inspect**.

## Plan a voyage

1. **Voyage** — capture **Bookmarks**, assemble a **Route**, build a
   **Mission** from waypoints.
2. Review **Analytics** (leg distances, totals).
3. Preview the route spline.

## Animate

1. **Animation** — **Preview Path**, set the **frame range**.
2. **Bake Mission to Timeline**.
3. **Add Timeline Markers**.
4. **Clear UNAV Keyframes** if you need to start over *(confirms
   first)*.

## Present / exhibit

1. **Overlays** — toggle navigation overlays, science layers, and
   presentation labels (kept compact).
2. (Exhibition / guided-tour chaptering lives in the presentation
   surfaces — see `docs/V3_8_EXHIBITION_WORKFLOWS.md`.)

## Diagnose / report

1. **Diagnostics** — **Run Health Check**, read the **Logs** (one entry
   per line), **Copy** them, or build an **Issue Report**.
2. **Reset tools** if you need a clean slate *(confirms first)*.

## Configure

1. **Settings** — workspace + cache paths, default limits, the external
   Python executable, UI preferences, safety limits.

## Destructive actions (always confirm)

Clear Scene • Clear Generated Objects • Reset Workspace • Reset
Preferences • Delete Mission • Remove Dataset • Clear Route • Clear UNAV
Keyframes • Clear Cache References • Clear Log.

See `ui/confirmations.py` for the registry and `UI_EXPERIENCE.md` for
how to guard a new one.

## Where each flow lives in code

| Flow | Primary module(s) |
| --- | --- |
| Dashboard | `ui/home_dashboard.py` |
| Dataset | `ui/dataset_manager.py`, `core/dataset_registry.py` |
| Navigator / sector | `ui/main_dialog.py`, `core/navigation_state.py` |
| Search | `ui/search_panel.py`, `ui/advanced_query_panel.py` |
| Voyage | `ui/route_panel.py`, `ui/mission_panel.py`, `ui/bookmarks_panel.py` |
| Animation | `ui/main_dialog.py` (missions/animation rows), `animation/` |
| Overlays | `ui/main_dialog.py` overlays tab, `core/` overlay builders |
| Tools | `ui/tools_panel.py`, `tools/` scripts |
| Diagnostics | `ui/diagnostics_panel.py`, `core/logger.py`, `core/log_format.py` |
| Settings | `core/config.py` |
