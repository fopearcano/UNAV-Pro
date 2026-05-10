# UNAV Pro — Roadmap

The forward-looking view of what's in UNAV Pro v2.5, what
might land in a future minor release, and what is
explicitly out of scope.

This document supersedes the older
`ROADMAP_CPP_GPU_VERSION.md` (which remains as a historical
record of the v0.8–v1.0 native-rendering work). The scope
of the *plugin going forward* is strictly the navigation +
voyage / camera-animation tool documented in
[`USER_MANUAL.md`](USER_MANUAL.md).

---

## 1. Implemented (v0.1 → v2.5)

The full feature set the v2.5 release ships with. Each
entry links to its milestone doc.

### Data layer

* **Catalog schema** — `CatalogObject`, JSONL/CSV I/O,
  derived-field computation. (v0.1)
* **Sample catalog** — bundled 100-row deterministic sample.
  (v0.1)
* **Connector layer** — Gaia DR3, JPL Horizons, SDSS, DESI
  HTTP normalisers. (v0.3 / v0.4 / v0.5)
* **Spatial index** — chunked per-cell JSONL. (v0.2)
* **SQLite back end** — v1.1 schema + bbox-prefiltered cone
  queries. ([`V1_1_QUERY_ENGINE.md`](V1_1_QUERY_ENGINE.md))
* **Time-aware schema** — v1.2 `object_states` table for
  proper-motion + ephemeris rows.
  ([`V1_2_TIME_NAVIGATION.md`](V1_2_TIME_NAVIGATION.md))

### Navigator + visible sector

* **Navigator null** with cone parameters, scale modes,
  source filters. (v0.1)
* **Visible-sector pipeline** — bbox prefilter + exact cone
  refine, diff/update materialisation. (v0.1+)
* **Render-mode layer** — debug-objects / instances / point-
  cloud / native-point-viewer. (v0.7+)
* **Native point viewer** — file-bridge protocol + GPU
  buffer architecture (Python writer + native reader).
  (v0.8 / v0.9 / v1.0)

### Authoring

* **Search + bookmarks + step-navigation** (v0.6).
* **Route planner** — v0.6 spline; v1.4 mission-to-route
  conversion.
* **Time Navigator** — Julian-date model, proper-motion
  propagation, JPL time-series fetch.
  ([`V1_2_TIME_NAVIGATION.md`](V1_2_TIME_NAVIGATION.md))
* **Knowledge layer** — v1.3 deterministic classifier,
  plain-text summary, glossary, physical-interpretation
  helpers.
* **Mission system** — waypoints, camera path (Catmull-Rom
  + slerp), playback engine, transports.
  ([`V1_4_GUIDED_VOYAGES.md`](V1_4_GUIDED_VOYAGES.md))
* **Voyage tools** — templates, route analytics, mission
  organiser, annotations, exporters.
  ([`V1_9_ADVANCED_VOYAGE_TOOLS.md`](V1_9_ADVANCED_VOYAGE_TOOLS.md))
* **Cinematic polish** — pause / look-at / roll fields,
  smooth/linear interpolation, scrub slider.
  ([`V1_8_CINEMATIC_NAVIGATION.md`](V1_8_CINEMATIC_NAVIGATION.md))

### Overlays + science

* **Procedural overlays** — grid, galactic / ecliptic
  planes, distance rings, sector cone, route corridor,
  waypoint labels.
  ([`V2_0_PROCEDURAL_AUTHORING_TOOLS.md`](V2_0_PROCEDURAL_AUTHORING_TOOLS.md))
* **Astrophysical layers** — distance / redshift /
  magnitude shells, motion vectors, catalog source regions,
  solar-system orbit placeholders, density / constellation
  placeholders.
  ([`V2_1_ASTROPHYSICAL_OVERLAYS.md`](V2_1_ASTROPHYSICAL_OVERLAYS.md))

### Animation + export

* **Animated state evaluator** — frame-aware
  `AnimatedSample`, sync markers, epoch-change frames.
  ([`V2_2_ANIMATION_TIMELINE_INTEGRATION.md`](V2_2_ANIMATION_TIMELINE_INTEGRATION.md))
* **Timeline keyframe baker** — camera + navigator +
  optional FOV. (v1.8 + v2.2)
* **Timeline-marker system** — UNAV-tagged markers
  (waypoint / epoch / sync / science). (v2.2)
* **Export pipelines** — Mission JSON, Route JSON, CSV,
  Markdown, Camera Path JSON, Timeline JSON, Science
  Layer JSON, Dataset Summary JSON.
  ([`V2_3_EXPORT_PIPELINES.md`](V2_3_EXPORT_PIPELINES.md))
* **Export package** — directory tree + manifest, atomic
  writes, fail-closed validation.
  ([`EXPORT_PACKAGE_FORMAT.md`](EXPORT_PACKAGE_FORMAT.md))

### Stability + release engineering

* **State-manager facade**, atomic writes, defensive scene
  walks, bounded-memory cone queries.
  ([`V1_7_STABILIZATION.md`](V1_7_STABILIZATION.md))
* **Version metadata + health check + packaging** —
  release-ready. ([`V2_4_RELEASE_PREP.md`](V2_4_RELEASE_PREP.md))
* **Documentation suite** — user manual, artist quickstart,
  TD guide, install / quickstart / troubleshooting,
  release-engineering docs.
  ([`USER_MANUAL.md`](USER_MANUAL.md), v2.5)

---

## 2. Planned

Items the v2.x cycle is likely to land. Each has a clear
problem statement; none introduces a new system.

* **SceneHook auto-sync.** A Cinema 4D `SceneHookData`
  that fires `Playback.advance()` per redraw, drives the
  v2.2 sync markers when the timeline cursor crosses
  them, and powers a real "Play" button in the dialog.
  Currently the dialog drives playback manually.
* **Per-track keyframe cleanup.** The v2.2 *Clear UNAV
  Keyframes* button is a placeholder. The cleanup needs
  per-DescID dispatch on the navigator + camera tracks.
* **DuckDB query path.** Optional swap-in for
  `db/spatial_query`; documented in
  [`V1_1_DATABASE_BACKEND.md`](V1_1_DATABASE_BACKEND.md).
* **GPU vertex-buffer renderer.** The v1.0 native-point-
  viewer prototype already ships; the
  `BaseDraw::DrawArrayWithVertexBuffer` swap inside
  `SdkRenderer::drawImpl` is the next step. Documented in
  [`V1_0_GPU_RENDERER.md`](V1_0_GPU_RENDERER.md). This is
  *internal viewport drawing*, not an external render
  bridge.
* **FTS5-backed name search.** The v0.6 search is
  substring-based; FTS5 would make `SELECT name LIKE`
  queries instant on a million-row catalog.
* **Per-document time-navigator state.** Two C4D
  documents currently share one process-wide
  `TimeNavigatorState`. Documented in
  [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) §6.
* **Real cosmology engine for redshift shells.** The v2.1
  proxy is loudly tagged `(approximate)`; a real
  cosmology engine (e.g. astropy.cosmology) would replace
  the proxy without changing the science-layer API.
* **Real density estimator.** The v2.1
  `object_density_volume` placeholder slot.
* **IAU constellation boundaries.** The v2.1 placeholder
  becomes data-driven once the IAU boundary set is
  ingested.

---

## 3. Optional future

Items with a clear use case but no commitment. Driven by
artist / TD demand.

* **External renderer interoperability — export-only.**
  Wrap the v2.3 `CameraExchangeDocument` JSON with FBX /
  Alembic / USD camera writers so the per-frame data lands
  in render pipelines that don't speak UNAV's format. This
  is **export-only**: UNAV produces files; the renderer
  reads them. **No live integration, no IPC, no socket
  bridge.**
* **Houdini / Blender / Maya importers.** Reference Python
  scripts that consume the camera-path JSON. Not part of
  the plugin; would live as separate companion packages.
* **Mission package versioning beyond schema_version: 1.**
  The current schema is wide and stable; a future v3.x
  bump is plausible but not planned.
* **Per-overlay opacity.** v2.0 stores the field but the
  C4D applier treats it as advisory; a future v2.x can
  wire it through display tags.
* **Looped playback.** The v1.4 `loop=True` flag is
  unchanged; per-segment loops are not on the radar.

---

## 4. Explicitly out of scope

These are the **never** list. UNAV's identity is the
navigation + voyage / camera-animation tool. Anything in
this section would change that identity and won't be
added.

* **Render engine.** UNAV does not produce images. No
  shaders, no render kernels, no path tracer, no real-time
  preview engine. Cinema 4D's native renderer (or
  Redshift / Octane / Arnold etc.) renders the scene; UNAV
  populates the scene.
* **RelativityRender bridge.** Explicitly excluded from
  every milestone since v1.4. The plugin will not link
  against, talk to, or assume the presence of any
  relativistic-render external service.
* **Sockets / IPC / network protocols.** UNAV is offline-
  first. The plugin makes no network calls; the
  preprocessing CLIs are the only path that touches HTTP.
* **Real-time per-frame visible-sector regeneration.**
  Sync is marker-based, not per-frame. The visible-sector
  pipeline is too expensive for per-frame use; the v2.2
  marker model is the only supported regeneration cadence.
* **Auto-update / online check.** UNAV is offline-first.
  The plugin does not phone home, check for updates, or
  fetch remote configuration.
* **Plugin signing / notarisation pipeline.** Maxon's
  plugin distribution doesn't require it; out of scope.
* **Cosmological inference / scientific publication
  output.** UNAV is a *visualisation* plugin. The redshift
  → distance helper is a coarse proxy; the magnitude-shell
  overlay is cosmetic. Real astrometric work uses
  astropy / SOFA / SPICE outside UNAV.

---

## 5. The boundary, restated

UNAV Pro is an **astronomical navigation + voyage / camera-
animation tool for Cinema 4D**. It populates the C4D scene
with real catalog data, lets the artist plan camera
movement through it, bakes the result to the timeline,
and exports the result as DCC-agnostic JSON.

Everything else — rendering, IPC, real-time scientific
simulation, online services, render-engine bridges — is
out of scope. The plugin's value comes from doing one
thing well in a host (Cinema 4D) that has a mature
rendering / scene-management ecosystem of its own.

If a future milestone changes this boundary, it will:

1. update this `ROADMAP.md` first,
2. document the new identity in `USER_MANUAL.md`,
3. ship in a major-version release (`v3.x`),
4. carry a migration path for existing v2.x state.

Until then, the v2.5 boundary is the contract.
