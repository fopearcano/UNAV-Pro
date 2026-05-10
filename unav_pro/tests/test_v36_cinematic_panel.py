"""v3.6 cinematic-panel facade tests."""

from __future__ import annotations

import pytest

from cinematic import (
    CameraPose,
    DriftParameters,
    FlybyParameters,
    FramingPreset,
    OrbitParameters,
    SmoothingMode,
)
from c4d_objects.camera_rigs import RigBuildPlan, RigKind
from ui.cinematic_panel import (
    CinematicPanelError,
    MotionTrackPreview,
    apply_cinematic_smoothing_action,
    auto_frame_target_action,
    create_flyby_rig_action,
    create_locked_target_rig_action,
    create_orbit_rig_action,
    create_target_follow_rig_action,
    enable_drift_action,
    preview_flyby_motion,
    preview_orbit_motion,
    select_framing_preset_action,
)


# ---------------------------------------------------------------------------
# auto_frame_target
# ---------------------------------------------------------------------------


def test_auto_frame_returns_camera_pose():
    pose = auto_frame_target_action(
        target=(0, 0, 0), subject_extent=1.0,
    )
    assert isinstance(pose, CameraPose)


def test_auto_frame_rejects_zero_extent():
    with pytest.raises(CinematicPanelError):
        auto_frame_target_action(target=(0, 0, 0), subject_extent=0.0)


def test_auto_frame_close_pulls_camera_in():
    pose_close = auto_frame_target_action(
        target=(0, 0, 0), subject_extent=1.0,
        preset=FramingPreset.CLOSE,
    )
    pose_wide = auto_frame_target_action(
        target=(0, 0, 0), subject_extent=1.0,
        preset=FramingPreset.WIDE,
    )
    # Wide framing puts the camera farther from the subject.
    import math
    d_close = math.sqrt(sum((pose_close.position[i] - 0) ** 2 for i in range(3)))
    d_wide = math.sqrt(sum((pose_wide.position[i] - 0) ** 2 for i in range(3)))
    assert d_close < d_wide


# ---------------------------------------------------------------------------
# Rig creation
# ---------------------------------------------------------------------------


def test_create_orbit_rig_returns_plan():
    plan = create_orbit_rig_action(
        rig_id="saturn", target=(100, 0, 0), radius=20.0,
    )
    assert isinstance(plan, RigBuildPlan)
    assert plan.descriptor.kind is RigKind.ORBIT
    assert plan.descriptor.rig_id == "saturn"
    assert plan.descriptor.radius == 20.0


def test_create_orbit_requires_rig_id():
    with pytest.raises(CinematicPanelError):
        create_orbit_rig_action(rig_id="", target=(0, 0, 0))


def test_create_orbit_rejects_zero_radius():
    with pytest.raises(CinematicPanelError):
        create_orbit_rig_action(rig_id="x", target=(0, 0, 0), radius=0.0)


def test_create_flyby_rig_returns_plan():
    plan = create_flyby_rig_action(
        rig_id="x", target=(0, 0, 0), label="Mars Flyby",
    )
    assert plan.descriptor.kind is RigKind.FLYBY
    assert plan.descriptor.label == "Mars Flyby"


def test_create_target_follow_returns_plan():
    plan = create_target_follow_rig_action(
        rig_id="x", target=(0, 0, 0),
    )
    assert plan.descriptor.kind is RigKind.TARGET_FOLLOW


def test_create_locked_target_returns_plan():
    plan = create_locked_target_rig_action(
        rig_id="x", target=(0, 0, 0),
    )
    assert plan.descriptor.kind is RigKind.LOCKED_TARGET


def test_label_defaults_to_rig_id():
    plan = create_orbit_rig_action(
        rig_id="my_rig", target=(0, 0, 0),
    )
    assert plan.descriptor.label == "my_rig"


# ---------------------------------------------------------------------------
# Cinematic smoothing
# ---------------------------------------------------------------------------


def test_smoothing_action_requires_mission():
    with pytest.raises(CinematicPanelError):
        apply_cinematic_smoothing_action(mission=None)


def test_smoothing_action_returns_report():
    from voyage import Mission, MissionWaypoint
    mission = Mission(title="X")
    for x in (0.0, 10.0, 10.0):
        mission.waypoints.append(MissionWaypoint(
            kind="coordinate", label=f"wp{x}",
            x_c4d=x, y_c4d=x / 2.0, z_c4d=0.0,
        ))
    rep = apply_cinematic_smoothing_action(
        mission=mission, mode=SmoothingMode.CHAIKIN,
    )
    assert rep.input_point_count == 3
    assert rep.output_point_count > 3


# ---------------------------------------------------------------------------
# Motion previews
# ---------------------------------------------------------------------------


def test_preview_orbit_returns_motion_track_preview():
    preview = preview_orbit_motion(
        target=(0, 0, 0), parameters=OrbitParameters(),
        sample_count=16,
    )
    assert isinstance(preview, MotionTrackPreview)
    assert preview.kind == "orbit"
    assert len(preview.samples) == 16


def test_preview_flyby_returns_motion_track_preview():
    preview = preview_flyby_motion(
        target=(0, 0, 0), parameters=FlybyParameters(),
        sample_count=16,
    )
    assert preview.kind == "flyby"
    assert len(preview.samples) == 16


def test_motion_track_preview_short_summary():
    preview = MotionTrackPreview(kind="orbit", samples=[(0, 0, 0)])
    assert "orbit" in preview.short_summary()
    assert "1 sample" in preview.short_summary()


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------


def test_enable_drift_returns_seeded_parameters():
    p = enable_drift_action(seed=42, amplitude=0.1, frequency=0.5)
    assert isinstance(p, DriftParameters)
    assert p.seed == 42
    assert p.amplitude == 0.1
    assert p.frequency == 0.5


def test_enable_drift_rejects_negative_amplitude():
    with pytest.raises(CinematicPanelError):
        enable_drift_action(seed=0, amplitude=-1.0)


def test_enable_drift_rejects_zero_frequency():
    with pytest.raises(CinematicPanelError):
        enable_drift_action(seed=0, frequency=0.0)


# ---------------------------------------------------------------------------
# select_framing_preset
# ---------------------------------------------------------------------------


def test_select_framing_preset_canonical_names():
    for preset in FramingPreset:
        out = select_framing_preset_action(preset.value)
        assert out is preset


def test_select_framing_preset_case_insensitive():
    out = select_framing_preset_action("MEDIUM")
    assert out is FramingPreset.MEDIUM


def test_select_framing_preset_strips_whitespace():
    out = select_framing_preset_action("  wide  ")
    assert out is FramingPreset.WIDE


def test_select_framing_preset_rejects_blank():
    with pytest.raises(CinematicPanelError):
        select_framing_preset_action("")


def test_select_framing_preset_rejects_unknown():
    with pytest.raises(CinematicPanelError):
        select_framing_preset_action("ultra_close")
