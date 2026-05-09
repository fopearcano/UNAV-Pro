# Timeline Baking

How the v1.8 voyage system writes a mission's camera path
into Cinema 4D's timeline as keyframes. The reference
implementation lives in
`unav_pro/c4d_objects/timeline_keys.py`.

---

## 1. The contract

> Given a built `CameraPath` and a `BakeRange`, produce one
> `KeyframeRecord` per integer frame in the range, then
> write those records as keyframes on a navigator null and a
> camera object.

The pure-Python *generation* path is testable without Cinema
4D; the *application* path is c4d-bound and only fires when
the dialog runs inside the host.

This separation is intentional: v1.8 acceptance criteria
require "keyframe data generation without requiring C4D".
Tests cover only the generator; the applier is a thin wrapper
the dialog calls at runtime.

---

## 2. Frame range and FPS

```python
@dataclass
class BakeRange:
    start_frame: int = 0
    end_frame: int = 240
    fps: int = 30
    include_fov: bool = False
    fov_rad: Optional[float] = None
```

The bake operates on a half-open inclusive integer range
`[start_frame, end_frame]` (i.e. `end_frame - start_frame +
1` frames). The frame count is bounded:

* `MIN_FRAMES_FOR_BAKE = 2` — single-frame baking is
  meaningless (no curve to draw between keys).
* `MAX_FRAMES_FOR_BAKE = 36_000` — 10 minutes at 60 fps.
  Above this the helper raises; the artist can split the
  mission or lower the FPS.

`fps` defaults to 30 but the dialog reads the active C4D
document's project FPS so the bake matches the host's
playback rate.

---

## 3. The mapping

The mission's normalised `[0, 1]` progress maps **uniformly**
into the frame range:

```
progress = (frame - start_frame) / (end_frame - start_frame)
```

No per-segment quantisation. No easing. Same input → same
output. If an artist wants 3 seconds at Mars in a 10-second
mission, they set `pause_seconds=3.0` on Mars; the bake
inherits the dwell automatically through the path's
`cumulative_normalised` table.

`frame_to_progress(frame, range)` and
`progress_to_frame(progress, range)` are pure helpers the
dialog uses to keep the timeline cursor synchronised with
the playback engine's progress slider.

---

## 4. What gets written

```python
@dataclass
class KeyframeRecord:
    frame: int
    position: Tuple[float, float, float]    # C4D world units
    rotation_hpb: Tuple[float, float, float] # radians, C4D HPB convention
    fov_rad: Optional[float] = None
```

The applier writes each record as keyframes on:

| Channel             | Object       | When                                                 |
|---------------------|--------------|------------------------------------------------------|
| Position            | Navigator    | `apply_position_to_navigator=True` (default).        |
| Position            | Camera       | `apply_position_to_camera=True` (default).           |
| Rotation HPB        | Camera       | `apply_rotation_to_camera=True` (default).           |
| FOV                 | Camera       | `apply_fov_to_camera=True` and `record.fov_rad` set. |

The navigator gets position-only; rotation lives on the
camera object. This matches Cinema 4D's typical rig where
the navigator is a "tracking null" you parent the camera to,
or where the navigator is a position anchor the artist drives
with handles.

The applier wraps every write in a single `StartUndo` /
`EndUndo` block so the entire bake is one undo step. After
the bake, `EventAdd` fires once.

---

## 5. Quaternion → HPB

Cinema 4D's camera object stores rotation as Heading-Pitch-
Bank (HPB) Euler angles in radians. The voyage system uses
unit quaternions internally. The conversion lives in
`quaternion_to_hpb(q)`:

* Normalises the input defensively. A zero quaternion
  becomes the identity.
* Detects gimbal-lock (|pitch| ≈ 90°) and folds heading +
  bank into a single rotation about ±Y so the bake doesn't
  produce 180° flips.
* Standard Tait-Bryan ZYX decomposition otherwise.

Tests in `test_v18_timeline_keys.py::test_quaternion_to_hpb_*`
assert the round-trip (identity → zero HPB; small rotations
about each axis decompose correctly; gimbal-lock case
returns finite values).

---

## 6. Visible-sector decoupling

The bake **never** triggers a visible-sector sync. This is
explicit in the v1.8 acceptance criteria:

> visible-sector generation remains decoupled from animation

If an artist needs the visible sector to update during
playback of the baked timeline, they can add a separate
"sync at frame X" event by hand, or trigger
`Sync Visible Sector` as the playback hits known anchor
frames. The bake itself only writes camera + navigator
position / rotation channels.

This decoupling is what lets a multi-minute mission bake in
a few seconds rather than spending most of that time
re-streaming the catalog.

---

## 7. Failure modes

| Condition                     | Behaviour                                       |
|-------------------------------|-------------------------------------------------|
| Empty path                    | `generate_keyframes` returns `[]`. Applier no-ops. |
| `end_frame <= start_frame`    | `BakeRange` raises `ValueError`. Dialog logs.   |
| Frame range below floor       | Same — `MIN_FRAMES_FOR_BAKE = 2`.               |
| Frame range above cap         | Same — `MAX_FRAMES_FOR_BAKE = 36_000`.          |
| `fps <= 0`                    | `BakeRange` raises.                             |
| C4D not importable            | `apply_keyframes` returns 0. The dialog logs   |
|                               | the empty result.                               |
| Navigator / camera both None  | Applier no-ops; logs a warning.                 |

The dialog catches every `ValueError` and surfaces a one-
line "Mission: bake refused — <reason>" log so the artist
can fix the inputs without leaving the panel.

---

## 8. The pure-Python applier sketch

The current `apply_keyframes` in `c4d_objects/timeline_keys.py`
is a v1.8 **first-pass** implementation. It correctly:

* Wraps the bake in a single undo block.
* Handles the C4D import boundary (no-op when c4d is
  missing).
* Iterates records once per object channel.

It is intentionally **simple-minded** about the per-channel
key-set protocol: future polish passes may switch to per-
component `DescID(c4d.ID_BASEOBJECT_REL_POSITION,
c4d.VECTOR_X)` setters for finer control over scalar curves
vs. vector tracks. The v1.8 tests do not cover this code
path (it's c4d-bound); the dialog's own bake button is the
only caller.

If you find a baked key writing to the wrong DescID, the fix
is local to `_set_position_key` / `_set_rotation_key` /
`_set_fov_key` / `_record_track_key`.
