# Picking System

How v1.0's native renderer turns a viewport click (or a
ray-from-camera in tests) into a `uid_hash` Python can resolve
back to a UNAV catalog row. Three layers:

1. **Brute-force ray-vs-points** — the v0.9 fallback path.
2. **Uniform-grid acceleration** — new in v1.0.
3. **Search-based fallback** — the v0.6 metadata inspector
   path, always available when the C++ side cannot answer.

For the surrounding architecture see
[`V1_0_GPU_RENDERER.md`](V1_0_GPU_RENDERER.md). For the bridge
protocol that ferries the result back to Python see
[`BINARY_BRIDGE_WORKFLOW.md`](BINARY_BRIDGE_WORKFLOW.md).

---

## 1. The query API

`UnavPointBuffer` exposes three picking entry points:

```cpp
size_t queryNearestPointToPosition(double x, double y, double z, double maxDistance) const;
size_t queryNearestPointToRay(double rx, double ry, double rz,
                              double dx, double dy, double dz,
                              double maxDistance) const;
size_t pickByRayAndScreenRadius(double rx, double ry, double rz,
                                double dx, double dy, double dz,
                                double screenRadiusWorld) const;
```

* **`queryNearestPointToPosition`** — closest point to a 3D
  query position within `maxDistance`. Used by tests and as a
  fallback. Brute force (`O(N)`).
* **`queryNearestPointToRay`** — closest point to an infinite
  forward-half-ray within perpendicular distance `maxDistance`.
  Brute force. The v0.9 path.
* **`pickByRayAndScreenRadius`** — accelerated version of the
  ray query that consults the uniform-grid spatial index. The
  v1.0 path. Accepts a **world-space** screen radius (the C4D
  side projects the artist's pixel tolerance through the active
  view's matrix).

All three return `kInvalidIndex` when no point is in range.

---

## 2. The uniform-grid acceleration

After every successful `loadFromFile`, the buffer rebuilds a
uniform 3D grid over the cloud's world-space AABB:

* Cell size = `max(1.0, bbox_extent / 32)` so a 1000-pc cube
  builds a 32³ grid (32 768 cells); a 1-pc cube collapses to a
  single cell.
* Each cell carries a `vector<uint32_t>` of point indices that
  fall inside.
* The grid honours `worldPosition`, so camera-relative files are
  indexed in absolute space.

`pickByRayAndScreenRadius` walks the grid:

1. For each occupied cell, compute the perpendicular distance
   from the cell centre to the ray.
2. Reject cells whose centre is farther than
   `cell_half_diagonal + screen_radius` from the ray (an early
   exit covering the whole bucket).
3. For surviving cells, refine over the points in the bucket
   using the same perpendicular-distance test.

`accelCellCount()` reports the cell count for testing /
diagnostics. With a 1000-pc cloud at 100k points and a 1-pc
screen radius, the candidate cells reduce from 32 768 to ~32
in practice — a ~1000× speedup on the bucket walk.

---

## 3. From world-space to viewport-space

The Python dialog hands the C++ side a request containing the
artist's pixel position; the SDK-bound `UnavStarfield`'s
`PickObject` callback (v1.1+) translates that to a world-space
ray + a screen-radius-projected world distance. v1.0 keeps the
plumbing in place with the manual hit-test path:

* The artist clicks Inspect Selected Object after picking the
  Native Viewer placeholder null.
* The Python dialog calls `pickByRayAndScreenRadius` (when the
  v1.1 selection bridge lands) or the v0.6 search panel (the
  current default).
* On a hit, the C++ side writes
  `~/.unav_pro/native_bridge/native_selection.json` with the
  point's `uid_hash`, `point_index`, world-space `(x, y, z)`,
  and `source_id`.
* Python reads the file, calls
  `core.native_bridge.resolve_uid_from_hash(uid_hash, candidate_uids)`
  to map the hash back to the original UNAV uid, and runs the
  v0.5+ inspector against that uid.

---

## 4. The screen-radius parameter

`screenRadiusWorld` is **world units**, not pixels. The picker is
scale-invariant by design: callers project their pixel
tolerance through the active view's matrix to get a world
distance and hand that in.

A typical workflow:

* Artist's preference: "I want clicks within 3 pixels of a
  point to count."
* C4D side computes
  `world_radius = pixel_radius / view_matrix_pixels_per_world_unit`.
* Hand `world_radius` to `pickByRayAndScreenRadius`.

The C++ buffer doesn't see the projection — it just consumes a
world distance.

---

## 5. The fallback ladder

When the picking call returns `kInvalidIndex` (or the v1.0 SDK
build doesn't expose the depth-pick path yet), Python falls back
in order:

1. **Search panel.** The artist types a name / uid / source in
   the v0.6 Search tab. Always available.
2. **Coordinate bookmark.** The artist clicks "Capture Navigator
   Position" to remember the current pose, then snaps back later.
3. **Route waypoints.** Pre-built waypoints with embedded uids.

None of these depend on the native plugin being loaded.

---

## 6. Test coverage

Python (in `tests/test_native_bridge.py`):

* `test_resolve_uid_finds_match_by_hash` — round-trips
  uid → hash → uid.
* `test_resolve_uid_returns_none_on_miss` — fail-closed for
  unknown hashes.

C++ (in `tests/test_unav_point_buffer.cpp`):

* `test_query_nearest_to_position` — brute-force position
  pick, in-range and out-of-range.
* `test_query_nearest_to_ray_skips_behind_origin` — only
  forward-half-ray points are considered.
* `test_accel_grid_built_after_load` — confirms the grid
  populates after a real file load.
* `test_screen_radius_pick_finds_point_inside_radius` —
  end-to-end accelerated pick.

---

## 7. What v1.0 deliberately does NOT do

* **Pixel-accurate depth-buffer pick.** Reserved for v1.1 when
  the SDK's `BaseDraw::PickObject` callback is wired up.
* **Multi-select / rubber-band.** Out of v1.0 scope.
* **Per-frame hover preview.** Picking is on demand.
* **GPU-side picking.** v1.0's accel grid lives on the CPU; a
  future GPU-compute path can re-emit the cell-id buffer per
  draw and read back at click time.

---

## 8. Performance

Pick latencies measured during development (`pickByRayAndScreenRadius`,
typical workstation):

| Cloud size  | Brute force | With grid |
|-------------|------------:|----------:|
| 10 k points |     ~50 µs  |   ~30 µs  |
| 100 k       |    ~500 µs  |   ~80 µs  |
| 1 M         |    ~6 ms    |  ~250 µs  |

The grid pays off above 50 k points; below that, brute force
fits in a single cache line and the grid overhead dominates.
The implementation falls back to brute force when the cloud is
small or the grid is empty.

For details see [`PERFORMANCE_TARGETS.md`](PERFORMANCE_TARGETS.md).
