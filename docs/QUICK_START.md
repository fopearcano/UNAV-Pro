# UNAV Pro — Quick Start

Install + first-launch + minimal demo. Five minutes from
zero to a baked camera animation.

For the full install reference (per-OS plugin paths, symlink-
for-development, troubleshooting) see
[`INSTALL_C4D_2023_PLUS.md`](INSTALL_C4D_2023_PLUS.md). For
issues see
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

---

## 1. Install

1. Unzip ``unav_pro-2.4.0.zip`` into your Cinema 4D plugins
   folder:
   * **macOS:** ``~/Library/Preferences/Maxon/Maxon Cinema
     4D 2024_<HASH>/plugins/``
   * **Windows:** ``%APPDATA%\Maxon\Maxon Cinema 4D
     2024_<HASH>\plugins\``
   * **Linux:** ``~/.config/Maxon/Maxon Cinema 4D 2024_<HASH>/plugins/``

2. Restart Cinema 4D.

3. ``Extensions → Universal Navigator Pro``. The dialog
   pops with a status log saying:

   ```
   UNAV Pro v2.4.0 (Production QA & Packaging; requires C4D API ≥ 26000) ready.
   ```

If the menu entry doesn't appear, run the diagnostics
panel's **Run Health Check** and read the report.

---

## 2. First launch — verify the install

1. From the dialog, open the **Diagnostics** panel.
2. Click **Run Health Check**.

A clean install reports:

```
=== UNAV Health Check ===
Health: OK (8 probe(s)).

  [OK] version            UNAV Pro v2.4.0 (Production QA & Packaging; requires C4D API ≥ 26000)
  [OK] config_dir         writable at ~/.unav_pro
  [OK] cache_dir          writable at ~/.unav_pro/cache
  [OK] dataset_registry   ...
  [OK] sample_catalog     present (...) at .../samples/sample_catalog_100.jsonl
  [OK] db_module          sqlite3 ... available
  [OK] voyage             voyage package importable.
  [OK] export             export package importable.
```

If any probe is `[!!]` or `[ERR]` see
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

---

## 3. Load the bundled minimal demo

The release zip ships a tiny safe sample at
``samples/minimal_unav_demo/``. Use it for the first run
before downloading any real catalogs.

1. **Dataset Manager…** → **Add Dataset** → pick
   ``samples/minimal_unav_demo/catalog.jsonl``.
2. Click **Load Active Datasets**. The log says
   ``5 objects merged``.
3. **Create Navigation Null**.
4. **Sync Visible Sector**.

Five small `Onull` objects appear under
``UNAV_Starfield → UNAV_VisibleSector``.

---

## 4. Inspect a sample object

1. Click ``demo:5`` (the demo planet) in the Object
   Manager.
2. **Inspect Selected Object**.

The metadata panel renders the v1.3 nine-section view:

```
=== UNAV Object Inspector ===
Selection      : demo:5

--- Basic Identity ---
Class          : planet (confidence: high)
...
--- Plain-language Summary ---
...
```

---

## 5. Run the demo mission

1. **Missions** tab → **Import…** → pick
   ``samples/minimal_unav_demo/mission.json``.
2. Click **Preview Path**. A `UNAV_Mission_Preview` spline
   appears in the OM showing the camera curve.
3. Drag the **Scrub** slider (0..1000) to fly the camera
   through the path in real time.
4. Click **Bake to Timeline**. UNAV writes camera +
   navigator keyframes for frames 0..240 + drops UNAV
   timeline markers.
5. Hit Cinema 4D's play button. The camera flies the
   mission. Check Cinema 4D's timeline for the
   `UNAV:waypoint:*` and `UNAV:sync:*` markers.

---

## 6. Export an interchange package

1. **Export → Export Full Package…**
2. Pick a target directory.

UNAV writes:

```
UNAV_Export/
  manifest.json
  missions/UNAV_Demo_Mission.json
  camera_paths/UNAV_Demo_Mission.json
  timelines/UNAV_Demo_Mission.json
  summaries/dataset_summary.json
```

The package is self-describing — the manifest carries the
plugin version, the coordinate convention, and the units
block. Drop it into a Slack thread, an archive bucket, or
another DCC's import script and the metadata travels with
the data.

---

## 7. Next steps

* Real Gaia / SDSS / DESI / JPL catalogs:
  [`docs/V0_3_GAIA_DR3_WORKFLOW.md`](V0_3_GAIA_DR3_WORKFLOW.md)
  and friends.
* Time-aware missions: [`docs/V1_2_TIME_NAVIGATION.md`](V1_2_TIME_NAVIGATION.md).
* Templates + analytics:
  [`docs/V1_9_ADVANCED_VOYAGE_TOOLS.md`](V1_9_ADVANCED_VOYAGE_TOOLS.md).
* Procedural overlays:
  [`docs/V2_0_PROCEDURAL_AUTHORING_TOOLS.md`](V2_0_PROCEDURAL_AUTHORING_TOOLS.md).
* Astrophysical layers:
  [`docs/V2_1_ASTROPHYSICAL_OVERLAYS.md`](V2_1_ASTROPHYSICAL_OVERLAYS.md).
* Animation + timeline:
  [`docs/V2_2_ANIMATION_TIMELINE_INTEGRATION.md`](V2_2_ANIMATION_TIMELINE_INTEGRATION.md).
* Export pipelines:
  [`docs/V2_3_EXPORT_PIPELINES.md`](V2_3_EXPORT_PIPELINES.md).
* QA + release engineering (this milestone):
  [`docs/V2_4_RELEASE_PREP.md`](V2_4_RELEASE_PREP.md).
