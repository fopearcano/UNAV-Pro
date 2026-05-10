# UNAV Pro — v3.4 Internal Beta Checklist

The release-engineer's pre-beta ritual. Every line in
this document is a test that has caught at least one
real bug across v0.1 → v3.3. Run through it on a fresh
machine before tagging an internal beta.

For the v2.4 production-QA checklist see
[`QA_CHECKLIST.md`](QA_CHECKLIST.md). This document is
the **internal beta** companion: the v2.4 checklist
covers *the release pipeline*; this one covers *the
artist's first hour with the plugin*.

---

## 1. Fresh install

* [ ] Download the v3.4 release zip from the GitHub
  release page (not the local `dist/` build).
* [ ] On a Cinema 4D 2023+ install with **no prior
  UNAV config**, unzip the package into the plugins
  folder.
* [ ] Restart Cinema 4D.
* [ ] `Extensions → Universal Navigator Pro` opens
  the dialog.
* [ ] The status log's first line shows
  `UNAV Pro v3.4.0 (Internal Beta Hardening; …)`.
* [ ] No traceback / log spam during plugin import.

## 2. Sample project load

* [ ] `Project → Open Workspace…` accepts
  `samples/internal_beta_demo/` (the v3.4 bundled
  sample).
* [ ] Workspace summary panel shows:
  *2 datasets enabled*, *1 mission*, *1 route*,
  *1 presentation*, *1 note*.
* [ ] No "missing path" warnings.

## 3. Gaia sample import

* [ ] `Dataset Manager → Add Dataset` accepts
  `samples/internal_beta_demo/datasets/gaia_demo.jsonl`.
* [ ] Dataset stats panel reports 5 rows.
* [ ] `Build Index` runs without error; an
  `index.json` appears next to the dataset.

## 4. JPL sample import

* [ ] `Dataset Manager → Add Dataset` accepts
  `samples/internal_beta_demo/datasets/jpl_demo.jsonl`.
* [ ] Dataset stats panel reports 3 rows
  (Mercury, Earth, Mars).
* [ ] `metadata_json["epoch"]` is populated for
  every JPL row.

## 5. Create navigator

* [ ] `Navigator → Create Navigation Null` adds
  `UNAV_Project / UNAV_Navigation / UNAV_Navigator`
  to the scene.
* [ ] Default `cone_angle_deg = 30`,
  `far_clip_parsec = 500.0`,
  `max_visible_objects = 10000`.

## 6. Sync visible sector

* [ ] `Sync Visible Sector` produces
  `UNAV_Project / UNAV_VisibleSector` with the
  expected children.
* [ ] Status log shows `+N added, =M kept,
  -K removed`.
* [ ] Status log shows `mode=…` (the active
  render-backend token).
* [ ] Diagnostics panel's "Cone cache" line
  reports `entries: 1/16`.

## 7. Inspect metadata

* [ ] Select a starfield child. `Inspect Selected
  Object` renders the v1.3 nine-section view.
* [ ] **v3.2:** the inspector also renders a
  *Provenance* block (catalog source / connector /
  units / known limitations) and a
  *Data integrity findings* block when the row
  has any issues.

## 8. Create mission

* [ ] `Missions → Import` accepts
  `samples/internal_beta_demo/missions/demo_tour.json`.
* [ ] Mission panel shows 3 waypoints.
* [ ] `Preview Path` drops a
  `UNAV_Mission_Preview` spline.
* [ ] `▶ Play` scrubs the camera through the path.

## 9. Bake timeline

* [ ] `Bake to Timeline` writes camera + navigator
  keyframes.
* [ ] Timeline shows `UNAV:waypoint:*` and
  `UNAV:sync:*` markers.
* [ ] Scrubbing the timeline animates the camera
  smoothly.

## 10. Create overlays

* [ ] Toggle `show_grid`, `show_galactic_plane`,
  `show_distance_rings` in the *Overlays* panel.
* [ ] `Build / Refresh` materialises geometry under
  `UNAV_Project / UNAV_Overlays`.
* [ ] Toggling a flag off and rebuilding removes
  only the affected overlay (v3.0 partial-rebuild).

## 11. Export package

* [ ] `Export → Export Full Package…` writes a
  `UNAV_Export/` directory inside
  `<workspace>/exports/<timestamp>/`.
* [ ] `manifest.json` contains:
  * `manifest_version`, `plugin_version=3.4.0`,
    `coordinate_convention`,
  * **v3.2:** `provenance_summary`,
    `audit_summary`, `coordinate_conventions`,
    `known_limitations`,
  * `included_assets` listing every emitted file.

## 12. Create presentation

* [ ] `Presentation → New Presentation` from the
  panel.
* [ ] Add 2–3 steps; assign waypoint refs from
  the demo mission.
* [ ] `Start Presentation` advances to step 0; the
  status panel shows
  *Presentation 'X' — step 1/3*.
* [ ] `Next Step` / `Previous Step` traverse
  cleanly.
* [ ] `Pause` / `Resume` flip the status to/from
  `paused`.
* [ ] `End Presentation` returns to idle.

## 13. Reload C4D scene

* [ ] Save the scene; close Cinema 4D.
* [ ] Reopen the same scene.
* [ ] `Load UNAV State` restores datasets +
  navigator + missions + overlays + presentations.
* [ ] No "schema version unrecognised" warnings.
* [ ] Re-running `▶ Play` produces the same camera
  motion.

## 14. Reopen workspace

* [ ] After the reload, `Project → Reopen
  Workspace` works without error.
* [ ] `Project Summary` reports the same counts
  as before the reload.

## 15. Diagnostics + reset tools

* [ ] `Diagnostics → Run Health Check`:
  * v3.4: 14 probes total. All `[OK]` or `[..]`
    info; no `[ERR]`.
  * `version`, `python_runtime`, `c4d_host`
    populated.
  * `workspace`, `active_mission`,
    `visible_sector`, `presentation` populated.
* [ ] `Diagnostics → Reset` group:
  * **Reset UI State** — selection clears
    cleanly.
  * **Reset Workspace State** — workspace
    pointer clears; on-disk tree intact.
  * **Clear Generated UNAV Objects** — only
    legacy / scratch UNAV roots removed; the
    `UNAV_Project` root preserved.
  * **Clear Cache References** — chunk-reuse
    cache + timing log + metadata-lookup default
    drop; status log shows the count.
  * **Rebuild Scene Hierarchy** — recreates
    canonical children.

## 16. No regressions

* [ ] Run the full automated suite:
  `python scripts/run_tests.py --quiet`.
* [ ] Every category reports a non-zero file
  count: state, animation, voyage, knowledge,
  overlays, science, export, v18, v19, release,
  workflow, scalability, workspace, integrity,
  presentation, beta.
* [ ] Total: **2200+ tests pass**.

## 17. Sign-off

* [ ] Tester's name + date in the release
  tracker.
* [ ] One screenshot of the diagnostics panel
  attached.
* [ ] Any `[!!]` warnings or unexpected behaviour
  filed as issues.

If every step is green: tag the internal beta. If any
step fails: file a release blocker and triage via
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).
