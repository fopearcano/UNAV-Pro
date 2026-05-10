# UNAV Pro — QA Checklist

The release-engineer's pre-publish ritual. Every release
runs through this checklist; every item is a step a
maintainer will ask for first when triaging a bug.

For the v2.4 release-engineering overview see
[`V2_4_RELEASE_PREP.md`](V2_4_RELEASE_PREP.md). For the
packaging mechanics see [`PACKAGING.md`](PACKAGING.md). For
issues that come up during QA see
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

---

## 1. Source repo

* [ ] Working tree is clean (`git status`).
* [ ] On the release branch (`claude/c4d-navigator-plugin-...`
  or wherever the milestone is being prepared).
* [ ] Last commit is the milestone commit (`v2.4-...`).
* [ ] `unav_pro/version.py::PLUGIN_VERSION` matches the
  release tag.
* [ ] `CHANGELOG.md` has a `[<version>]` heading dated to
  today.
* [ ] `RELEASE_NOTES_v<version>.md` exists.

## 2. Test suite

* [ ] `python scripts/run_tests.py --quiet` passes.
* [ ] No test marked as `xfail` was newly skipped.
* [ ] Every category reports a non-zero file count
  (state, animation, voyage, knowledge, overlays,
  science, export, v18, v19, release).
* [ ] On a fresh `~/.unav_pro/` (rename the existing one):
  `python scripts/run_tests.py` still passes — the suite
  must not depend on prior state.

## 3. Health check

* [ ] On a fresh install:
  `python -c "from unav_pro.core.health_check import run_health_check; print(run_health_check().render())"`
* [ ] Every probe is `[OK]` or `[..]` (info). No
  `[!!]` warnings.
* [ ] `version` probe reports the new release version.
* [ ] `sample_catalog` probe finds
  `data/samples/sample_catalog_100.jsonl`.

## 4. Packaging

* [ ] `python scripts/package_plugin.py` succeeds.
* [ ] Output zip name is `dist/unav_pro-<version>.zip`.
* [ ] Zip size is plausible (a few hundred KB to a few
  MB). Anything over 10 MB → investigate.
* [ ] Run again with `--keep-staging` and walk the
  staging tree:
  * No `__pycache__`, `.pytest_cache`, `.git`, `.venv`,
    `build`, `cache`, `data/catalogs`, `native`, `tools`,
    `tests`.
  * No `.pyc`, `.pyo`, `.log`, `.coverage`, `.db`, `.bin`.
  * No hidden files (anything starting with `.`).
  * Every file in `REQUIRED_FILES` is present.
  * `samples/minimal_unav_demo/` has all four files
    (`catalog.jsonl`, `mission.json`, `route.json`,
    `README.md`).

## 5. Manual end-to-end install test

The release-engineer follows this on a *fresh* machine
(or on a Cinema 4D install with no prior UNAV config) to
prove the published zip works for an artist who has never
run UNAV before. Each step has an expected observable
outcome — if any step deviates, file a release blocker.

1. **Install from package.**
   * [ ] Download the release zip from the GitHub release
     page (not the local `dist/` build).
   * [ ] Unzip it into the Cinema 4D plugins folder
     (`~/Library/Preferences/Maxon/.../plugins/` on macOS;
     `%APPDATA%\Maxon\...\plugins\` on Windows).
   * [ ] Restart Cinema 4D.
   * [ ] `Extensions → Universal Navigator Pro` is listed
     in the menu.
   * [ ] Opening the dialog shows the new release version
     in the status log.

2. **Load sample.**
   * [ ] `Dataset Manager → Add Dataset` accepts
     `samples/minimal_unav_demo/catalog.jsonl`.
   * [ ] The dataset appears in the active list with five
     rows.
   * [ ] No errors in the status log.

3. **Sync visible sector.**
   * [ ] Click `Sync Visible Sector`.
   * [ ] `UNAV_Starfield → UNAV_VisibleSector` appears in
     the Object Manager with five children.
   * [ ] The diff summary in the status log reports
     `added=5, updated=0, removed=0`.

4. **Inspect metadata.**
   * [ ] Select `demo:5` in the OM.
   * [ ] Click `Inspect Selected Object`.
   * [ ] The metadata panel renders the v1.3 nine-section
     view (identity, position, motion, photometry,
     classification, derived, summary, glossary,
     interpretation).
   * [ ] Numeric fields display with units; no `None` /
     `null` cells.

5. **Create mission.**
   * [ ] `Missions → Import` loads
     `samples/minimal_unav_demo/mission.json`.
   * [ ] Five waypoints appear in the Mission panel.
   * [ ] `Preview Path` drops `UNAV_Mission_Preview` (a
     Catmull-Rom spline) under the scene root.
   * [ ] `▶ Play` scrubs the camera through the path
     without errors.

6. **Bake timeline.**
   * [ ] Click `Bake to Timeline`.
   * [ ] The bake summary reports `frames > 0,
     waypoints=5, markers >= 5`.
   * [ ] The Timeline shows camera + navigator
     keyframes (PSR + nav fields).
   * [ ] `UNAV:waypoint:*`, `UNAV:sync:*` markers exist
     at the expected frames.
   * [ ] Scrubbing the timeline animates the camera
     smoothly.

7. **Export package.**
   * [ ] `Export → Export Full Package…` to a fresh
     directory.
   * [ ] The output directory contains a `manifest.json`
     plus eight per-asset files (mission, route,
     waypoints CSV, route Markdown, camera path,
     timeline keyframes, science layer, dataset
     summary).
   * [ ] `manifest.json` validates against the
     `EXPORT_PACKAGE_FORMAT.md` schema.
   * [ ] No partial / `.tmp` files left behind.

8. **Reload plugin.**
   * [ ] Close Cinema 4D.
   * [ ] Reopen the same scene.
   * [ ] `Load UNAV State` restores navigator, datasets,
     missions, overlays, and science layers.
   * [ ] The previously-baked timeline keyframes and
     `UNAV:` markers are still present.
   * [ ] Re-running `▶ Play` produces the same camera
     motion as before reload.

If every step is green: the release is artist-ready.
If any step fails: block the release and triage via
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

## 6. Cinema 4D smoke test

* [ ] On a clean Cinema 4D 2023+ install (no prior UNAV
  config), unzip the release into the plugins folder.
* [ ] Restart Cinema 4D.
* [ ] `Extensions → Universal Navigator Pro` opens the
  dialog.
* [ ] Status log shows the new version's `display_line`.
* [ ] `Diagnostics → Run Health Check` reports OK.
* [ ] `Dataset Manager → Add Dataset` accepts the
  bundled demo catalog.
* [ ] `Sync Visible Sector` produces the five demo
  objects under `UNAV_Starfield → UNAV_VisibleSector`.
* [ ] `Inspect Selected Object` on `demo:5` renders the
  v1.3 nine-section metadata view.
* [ ] `Missions → Import` accepts `mission.json`.
* [ ] `Preview Path` drops a `UNAV_Mission_Preview` spline
  into the OM.
* [ ] `▶ Play` scrubs the camera through the path.
* [ ] `Bake to Timeline` writes camera + navigator
  keyframes + drops `UNAV:waypoint:*` / `UNAV:sync:*`
  markers.
* [ ] `Export → Export Full Package…` writes a
  `UNAV_Export/` directory with the manifest +
  per-asset files.

## 7. Backwards compatibility

* [ ] Open a Cinema 4D scene saved with the previous
  release version. Verify:
  * `Load UNAV State` restores navigator + route + datasets
    + overlays + science layers + missions cleanly.
  * No "schema version unrecognised" warnings.
  * Re-saving the state produces the same JSON shape.

## 8. Docs

* [ ] `README.md` mentions the new version.
* [ ] `RELEASE_NOTES_v<version>.md` is included in the
  release zip.
* [ ] `docs/INSTALL_C4D_2023_PLUS.md`,
  `docs/QUICK_START.md`, `docs/TROUBLESHOOTING.md` are
  current for the new version.
* [ ] All cross-references in the new release-notes
  resolve to existing docs.

## 9. Publish

* [ ] Tag the commit (`git tag v<version>`).
* [ ] Push the tag (`git push origin v<version>`).
* [ ] Upload the release zip to the GitHub release page.
* [ ] Paste the contents of `RELEASE_NOTES_v<version>.md`
  into the GitHub release description.

## 10. Post-publish

* [ ] Verify the GitHub release page renders the release
  notes correctly.
* [ ] Re-run the Cinema 4D smoke test against the
  *uploaded* zip (download → unzip → Cinema 4D →
  health check). Catches "I forgot a file in the
  zip" mistakes.
* [ ] Bump `PLUGIN_VERSION` to the next development
  version (`<next>-dev`).

---

## Why so many steps?

Each item caught a real bug at least once during the
v0.1–v2.4 release cycles. The checklist is a stack of
"never again" tripwires. Skipping a step rarely fails on
that release; it usually fails *next* release when the
combination is fragile.

If a step has been green for ten consecutive releases,
that's evidence it's solid — not evidence it can be
retired. Retire steps when the underlying surface is
removed, not when the tests get boring.
