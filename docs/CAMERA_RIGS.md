# UNAV Pro — Camera Rigs

Reference for `unav_pro/c4d_objects/camera_rigs.py`.

For the workflow overview see
[`V3_6_PROCEDURAL_CINEMATIC_HELPERS.md`](V3_6_PROCEDURAL_CINEMATIC_HELPERS.md).

---

## 1. The four rig kinds

| Kind | Use case |
| --- | --- |
| `orbit` | Camera revolves around a target null. Use for "look at the system from outside" shots. |
| `target_follow` | Camera follows a route while always pointing at a target. Use for "fly through a sector while watching X." |
| `flyby` | Camera traverses a pre-built spline, passes alongside the target at midpoint. Use for "approach + flyby + depart" shots. |
| `locked_target` | Camera position is hand-keyed; orientation is constrained to look at the target. Use when the artist wants direct keyframe control of position but auto-look-at. |

## 2. Hierarchy

Every rig lives under `UNAV_CameraRigs` (a sibling
of `UNAV_Project`):

```
UNAV_CameraRigs
└── UNAV_Rig_<kind>_<rig_id>
    ├── UNAV_Rig_<kind>_<rig_id>__Target   ← target null
    └── UNAV_Rig_<kind>_<rig_id>__Camera   ← actual camera object
```

* The wrapper null carries a UNAV marker so cleanup
  walks find it.
* The target null is a freestanding `c4d.Onull`.
  The artist can re-parent it under any scene
  object (a Gaia star, a JPL planet, a route
  waypoint).
* The camera object is a stock `c4d.Ocamera`. UNAV
  doesn't subclass camera; this is intentional so
  the rig is renderer-friendly.

## 3. Naming determinism

`CameraRigDescriptor.root_name()` produces the same
name for the same `(kind, rig_id)` pair every time.
Re-running `build_camera_rig(...)` against an
existing rig **replaces in place** rather than
duplicating — the v3.6 builder removes the previous
incarnation inside the same undo block before
building the new one.

## 4. Building a rig

```python
from c4d_objects.camera_rigs import (
    CameraRigDescriptor, RigKind, build_camera_rig,
)

descriptor = CameraRigDescriptor(
    rig_id="saturn_orbit",
    kind=RigKind.ORBIT,
    label="Saturn Orbit",
    target_position=(100.0, 0.0, 0.0),
    radius=30.0,
)
rig_root = build_camera_rig(doc, descriptor)
```

The c4d-bound builder:

1. Ensures `UNAV_CameraRigs` exists
   (idempotent; AddUndo'd if newly created).
2. Drops any prior rig with the same root name
   (UNDO_DELETE-tracked).
3. Creates the wrapper null + target null + camera
   object (each UNDO_NEW-tracked).
4. Returns the wrapper null.

Outside Cinema 4D the builder raises
`RuntimeError`. Use `plan_camera_rig(descriptor)`
for tests + previews.

## 5. Idempotency

```python
from c4d_objects.camera_rigs import descriptor_identity_key

a = CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT)
b = CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT)
descriptor_identity_key(a) == descriptor_identity_key(b)  # True
```

Two descriptors that share `(kind, rig_id)` refer
to the same rig. The dialog uses this to decide
"create new" vs. "update existing."

## 6. Undo coverage

Every rig operation lives in v3.45's
`UNDO_POLICY`:

| Operation | Expected UNDOTYPE(s) |
| --- | --- |
| `build_camera_rig` | `UNDO_NEW`, `UNDO_DELETE` |
| `remove_camera_rig` | `UNDO_DELETE` |
| `ensure_camera_rigs_root` | `UNDO_NEW` |

Tests cover this in
`test_v36_camera_rigs::test_undo_policy_covers_rig_ops`.

## 7. Keeping rigs renderer-friendly

UNAV doesn't add render-affecting tags to rigs.
The artist:

* picks the active camera via Cinema 4D's standard
  *Set Active Camera* command;
* renders with whichever engine they have
  installed (Standard / Redshift / Octane /
  Arnold).

The rig's wrapper null carries a UNAV marker for
discovery, but no render-time data. This keeps the
rig deterministic across renderer choices.

## 8. Tests

* `test_v36_camera_rigs` — descriptor identity,
  build-plan shape, naming determinism, c4d-bound
  raise outside the host, undo-policy coverage.
