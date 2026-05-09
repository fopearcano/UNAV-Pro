# UNAV Pro — Release Notes v2.4.0 ("Production QA & Packaging")

This is the **release-engineering milestone**. v2.4 turns the
v2.3 codebase into something an artist can install, sanity-
check, and uninstall cleanly. No new navigation or rendering
features — every change is reliability, packaging, and
documentation.

If you only read one section, read **§5 Quick install**.

---

## 1. Highlights

* **Version metadata.** New ``unav_pro/version.py``: single
  source of truth for the plugin version string. Surfaced in
  the dialog log, the export manifest, and the packaging
  script.
* **Health check.** New ``unav_pro/core/health_check.py``:
  pre-flight diagnostics that verify the plugin's paths,
  config / cache writability, dataset registry, sample data,
  and DB availability. Exposed in the diagnostics panel.
* **Packaging script.** New ``scripts/package_plugin.py``:
  builds a release zip excluding tests / cache / generated
  data / heavy catalogs, validating contents before writing.
* **Test runner.** New ``scripts/run_tests.py``: one entry
  point that walks every test category and prints a summary.
* **Minimal sample demo.** New ``samples/minimal_unav_demo/``:
  five-row catalog + tiny mission JSON + tiny route JSON,
  with a 30-second walkthrough README. Safe + small enough to
  ship in the release zip.
* **Install docs refresh.** ``INSTALL_C4D_2023_PLUS.md``,
  ``QUICK_START.md``, ``TROUBLESHOOTING.md`` — refreshed for
  v2.4 with the full dialog → sample → mission → bake →
  export flow.
* **Three new release docs.** ``V2_4_RELEASE_PREP.md``,
  ``PACKAGING.md``, ``QA_CHECKLIST.md`` — covering the
  release engineering, the package layout, and the QA
  ritual every release runs.

**No new features.** No rendering, no IPC, no external
renderer bridge. Every v1.x + v2.0–v2.3 surface is
unchanged.

---

## 2. What's new at a glance

| Surface | Change |
|---------|--------|
| ``unav_pro/version.py`` | New module: ``PLUGIN_VERSION``, ``VersionInfo``, ``parse_version``. |
| ``unav_pro/core/health_check.py`` | New module: ``run_health_check()`` returns a ``HealthReport``. |
| ``scripts/package_plugin.py`` | New: builds a deterministic release zip. |
| ``scripts/run_tests.py`` | New: one-script test runner. |
| ``dist/README.md`` | New: how to consume a release zip. |
| ``samples/minimal_unav_demo/`` | New: tiny catalog + mission + route + README. |
| ``CHANGELOG.md`` | Updated with the v2.4 entry. |
| ``RELEASE_NOTES_v2.4.md`` | This file. |
| Tests | New ``test_v24_*`` files cover version, health check, packaging, sample demo. |

---

## 3. Acceptance criteria

* [x] The plugin packages into a deterministic zip.
* [x] The package excludes heavy / generated / cache files.
* [x] Install docs are step-by-step (folder location → first
  launch → sample → mission → bake → export).
* [x] Health check works and is reachable from the
  diagnostics panel.
* [x] Sample demo loads cleanly without external data.
* [x] Tests run through one script.
* [x] Release notes exist (this file).
* [x] No render-engine assumptions; no RelativityRender
  bridge; no IPC.

---

## 4. Compatibility

* Cinema 4D 2023 / 2024 / 2025 (API ≥ 26000). The plugin
  refuses to register on older hosts and logs the reason
  cleanly.
* Stdlib-only at runtime. No ``numpy``, no ``astropy``, no
  ``astroquery``, no ``pandas``.
* Saved state from v1.x and v2.0–v2.3 round-trips through
  v2.4 byte-identical.
* Mission JSON, route JSON, package manifest, camera-path
  exchange JSON, dataset summary JSON — all v2.x schemas
  unchanged.

---

## 5. Quick install

```text
1.  Unzip the release into your Cinema 4D plugins folder:
       Maxon → Cinema 4D 2024 → plugins/unav_pro/
2.  Restart Cinema 4D.
3.  Extensions → Universal Navigator Pro.
4.  Diagnostics → Run Health Check (verify all green).
5.  Dataset Manager → Add Dataset → samples/minimal_unav_demo/catalog.jsonl.
6.  Click Sync Visible Sector. The five sample stars appear.
7.  Missions tab → Import → samples/minimal_unav_demo/mission.json.
8.  Click ▶ Play to scrub the mission. Click Bake to Timeline.
9.  Export → Export Full Package… for an interchange-ready zip.
```

Detailed walkthroughs in
[`docs/QUICK_START.md`](docs/QUICK_START.md) and
[`docs/INSTALL_C4D_2023_PLUS.md`](docs/INSTALL_C4D_2023_PLUS.md).
Trouble?
[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

---

## 6. Tests

```bash
python scripts/run_tests.py
# → runs every test_*.py under unav_pro/tests/, prints a summary
```

The v2.4 release passes 1700+ Python tests across the
entire codebase. The test runner reports the count + the
first failing test (if any). Expected runtime: under five
seconds on modern hardware.

---

## 7. Known limitations (unchanged from v2.3)

See
[`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md). v2.4
adds zero new limitations — every behaviour the v2.3 codebase
exposed is preserved.

---

## 8. Upgrade notes

Upgrading from v2.x:

1. Close Cinema 4D.
2. Replace the existing ``plugins/unav_pro/`` folder with
   the v2.4 contents.
3. Reopen Cinema 4D. Saved state at ``~/.unav_pro/`` loads
   unchanged.

Downgrading: copy the previous release zip back over the
``plugins/unav_pro/`` folder. State on disk is forward- and
backward-compatible across the v2.x range.

---

## 9. Credits

UNAV Pro is built by Cinema 4D artists for Cinema 4D
artists. The v2.4 release engineering was coordinated under
the v2.4-production-qa-packaging milestone tag.
