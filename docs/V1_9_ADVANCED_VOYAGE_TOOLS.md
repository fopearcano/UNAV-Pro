# UNAV Pro v1.9 — Advanced Voyage Tools

UNAV's v1.9 milestone makes the v1.4 voyage system practical
for *real voyage planning*: richer waypoint types, ready-made
templates, route analytics, mission organisation, annotation
layers, and exporters for handing missions off to people who
don't have Cinema 4D open.

This is **not a rendering release**. v1.9 is navigation
intelligence, route design, mission organisation, and
animation planning. Visible-sector generation, camera-path
math, timeline baking, and the v1.7 stability layer are all
unchanged. v1.9 is **additive** — every v1.4 / v1.8 mission
file round-trips through v1.9 byte-identical.

For the per-feature deep dives:

* [`VOYAGE_TEMPLATES.md`](VOYAGE_TEMPLATES.md) — the five
  bundled templates and how to add new ones.
* [`ROUTE_ANALYTICS.md`](ROUTE_ANALYTICS.md) — what the
  analyser computes, what the warnings mean, and how to
  read them.
* [`MISSION_ORGANIZER.md`](MISSION_ORGANIZER.md) — the new
  duplicate / rename / tag / search / sort / package
  workflow.
* [`ANNOTATION_SYSTEM.md`](ANNOTATION_SYSTEM.md) — the three
  annotation layers (waypoint / scene / mission) and the
  metadata-derived note synthesiser.

---

## 1. What v1.9 actually delivers

| Surface | Change |
|---------|--------|
| `voyage/mission.py` | Three new waypoint kinds: ``search_result``, ``orbital``, ``annotation``. Three new optional fields: ``camera_offset``, ``tags``, ``search_query``. New ``scene_annotations`` list on ``Mission``. ``MissionWaypoint.is_path_contributing()`` and ``has_tag()`` predicates. |
| `voyage/templates.py` | New module with five editable mission templates: Solar System Tour, Nearest Stars Tour, Redshift Tour, Empty Voyage, Selected Objects Tour. |
| `voyage/route_analytics.py` | New module: ``analyse_route(mission)`` returns a structured ``RouteAnalytics`` report (segments, total distance, ETA, kind / type / source histograms, epoch consistency warnings). |
| `voyage/annotations.py` | New module with ``SceneAnnotation``, ``MissionAnnotations``, ``derive_notes()`` (metadata-derived prose), and CRUD helpers for scene annotations. |
| `voyage/export.py` | New module: ``mission_to_markdown``, ``mission_to_csv``, ``mission_to_json_file``, atomic ``write_markdown`` / ``write_csv``. |
| `voyage/mission_manager.py` | New methods: ``duplicate``, ``rename``, ``add_tags`` / ``remove_tag``, ``search``, ``sort``, ``export_package`` / ``import_package``. Per-mission file writes routed through the v1.7 ``safe_write_json`` helper. |
| `ui/main_dialog.py` | Missions tab gains template picker + **New From Template**, **Duplicate Mission**, **Route Analytics**, **Export Markdown…**, **Export CSV…**, and **Filter** controls plus a search input. |
| Tests | Five new test files (`test_v19_*`) covering waypoint kinds, templates, analytics, organizer, annotations + exports. |
| Docs | This file + four deep dives. |

**Not in v1.9:** rendering, RelativityRender / external
renderer integration, IPC / sockets, mission-system
rewrite, on-disk format bumps. The v1.4 mission shape is
unchanged; v1.9 is purely additive.

---

## 2. Advanced waypoint kinds

The v1.4 quartet (``object`` / ``coordinate`` / ``named`` /
``bookmark``) is unchanged. v1.9 adds three new kinds:

| Kind             | Purpose |
|------------------|---------|
| ``search_result``| A uid-backed waypoint that also remembers the search query that produced it. Behaves like ``object`` at playback time; the analytics / annotations layers cite the query as provenance. |
| ``orbital``      | Placeholder for an epoch-driven body whose position is resolved at playback time. Today the playback path treats it like ``object`` (uid lookup); v1.x will plug a real propagator behind it. |
| ``annotation``   | Pure metadata. Never participates in the camera path. Used to attach prose to a mission stop without inserting another camera anchor. |

Plus three new optional fields on every kind:

* ``camera_offset`` — ``(dx, dy, dz)`` C4D-units offset
  applied at path-build time. Lets the camera path sample a
  position different from the navigator anchor (e.g. "look
  at Mars from a few units behind").
* ``tags`` — free-form lower-case labels the analytics +
  organizer surfaces use to filter / group waypoints.
* ``search_query`` — set when the kind is
  ``search_result``; surfaced by the annotation renderer as
  the "found via search: X" provenance line.

A v1.4 waypoint with no v1.9 extensions serialises
byte-identical on round-trip.

---

## 3. Voyage templates

`voyage.templates` ships five ready-to-edit missions:

```python
from voyage import (
    solar_system_tour,
    nearest_stars_tour,
    redshift_tour,
    empty_voyage,
    selected_objects_tour,
)
```

Each template returns a *mutable* ``Mission`` — the artist
is expected to rename / reorder / add waypoints after
creation. Templates are not locked presets.

The dialog's **Template** picker lists every entry from
``TEMPLATE_REGISTRY``; clicking **New From Template** runs
the corresponding builder and registers the result via the
existing ``MissionManager``.

See [`VOYAGE_TEMPLATES.md`](VOYAGE_TEMPLATES.md) for the
full registry + per-template waypoint list.

---

## 4. Route analytics

`voyage.route_analytics.analyse_route(mission)` returns a
``RouteAnalytics`` report that the dialog renders verbatim
under "Route Analytics":

```
=== Route Analytics ===
Segments       : 5
Total (C4D)    : 16.69 C4D units
Total (pc)     : 16.69 pc
Travel ETA     : 16.69 s (at 1 pc/s)

--- Waypoint Kinds ---
  coordinate   : 1
  object       : 6

--- Object Types ---
  star         : 6

--- Catalog Sources ---
  Gaia DR3     : 6

--- Tags ---
  nearby, star, template

--- Warnings ---
  ! 0 waypoint(s) have no parsec position; total parsec distance is incomplete.
```

The warning surface is conservative: only fired when there
is a real inconsistency (missing parsec positions in a
positioned mission, partial epoch coverage, or an epoch
spread that exceeds 50 Julian Years).

See [`ROUTE_ANALYTICS.md`](ROUTE_ANALYTICS.md) for the
formula reference + every warning condition.

---

## 5. Mission organizer

`MissionManager` gains six new operations:

| Method | Purpose |
|--------|---------|
| ``duplicate(mission_id, *, new_title=None)`` | Deep-copy a registered mission. The clone gets a fresh id and a "Copy of …" title (overridable). |
| ``rename(mission_id, new_title)`` | Update the title in place; persists immediately. |
| ``add_tags(mission_id, tags)`` / ``remove_tag(mission_id, tag)`` | Manage the mission-level tag list. Tags are lower-cased on write. |
| ``search(query="", *, tag=None)`` | Free-text + tag filter over the live mission list. |
| ``sort(*, by="title", reverse=False)`` | Reorder the display list (`title` / `modified` / `waypoints` / `id`). |
| ``export_package(path)`` / ``import_package(path)`` | Pack / unpack the entire mission library into one JSON file. |

The dialog wires the most useful subset to buttons (Duplicate,
Filter, Export Markdown, Export CSV); the rest are reachable
programmatically (and from the upcoming v1.x mission organizer
panel).

Per-mission file writes now go through the v1.7
``safe_write_json`` so a crash mid-save can never truncate a
previously-valid mission file.

See [`MISSION_ORGANIZER.md`](MISSION_ORGANIZER.md) for the
package format and search semantics.

---

## 6. Annotations

Three layers:

* **Waypoint annotations** — the ``MissionWaypoint.notes``
  field plus the new ``derive_notes(wp)`` helper that
  synthesises plain-text notes from the row's metadata
  (catalog source, uid, epoch, search query, camera offset,
  parsec position).
* **Scene annotations** — free 3D labels at fixed
  coordinates that don't drive the camera path. Stored in
  the new ``Mission.scene_annotations`` list.
* **Mission annotations** — the v1.4 ``Mission.description``
  field plus the union of waypoint + mission tags.

`build_mission_annotations(mission, scene_annotations=…)`
returns a ``MissionAnnotations`` report the dialog renders
verbatim. The Markdown exporter consumes the same structure
to produce a publication-quality summary.

See [`ANNOTATION_SYSTEM.md`](ANNOTATION_SYSTEM.md) for
examples + the metadata-derived-note rules.

---

## 7. Exporters

Three formats:

| Format    | Function | Used for |
|-----------|----------|----------|
| Markdown  | ``mission_to_markdown(mission)`` / ``write_markdown(...)`` | Publication-style mission summaries with route analytics + annotations. |
| CSV       | ``mission_to_csv(mission)`` / ``write_csv(...)`` | Spreadsheet round-trips; one row per waypoint. |
| JSON      | ``Mission.to_json()`` (existing) / ``mission_to_json_file(...)`` | The on-disk mission format. The new helper writes atomically via `safe_write_json`. |

All three writers use the v1.7 ``safe_write_json`` helper so
a crash mid-write cannot truncate a destination file. Tests
assert the round-trip and the atomic-write property.

---

## 8. Acceptance criteria

* [x] User can build complex voyages from real data
  (Gaia / SDSS / DESI / JPL via the existing connector
  surfaces).
* [x] Missions are organised: duplicate, rename, tag, search,
  sort.
* [x] Routes can be analysed before animation; analytics
  warns about unknown distances + epoch inconsistencies.
* [x] Annotations persist (per-waypoint notes + scene
  annotations on the mission).
* [x] Mission packages export / import via a single JSON
  file.
* [x] No rendering assumptions; no external renderer bridge;
  no IPC.
* [x] v1.8 timeline baking is unchanged; the bake button
  still ignores annotation waypoints + the new path-shape
  fields.

---

## 9. What v1.9 explicitly does **not** do

| Out of scope                                          | Why                                                |
|-------------------------------------------------------|----------------------------------------------------|
| New rendering features                                | Out of scope by spec.                              |
| RelativityRender or any external renderer integration | Out of scope by spec.                              |
| IPC / sockets                                         | Out of scope by spec.                              |
| Real-time orbital propagation                         | The ``orbital`` kind is a placeholder; the v1.x propagator lands later. |
| Mission system rewrite                                | The v1.4 mission shape is unchanged; v1.9 is additive. |
| Per-frame visible-sector update                       | Animation stays decoupled from the catalog pipeline (v1.4 contract). |
| Audio / narration                                     | Out of scope.                                       |
