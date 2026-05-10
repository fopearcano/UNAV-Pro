"""v3.6 camera-rig tests."""

from __future__ import annotations

import pytest

from c4d_objects.camera_rigs import (
    CAMERA_RIGS_ROOT_NAME,
    RIG_KINDS,
    CameraRigDescriptor,
    RigBuildPlan,
    RigKind,
    build_camera_rig,
    descriptor_identity_key,
    ensure_camera_rigs_root,
    find_camera_rig,
    plan_camera_rig,
)
from c4d_objects.naming import SCENE_OBJECT_PREFIX
from c4d_objects.undo_policy import (
    OP_BUILD_CAMERA_RIG,
    OP_ENSURE_CAMERA_RIGS_ROOT,
    OP_REMOVE_CAMERA_RIG,
    UNDO_DELETE,
    UNDO_NEW,
    UNDO_POLICY,
    policy_for,
)


# ---------------------------------------------------------------------------
# RigKind + constants
# ---------------------------------------------------------------------------


def test_rig_kinds_complete():
    expected = {
        RigKind.ORBIT, RigKind.TARGET_FOLLOW,
        RigKind.FLYBY, RigKind.LOCKED_TARGET,
    }
    assert expected == set(RIG_KINDS)


def test_camera_rigs_root_name_uses_unav_prefix():
    assert CAMERA_RIGS_ROOT_NAME.startswith(SCENE_OBJECT_PREFIX)
    assert "CameraRigs" in CAMERA_RIGS_ROOT_NAME


# ---------------------------------------------------------------------------
# Descriptor naming determinism
# ---------------------------------------------------------------------------


def test_descriptor_root_name_deterministic():
    a = CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT)
    b = CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT)
    assert a.root_name() == b.root_name()


def test_descriptor_root_name_includes_kind():
    desc = CameraRigDescriptor(rig_id="saturn", kind=RigKind.FLYBY)
    assert "flyby" in desc.root_name()
    assert "saturn" in desc.root_name()


def test_descriptor_camera_and_target_names_distinct():
    desc = CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT)
    assert desc.camera_name() != desc.target_name()


def test_descriptor_short_summary_includes_label():
    desc = CameraRigDescriptor(
        rig_id="x", kind=RigKind.ORBIT, label="Saturn Orbit",
        target_position=(1, 2, 3),
    )
    s = desc.short_summary()
    assert "orbit" in s
    assert "Saturn Orbit" in s


# ---------------------------------------------------------------------------
# Identity key
# ---------------------------------------------------------------------------


def test_identity_key_same_for_same_kind_and_id():
    a = CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT)
    b = CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT, radius=999)
    assert descriptor_identity_key(a) == descriptor_identity_key(b)


def test_identity_key_differs_when_kind_differs():
    a = CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT)
    b = CameraRigDescriptor(rig_id="x", kind=RigKind.FLYBY)
    assert descriptor_identity_key(a) != descriptor_identity_key(b)


def test_identity_key_differs_when_id_differs():
    a = CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT)
    b = CameraRigDescriptor(rig_id="y", kind=RigKind.ORBIT)
    assert descriptor_identity_key(a) != descriptor_identity_key(b)


# ---------------------------------------------------------------------------
# plan_camera_rig
# ---------------------------------------------------------------------------


def test_plan_returns_build_plan_dataclass():
    desc = CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT)
    plan = plan_camera_rig(desc)
    assert isinstance(plan, RigBuildPlan)


def test_plan_lists_three_objects():
    desc = CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT)
    plan = plan_camera_rig(desc)
    assert len(plan.objects_to_create) == 3


def test_plan_first_entry_is_root_under_rigs():
    desc = CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT)
    plan = plan_camera_rig(desc)
    role, name = plan.objects_to_create[0]
    assert role == "rigs_root"
    assert name == desc.root_name()


def test_plan_includes_rig_kind_specific_note():
    for kind in RIG_KINDS:
        desc = CameraRigDescriptor(rig_id="x", kind=kind)
        plan = plan_camera_rig(desc)
        assert plan.notes  # at least one note
        # Most plans surface the kind name in the note;
        # locked-target uses the dashed form.
        joined = " ".join(plan.notes).lower()
        token = kind.value.replace("_", "-")
        assert (kind.value in joined) or (token in joined)


def test_plan_short_summary():
    desc = CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT)
    plan = plan_camera_rig(desc)
    assert "orbit" in plan.short_summary()
    assert "object" in plan.short_summary()


# ---------------------------------------------------------------------------
# Undo coverage
# ---------------------------------------------------------------------------


def test_undo_policy_covers_rig_ops():
    for op in (
        OP_BUILD_CAMERA_RIG, OP_REMOVE_CAMERA_RIG,
        OP_ENSURE_CAMERA_RIGS_ROOT,
    ):
        assert op in UNDO_POLICY


def test_build_camera_rig_records_new_and_delete():
    pol = policy_for(OP_BUILD_CAMERA_RIG)
    assert UNDO_NEW in pol
    assert UNDO_DELETE in pol  # for replacing existing


def test_remove_camera_rig_records_delete():
    assert UNDO_DELETE in policy_for(OP_REMOVE_CAMERA_RIG)


def test_ensure_camera_rigs_root_records_new():
    assert UNDO_NEW in policy_for(OP_ENSURE_CAMERA_RIGS_ROOT)


# ---------------------------------------------------------------------------
# C4D-bound builders raise outside the host
# ---------------------------------------------------------------------------


def test_ensure_camera_rigs_root_requires_c4d():
    with pytest.raises(RuntimeError):
        ensure_camera_rigs_root(None)


def test_build_camera_rig_requires_c4d():
    with pytest.raises(RuntimeError):
        build_camera_rig(
            None,
            CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT),
        )


def test_find_camera_rig_requires_c4d():
    with pytest.raises(RuntimeError):
        find_camera_rig(
            None,
            CameraRigDescriptor(rig_id="x", kind=RigKind.ORBIT),
        )
