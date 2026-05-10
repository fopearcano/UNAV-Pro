# UNAV Pro — Route Beautification

Reference for `unav_pro/cinematic/route_beautify.py`.

For the workflow overview see
[`V3_6_PROCEDURAL_CINEMATIC_HELPERS.md`](V3_6_PROCEDURAL_CINEMATIC_HELPERS.md).

---

## 1. The problem

A v1.4 mission with sharp 90° corners produces a
camera path that looks robotic. v3.6's
beautification helpers smooth those corners while
**preserving the original mission data** — they
return a new polyline; the input mission is never
mutated.

## 2. Two algorithms

### 2.1 Chaikin corner cutting

Each iteration replaces every interior point with
two fractional cuts (typically at the 1/4 + 3/4
positions along each edge). After N iterations the
polyline approaches a B-spline-like curve.

```python
from cinematic import chaikin_smooth

points = [(0, 0, 0), (10, 0, 0), (10, 10, 0)]
smoothed = chaikin_smooth(points, iterations=2, cut_ratio=0.25)
# Endpoints preserved; interior corner rounded.
```

* **Iterations** — typically 1-3. Each iteration
  doubles the polyline density.
* **Cut ratio** — 0.25 is the classical value;
  smaller ratios cut tighter, larger ratios
  smooth more aggressively.

### 2.2 Gaussian-window averaging

Each interior vertex is replaced with a weighted
average of its `window` neighbours. Lighter touch
than Chaikin; preserves the gross shape of the
route.

```python
from cinematic import gaussian_smooth

smoothed = gaussian_smooth(points, window=1, sigma=0.7)
# 3-tap blur; very light smoothing.
```

* **Window** — radius in vertices. `window=1`
  gives a 3-tap filter.
* **Sigma** — controls the smoothness vs.
  fidelity trade-off.

## 3. Endpoint preservation

Both algorithms preserve the first + last point of
the polyline. The route still **starts and ends at
the original waypoints** — only interior corners
are smoothed. This means a baked timeline still
hits the artist's chosen first / last shot.

## 4. Sharp-angle detection

`detect_sharp_angles(points, angle_threshold_deg=60)`
returns the indices of interior vertices whose
interior angle is sharper than the threshold (the
camera would "elbow" through them):

```python
from cinematic import detect_sharp_angles

points = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (20, 10, 0)]
sharp = detect_sharp_angles(points, angle_threshold_deg=80.0)
# → [1, 2]   (both interior corners are 90°, sharper than 80°)
```

The cinematic panel surfaces this so the artist
can decide which corners to smooth.

## 5. Top-level entry: `beautify_polyline`

```python
from cinematic import beautify_polyline, SmoothingMode

report = beautify_polyline(
    points,
    mode=SmoothingMode.CHAIKIN,
    densify_segments=4,   # interpolate before smoothing
)
print(report.short_summary())  # "beautify[chaikin]: 4 → 18 point(s)"
print(report.points)
```

The `BeautificationReport` carries the mode +
parameters + input/output point counts + the
smoothed polyline. The dialog uses this to drop a
preview spline into the scene under
`UNAV_Project / UNAV_Missions`.

## 6. Mission + Route facades

`beautify_mission_path(mission, ...)` runs the
smoother over a v1.4 `Mission`'s C4D-coordinate
waypoints. `beautify_route_path(route, ...)` does
the same for v0.6 `Route` objects. Both return a
`BeautificationReport`; **neither mutates the
input.**

## 7. Path tension control (placeholder)

`SmoothingParameters.tension` is a value in
`[0.0, 1.0]` reserved for a future Catmull-Rom
integration. v3.6 stores it on the report so a
future spline-based smoother can read it without
a schema bump; the v3.6 algorithms ignore it.

## 8. Tests

* `test_v36_route_beautify` — Chaikin endpoint
  preservation + iteration count, Gaussian
  3-tap math, sharp-angle detection at known
  thresholds, mission/route facades produce
  a report without mutating the input.
