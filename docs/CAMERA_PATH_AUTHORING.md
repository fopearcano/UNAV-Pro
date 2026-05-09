# Camera Path Authoring

How the v1.8 mission system turns a list of waypoints into a
cinematic camera path. This document is the deep-dive
companion to
[`CINEMATIC_CAMERA_PATHS.md`](CINEMATIC_CAMERA_PATHS.md) (the
v1.4 baseline) — it focuses on the v1.8 *authoring* knobs:
pause time, look-at targets, roll, and the smooth/linear
interpolation switch.

---

## 1. The authoring surface

A v1.8 `MissionWaypoint` carries the v1.4 fields plus four
optional v1.8 extensions:

```python
@dataclass
class MissionWaypoint:
    kind: str
    label: str = ""
    uid: Optional[str] = None
    bookmark_id: Optional[str] = None
    x_c4d: Optional[float] = None
    y_c4d: Optional[float] = None
    z_c4d: Optional[float] = None
    epoch_jd: Optional[float] = None
    orientation_quat: Optional[Quaternion] = None
    duration_seconds: float = 4.0

    # v1.8 cinematic-polish fields:
    pause_seconds: float = 0.0
    look_at_uid: Optional[str] = None
    look_at_position: Optional[Tuple[float, float, float]] = None
    roll_deg: float = 0.0

    notes: str = ""
```

All four v1.8 fields default to no-op behaviour. A mission
saved by v1.4 round-trips through v1.8 byte-identical.

---

## 2. `duration_seconds` vs `pause_seconds`

Two separate concepts the v1.4 model conflated by accident:

* **`duration_seconds`** — the *travel* time the cursor
  spends moving from the previous waypoint to this one.
  Required to be > 0.
* **`pause_seconds`** — the *dwell* time the cursor spends
  *at* the waypoint after arrival, before moving toward
  the next waypoint. Optional, defaults to 0.0. Required
  to be ≥ 0.

Pauses are **additive**: the segment's contribution to the
total path duration is `duration_seconds + pause_seconds`.
A waypoint with `duration_seconds=2, pause_seconds=3`
takes 5 seconds of total runtime: 2 s travelling, then 3 s
sitting still at the waypoint.

The dwell is implemented as additional segment time at the
arrival pose — not as a separate "stationary segment". This
keeps the cumulative-normalised parameter table simple and
the camera-path determinism guarantee intact.

---

## 3. Look-at targets

A waypoint can specify what the camera should *point at*
while the cursor is on it. v1.8 supports two forms:

* **`look_at_position`** — a free 3D point in C4D world
  units. Cheapest path; no lookup needed.
* **`look_at_uid`** — a catalog uid resolved by the active
  `MetadataLookup`. Useful for "track Mars" without
  manually computing its coordinates.

Order of precedence at build time:

1. Explicit `orientation_quat` always wins (the artist has
   computed the exact pose they want).
2. `look_at_position` wins over `look_at_uid` (the position
   is final; the uid would re-resolve).
3. `look_at_uid` resolves through the lookup; if the lookup
   is missing or doesn't know the uid, the field is ignored
   and we fall through.
4. Default v1.4 behaviour: orient toward the next waypoint.
5. Last waypoint inherits the previous one's orientation.

The dialog's "Add Selected as Waypoint" button does not
populate `look_at_position` automatically — the artist sets
it explicitly when they want a look-at. (This is a v1.8 UX
choice; we may add a "Set look-at to current selection"
button in v1.9.)

---

## 4. Roll

`roll_deg` is the camera's rotation about its own forward
axis, in degrees, applied **after** the look-at / orient-
toward step. Defaults to 0 (no roll).

Roll interpolates linearly between waypoints. A waypoint
with `roll_deg=45` and the next with `roll_deg=0` produces
a continuous, monotone unroll across the segment.

Roll is composed onto the slerp output as a quaternion, so
the resulting orientation is still a unit quaternion — slerp
+ roll is a well-defined operation.

**Caveat.** Roll is a body-frame rotation, so a 360°
rotation produces no visible motion (it's the identity).
For continuous "barrel rolls" use multiple waypoints with
roll values that increment linearly — the slerp + roll
composition does not implement axis-angle accumulation.

---

## 5. Interpolation modes

`CameraPathConfig.interp_mode` selects between two position
interpolators:

* **`INTERP_SMOOTH`** (default) — the v1.4 Catmull-Rom
  spline. Curve passes through every waypoint exactly,
  with smooth tangent continuity. Can overshoot at sharp
  corners (use intermediate `coordinate` waypoints to
  tame).
* **`INTERP_LINEAR`** — straight line between waypoints.
  No overshoot, no smoothing. Useful for "constant-velocity
  flight" cinematics.

Mode applies to *position only*. Orientation always uses
slerp (which is the spherical analogue of "smooth" — there's
no compelling case for a "linear quaternion" mode). Epoch
always uses linear lerp.

The dialog's "Interp" combo box flips between the two.
Switching modes triggers a fresh path build the next time
the artist clicks Play / Preview / Scrub / Bake.

---

## 6. Path tessellation

`tessellate_path(path, samples_per_segment=N)` returns a
list of `(x, y, z)` points that approximate the camera
path's curve, suitable for a Cinema 4D `SplineObject`.

* For `INTERP_SMOOTH` the function samples the analytic
  Catmull-Rom curve at `N` points per segment plus the
  final endpoint.
* For `INTERP_LINEAR` it returns the same density (so the
  preview spline density doesn't visibly change when the
  artist flips modes).

Default `samples_per_segment=16`. Higher values produce
smoother previews but a heavier `SplineObject`. The dialog
uses the default.

The tessellation is **purely visual**. The playback engine
samples the analytic curve directly via `path.sample(t)` and
never consults the tessellation.

---

## 7. The dialog flow

A typical authoring session:

1. Click **New Mission** in the Missions tab.
2. Select a UNAV object → **Add Selected as Waypoint**.
3. (Optional) Hand-edit the waypoint's mission JSON in
   `~/.unav_pro/missions/<id>.json` to set `pause_seconds`,
   `look_at_position`, `roll_deg` — or use the dialog's
   `Reload` to re-read after editing.
4. Click **Preview Path** to drop a Cinema 4D
   `SplineObject` into the active document. Verify the
   curve geometry.
5. Adjust the **Interp** dropdown (`smooth` / `linear`) +
   the **Speed ×** value.
6. Click **▶ Play** or drag the **Scrub** slider to verify
   timing.
7. Click **Bake to Timeline** when the cinematic looks
   right.
8. Click **Clear Path Preview** to remove the spline (or
   leave it — it's cosmetic).

Per-waypoint pause / look-at / roll editing in the dialog UI
is reserved for v1.9; today the artist edits the mission
JSON directly and the dialog's `Reload` (Sync) button picks
up the changes.

---

## 8. Determinism

Every v1.8 extension preserves the v1.4 determinism contract:

* Same mission + same `CameraPathConfig` → byte-identical
  `CameraPath`.
* Same `CameraPath` + same parameter `t` → byte-identical
  `CameraSample`.
* Same `CameraPath` + same `BakeRange` → byte-identical
  `KeyframeRecord` list.

Tests in `test_v18_camera_path.py` assert this end-to-end.
