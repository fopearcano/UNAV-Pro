# UNAV Pro — Presentation Sequences

Reference for the v3.3 step-based sequence shape.

For the milestone overview see
[`V3_3_PRESENTATION_MODE.md`](V3_3_PRESENTATION_MODE.md).

---

## 1. The PresentationStep

```python
@dataclass
class PresentationStep:
    step_id: str
    title: str
    narration: str
    presenter_notes: str
    pause_seconds: float
    waypoint_ref: Optional[str]
    camera_position: Optional[Tuple[float, float, float]]
    camera_target: Optional[Tuple[float, float, float]]
    camera_fov_deg: Optional[float]
    epoch_jd: Optional[float]
    overlay_flags: Dict[str, bool]
    science_flags: Dict[str, bool]
    visible_annotation_indices: List[int]
    highlighted_annotation_indices: List[int]
    tags: List[str]
```

Every Optional field defaults to ``None``, which means
"inherit from the previous step." A step that only
changes the active annotation doesn't need to re-spell
the camera pose; the runtime resolver fills it in.

## 2. The PresentationSequence

```python
@dataclass
class PresentationSequence:
    presentation_id: str
    title: str
    description: str
    presenter_notes: str
    mission_ref: Optional[str]
    steps: List[PresentationStep]
    tags: List[str]
    created_at_iso: str
    updated_at_iso: str
    schema_version: int        # v3.3 ships 1
```

`mission_ref` is the optional v1.4 mission_id this
presentation drives. When set, waypoint refs in the
steps are resolved against that mission.

## 3. Inheritance

Each step's `Optional` field is either *populated*
(value applies) or *None* (inherit). The
`resolved_steps()` walker produces a list of
`ResolvedStep` records with every chain folded in.

Example:

```python
seq = PresentationSequence(steps=[
    PresentationStep(camera_position=(0, 0, 0)),
    PresentationStep(camera_position=None),       # inherits (0, 0, 0)
    PresentationStep(camera_position=(10, 0, 0)),
    PresentationStep(camera_position=None),       # inherits (10, 0, 0)
])
resolved = seq.resolved_steps()
# resolved[0].camera_position == (0, 0, 0)
# resolved[1].camera_position == (0, 0, 0)
# resolved[2].camera_position == (10, 0, 0)
# resolved[3].camera_position == (10, 0, 0)
```

The walker handles every Optional field uniformly:
camera pose, FOV, epoch, overlay flags, science flags,
annotation visibility / highlight.

## 4. Building a sequence

```python
from presentation import (
    PresentationSequence, PresentationStep,
)

seq = PresentationSequence(
    title="Voyager Cinematic",
    description="Ten-step talk through the outer planets.",
    mission_ref="voyager-arrival",
)

step1 = PresentationStep(
    title="Saturn approach",
    narration="Saturn fills the frame...",
    waypoint_ref="saturn",
    pause_seconds=8.0,
    overlay_flags={"show_distance_rings": True},
    visible_annotation_indices=[0, 1],
    highlighted_annotation_indices=[1],
)
seq.add_step(step1)
```

`add_step` enforces the cap (`MAX_STEPS_PER_PRESENTATION
= 200`) and refuses duplicate `step_id` values.

## 5. Reordering

```python
seq.move_step(step1.step_id, new_index=2)
```

Step ids are immutable, so external state (presenter
notes, marker bindings) survives reorder.

## 6. Validation

```python
errs = seq.validate()
if errs:
    print("\n".join(errs))
```

Empty list → safe to persist. The v3.3 validator
catches:

* unknown / future schema versions;
* duplicate step ids;
* negative pause durations;
* over-cap step counts.

## 7. JSON I/O

`to_json()` / `from_json()` produce stable,
indented JSON. Round-trips are byte-identical for the
populated fields (timestamps obviously change).

## 8. Tests

* `test_v33_presentation_sequence`.
