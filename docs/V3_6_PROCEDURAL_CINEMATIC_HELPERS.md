# UNAV Pro — v3.6 Procedural Cinematic Helpers

The v3.6 milestone is about **camera choreography,
shot planning, and artistic voyage creation** inside
Cinema 4D. **Not** rendering. **Not** physics. **Not**
randomness without a seed. v3.5 runtime preserved
byte-for-byte; v3.6 layers cinematic helpers on top
of the v1.4 voyage / v1.8 timeline / v3.45 native
integration stack.

For the deep dives see:

* [`CINEMATIC_FRAMING.md`](CINEMATIC_FRAMING.md) —
  framing presets + auto-look-at math.
* [`CAMERA_RIGS.md`](CAMERA_RIGS.md) — orbit / flyby
  / target-follow / locked-target rigs under
  ``UNAV_CameraRigs``.
* [`ROUTE_BEAUTIFICATION.md`](ROUTE_BEAUTIFICATION.md)
  — Chaikin + Gaussian smoothing that preserves the
  original mission data.

---

## 1. New surfaces

* **`unav_pro/cinematic/framing.py`** — five framing
  presets (close / medium / wide / extreme-wide /
  extreme-scale), framing distance trig,
  ``compose_look_at_pose``, slerp-friendly
  ``blend_look_at``.
* **`unav_pro/cinematic/motion.py`** — drift / orbit
  / flyby / approach-depart sample generators with
  six classic easing presets (linear / ease-in /
  ease-out / ease-in-out / step / slow-settle).
  All deterministic — drift takes an explicit
  ``seed``.
* **`unav_pro/cinematic/route_beautify.py`** — Chaikin
  corner cutting + Gaussian-window smoothing +
  sharp-angle detector. Preserves the input;
  returns new polylines.
* **`unav_pro/c4d_objects/camera_rigs.py`** — four
  rig descriptors + pure planning helpers + a
  c4d-bound builder that materialises rigs under
  ``UNAV_CameraRigs`` (sibling of ``UNAV_Project``).
* **`unav_pro/ui/cinematic_panel.py`** — pure
  Cinematic-panel facade for the dialog.

## 2. Determinism

Every cinematic helper is **pure** and
**deterministic**. Same input → same output, byte
for byte:

* Framing math is plain trig.
* Smoothing algorithms are deterministic recursions.
* Motion generators take parameters + (for drift) a
  seed; no PRNG state.

Tests assert this directly via the
``determinism_signature`` helper in
``cinematic/motion.py``.

## 3. Acceptance

* [x] User can generate cinematic camera helpers
  (orbit / flyby / target-follow / locked-target).
* [x] Routes can be smoothed aesthetically (Chaikin
  + Gaussian).
* [x] Orbit / flyby rigs work safely in C4D
  (descriptor → plan → undo-tracked builder).
* [x] Cinematic helpers integrate with missions /
  timeline (built on top of v1.4 ``Mission`` +
  v1.8 timeline keys).
* [x] Generated rigs remain organised
  (single ``UNAV_CameraRigs`` root, deterministic
  per-rig names).
* [x] Deterministic playback preserved (no RNG
  state; every helper is a pure function).
* [x] No rendering assumptions.

## 4. Out of scope

* No render features — UNAV remains a populator;
  Cinema 4D's renderers draw the scene.
* No physics — drift is a deterministic sin/cos
  modulation, not a spring system.
* No procedural randomness without a seed —
  ``DriftParameters.seed`` is required + plumbed
  through every helper.
* No per-frame heavy rebuilds — the cinematic
  panel produces *pre-baked* tracks; the v1.8
  timeline writer consumes them.

## 5. Tests

* `test_v36_framing` — preset table, framing distance
  trig, look-at quaternion shape, slerp.
* `test_v36_motion` — easing curves, drift / orbit /
  flyby / approach-depart determinism, parameter
  validation.
* `test_v36_route_beautify` — Chaikin convergence,
  Gaussian smoothing, sharp-angle detection,
  endpoint preservation.
* `test_v36_camera_rigs` — descriptor identity,
  build-plan shape, naming determinism, c4d-bound
  builder raises outside the host.
* `test_v36_cinematic_panel` — pure panel-action
  facade end-to-end.
