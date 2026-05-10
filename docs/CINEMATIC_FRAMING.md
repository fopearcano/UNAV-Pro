# UNAV Pro — Cinematic Framing

Reference for `unav_pro/cinematic/framing.py`.

For the workflow overview see
[`V3_6_PROCEDURAL_CINEMATIC_HELPERS.md`](V3_6_PROCEDURAL_CINEMATIC_HELPERS.md).

---

## 1. The five framing presets

| Preset | Apparent fraction of frame | Use case |
| --- | --- | --- |
| `CLOSE` | ~60% | Subject fills the frame; portrait-style shot of a star or planet. |
| `MEDIUM` | ~30% | Default cinematic mid-shot. |
| `WIDE` | ~12% | Subject sits in context; environment matters as much as the subject. |
| `EXTREME_WIDE` | ~3% | Subject is a noticeable speck in a dense field. |
| `EXTREME_SCALE` | ~0.5% | Subject is a fraction of a pixel — used for "you are here, the universe is huge" shots. |

Each preset clamps the framing distance to a
sensible range (`min_distance` / `max_distance`)
so a tiny subject doesn't push the camera into the
geometry, and a galaxy-scale subject doesn't push
the camera past the observable universe.

## 2. Framing math

The trig is straight first-principles:

```
apparent_subject_fov = 2 · atan(extent / 2d)
apparent_subject_fov = preset_fraction · camera_fov
⇒ d = extent / (2 · tan(preset_fraction · camera_fov / 2))
```

Implemented in
`framing_distance_for_subject_size(...)`:

```python
from cinematic import (
    framing_distance_for_subject_size, FramingPreset,
)

# Saturn: ~120 000 km diameter ≈ 0.0388 pc.
distance = framing_distance_for_subject_size(
    subject_extent=0.0388,
    camera_horizontal_fov_deg=36.0,
    preset=FramingPreset.MEDIUM,
)
# → distance ≈ 0.21 pc (Saturn fills 30% of frame at 36° FOV)
```

## 3. Auto-look-at

`look_at_quaternion(...)` builds a quaternion whose
camera-local **−Z** points at the target (the
Cinema 4D camera-forward convention):

```python
from cinematic import look_at_quaternion

q = look_at_quaternion(
    camera_position=(0, 0, 100),
    target=(0, 0, 0),
)
```

The math handles the degenerate case (camera +
target coincide ⇒ identity quat) defensively.

## 4. Composing a complete pose

`compose_look_at_pose(...)` is the one-stop helper:

```python
from cinematic import compose_look_at_pose, FramingPreset

pose = compose_look_at_pose(
    target=(0, 0, 0),
    subject_extent=2.0,
    preset=FramingPreset.WIDE,
    pull_back_axis=(0.0, 0.5, 1.0),       # off-axis pull-back
    target_offset=(1.0, 0.0, 0.0),         # subject sits off-centre
)
print(pose.position, pose.orientation, pose.fov_deg)
```

Returns a `CameraPose` with position + target +
orientation + FOV. The dialog hands this to the
v1.4 mission editor as the "next waypoint pose"
or to the v1.8 timeline baker as "this is where
the camera should be at frame N."

## 5. Smooth look-at blending

`blend_look_at(qa, qb, t)` is a slerp between two
look-at quaternions:

```python
from cinematic import blend_look_at, look_at_quaternion

q_a = look_at_quaternion(camera_position=(0, 0, 100), target=(0, 0, 0))
q_b = look_at_quaternion(camera_position=(0, 0, 100), target=(50, 0, 0))

# Halfway between looking at the origin + looking at (50, 0, 0):
q_mid = blend_look_at(q_a, q_b, 0.5)
```

Use this when you want the camera to "swing
gracefully" from one target to another across N
frames rather than snapping.

## 6. Per-waypoint framing

`WaypointFraming` lets a mission carry per-waypoint
framing decisions:

```python
from cinematic import WaypointFraming, FramingPreset

framing = WaypointFraming(
    waypoint_index=2,
    preset=FramingPreset.CLOSE,
    target_offset=(2.0, 0.0, 0.0),
    fov_deg=24.0,
)
```

Pure data; the dialog stores it alongside the
mission JSON (in v1.9 mission annotations) without
mutating the v1.4 schema.

## 7. Tests

* `test_v36_framing` — preset table coverage,
  framing distance trig at known angles,
  look-at quaternion shape (identity for
  degenerate inputs), slerp shape +
  endpoint-preservation, `WaypointFraming`
  serialisation.
