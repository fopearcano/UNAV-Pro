# Route Workflow v2

The v0.6 polish on top of the v0.1 route planner. Adds insert /
replace / reorder, a per-segment distance table, and the supporting
panel rendering. The waypoint data model and the C4D-side
spline-build / focus-on-waypoint pipeline are unchanged from v0.1, so
existing scenes continue to round-trip through *Save UNAV State* /
*Load UNAV State*.

The implementation lives in `core/route.py`; the c4d-bound glue stays
in `ui/route_panel.py`.

---

## 1. The new mutators

`Route` gains three methods:

| Method                                  | Behaviour                                                           |
|-----------------------------------------|---------------------------------------------------------------------|
| `insert_at(index, waypoint)`            | Inserts `waypoint` at `index`. Negative → start; past-end → append. Returns the inserted waypoint. |
| `replace_at(index, waypoint)`           | Swaps the waypoint at `index` for `waypoint`. Returns the old waypoint, or `None` if out of range. |
| `move(from_idx, to_idx)`                | Reorders. Both indices clamp to the valid range; same index is a no-op that returns True. |

The pre-existing `add(...)`, `remove_at(idx)`, `clear()`, `last()`
remain untouched — every v0.1 call site keeps working.

---

## 2. The segment table

`compute_route(route, resolver=...)` was already producing a
`RouteSummary` with per-segment distances:

```python
@dataclass
class RouteSegment:
    from_idx: int
    to_idx: int
    distance_c4d: Optional[float] = None
    distance_pc: Optional[float] = None
```

What v0.6 adds is `render_summary_v2(route, summary)` — a wrapper
around the v0.1 `render_summary` that appends a per-segment table
to the existing header / total block:

```
=== UNAV Route ===
Waypoints       : 4 (4 resolved)
Total (C4D)     : 17.3 units
Total (parsec)  : 17.3 pc

Waypoints:
  [0] Sun (object)  — Gaia DR3, star
  [1] Sirius (object)  — Gaia DR3, star
  [2] Pleiades centroid (coordinate)
  [3] M31 nucleus (object)  — DESI, galaxy

Segments:
  [0→1] Sun → Sirius  (8.6 C4D, 8.6 pc)
  [1→2] Sirius → Pleiades centroid  (130 C4D, 130 pc)
  [2→3] Pleiades centroid → M31 nucleus  (unresolved — skipped)
```

Unresolved segments (an endpoint with no usable position) are
labelled `unresolved — skipped` so the artist sees that the parsec
total excluded them.

---

## 3. Distance computation

The resolver pipeline from v0.1 still applies:

* `passthrough_resolver` — trust the cached `*_c4d` / `*_pc`
  positions on the waypoint.
* `make_lookup_resolver(lookup, scale_mode)` — for object
  waypoints whose cached position is missing, consult the
  `MetadataLookup` to refill it via `compute_derived_fields`.

Per-segment distance is a Euclidean straight-line in C4D units;
parsec distance is the same Euclidean line on the `cartesian_*`
fields when both endpoints carry pc coordinates. Mixed segments
(one endpoint pc-aware, one not) contribute to the C4D total but
not the parsec total — `RouteSummary.incomplete_pc_segments`
records the count.

---

## 4. Spline updates

`build_route_spline(doc, route, lookup=None)` removes the old
spline child of `UNAV_Route` and rebuilds a fresh linear
`SplineObject` through the resolvable waypoints. The behaviour is
unchanged from v0.1 — every Add / Insert / Remove / Move click is
followed by the artist re-clicking *Build Route Spline* to see the
updated path.

(A future polish pass can wire automatic spline rebuilding into the
mutator side, but that's out of v0.6 scope to keep the C4D-side
mutation surface minimal.)

---

## 5. UI surface

The Route Planner panel rendering is the v0.6 priority:

* The dialog calls `render_summary_v2` so artists see the
  per-segment table plus the existing header / total block.
* The four existing buttons — Add Selected Object as Waypoint /
  Clear Route / Build Route Spline / Focus Navigator on Waypoint
  — keep working unchanged.
* The new mutators (`insert_at`, `replace_at`, `move`) are
  exposed via the data model; the dialog buttons that drive them
  ("Insert at #", "Move to #") are reserved for v0.7's full
  per-tab refactor.

---

## 6. Persistence

`Route.to_dict()` / `Route.from_dict()` — unchanged. The v0.1
sidecar JSON shape continues to round-trip; v0.6 adds no new
fields to the on-disk format. Routes saved before v0.6 reopen
verbatim.

---

## 7. What this version does not add

* **No spline-shape options.** The build path remains a linear
  `SplineObject`. Bezier / cubic interpolation is reserved.
* **No per-waypoint C4D-side label markers.** The panel labels
  the waypoints; the spline draws the line. A future polish can
  drop name-labelled child nulls under `UNAV_Route` for in-viewport
  labelling.
* **No real-distance metric for solar-system bodies in mixed
  scenes.** Parsec totals across a Sun → Mars → Sirius route are
  dominated by the Sirius leg; the AU-scale planet hop reads as
  ~5e-6 pc. `_fmt_pc` falls back to AU display under 1 pc, so the
  panel still surfaces the small leg legibly.

---

## 8. Test coverage

`tests/test_route_v06_refinements.py` covers:

* `insert_at` at start / middle / end / clamped overshoots;
* `replace_at` returns the old waypoint, refuses out-of-range
  indices;
* `move` reorders, clamps, refuses empties, no-ops same-index;
* Distance updates after insert and remove;
* `render_summary_v2` produces the segment table, marks
  unresolved segments, and preserves the v0.1 header.

The pre-v0.6 route tests in `tests/test_route.py` continue to pass
unchanged.
