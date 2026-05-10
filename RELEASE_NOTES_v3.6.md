# UNAV Pro v3.6 — Procedural Cinematic Helpers

Release date: 2026-05-10
Codename: *Procedural Cinematic Helpers*

v3.6 adds **camera choreography, shot planning, and
artistic voyage creation** helpers on top of the
v1.4 voyage / v1.8 timeline / v3.45 native-
integration stack. **Not** rendering. **Not**
physics. **Not** randomness without a seed. v3.5
runtime preserved byte-for-byte.

---

## Highlights

* **Cinematic framing** (`unav_pro/cinematic/framing.py`).
  Five framing presets (close / medium / wide /
  extreme-wide / extreme-scale), framing-distance
  trig, ``compose_look_at_pose``, slerp-friendly
  ``blend_look_at`` for smooth orientation
  transitions.
* **Camera motion generators**
  (`unav_pro/cinematic/motion.py`). Drift / orbit
  / flyby / approach-depart sample tracks +
  six classic easing presets (linear / ease-in /
  ease-out / ease-in-out / step / slow-settle).
  All deterministic — drift takes an explicit
  ``seed``; the same parameters always produce the
  same samples.
* **Route beautification**
  (`unav_pro/cinematic/route_beautify.py`). Chaikin
  corner cutting + Gaussian-window smoothing + a
  sharp-angle detector. The original mission /
  route data is **never mutated** — the helpers
  return new polylines.
* **Camera rigs**
  (`unav_pro/c4d_objects/camera_rigs.py`). Four
  rig kinds (orbit / target-follow / flyby /
  locked-target). Each rig materialises a wrapper
  null + target null + camera object under
  ``UNAV_CameraRigs`` (sibling of
  ``UNAV_Project``). Idempotent: a rig with the
  same identity key replaces in place.
* **Cinematic panel facade**
  (`unav_pro/ui/cinematic_panel.py`). Pure-Python
  wrappers for the dialog's *Cinematic* panel
  (auto-frame target, create rig, apply smoothing,
  motion preview, drift toggle, framing-preset
  picker).
* **v3.45 undo-policy extension.** Five new
  cinematic operations
  (`build_camera_rig`,
  `remove_camera_rig`,
  `ensure_camera_rigs_root`,
  `apply_framing_preset`,
  `apply_route_beautify`) added to
  ``UNDO_POLICY``.

## What didn't change

* No new on-disk schemas. Mission JSON, Route JSON,
  Camera Path JSON, Export Manifest, DB schema,
  binary format, provenance JSON, presentation
  JSON byte-identical to v3.5.
* No runtime dependencies. Stdlib-only.
* No rendering, no IPC, no RelativityRender bridge,
  no threading.
* No physics simulator — drift is a deterministic
  sin/cos modulation, not a spring system.

## Acceptance

* [x] User can generate cinematic camera helpers
  (orbit / flyby / target-follow / locked-target).
* [x] Routes can be smoothed aesthetically (Chaikin
  + Gaussian + densification).
* [x] Orbit / flyby rigs work safely in C4D
  (descriptor → plan → undo-tracked builder).
* [x] Cinematic helpers integrate with missions /
  timeline (built on v1.4 ``Mission`` + v1.8
  timeline keys).
* [x] Generated rigs remain organised
  (single ``UNAV_CameraRigs`` root, deterministic
  per-rig names, idempotent rebuild).
* [x] Deterministic playback preserved (no PRNG
  state; every helper is a pure function).
* [x] No rendering assumptions.

## Testing

* Full suite passes: **2725 tests** (2590 v3.5
  baseline + 135 new v3.6 tests).
* New v3.6 test files:
  * `test_v36_framing` — preset table, framing
    distance trig, look-at quaternion, slerp.
  * `test_v36_motion` — easing curves, drift /
    orbit / flyby / approach-depart determinism.
  * `test_v36_route_beautify` — Chaikin endpoint
    preservation, Gaussian smoothing, sharp-
    angle detection, mission/route facades.
  * `test_v36_camera_rigs` — descriptor identity,
    build-plan shape, naming determinism, undo-
    policy coverage, c4d-bound builders raise
    outside the host.
  * `test_v36_cinematic_panel` — pure facade
    end-to-end.

## Boundary, restated

UNAV Pro v3.6 remains an **astronomical navigation
+ voyage / camera-animation tool for Cinema 4D**.
Rendering, IPC, real-time scientific simulation,
online services, and render-engine bridges remain
explicitly out of scope. See
[`docs/ROADMAP.md`](docs/ROADMAP.md) §4.
