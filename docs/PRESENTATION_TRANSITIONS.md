# UNAV Pro — Presentation Transitions

Reference for `unav_pro/presentation/transitions.py`.

For the milestone overview see
[`V3_8_EXHIBITION_WORKFLOWS.md`](V3_8_EXHIBITION_WORKFLOWS.md).

---

## 1. The scope (and what's not in it)

v3.8 transitions are **navigation-state
sequencing**: how state changes between two
presentation steps unfold over a fixed number of
intermediate frames. Pure deterministic
computation.

What's **not** in scope:

* Real rendering fades. The
  `crossfade_placeholder` transition emits
  metadata only; no fade is rendered. (UNAV is
  not a renderer.)
* Audio cross-fades.
* Per-frame heavy rebuilds. The transition
  sequencer produces a flat list of state
  records; nothing here drives Cinema 4D.

## 2. Four transition kinds

```python
class TransitionKind(str, Enum):
    HARD_CUT = "hard_cut"                  # 0 frames
    SMOOTH_CAMERA = "smooth_camera"        # slerp/lerp camera
    CROSSFADE_PLACEHOLDER = "crossfade_placeholder"
    WAYPOINT_PAUSE = "waypoint_pause"      # hold then snap
```

* `hard_cut` — instantaneous swap. Sequencer
  emits 0 frames.
* `smooth_camera` — N evenly-spaced frames; each
  frame interpolates camera position + target +
  FOV between source and destination steps.
  Pure linear interpolation in v3.8; a future
  v3.x can swap in slerp / Catmull-Rom.
* `crossfade_placeholder` — N frames carrying a
  `crossfade_fraction` field the dialog can
  surface as a UI hint. Camera positions still
  lerp between source + destination so the
  underlying motion is sane.
* `waypoint_pause` — N "hold" frames on the
  source step. Used to hold a waypoint for a
  configured `pause_seconds` before snapping to
  the next step.

## 3. TransitionSpec

```python
@dataclass(frozen=True)
class TransitionSpec:
    kind: TransitionKind = TransitionKind.HARD_CUT
    frame_count: int = 12
    pause_seconds: float = 0.0   # WAYPOINT_PAUSE only
```

`frame_count >= 0`; `pause_seconds >= 0`. The
`__post_init__` validation rejects negatives.

## 4. Sequencing one transition

```python
from presentation import (
    sequence_transition, StepProjection, TransitionSpec,
    TransitionKind,
)

source = StepProjection(
    step_id="a", camera_position=(0, 0, 0),
    camera_target=(10, 0, 0),
)
dest = StepProjection(
    step_id="b", camera_position=(0, 0, 100),
    camera_target=(10, 0, 0),
)
frames = sequence_transition(
    source=source, destination=dest,
    spec=TransitionSpec(
        kind=TransitionKind.SMOOTH_CAMERA,
        frame_count=12,
    ),
)
```

The frames list is deterministic — same inputs
always produce the same output. Each frame
carries:

* `index` — re-based when used inside
  `TransitionSequence`.
* `t` — parametric position in `[0.0, 1.0]`.
* `camera_position` / `camera_target` /
  `fov_deg` — interpolated values.
* `crossfade_fraction` — populated only for
  `crossfade_placeholder`.
* `holds_source` — populated only for
  `waypoint_pause`.

## 5. Multi-step sequencing

`build_transition_sequence(...)` composes a
flat sequence across N steps + N-1 specs:

```python
sequence = build_transition_sequence(
    steps=[step_a, step_b, step_c],
    specs=[
        TransitionSpec(kind=TransitionKind.SMOOTH_CAMERA, frame_count=8),
        TransitionSpec(kind=TransitionKind.HARD_CUT),
    ],
)
print(sequence.short_summary())
```

The frame indices are re-based 0..N. Notes
reflect placeholder + pause transitions so the
dialog can surface them in the cue sheet.

## 6. Determinism

Every helper is pure. Tests assert byte-stable
output for byte-stable input. No PRNG, no global
state.

## 7. Tests

* `test_v38_transitions` — every kind +
  multi-step sequencing + endpoint preservation
  + spec validation + determinism.
