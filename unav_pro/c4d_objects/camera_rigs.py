"""v3.6 camera-rig descriptors + builders.

Four cinematic camera rigs:

* **Orbit rig** — camera follows a circular orbit
  around a target null. The target is a separate
  null the artist can re-parent to anything.
* **Target-follow rig** — camera + target null +
  spline constraint placeholder; the camera follows
  a route while always pointing at the target.
* **Flyby rig** — camera traverses a pre-built
  spline that starts behind the target, passes
  alongside it, and ends past it.
* **Locked-target rig** — camera is constrained to
  always point at a target null without moving on
  its own; useful for hand-keyed motion.

Every rig is **declarative** — the
``CameraRigDescriptor`` records the rig kind +
parameters; the c4d-bound builder reads it and
materialises the actual ``BaseObject`` tree under
``UNAV_CameraRigs`` (a sibling of v3.1's
``UNAV_Project``).

Pure stdlib in the planning + descriptor layer.
``build_camera_rig`` raises ``RuntimeError`` outside
Cinema 4D.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False

from .naming import SCENE_OBJECT_PREFIX, safe_token


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


CAMERA_RIGS_ROOT_NAME: str = f"{SCENE_OBJECT_PREFIX}CameraRigs"

#: Tag suffix the rig builder appends to the camera
#: object's name so it's unambiguous in the OM.
CAMERA_OBJECT_SUFFIX: str = "Camera"

#: Tag suffix for the target null inside each rig.
TARGET_OBJECT_SUFFIX: str = "Target"


# ---------------------------------------------------------------------------
# Rig kinds
# ---------------------------------------------------------------------------


class RigKind(str, Enum):
    """Four cinematic rig kinds."""

    ORBIT = "orbit"
    TARGET_FOLLOW = "target_follow"
    FLYBY = "flyby"
    LOCKED_TARGET = "locked_target"


RIG_KINDS = tuple(RigKind)


# ---------------------------------------------------------------------------
# Descriptor
# ---------------------------------------------------------------------------


Vec3 = Tuple[float, float, float]


@dataclass
class CameraRigDescriptor:
    """Declarative description of one camera rig.

    Pure data; no Cinema 4D imports here. Tests
    construct + serialise these without a host."""

    rig_id: str
    kind: RigKind
    label: str = ""
    target_position: Vec3 = (0.0, 0.0, 0.0)
    radius: float = 10.0
    fov_deg: float = 36.0
    extra: dict = field(default_factory=dict)

    def short_summary(self) -> str:
        return (
            f"rig[{self.kind.value}] '{self.label or self.rig_id}' "
            f"target={self.target_position}"
        )

    def root_name(self) -> str:
        """Object name the rig's wrapper null carries.
        Stable across rebuilds (same input → same
        name)."""
        return (
            f"{SCENE_OBJECT_PREFIX}Rig_{self.kind.value}_"
            f"{safe_token(self.rig_id)}"
        )

    def camera_name(self) -> str:
        return f"{self.root_name()}__{CAMERA_OBJECT_SUFFIX}"

    def target_name(self) -> str:
        return f"{self.root_name()}__{TARGET_OBJECT_SUFFIX}"


# ---------------------------------------------------------------------------
# Build plan (pure)
# ---------------------------------------------------------------------------


@dataclass
class RigBuildPlan:
    """Plan the c4d-bound builder reads.

    ``objects_to_create`` is a list of
    ``(parent_role, name)`` pairs the builder walks
    in order. The "parent_role" is one of
    ``"rigs_root"`` / ``"rig_root"``.
    """

    descriptor: CameraRigDescriptor
    objects_to_create: List[Tuple[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def short_summary(self) -> str:
        return (
            f"plan {self.descriptor.kind.value} "
            f"({len(self.objects_to_create)} object(s))"
        )


def plan_camera_rig(
    descriptor: CameraRigDescriptor,
) -> RigBuildPlan:
    """Compose a build plan for a rig descriptor.

    Pure helper — produces a deterministic list of
    objects the c4d-bound builder will materialise.
    Tests assert the plan shape without booting
    Cinema 4D."""
    plan = RigBuildPlan(descriptor=descriptor)
    plan.objects_to_create.append(
        ("rigs_root", descriptor.root_name()),
    )
    plan.objects_to_create.append(
        ("rig_root", descriptor.target_name()),
    )
    plan.objects_to_create.append(
        ("rig_root", descriptor.camera_name()),
    )
    if descriptor.kind is RigKind.ORBIT:
        plan.notes.append(
            f"orbit radius={descriptor.radius:.2f}; "
            "camera revolves around the target null"
        )
    elif descriptor.kind is RigKind.TARGET_FOLLOW:
        plan.notes.append(
            "target-follow: camera follows a route while "
            "looking at the target null (route binding handled "
            "by the dialog)"
        )
    elif descriptor.kind is RigKind.FLYBY:
        plan.notes.append(
            "flyby: camera traverses a pre-built spline + "
            "looks at the target null at midpoint"
        )
    else:  # LOCKED_TARGET
        plan.notes.append(
            "locked-target: camera position is hand-keyed; "
            "orientation is constrained to look at target"
        )
    return plan


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------


def descriptor_identity_key(
    descriptor: CameraRigDescriptor,
) -> Tuple[str, str]:
    """Stable identity key for "is this the same rig?".

    Two descriptors that share both kind + rig_id
    refer to the same on-disk rig and the c4d-bound
    builder treats them as updates rather than new
    creations.
    """
    return (descriptor.kind.value, descriptor.rig_id)


# ---------------------------------------------------------------------------
# C4D-bound builder
# ---------------------------------------------------------------------------


def _require_c4d() -> None:
    if not _C4D_AVAILABLE:
        raise RuntimeError(
            "camera_rigs: this code path requires Cinema 4D; "
            "use the pure planners (plan_camera_rig) outside the host."
        )


def ensure_camera_rigs_root(doc):
    """Ensure ``UNAV_CameraRigs`` exists at the
    document root. Returns the null. Idempotent."""
    _require_c4d()
    obj = doc.GetFirstObject()
    while obj is not None:
        try:
            if obj.GetName() == CAMERA_RIGS_ROOT_NAME:
                return obj
        except Exception:  # noqa: BLE001
            pass
        obj = obj.GetNext()
    null = c4d.BaseObject(c4d.Onull)
    null.SetName(CAMERA_RIGS_ROOT_NAME)
    doc.InsertObject(null)
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, null)
    return null


def build_camera_rig(
    doc, descriptor: CameraRigDescriptor,
):
    """Materialise ``descriptor`` under
    ``UNAV_CameraRigs``. Idempotent: a rig with the
    same identity key replaces in place rather than
    duplicating.

    Outside Cinema 4D this raises ``RuntimeError`` —
    use ``plan_camera_rig`` for tests + previews.
    """
    _require_c4d()
    rigs_root = ensure_camera_rigs_root(doc)
    plan = plan_camera_rig(descriptor)
    # Drop a previous rig with the same root name so
    # the builder is idempotent.
    existing = rigs_root.GetDown()
    while existing is not None:
        nxt = existing.GetNext()
        try:
            if existing.GetName() == descriptor.root_name():
                doc.AddUndo(c4d.UNDOTYPE_DELETE, existing)
                existing.Remove()
        except Exception:  # noqa: BLE001
            pass
        existing = nxt
    # Build the new tree.
    rig_root = c4d.BaseObject(c4d.Onull)
    rig_root.SetName(descriptor.root_name())
    rig_root.InsertUnder(rigs_root)
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, rig_root)
    target = c4d.BaseObject(c4d.Onull)
    target.SetName(descriptor.target_name())
    target.SetRelPos(c4d.Vector(*descriptor.target_position))
    target.InsertUnder(rig_root)
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, target)
    camera = c4d.BaseObject(c4d.Ocamera)
    camera.SetName(descriptor.camera_name())
    camera.InsertUnder(rig_root)
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, camera)
    return rig_root


def find_camera_rig(doc, descriptor: CameraRigDescriptor):
    """Look up an existing rig by descriptor. Returns
    ``None`` when not present."""
    _require_c4d()
    obj = doc.GetFirstObject()
    rigs_root = None
    while obj is not None:
        try:
            if obj.GetName() == CAMERA_RIGS_ROOT_NAME:
                rigs_root = obj
                break
        except Exception:  # noqa: BLE001
            pass
        obj = obj.GetNext()
    if rigs_root is None:
        return None
    child = rigs_root.GetDown()
    target_name = descriptor.root_name()
    while child is not None:
        try:
            if child.GetName() == target_name:
                return child
        except Exception:  # noqa: BLE001
            pass
        child = child.GetNext()
    return None
