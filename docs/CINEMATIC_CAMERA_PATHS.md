# Cinematic Camera Paths

How the v1.4 voyage system turns a mission into an evaluable
camera path. The reference implementation is
`unav_pro/voyage/camera_path.py`; this document describes the
math and the deterministic guarantees.

---

## 1. The contract

`build_camera_path(mission, config) → CameraPath`

Inputs:

* A `Mission` (ordered list of `MissionWaypoint`).
* A `CameraPathConfig` (speed multiplier, include-epoch
  flag, orient-toward-next flag).

Output:

* A `CameraPath` whose `sample(t)` and `sample_at_step(i,
  total)` return one `CameraSample` (position + orientation
  + epoch + originating waypoint index).

The path is **purely a parameterised lookup table**. There
is no internal clock, no easing-curve catalogue, and no per-
frame state. Same input → byte-identical output.

---

## 2. Position interpolation

### 2.1 Catmull-Rom spline

UNAV uses the standard uniform Catmull-Rom basis. For four
control points P0..P3 and parameter t in [0, 1]::

    a = -0.5*P0 + 1.5*P1 - 1.5*P2 + 0.5*P3
    b =      P0 - 2.5*P1 + 2.0*P2 - 0.5*P3
    c = -0.5*P0           + 0.5*P2
    d =                P1
    point(t) = a*t^3 + b*t^2 + c*t + d

The curve passes through P1 at t=0 and through P2 at t=1, so
each segment exactly hits its two waypoints.

### 2.2 Endpoint mirroring

For the first segment (where there is no P0) and the last
(where there is no P3), the missing control point is replaced
with the nearest interior point. This makes the curve start
exactly at waypoint[0] and end exactly at waypoint[-1] — a
property the tests assert (`test_two_waypoint_endpoints_are_exact`).

### 2.3 Why Catmull-Rom?

* **Local control** — moving one waypoint affects only the
  two adjacent segments.
* **Interpolating** — the curve passes through every
  waypoint (Bezier control polygons don't).
* **Closed-form** — no iterative solve, no spline-fit step
  at build time.
* **Cheap** — three multiplies + three adds per axis per
  sample.

The downside: Catmull-Rom can overshoot at sharp corners
(the curve loops outside the waypoint convex hull). For the
v1.4 visualisation use case this is acceptable — the artist
can add a midpoint coordinate to tame any specific corner.
Centripetal Catmull-Rom (which clamps overshoot) is a future
upgrade.

---

## 3. Segment timing

Each waypoint contributes `duration_seconds` (default 4.0)
to the path. The cumulative-normalised parameter table is::

    cum[i] = sum(durations[0..i]) / total_duration

so that `cum[0] = 0.0` and `cum[-1] = 1.0`. `sample(t)`
locates the segment containing `t` via this table, then
evaluates the local parameter inside that segment.

The `speed_multiplier` divides every duration uniformly:
`speed × 2.0` halves the total runtime; `speed × 0.5`
doubles it. Bounded to `[0.1, 10.0]` so the playback engine
can't be told to step at one tick per millennium.

---

## 4. Orientation interpolation

### 4.1 Quaternion slerp

Between two waypoint quaternions q_a, q_b at local parameter
t, UNAV uses spherical linear interpolation::

    cos_θ = q_a · q_b
    if cos_θ < 0:           # take the short path
        q_b = -q_b
        cos_θ = -cos_θ
    if cos_θ > 0.9995:      # nearly identical → lerp + normalise
        return normalise(lerp(q_a, q_b, t))
    θ = acos(cos_θ)
    return (sin((1-t)·θ) · q_a + sin(t·θ) · q_b) / sin(θ)

Quaternions are normalised on entry; the slerp output is
also a unit quaternion (the tests assert this — every
segment endpoint passes `|q| ≈ 1`).

### 4.2 Synthesised "look toward next"

When `config.orient_toward_next = True` (default) and a
waypoint doesn't carry an explicit `orientation_quat`, UNAV
synthesises one at build time:

* Compute the unit vector from waypoint *i* to waypoint
  *i+1*.
* Build the quaternion that rotates `(0, 0, 1)` (camera's
  forward axis in C4D) onto that vector.
* Pole singularities (vector aligned with ±z to within
  ε) fall back to the identity / a 180° flip about y.
* The last waypoint inherits the previous waypoint's
  orientation (it has no "next" to look at).

When `orient_toward_next = False`, missing orientations get
the identity quaternion. Useful when the artist is using an
external camera rig and just wants positional sync.

---

## 5. Epoch interpolation

Epochs are floats (Julian Dates) and interpolate linearly
between waypoints::

    epoch(local) = (1 - local) · epoch_a + local · epoch_b

When a waypoint has `epoch_jd = None` and the previous
waypoint has one, the missing waypoint inherits it (fall-
through). When `config.include_epoch = False`, every sample
gets `epoch_jd = None` regardless of waypoint epochs — useful
when the artist wants to scrub the camera through a static
scene.

---

## 6. Determinism

The camera path is deterministic by construction:

* All math is closed-form (no iterative solver).
* No randomness, no time-of-day dependency, no cache-state
  dependency.
* `to_json` round-trips through canonical (sorted-key) form,
  so the input file is reproducible.
* Tests (`test_path_sampling_is_deterministic`) sample the
  same `t` twice and assert byte equality.

Determinism is the seam that lets the playback engine claim
"same step → same camera pose, every time" — a property the
v1.4 acceptance criteria explicitly require.

---

## 7. Building a route preview

`build_route_from_mission(mission)` converts the mission into
a v0.6 `core.route.Route`. The route is what the existing
"Build Route Spline" path renders into the C4D scene as a
draggable `SplineObject`. Mission waypoints without a cached
position are silently dropped — same convention as
`build_camera_path`.

The dialog uses this for the "Preview as Route Spline"
button: the artist sees the path geometry in the viewport
before hitting Play, which catches "I forgot to add a
midpoint" mistakes early.

---

## 8. What the camera path is *not*

* **Not a real-time keyframe engine.** It does not interpolate
  every C4D channel. It produces position + orientation +
  epoch.
* **Not eased.** Linear timing per segment. Easing curves
  (ease-in / ease-out) are explicitly out of scope for v1.4.
* **Not a fly-through generator.** The artist places every
  waypoint by hand; the path connects them. Procedural
  "orbit-around-X" paths are out of scope.
* **Not bound to a frame rate.** The dialog (or a future
  SceneHook) decides how often to advance; the path is
  agnostic to wall-clock time.
