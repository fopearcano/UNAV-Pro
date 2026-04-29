# UNAV Pro — System Architecture

**Project:** C4D Universal Navigator Pro
**Target host:** Cinema 4D 2023+ (R2023, 2024, 2025)
**Document status:** Draft v0.1 (architecture, no implementation)

---

## 1. Purpose

UNAV Pro is a universal interstellar navigation system embedded in Cinema 4D.
It ingests real astrophysical catalogs (Gaia, SDSS, DESI, NASA/JPL, and future
sources), produces an interactive particle/point-cloud representation of the
observable universe at multiple scales, and provides camera- and null-based
navigation, view-frustum filtering, and per-object metadata inspection.

The system is designed so that the C4D plugin is a **thin viewport and
interaction layer** over a **decoupled, language-agnostic data pipeline**.
This separation is the central architectural decision: it keeps the C4D layer
small, performant, and replaceable (Python today, C++/Maxon SDK later) while
the heavy ingestion, normalization, and spatial-indexing work happens
out-of-process and is cached locally.

---

## 2. Top-level architecture

```
                 +--------------------------------------------------+
                 |                Cinema 4D 2023+ host              |
                 |                                                  |
                 |   +-----------------+    +-------------------+   |
                 |   | Viewport &      |<-->| Camera / Null     |   |
                 |   | Particle Layer  |    | Navigation Ctrl   |   |
                 |   +--------+--------+    +---------+---------+   |
                 |            ^                       ^             |
                 |            |                       |             |
                 |   +--------+-----------------------+---------+   |
                 |   |        Ray / Cone Selection & Filter      |  |
                 |   +--------+-----------------------+---------+   |
                 |            ^                       ^             |
                 |   +--------+--------+    +---------+---------+   |
                 |   | Metadata        |    | Plugin Core /     |   |
                 |   | Inspector UI    |    | Command Dispatch  |   |
                 |   +-----------------+    +-------------------+   |
                 +-------------------------|------------------------+
                                           |  IPC / file I/O / shared mem
                 +-------------------------v------------------------+
                 |               UNAV Pro Engine (out-of-process)   |
                 |                                                  |
                 |   +-----------------+    +-------------------+   |
                 |   | Spatial Index   |<-->| Local Cache /     |   |
                 |   | (Octree/BVH/    |    | Embedded DB       |   |
                 |   |  HEALPix)       |    | (SQLite/Parquet)  |   |
                 |   +--------+--------+    +---------+---------+   |
                 |            ^                       ^             |
                 |   +--------+-----------------------+---------+   |
                 |   |          Data Ingestion / Normalization  |   |
                 |   |  Gaia | SDSS | DESI | NASA/JPL | plugins |   |
                 |   +-------------------------------------------+  |
                 +--------------------------------------------------+
                                           |
                                           v
                              External catalogs / archives
                          (Gaia DR3, SDSS DR18, DESI EDR, JPL SPK)
```

The dashed boundary between the C4D host and the engine is crossed by a
narrow, versioned protocol (see §3.10). The engine is a normal OS process
(or library) and is invoked by the plugin; this allows the engine to be
reimplemented in C++ without touching plugin code.

---

## 3. Layers

### 3.1 C4D plugin layer

**Responsibility:** integrate UNAV into Cinema 4D as a first-class tool —
register commands, scene objects, tags, dialogs, and viewport hooks.

**Components:**
- **Plugin core / command dispatch.** Registers `CommandData`, `ObjectData`,
  `TagData`, and `MessageData` plugin classes. Owns the lifecycle of UNAV
  scene objects (the *Universe* null, the *Navigator* camera tag, the
  *Filter Cone* tag).
- **Scene model.** A small set of generator objects:
  - `UnavUniverse` — the root generator that produces the visible particle
    cloud for the current frame.
  - `UnavDataset` — references a cached catalog tile-set on disk.
  - `UnavFilterCone` — tag/object that defines a camera-space ray or cone
    used to subset visible particles.
  - `UnavMetadataInspector` — a non-rendering helper that queries the engine
    for object data near the cursor or selection.
- **Settings / preferences.** Plugin preferences page: cache root, network
  policy, max points in viewport, level-of-detail thresholds, GPU/CPU
  preference for particle rendering.

**Constraint:** the plugin layer never speaks to remote catalogs directly and
never parses raw scientific files. It calls the engine.

### 3.2 Data ingestion layer

**Responsibility:** acquire raw data from external archives, normalize it to
the internal schema, and hand it to the cache layer.

- **Source adapters** — one per catalog (Gaia, SDSS, DESI, NASA/JPL/Horizons,
  Hipparcos/Tycho, exoplanet archives, …). Each adapter implements a common
  interface: `discover()`, `fetch(query)`, `normalize(rows) -> CanonicalRows`.
- **Canonical schema** — see *UNAV_PRO_DATA_PIPELINE.md*. Minimum fields:
  `uid`, `source`, `ra`, `dec`, `parallax_mas` or `distance_pc`,
  `pm_ra_masyr`, `pm_dec_masyr`, `radial_velocity_kms`, photometric bands,
  `object_type`, `epoch`, plus a JSON `extra` blob for catalog-specific data.
- **Coordinate transforms** — ICRS → galactic → barycentric Cartesian (parsec)
  → C4D world units. Performed once at ingest time and stored.
- **Quality flags** — preserve catalog flags so the index can filter by
  astrometric quality.

### 3.3 Local cache / database layer

**Responsibility:** persist normalized data so that the plugin can run offline
and so that no scene-load triggers a network request.

- **Storage format.** Parquet for bulk point data (columnar, compressed,
  memory-mappable). SQLite for catalog metadata, ingestion history, and
  small lookup tables.
- **Tile layout.** Data is partitioned by HEALPix cell (Nside configurable
  per source) and by distance shell. Each tile is a self-contained Parquet
  file plus a manifest entry.
- **Cache root.** Default `~/UNAV-Pro/cache/`, overridable per-project.
- **Versioning.** Each cache entry stores `(source, release, schema_version,
  ingest_timestamp)`. Schema migrations are explicit.
- **Eviction.** LRU on tile granularity, with pinning for tiles referenced
  by an open scene.

### 3.4 Spatial index layer

**Responsibility:** answer the spatial queries the viewport and the filter
cone need, in time bounded by viewport frame budget.

- **Primary index.** HEALPix tiling at multiple Nside levels (typical
  Nside = 64 / 256 / 1024 for sky, plus distance binning).
- **Secondary index.** Per-tile linear BVH or Morton-ordered point list to
  accelerate cone/frustum queries inside a tile.
- **Query API.**
  - `query_frustum(camera, near, far, max_points, lod)`
  - `query_cone(apex, axis, half_angle, length, max_points)`
  - `query_ray(origin, dir, tolerance, max_results)`
  - `query_id(uid) -> full record`
- **LOD policy.** Each tile carries multiple decimations (e.g. 1×, 1/16×,
  1/256×). The index returns the coarsest level that meets a per-pixel
  density target derived from the camera and viewport size.

### 3.5 Viewport particle generation layer

**Responsibility:** convert the index's query result into something C4D draws
fast.

- **Default path:** Cinema 4D **Thinking Particles** / Particle Geometry
  (or a `BaseDraw` callback for direct GL drawing on R2023+). Points are
  pushed as a flat float buffer keyed by `uid`.
- **Color and brightness:** mapped from photometric bands in the canonical
  schema; mapping curve is user-editable.
- **Streaming:** the layer requests an updated point set whenever the camera
  moves more than a configurable threshold or the cone parameters change.
  Streaming is debounced on a background thread; the C4D thread only swaps
  buffers.
- **Selection rendering:** picked points are drawn into a separate overlay
  pass with a halo so they remain visible at small pixel sizes.

### 3.6 Camera / null navigation controller

**Responsibility:** turn standard C4D camera and null manipulation into
parsec-scale navigation without breaking C4D's float32 transform stack.

- **Reference frame.** UNAV uses a *floating origin*: world-space coordinates
  in C4D are always relative to a current `origin_pc` vector held by the
  Universe object. When the camera moves far from the C4D origin, the
  controller rebases the scene and offsets the cached point buffers
  accordingly. This is the only way to keep float32 viewport precision at
  galactic scale.
- **Scale modes.** AU, light-year, parsec, kiloparsec, megaparsec — chosen
  per scene and reflected in C4D's unit display.
- **Travel modes.**
  - *Free fly* (camera is the navigator).
  - *Null follow* (a null is the navigator; the camera is parented).
  - *Goto target* (animated transition to a selected object).
- **Time axis.** Optional epoch slider that applies proper-motion / orbital
  propagation (handled by the engine, not in C4D).

### 3.7 Ray / cone selection / filter system

**Responsibility:** let the user reduce the working set so that the scene
file and viewport memory stay bounded.

- **Geometry.** A filter is defined as one or more `(apex, axis, half_angle,
  length)` cones (a ray is a cone with `half_angle = 0`). Multiple cones
  combine with union/intersection/difference.
- **Source.** The apex and axis are driven by a C4D camera or null, so
  filters animate naturally.
- **Modes.**
  - *Visualization filter* — affects only what is drawn; the cache is
    unchanged.
  - *Bake filter* — produces a new `UnavDataset` containing only the points
    that pass the filter. This is what shrinks the saved scene.
  - *Selection* — picks all objects inside the cone for the metadata
    inspector.
- **Implementation.** All cone tests run in the engine against the spatial
  index; the plugin only sends cone parameters and receives a list of
  surviving uids plus their decimated render buffer.

### 3.8 Metadata inspector

**Responsibility:** show full per-object data on demand without loading the
full catalog.

- **Trigger.** Hover, click, or list-select inside the inspector dialog.
- **Lookup.** `query_id(uid)` → full canonical record + raw `extra` blob.
- **UI.** A C4D dialog (`GeDialog`) with tabs:
  - *Identity* (uid, source, cross-IDs)
  - *Astrometry* (position, parallax, proper motion, RV)
  - *Photometry* (bands, magnitudes, derived absolute magnitude)
  - *Provenance* (catalog, release, ingest time)
  - *Raw* (JSON dump of the source row).
- **Cross-references.** If multiple sources contain the same physical object,
  the inspector shows them grouped by `match_group_id` produced at ingest.

### 3.9 Export / import format

**Responsibility:** make scenes portable and reproducible.

- **`.unavscene` (JSON).** Holds:
  - cache references (source, release, tile list, hashes)
  - active filter cones and their animation
  - camera/navigator state
  - LOD and rendering preferences
  - **No raw point data** — only references into the cache.
- **`.unavbake` (Parquet + manifest).** A self-contained, filtered point set
  produced by *Bake filter*. This is what gets shipped with a `.c4d` file
  when the user wants the scene to open on a machine without the full cache.
- **C4D side.** The `UnavDataset` object stores either a cache reference or
  a path to a `.unavbake` file. Saving a `.c4d` never embeds raw catalog
  data unless the user explicitly bakes.

### 3.10 Plugin ↔ engine protocol

- **Transport, phase 1 (Python prototype):** in-process Python; the engine
  is a Python package the plugin imports. Long-running calls run on a worker
  thread, results returned via a thread-safe queue and dispatched on the
  C4D main thread via `c4d.SpecialEventAdd`.
- **Transport, phase 2 (decoupled engine):** local subprocess, msgpack over
  stdin/stdout, with a shared-memory ring for bulk point buffers (numpy
  `memmap` or `multiprocessing.shared_memory`).
- **Transport, phase 3 (C++ engine):** native shared library loaded by the
  plugin; the same msgpack/shared-memory contract is preserved so the
  Python prototype keeps working as a fallback.
- **Versioning.** Every message carries a protocol version. The plugin
  refuses to talk to a mismatched engine and shows an actionable error.

---

## 4. Performance constraints

These are budgets the implementation must meet, not aspirations.

| Concern                          | Budget                                       |
|----------------------------------|----------------------------------------------|
| Viewport frame                   | ≤ 16 ms at 60 fps target, ≤ 33 ms at 30 fps  |
| Default visible point count      | ≤ 2 M points active in viewport              |
| Hard cap visible point count     | ≤ 10 M (with GPU path)                       |
| Cone query latency               | ≤ 50 ms for 1 M-point working set            |
| Metadata `query_id` latency      | ≤ 20 ms                                      |
| Cold scene load                  | ≤ 3 s (cache hot), ≤ 30 s (cache cold)       |
| Cache disk per source (typical)  | Gaia DR3 sample: 5–40 GB depending on cuts   |
| RAM ceiling, plugin process      | ≤ 2 GB above C4D baseline                    |
| Saved `.c4d` overhead            | ≤ 50 MB without bake; bake size = user choice|

Floating-point precision: all stored positions are `float64` parsec.
Viewport positions are `float32` relative to the current floating origin.
Conversion happens in the engine, never in C4D Python.

---

## 5. Path to C++ acceleration

The architecture is set up so the Python prototype can be replaced piece by
piece. Order of replacement, in expected priority:

1. **Spatial index core.** A C++ HEALPix + BVH library exposed via pybind11
   or as a Maxon-SDK module. This is the hottest path and the easiest win.
2. **Particle buffer assembly.** Move buffer packing (uid, position, color,
   size) into native code; expose via shared memory to avoid GIL contention.
3. **Cone/ray query kernels.** SIMD-friendly batch query, optionally
   GPU-offloaded via CUDA/Metal/Vulkan compute.
4. **Ingestion adapters.** Last to migrate; Python is fine here because
   ingestion is offline and IO-bound.

The Maxon C++ SDK plugin will reuse the same `.unavscene` / `.unavbake`
formats and the same engine protocol, so a project authored with the Python
plugin opens unchanged in the C++ plugin.

---

## 6. Out of scope (v1)

- Real-time scientific simulation (n-body, hydrodynamics).
- Authoring of new astrometric catalogs.
- Render-time path-traced star physics — UNAV emits geometry/particles; the
  user renders with C4D's renderers (Standard, Physical, Redshift, Octane).
- Cloud-hosted shared cache. The cache is local; sharing is via `.unavbake`.

---

## 7. Open questions

- Whether to ship our own GL/viewport draw or rely entirely on C4D Thinking
  Particles for the cloud. Decision deferred until we measure 2 M-point
  draw cost on R2024 and 2025.
- Whether HEALPix Nside should be per-source or unified. Leaning per-source
  because Gaia and DESI have very different sky densities.
- Object-match strategy across catalogs — start with positional crossmatch
  at ingest time; revisit once we have real failure cases.
