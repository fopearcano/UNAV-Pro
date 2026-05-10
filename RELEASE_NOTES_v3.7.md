# UNAV Pro v3.7 — Advanced Astronomical Queries

Release date: 2026-05-10
Codename: *Advanced Astronomical Queries*

v3.7 turns UNAV into a **strong astronomical search
and discovery tool inside Cinema 4D**. **Not**
rendering. **Not** new authoring surfaces. **Not**
huge new data downloads. v3.6 runtime preserved
byte-for-byte; v3.7 adds a structured query engine
on top of the existing v0.x catalog stack.

---

## Highlights

* **`unav_pro/query/` (new package).** Pure-Python
  query engine + presets + route-aware queries +
  result actions + exporters. Stdlib only; no
  network calls; deterministic output.
* **Eleven structured query kinds** (`nearest`,
  `brightest`, `highest_redshift`,
  `distance_range`, `magnitude_range`,
  `redshift_range`, `by_source`, `by_type`,
  `within_visible_sector`, `near_selected`,
  `near_route`).
* **Eight named presets** (nearest stars,
  brightest stars, nearby Gaia objects, high-z
  galaxies / quasars, solar system at epoch,
  around navigator, along route, selected-dataset
  summary).
* **Route-aware discovery** — polyline-corridor
  matching, per-waypoint nearest neighbour, route
  distribution summary.
* **Result actions** — pure helpers translating a
  `QueryResult` into bookmark / route / mission /
  navigator-focus / inspector deltas; the dialog
  forwards them to the existing v0.6 / v1.4 / v1.3
  state-managers.
* **JSON / CSV / Markdown exporters.** Atomic file
  writes; deterministic output (modulo timestamp).
* **Advanced Query panel facade**
  (`unav_pro/ui/advanced_query_panel.py`). Pure
  wrappers for run-query / preset-pick / export /
  route-query.
* **Epoch-aware safety.** Setting `epoch_jd` on a
  query without `interpolate_ephemeris` produces
  an explicit warning ("evaluating positions
  statically"). Setting both produces an
  informational note pointing at the v3.7
  limitation doc.

## What didn't change

* No new on-disk schemas. Mission JSON, Route
  JSON, Camera Path JSON, DB schema, binary
  format, provenance JSON, presentation JSON
  byte-identical to v3.6.
* No new runtime dependencies. Stdlib-only.
* No rendering, no IPC, no RelativityRender
  bridge, no threading.
* No physics simulator; no PRNG state.

## Acceptance

* [x] User can discover objects through advanced
  queries (engine + presets).
* [x] Query results can become bookmarks / routes
  / missions (`bookmark_action`,
  `add_to_route_action`, `add_to_mission_action`,
  bulk variants).
* [x] Route-aware discovery works
  (`find_objects_near_route`,
  `closest_object_to_each_waypoint`,
  `summarise_route_distribution`).
* [x] Query outputs are exportable
  (`render_json` / `render_csv` /
  `render_markdown` + atomic write helpers).
* [x] Limitations are clearly reported (engine
  warnings + Markdown *Warnings* section + the
  `EPOCH_AWARE_QUERY_LIMITATIONS.md` doc).
* [x] No rendering assumptions.

## Testing

* Full suite passes: **2870 tests** (2725 v3.6
  baseline + 145 new v3.7 tests).
* New v3.7 test files:
  * `test_v37_advanced_query` — engine filtering,
    ranking, caps, warnings, determinism.
  * `test_v37_query_presets` — registry shape,
    builder coverage, parameter forwarding.
  * `test_v37_route_query` — polyline math,
    corridor matching, per-waypoint nearest,
    route summary.
  * `test_v37_result_actions` — focus / bookmark
    / route / mission / inspect deltas + bulk.
  * `test_v37_query_export` — JSON / CSV /
    Markdown rendering + atomic file writes.
  * `test_v37_advanced_query_panel` — panel-action
    facade + form validation + preset picker.

## Boundary, restated

UNAV Pro v3.7 remains an **astronomical
navigation + voyage / camera-animation tool for
Cinema 4D**. Rendering, IPC, real-time scientific
simulation, online services, and render-engine
bridges remain explicitly out of scope.

For the long-form view of the boundary see
[`docs/ROADMAP.md`](docs/ROADMAP.md) §4.
