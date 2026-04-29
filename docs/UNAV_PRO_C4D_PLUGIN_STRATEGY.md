# UNAV Pro — C4D Plugin Strategy & Roadmap

**Project:** C4D Universal Navigator Pro
**Document status:** Draft v0.1
**Companion docs:** UNAV_PRO_ARCHITECTURE.md, UNAV_PRO_DATA_PIPELINE.md

---

## 1. Strategic question

> Should UNAV Pro start as a Cinema 4D Python plugin, an external Python
> data-preprocessing tool, or a C++/Maxon SDK plugin?

**Answer:** all three, in sequence — but they are not three different
projects. They are three phases of the same architecture. The split is:

1. **External Python data-preprocessing tool** is *required from day one*.
   It is the only sane place for catalog ingestion, normalization, and
   tiling. It runs offline, has no C4D dependency, and produces the cache
   that the plugin reads.
2. **Cinema 4D Python plugin (prototype)** is the *first user-facing
   deliverable*. It validates the architecture, the UX, the viewport
   performance envelope, and the engine protocol.
3. **C++ / Maxon SDK plugin** is a *later performance migration*, only for
   the hot paths that the Python prototype proves are bottlenecks. It is
   not a rewrite — it reuses the same pipeline output and the same engine
   protocol.

This phasing is non-negotiable: skipping phase 1 produces a plugin that
reaches into the network at scene-load time; skipping phase 2 produces a
C++ codebase whose UX has never been tested; starting with phase 3
optimizes code that may not survive the design.

---

## 2. Why start with Python in C4D

- **Cinema 4D 2023+ exposes a stable Python 3 API** (`c4d` module,
  `GeDialog`, `ObjectData`, `TagData`, `MessageData`, `BaseDraw`
  callbacks). All UNAV interactions — registering objects, drawing
  particles, opening dialogs, reacting to camera changes — are reachable
  from Python.
- **Iteration speed.** The viewport interaction model and the metadata
  inspector UI will go through many revisions. Python lets us reload
  plugin code without recompiling against the Maxon SDK.
- **Ecosystem fit.** Astronomy in Python is a solved problem (`astropy`,
  `astroquery`, `healpy`, `pyarrow`, `numpy`, `scipy.spatial`). None of
  these have first-class C++ equivalents we'd want to maintain.
- **Risk isolation.** The Maxon SDK has had breaking changes between R23,
  R24, R25; the Python API has been more stable. A Python plugin survives
  more host upgrades with less rework.

The cost is performance on the hot path (cone queries, particle buffer
assembly, large `BaseDraw` callbacks). The architecture (see
ARCHITECTURE §5) is shaped so those exact functions can be replaced with
native code without touching the rest of the plugin.

---

## 3. Phase plan

### Phase 0 — Foundations (weeks 0–2)

- Lock the canonical schema (DATA_PIPELINE §4).
- Lock the engine protocol surface (ARCHITECTURE §3.10, DATA_PIPELINE §12).
- Stand up the cache directory layout and the `manifest.sqlite` schema.
- Decide HEALPix Nside per source.

Exit criteria: schema and protocol documents accepted; nothing in the C4D
plugin yet.

### Phase 1 — External preprocessing tool (weeks 2–6)

- Implement `unav-ingest`, `unav-tile`, `unav-verify`, `unav-cache`.
- Adapters: Gaia DR3 (subset), Hipparcos/Tycho-2.
- Coordinate transforms, quality cuts, distance estimation.
- Tile writer with LOD decimation.
- Spatial index: HEALPix lookup + per-tile BVH (Python, `numpy`-vectorized).

Exit criteria: a 10 M-row Gaia subset can be ingested, tiled, and queried
by frustum and cone in ≤ 50 ms from a Python REPL.

### Phase 2 — Python C4D plugin, MVP (weeks 6–12)

- Plugin skeleton: `UnavUniverse` (ObjectData), `UnavDataset` (ObjectData),
  `UnavFilterCone` (TagData), `UnavMetadataInspector` (CommandData +
  GeDialog), preferences page.
- Floating-origin camera/null controller.
- Viewport particle generation via Thinking Particles **and** a `BaseDraw`
  point cloud, benchmarked against each other.
- Cone filter (visualization mode only; no bake yet).
- `.unavscene` save/load.
- Metadata inspector with hover-pick.

Exit criteria: load a Gaia subset, fly through it interactively at
≥ 30 fps with ≥ 1 M visible points, click a star, see its full record.

### Phase 3 — Production features (weeks 12–20)

- Bake filter → `.unavbake`.
- Multi-source: SDSS DR18, DESI EDR, NASA Exoplanet Archive.
- Crossmatch and cross-reference UI.
- Time axis (proper-motion propagation).
- Solar system via JPL Horizons.
- Render-time considerations: ensure particle output is consumable by
  Standard, Physical, Redshift, Octane.

Exit criteria: a representative production scene (e.g. sun → nearby stars
→ Milky Way → galaxy cluster) loads, navigates, and renders with no
manual intervention beyond UNAV's own UI.

### Phase 4 — Performance migration to C++ (weeks 20+)

Driven by measured bottlenecks, not speculation. Likely order:

1. Spatial index core in C++ (pybind11 or Maxon SDK module).
2. Particle buffer assembly and `BaseDraw` path in C++.
3. Optional GPU compute for cone/frustum kernels.

Exit criteria: 10 M visible points sustained at 60 fps on a reference
workstation, with the same `.unavscene` files produced by phase 3.

---

## 4. Cinema 4D plugin surface (phase 2 scope)

### 4.1 Plugin types registered

| Plugin class            | Purpose                                              |
|-------------------------|------------------------------------------------------|
| `UnavUniverse` (ObjectData) | Root generator, owns floating origin and LOD state |
| `UnavDataset` (ObjectData)  | Reference to a cached source/region              |
| `UnavFilterCone` (TagData)  | Cone/ray filter parameters, attached to a camera or null |
| `UnavInspectorCommand` (CommandData) | Opens the metadata inspector dialog     |
| `UnavIngestCommand` (CommandData)    | Opens the ingest dialog                  |
| `UnavPreferences` (PreferenceData)   | Cache root, network policy, LOD prefs    |

### 4.2 Object hierarchy in the C4D scene

```
UnavUniverse
├── UnavDataset (Gaia DR3 — local arm)
├── UnavDataset (SDSS DR18 — galaxies z<0.5)
├── Camera (with UnavFilterCone tag)
└── Null  (with UnavFilterCone tag) — alternative navigator
```

### 4.3 Threading model

- C4D's Python runs on the main thread; long operations must not block it.
- Engine calls go through a single `EngineClient` that owns a worker
  thread. Calls return futures.
- Results are delivered to the main thread via `c4d.SpecialEventAdd` +
  `MSG_CORE` so the plugin can swap buffers and request a viewport
  refresh.
- Cone filters are debounced (default 50 ms) so dragging the camera
  doesn't flood the engine.

### 4.4 Viewport rendering decision

Two candidates, both implemented in phase 2, then chosen per scene:

- **Thinking Particles / Particle Geometry.** Plays well with C4D
  renderers and selection. Cost: per-particle objects scale poorly past
  ~ 500 k.
- **`BaseDraw` direct GL callback.** Draws the point buffer with a single
  call. Cost: not visible to renderers without a fallback path; selection
  needs custom hit-testing.

The plugin will let the user pick *Editor draw* (BaseDraw) vs *Render-
ready* (TP) per `UnavDataset`. Most users will keep BaseDraw for editing
and switch to TP only when rendering.

---

## 5. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| C4D Python API changes between 2023/2024/2025 break plugin | Med | High | CI matrix testing on all supported hosts; abstract host calls behind a thin compatibility layer |
| Float32 viewport precision blows up at galactic scales | High | High | Floating origin from day one; never store world positions in `BaseObject` matrices for distant points |
| Catalog redistribution license restricts cache sharing | Med | Med | Ship adapters, not data; bakes record license; prompt users on export |
| Gaia DR4 / new DESI release invalidates cache | High | Low | Releases are pinned per dataset; new releases are additive |
| Python performance insufficient at 1 M+ points | Med | High | Phase 4 C++ path is part of the plan, not a contingency |
| C4D Thinking Particles deprecated for new particle system | Med | Med | Dual-path (TP + BaseDraw) means we can drop either side |
| Studio firewalls block catalog endpoints | High | Low | All ingestion is offline; the plugin itself never needs the network |

---

## 6. Definition of done — v1.0

UNAV Pro v1.0 ships when:

- A user can install the plugin into C4D 2023, 2024, and 2025.
- Without leaving C4D, they can pick a pre-ingested Gaia subset and a
  pre-ingested SDSS subset, see them in the viewport at ≥ 30 fps, fly
  around them with a camera or a null, draw a cone filter from the
  camera, bake the filter result, save the scene, reopen it on another
  machine that has only the bake, and render it with their renderer of
  choice.
- The metadata inspector returns the correct full record for any visible
  object in ≤ 100 ms.
- The plugin obeys its RAM and viewport-frame budgets on the reference
  workstation.
- The data pipeline can be re-run end-to-end on a clean machine from
  documented commands.

Anything beyond that — GPU acceleration, cloud cache, additional
catalogs, scientific simulation — is post-1.0.

---

## 7. Decision log (initial)

- **D1.** Start with Python plugin + external Python pipeline; defer C++
  to a measured phase 4. *Reason:* iteration speed and ecosystem fit.
- **D2.** Cache format is Parquet + SQLite manifest. *Reason:* columnar,
  mmap-friendly, transactional manifest, zero binary dependencies.
- **D3.** Spatial primary index is HEALPix. *Reason:* native to astronomy
  data, equal-area cells, mature tooling (`healpy`).
- **D4.** Floating-origin scene rebasing is mandatory. *Reason:* float32
  viewport stack cannot represent parsec coordinates accurately.
- **D5.** No raw catalog data is embedded in `.c4d` files; portability is
  via explicit `.unavbake`. *Reason:* license, file size, reproducibility.
- **D6.** The plugin never speaks to remote catalogs at runtime. *Reason:*
  scene loads must be deterministic and offline-capable.
