# UNAV Demo — Minimal On-Board Sample

A tiny, self-contained demo bundle that ships with every
UNAV Pro release. Use it to verify the install, exercise
the dialog, and learn the workflow without downloading any
catalogs.

## Contents

```
minimal_unav_demo/
├── catalog.jsonl     5-row JSONL (3 stars, 1 galaxy, 1 demo planet)
├── mission.json      5-waypoint mission JSON (v1.4 schema)
├── route.json        3-waypoint route JSON (v0.6 schema)
└── README.md         this file
```

Total size: a few hundred bytes per file. Safe to ship in
the release zip; safe to commit to source control; safe to
hand to anyone who wants to "show me what UNAV does."

## Workflow

### 1. Load the catalog

1. Open Cinema 4D 2023+.
2. **Extensions → Universal Navigator Pro**.
3. **Dataset Manager…** → **Add Dataset** → pick
   ``catalog.jsonl`` from this directory.
4. **Load Active Datasets**.

You should see "5 objects merged" in the dialog log.

### 2. Build the visible sector

1. **Create Navigation Null**.
2. **Sync Visible Sector**.

Five small `Onull` objects appear in the Object Manager
under ``UNAV_Starfield → UNAV_VisibleSector``: the three
stars, the galaxy, and the demo planet.

### 3. Inspect the demo planet

1. Click ``demo:5`` in the Object Manager.
2. **Inspect Selected Object**. The metadata panel should
   show the v1.3 nine-section render: Basic Identity,
   Position, Motion, Photometry, Cosmology (empty),
   Catalog Notes (epoch + body), Plain-language Summary,
   Missing Data, Available Actions.

### 4. Run the demo mission

1. **Missions** tab → **Import…** → ``mission.json``.
2. The dialog log says "Mission: imported 'UNAV Demo
   Mission'."
3. Click **▶ Play** to scrub the camera through the five
   waypoints. **Preview Path** drops a Cinema 4D
   ``SplineObject`` into the scene so you can see the
   curve.
4. **Bake to Timeline** writes camera + navigator
   keyframes (start frame 0, end frame 240, project FPS).

### 5. Export an interchange package

1. **Export → Export Full Package…**
2. Pick a target directory.
3. UNAV writes ``UNAV_Export/`` containing ``manifest.json``,
   ``missions/UNAV_Demo_Mission.json``,
   ``camera_paths/UNAV_Demo_Mission.json``, and
   ``summaries/dataset_summary.json``.

That's the whole v2.4 happy path in five steps. If anything
fails, see [`docs/TROUBLESHOOTING.md`](../../docs/TROUBLESHOOTING.md).

## Determinism

The demo files are stable across UNAV Pro releases. Mission
and route schemas are versioned (``schema_version: 1``);
loading the demo on a future plugin version produces the
same scene state.

## What the demo is not

* Not a substitute for a real catalog. Five rows is enough
  to exercise the workflow; a real cinematic needs Gaia /
  SDSS / DESI / JPL data fetched via the v0.x preprocessing
  CLIs.
* Not a benchmark. The release-perf benchmarks in
  ``tools/benchmark_*.py`` use synthetic 100k-row catalogs.
* Not an artistic reference. Distances and positions are
  for plumbing tests; the planet's epoch is "2026-01-01"
  but the position isn't a real ephemeris value.
