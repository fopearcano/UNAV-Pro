# UNAV Pro — Route-Aware Queries

Reference for `unav_pro/query/route_query.py`.

For the milestone overview see
[`V3_7_ADVANCED_ASTRONOMICAL_QUERIES.md`](V3_7_ADVANCED_ASTRONOMICAL_QUERIES.md).

---

## 1. Four entry points

* `find_objects_near_route` — every catalog row
  within a corridor radius of any segment of a
  polyline.
* `find_objects_between_waypoints` — same, but
  restricted to one segment `[a, b]`.
* `closest_object_to_each_waypoint` — for each
  waypoint, the single closest catalog row.
* `summarise_route_distribution` — counts +
  per-source / per-type breakdown.

All four are **pure helpers** over a polyline +
an iterable of `CatalogObject` rows. No Cinema
4D, no network, no mutation.

## 2. Polyline math

`distance_point_to_segment(point, a, b)` and
`distance_point_to_polyline(point, polyline)` are
the geometric primitives. Pure 3D math:

```
ab = b − a
t = clamp((point − a) · ab / |ab|², 0, 1)
projection = a + t · ab
distance = |point − projection|
```

The polyline variant scans every segment + keeps
the smallest distance.

## 3. Corridor radius

The default corridor is `5.0 pc`
(`DEFAULT_CORRIDOR_RADIUS_PC`). Tune via the
`corridor_radius_pc` kwarg:

```python
from query import find_objects_near_route

report = find_objects_near_route(
    polyline=route_points,
    candidates=catalog_rows,
    corridor_radius_pc=20.0,
    max_results=500,
)
print(report.short_summary())
for r in report.results[:10]:
    print("  ", r.short_summary())
```

The report carries:

* `corridor_radius_pc` + `polyline_point_count` —
  the inputs;
* `candidates_scanned` — total iterated;
* `matched_before_cap` — how many passed the
  filter;
* `returned` — after `max_results` cap;
* `results` — distance-sorted (closest first).

## 4. Per-waypoint nearest-neighbour

```python
from query import (
    closest_object_to_each_waypoint,
    polyline_from_waypoints,
)

points = polyline_from_waypoints(mission.waypoints)
matches = closest_object_to_each_waypoint(
    waypoints=points,
    candidates=catalog_rows,
)
for m in matches:
    if m.closest is not None:
        print(f"WP {m.waypoint_index}: "
              f"closest={m.closest.uid} "
              f"d={m.distance_pc:.2f}pc")
```

Used by the dialog's *Snap to Catalog* helper:
when the artist's waypoint sits "near a Gaia
star," the dialog suggests snapping to it.

## 5. Route summary

```python
from query import summarise_route_distribution

summary = summarise_route_distribution(
    polyline=route_points,
    candidates=catalog_rows,
    corridor_radius_pc=10.0,
)
print(summary.short_summary())
```

Returns a `RouteSummary` with:

* `total` — count of objects in the corridor;
* `per_source` — `{source_name: count}`;
* `per_type` — `{object_type: count}`.

The dialog renders this in the route panel's
*Distribution* section.

## 6. Performance notes

* The helper iterates every candidate once per
  query. For a million-row catalog use the v3.0
  task queue + a v1.1 spatial-DB cone first to
  narrow the candidate set.
* Polyline distance is O(N segments). A 200-
  waypoint polyline against a 100 K candidate
  list is ~20 M segment-distance evaluations —
  still sub-second in plain Python.
* All math is `math.sqrt` / `math.cos` —
  avoid invoking the helper inside a tight
  per-frame loop.

## 7. Determinism

All four helpers are pure functions of their
inputs. Same polyline + same candidate iterable +
same corridor radius → same output, byte for
byte. No PRNG, no global state.

## 8. Tests

* `test_v37_route_query` — segment / polyline
  distance math, corridor matching at known
  thresholds, per-waypoint nearest, route
  summary.
