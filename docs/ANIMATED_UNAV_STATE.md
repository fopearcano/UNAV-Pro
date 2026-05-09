# Animated UNAV State

The pure-Python frame-aware evaluator at the heart of v2.2.
Lives in `unav_pro/animation/animated_state.py`; tests drive
it directly without Cinema 4D.

For the milestone overview see
[`V2_2_ANIMATION_TIMELINE_INTEGRATION.md`](V2_2_ANIMATION_TIMELINE_INTEGRATION.md).

---

## 1. The contract

```python
from animation import (
    AnimatedStateConfig,
    evaluate_animated_state,
)
from c4d_objects.timeline_keys import BakeRange

timeline = evaluate_animated_state(
    mission, path,
    frame_range=BakeRange(start_frame=0, end_frame=240, fps=30),
    config=AnimatedStateConfig(
        fov_rad=math.radians(45),
        sync_markers=[60, 120, 180],
    ),
)
```

`evaluate_animated_state` is a pure function. Same inputs →
byte-identical output. It walks every frame in the bake
range and emits one `AnimatedSample` per frame plus an
``AnimatedTimeline.keyframes`` list ready for the v1.8
``apply_keyframes`` applier.

---

## 2. Per-frame fields

```python
@dataclass
class AnimatedSample:
    frame: int
    progress: float
    seconds: float
    navigator_position: Vec3
    camera_position: Vec3
    camera_orientation_quat: Quaternion
    rotation_hpb: Tuple[float, float, float]
    fov_rad: Optional[float] = None
    epoch_jd: Optional[float] = None
    waypoint_index: int = 0
    is_sync_marker: bool = False
```

* **`frame`** — Cinema 4D frame number.
* **`progress`** — mission progress in `[0, 1]`. Linear
  mapping from `frame` to the v1.8 ``frame_to_progress``
  helper.
* **`seconds`** — wall-clock seconds relative to
  `frame_range.start_frame`.
* **`navigator_position` vs `camera_position`** — split
  when the waypoint carries a `camera_offset` (v1.9). The
  navigator anchors at the waypoint; the camera samples
  the offset path. With `apply_camera_offset_to_navigator
  = False`, both are identical.
* **`camera_orientation_quat`** — UNAV-convention
  ``(w, x, y, z)`` unit quaternion from
  ``CameraPath.sample``.
* **`rotation_hpb`** — Cinema 4D Heading-Pitch-Bank radians,
  via `c4d_objects.timeline_keys.quaternion_to_hpb`. The
  v1.8 applier consumes this verbatim.
* **`fov_rad`** — the constant FOV from the config (v2.2
  doesn't animate FOV; this field is the same for every
  sample).
* **`epoch_jd`** — the path's interpolated epoch at this
  frame, via the v1.4 lerp.
* **`waypoint_index`** — the segment index that owns this
  sample (forwarded from the camera path).
* **`is_sync_marker`** — True iff this frame is in
  `timeline.sync_marker_frames`.

---

## 3. The timeline

```python
@dataclass
class AnimatedTimeline:
    samples: List[AnimatedSample]
    keyframes: List[KeyframeRecord]
    waypoint_arrival_frames: List[int]
    sync_marker_frames: List[int]
    epoch_change_frames: List[int]
    warnings: List[str]
```

* `samples` — one per frame; the per-frame log + any UI
  preview reads.
* `keyframes` — v1.8 `KeyframeRecord` rows. The
  ``c4d_objects.timeline_keys.apply_keyframes`` applier
  consumes them unchanged.
* `waypoint_arrival_frames` — frames at which each
  waypoint's anchor lands. Computed from
  ``path.cumulative_normalised``.
* `sync_marker_frames` — sorted, deduplicated union of:
  * the artist's explicit `config.sync_markers` list, and
  * (when `config.waypoint_arrival_markers=True`)
    `waypoint_arrival_frames`.
* `epoch_change_frames` — frames at which the path's
  per-waypoint epoch changes. Computed at
  *waypoint granularity*, **not** by sampling the
  per-frame interpolated epoch (which would fire every
  frame within a segment because of the v1.4 epoch lerp).
* `warnings` — human-readable strings the dialog appends to
  the log. v2.2 emits them for:
  * fewer than two resolvable waypoints,
  * more than 32 sync markers (the visible-sector pipeline
    is the plugin's most expensive operation).

---

## 4. The single-frame read API

`evaluate_at_frame(mission, path, frame, frame_range, config)`
returns just one `AnimatedSample` — useful when the dialog
wants to preview without paying for the full timeline.

`evaluate_at_seconds(mission, path, seconds, frame_range, config)`
is the seconds-precision wrapper.

Both return ``None`` for empty / single-waypoint paths.
Out-of-range frames clamp to the bake range.

The standalone ``animation.evaluate_at_frame`` mirrors
``Playback.evaluate_at_frame`` but skips the playback engine
entirely. The dialog uses the standalone helper so it
doesn't need a Playback instance to drive the preview button.

---

## 5. Determinism

The evaluator is deterministic by construction:

* Closed-form Catmull-Rom / slerp / linear lerp via the
  v1.4 ``CameraPath`` builder.
* No randomness, no external state, no time-of-day
  dependency.
* Sync markers are a sorted set; epoch-change frames are
  computed via stable waypoint indexing.

Tests
(`test_v22_animated_state.py::test_animated_state_is_deterministic`)
sample two consecutive runs and assert byte equality of the
sample list, the sync marker list, and the epoch-change
frame list.

---

## 6. The frame ↔ time helpers

Three helpers re-exported from the animation module:

* `frame_to_progress(frame, range)` — same as the v1.8
  helper, re-exposed for callers that don't want to import
  from `timeline_keys`.
* `frame_to_seconds(frame, range)` — wall-clock seconds
  relative to `range.start_frame`.
* `seconds_to_frame(seconds, range)` — inverse, with
  rounding to the nearest integer frame.

These are pure functions over the v1.8 ``BakeRange``;
neither the bake range nor the helpers know about a Cinema
4D document.

---

## 7. Caveats

* **No FOV animation.** The `fov_rad` field is constant
  across the timeline — v2.2 design choice. A future v2.x
  can add a `FovKeyframe` track without changing the
  evaluator's signature; keyframes already accept
  `fov_rad=None` per record.
* **No bank/roll keyframes.** The v1.8 ``rotation_hpb``
  triple already carries roll (it's just a body-frame Z
  rotation), but the evaluator doesn't expose a separate
  roll track.
* **No looped playback.** The evaluator walks `[start,
  end]` linearly. A future v2.x could add a loop count.
* **No easing.** Linear timing per segment, same as the
  v1.4 / v1.8 contract.
