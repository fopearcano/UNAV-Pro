# UNAV Pro — Artist Quickstart

Ten minutes from a fresh install to a baked, exportable
camera mission. Read this once. Skim later.

For the full reference, see
[`USER_MANUAL.md`](USER_MANUAL.md). For the technical-
director / data-pipeline view, see
[`TD_GUIDE.md`](TD_GUIDE.md). When something goes wrong,
see [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

---

## 1. Install the plugin (1 minute)

1. Unzip `unav_pro-<version>.zip` into your Cinema 4D
   plugins folder:
   * **macOS:** `~/Library/Preferences/Maxon/Maxon Cinema
     4D 2024_<HASH>/plugins/`
   * **Windows:** `%APPDATA%\Maxon\Maxon Cinema 4D
     2024_<HASH>\plugins\`
2. Restart Cinema 4D.
3. **Extensions → Universal Navigator Pro**.

You should see a status line in the dialog log:
`UNAV Pro v<version> ready — …`.

---

## 2. Verify the install (30 seconds)

In the dialog: **Diagnostics → Run Health Check**.

Look for `Health: OK (8 probe(s)).` in the panel. Every
probe should be `[OK]` or `[..]` (info). Warnings are
acceptable; errors mean the install is broken — see
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

---

## 3. Load the bundled minimal demo (30 seconds)

The release zip ships a tiny safe sample at
`samples/minimal_unav_demo/`. Use it for the first run.

1. **Dataset Manager…** → **Add Dataset** → pick
   `samples/minimal_unav_demo/catalog.jsonl`.
2. **Load Active Datasets**.

Dialog log: `5 objects merged`.

---

## 4. Create the navigator (15 seconds)

1. Click **Create Navigation Null**.
2. Click **Sync Visible Sector**.

Five small null objects appear in the Object Manager under
`UNAV_Starfield → UNAV_VisibleSector`. They are the demo
catalog's three stars, one galaxy, and one demo planet.

---

## 5. Search for an object (30 seconds)

The **Search** tab lets you find any object by name / uid /
source.

1. Type `demo` into the **Find** field.
2. Click **Search**.
3. The panel lists the five demo objects. Pick #0 selects
   the first hit.
4. Click **Focus** to snap the navigator to the picked
   object's position.

---

## 6. Build a route (1 minute)

1. Pick a UNAV object in the Object Manager.
2. **Add Selected Object as Waypoint**.
3. Repeat for two or three more objects.
4. Click **Build Route Spline**. UNAV draws a Cinema 4D
   spline through the waypoints.

---

## 7. Create / load a mission (1 minute)

The fastest path is to import the bundled demo mission:

1. **Missions** tab → **Import…** → pick
   `samples/minimal_unav_demo/mission.json`.
2. Dialog log:
   `Mission: imported 'UNAV Demo Mission'`.

Or build one from scratch:

1. **Missions → New Mission** (type a title first).
2. Pick a UNAV object in the Object Manager.
3. **Add Selected Object as Waypoint**.
4. Repeat for as many stops as you want.
5. (Optional) **New From Template** to start from
   `solar_system_tour`, `nearest_stars_tour`,
   `redshift_tour`, or `empty_voyage`.

---

## 8. Preview the camera path (1 minute)

1. **Preview Path**. UNAV drops a `UNAV_Mission_Preview`
   spline into the OM showing the camera curve.
2. Drag the **Scrub** slider (0..1000) to fly the camera
   through the path live. The status line shows the
   current frame + elapsed seconds.
3. Use ▶ Play / ❚❚ Pause / ◼ Stop / |◀ Start / End ▶| /
   ◀◀ Prev / Next Wp ▶▶ for transport.

The Interp dropdown switches between `smooth` (Catmull-
Rom; default) and `linear` (straight-line per segment).

---

## 9. Bake to the timeline (30 seconds)

1. Set the **Start frame** / **End frame** range
   (defaults: 0 / 240).
2. Optional: set **FOV (deg)**.
3. Click **Bake to Timeline**.

UNAV writes camera + navigator keyframes for every frame
in the range and drops UNAV-tagged timeline markers
(`UNAV:waypoint:*` / `UNAV:epoch:*` / `UNAV:sync:*`).
Cinema 4D's play button now plays the cinematic.

The bake never triggers a visible-sector sync. The sync
markers are *requests* — click **Sync Visible Sector at
Frame** at any marker to refresh the catalog content.

---

## 10. Export an interchange package (1 minute)

1. **Missions → Export Full Package…**
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

The manifest carries the plugin version, coordinate
convention, units block, and an inventory of every file in
the package. Drop the directory into a Slack thread, an
archive bucket, or another DCC's import script and the
metadata travels with the data.

---

## 11. Save your scene state (15 seconds)

**Save UNAV State**. UNAV writes the navigator pose, the
route, the active datasets, the visual-encoding choices,
the overlay visibility, the science-layer settings, and the
mission references into both the C4D document's
BaseContainer (so it persists with `.c4d` save) and a
sidecar JSON at `~/.unav_pro/projects/<scene>.json`.

Reopen the C4D file and the same state loads back.

---

## 12. Next steps

* Real catalog data: `tools/fetch_gaia_region.py`,
  `tools/fetch_jpl_solar_system.py`, etc. See
  [`DATA_SOURCE_OVERVIEW.md`](DATA_SOURCE_OVERVIEW.md).
* Time-aware missions: [`V1_2_TIME_NAVIGATION.md`](V1_2_TIME_NAVIGATION.md).
* Templates + analytics: [`V1_9_ADVANCED_VOYAGE_TOOLS.md`](V1_9_ADVANCED_VOYAGE_TOOLS.md).
* Overlays + science layers: [`V2_0_PROCEDURAL_AUTHORING_TOOLS.md`](V2_0_PROCEDURAL_AUTHORING_TOOLS.md), [`V2_1_ASTROPHYSICAL_OVERLAYS.md`](V2_1_ASTROPHYSICAL_OVERLAYS.md).
* Export pipelines: [`V2_3_EXPORT_PIPELINES.md`](V2_3_EXPORT_PIPELINES.md).
* For everything: [`USER_MANUAL.md`](USER_MANUAL.md).
