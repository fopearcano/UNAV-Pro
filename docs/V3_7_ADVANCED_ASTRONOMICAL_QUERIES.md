# UNAV Pro — v3.7 Advanced Astronomical Queries

The v3.7 milestone is about **discovery**: turning
UNAV into a strong astronomical search and
exploration tool inside Cinema 4D. **Not**
rendering. **Not** new authoring surfaces.

For deep dives see:

* [`QUERY_PRESETS.md`](QUERY_PRESETS.md) — eight
  named preset shortcuts.
* [`ROUTE_AWARE_QUERIES.md`](ROUTE_AWARE_QUERIES.md)
  — polyline-corridor + per-waypoint nearest-
  neighbour helpers.
* [`EPOCH_AWARE_QUERY_LIMITATIONS.md`](EPOCH_AWARE_QUERY_LIMITATIONS.md)
  — what the engine does (and doesn't) do with
  `epoch_jd`.

---

## 1. The new package

`unav_pro/query/` ships:

* **`advanced_query.py`** — the engine.
  `AdvancedQuery` declares the search; `run_query`
  applies filters + ranks + caps; `QueryReport`
  carries results + counts + warnings.
* **`query_presets.py`** — eight named factory
  functions (nearest stars, brightest stars,
  nearby Gaia, high-z galaxies / quasars, solar
  system at epoch, around navigator, along route,
  selected-dataset summary).
* **`route_query.py`** — polyline-corridor + per-
  waypoint nearest-neighbour helpers.
* **`result_actions.py`** — pure helpers that
  translate a `QueryResult` into
  bookmark / route / mission / focus / inspect
  deltas.
* **`export.py`** — JSON / CSV / Markdown
  exporters.

The dialog's *Advanced Query* panel facade lives
in `unav_pro/ui/advanced_query_panel.py`.

## 2. Eleven query kinds

| Kind | Use case |
| --- | --- |
| `nearest` | Closest objects to a reference point. |
| `brightest` | Smallest apparent magnitude. |
| `highest_redshift` | Largest redshift. |
| `distance_range` | Distance ∈ [min, max]. |
| `magnitude_range` | Apparent magnitude ∈ [min, max]. |
| `redshift_range` | Redshift ∈ [min, max]. |
| `by_source` | Match catalog source (any of N). |
| `by_type` | Match object type (any of N). |
| `within_visible_sector` | Restrict to visible-sector uids. |
| `near_selected` | Nearest neighbours of a selected uid. |
| `near_route` | Sentinel; route-aware lives in `route_query`. |

Kinds set the *default sort order*; the artist
can override via `sort_order=...`.

## 3. Determinism

Every helper is **pure** + **deterministic**:

* No PRNG anywhere.
* Stable tie-break by uid in every sort.
* Same input + same query → byte-identical
  output.

## 4. Result actions

For every `QueryResult`:

* `focus_navigator_action(r)` →
  `NavigationFocus`.
* `bookmark_action(r)` → `BookmarkDelta`.
* `add_to_route_action(r)` →
  `RouteWaypointDelta`.
* `add_to_mission_action(r, duration_seconds=...)`
  → `MissionWaypointDelta`.
* `inspect_action(r)` → `InspectorRequest`.

Plus three bulk variants
(`bookmark_all`, `add_all_to_route`,
`add_all_to_mission`).

The dialog forwards each delta to the existing
v0.6 / v1.4 / v1.3 state-managers — none of them
mutates anything itself.

## 5. Export

All three exporters take a `QueryReport` + a
target path, write atomically, and return the
absolute output path.

* `write_json_report` — full report incl. the
  query, counts, warnings, every result.
* `write_csv_report` — one row per result
  (`uid`, `catalog_source`, `object_type`,
  `common_name`, `score`, `distance_pc`,
  `apparent_magnitude`, `redshift`).
* `write_markdown_report` — a single page with
  query summary, counts, results table, warnings.

## 6. Acceptance

* [x] User can discover objects through advanced
  queries.
* [x] Query results can become bookmarks /
  routes / missions.
* [x] Route-aware discovery works.
* [x] Query outputs are exportable.
* [x] Limitations are clearly reported (engine
  emits warnings; the markdown exporter has a
  dedicated *Warnings* section).
* [x] No rendering assumptions.

## 7. Out of scope

* No new HTTP fetchers — the engine only filters
  rows already in memory or stored on disk.
  Fetching catalogs is a v0.x preprocessing-CLI
  concern.
* No catalog crossmatch — two rows that describe
  the same physical object aren't reconciled.
* No spectral-classification reasoning beyond the
  v1.3 deterministic classifier.
* No multi-process / async query farming —
  single-threaded, in-memory; the v3.0 task queue
  can host long-running queries cooperatively.

## 8. Tests

* `test_v37_advanced_query` — engine filtering +
  ranking + caps + warning surface.
* `test_v37_query_presets` — registry, builder
  shape, parameter forwarding.
* `test_v37_route_query` — polyline distance,
  corridor matching, per-waypoint nearest, route
  summary.
* `test_v37_result_actions` — focus, bookmark,
  route, mission, inspect deltas + bulk
  variants.
* `test_v37_query_export` — JSON / CSV / Markdown
  outputs + atomic file writes.
* `test_v37_advanced_query_panel` — panel-action
  facade + form validation.
