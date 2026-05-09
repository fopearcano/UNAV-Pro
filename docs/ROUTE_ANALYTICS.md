# Route Analytics

The v1.9 ``voyage.route_analytics`` module turns a mission
into a structured *pre-animation* report: per-segment
distances, totals, histograms, epoch consistency warnings.

The dialog's **Route Analytics** button prints the report
verbatim. Tests drive the analytics module directly without
the host.

---

## 1. The contract

```python
from voyage import analyse_route, RouteAnalytics

report = analyse_route(mission, travel_speed_pc_per_s=1.0)
print(report.render_text())
```

`analyse_route` is a pure function. Same input → byte-
identical report.

---

## 2. What the report contains

| Field | Meaning |
|-------|---------|
| ``segments`` | One ``SegmentMetric`` per (waypoint[i], waypoint[i+1]) pair among *path-contributing* waypoints (annotation kinds are skipped). |
| ``total_distance_c4d`` | Sum of segment distances in C4D world units. |
| ``total_distance_pc`` | Sum of segment distances in parsec — only when *every* waypoint has a parsec position. ``None`` otherwise. |
| ``estimated_travel_seconds`` | ``total_distance_pc / travel_speed_pc_per_s``. ``None`` when ``total_distance_pc`` is ``None``. |
| ``waypoints_with_unknown_distance`` | List of indices whose parsec position is missing. Drives the "X waypoints have no parsec position" warning. |
| ``object_type_counts`` | Histogram of waypoint ``object_type`` strings. |
| ``catalog_source_counts`` | Histogram of waypoint ``catalog_source`` strings. |
| ``waypoint_kind_counts`` | Histogram of waypoint ``kind`` strings (``annotation`` included). |
| ``tags`` | Sorted union of mission-level + per-waypoint tags. |
| ``epoch_min_jd`` / ``epoch_max_jd`` | Min / max JD across waypoints that *carry* an epoch. ``None`` when no waypoint has one. |
| ``epoch_spread_days`` | ``epoch_max_jd - epoch_min_jd`` (or ``None``). |
| ``epoch_spread_warning`` | A string when the spread exceeds ``EPOCH_SPREAD_WARN_THRESHOLD_DAYS`` (50 Julian Years). ``None`` otherwise. |
| ``waypoints_without_epoch`` | List of indices for path-contributing waypoints that lack an epoch. Surfaced as a warning *only* when the mission is partially-timed (some waypoints have an epoch, some don't). |

---

## 3. The travel-speed knob

`travel_speed_pc_per_s` is intentionally cosmetic. UNAV
doesn't model relativistic travel; the figure is a placeholder
the artist can override per cinematic intent. Default:
**1 parsec per second**, so the ETA reads back the total
distance directly.

If an artist wants "warp factor 9 → ~13 pc/s", they pass
that value:

```python
report = analyse_route(mission, travel_speed_pc_per_s=13.0)
```

---

## 4. Distance formula

Each segment's distance is the Euclidean L2 norm between
adjacent path-contributing waypoints:

```
distance_pc(a, b) = sqrt((a.x_pc - b.x_pc)² + (a.y_pc - b.y_pc)² + (a.z_pc - b.z_pc)²)
distance_c4d(a, b) = sqrt((a.x_c4d - b.x_c4d)² + ...)
```

This is **straight-line cartesian distance**. UNAV does
not compute great-circle distance, light-travel distance, or
any cosmologically-corrected distance for high-z anchors.
The Hubble-law proxy distances baked into the v0.5
extragalactic templates are still treated as Euclidean — which
is fine for visualisation, wrong for cosmology.

---

## 5. Warning conditions

The analytics layer fires three warnings:

1. **Unknown parsec distances.** Any path-contributing
   waypoint without ``x_pc/y_pc/z_pc`` set. The total
   parsec distance becomes ``None``; the warning lists how
   many waypoints are affected.
2. **Long epoch spread.** ``epoch_spread_days`` exceeds
   ``EPOCH_SPREAD_WARN_THRESHOLD_DAYS`` (50 Julian Years).
   The cinematic crosses a long temporal range; the
   warning asks the artist to verify intent.
3. **Partial epoch coverage.** Some waypoints have an
   epoch, some don't. The temporal resolver will fall
   through to the previous waypoint's epoch (the v1.2
   contract); the warning surfaces this so the artist
   notices.

A clean mission produces no warnings — `analyse_route`
silently produces a no-warning report.

---

## 6. Annotation waypoints

``annotation``-kind waypoints participate in the kind /
type / source histograms but are **excluded** from the
segment math (they have no position). This matches the v1.4
camera-path convention: annotations are pure metadata.

---

## 7. Determinism

The analytics layer is deterministic by construction:

* Histograms use Python's stdlib ``Counter``, which is
  insertion-order-stable for our use case.
* The `tags` list is sorted before render.
* All math is closed-form Euclidean.

Tests in ``test_v19_route_analytics.py`` assert that a
second call on the same mission produces a byte-identical
``render_text()`` output.

---

## 8. The render-text format

The dialog prints `report.render_text()` verbatim:

```
=== Route Analytics ===
Segments       : N
Total (C4D)    : X C4D units
Total (pc)     : Y pc      |  (unknown — see warnings)
Travel ETA     : Z s (at K pc/s)

--- Waypoint Kinds ---
  <kind>       : count

--- Object Types ---
  <type>       : count

--- Catalog Sources ---
  <source>     : count

--- Tags ---
  tag1, tag2, …

--- Epoch Range ---
  JD A → JD B (spread D days)

--- Warnings ---
  ! …
```

Sections that don't apply are omitted (no histograms when
the field is empty; no Epoch Range section when no
waypoint carries an epoch). The Warnings block only
appears when at least one warning fired.

---

## 9. What route analytics is *not*

* **Not a cosmology engine.** Distances are Euclidean.
  Redshift-derived distances are the v0.5 Hubble proxy.
* **Not an astrodynamics engine.** ETA is the artist's
  cinematic-intent number; UNAV doesn't model orbital
  mechanics or relativistic travel.
* **Not a route optimiser.** The analytics layer reports;
  it does not propose alternative orderings.
* **Not a renderer.** The figures are for the artist's
  decision-making before they hit Bake.
