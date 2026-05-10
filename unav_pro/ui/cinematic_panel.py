"""v3.6 cinematic panel — pure-Python facade.

The dialog's *Cinematic* panel surfaces seven actions:

* **Auto-frame target** — pick a framing preset and
  compute the camera pose.
* **Create orbit rig**.
* **Create flyby rig**.
* **Apply cinematic smoothing** to the active
  mission's camera path.
* **Camera motion preset picker** (drift / orbit /
  flyby / approach / depart).
* **Enable drift motion** on the camera (deterministic;
  always seeded).
* **Framing preset selector**.

Every helper is **pure Python** and returns plain
data. The dialog is responsible for the OS-level
parts (picking the active waypoint, materialising the
rig under ``UNAV_CameraRigs``, calling the v3.45
``UndoSession``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from cinematic import (
    CameraPose,
    DriftParameters,
    FlybyParameters,
    FramingPreset,
    OrbitParameters,
    SmoothingMode,
    SmoothingParameters,
    beautify_mission_path,
    compose_look_at_pose,
    flyby_track,
    orbit_track,
)
from c4d_objects.camera_rigs import (
    CameraRigDescriptor,
    RigBuildPlan,
    RigKind,
    plan_camera_rig,
)


Vec3 = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CinematicPanelError(RuntimeError):
    """Raised on panel-action failures. Carries a
    short human message the dialog renders into the
    status log."""


# ---------------------------------------------------------------------------
# Auto-frame target
# ---------------------------------------------------------------------------


def auto_frame_target_action(
    *,
    target: Vec3,
    subject_extent: float,
    preset: FramingPreset = FramingPreset.MEDIUM,
    pull_back_axis: Vec3 = (0.0, 0.0, 1.0),
    target_offset: Vec3 = (0.0, 0.0, 0.0),
    fov_deg: float = 36.0,
) -> CameraPose:
    """Compose a ``CameraPose`` looking at ``target``
    from a distance picked by the framing preset."""
    if subject_extent <= 0:
        raise CinematicPanelError(
            f"subject_extent must be > 0; got {subject_extent}"
        )
    return compose_look_at_pose(
        target=target,
        subject_extent=subject_extent,
        preset=preset,
        pull_back_axis=pull_back_axis,
        target_offset=target_offset,
        camera_horizontal_fov_deg=fov_deg,
    )


# ---------------------------------------------------------------------------
# Camera rig creation
# ---------------------------------------------------------------------------


def create_orbit_rig_action(
    *,
    rig_id: str,
    target: Vec3,
    radius: float = 10.0,
    label: str = "",
    fov_deg: float = 36.0,
) -> RigBuildPlan:
    """Compose a build plan for an orbit rig. The
    dialog hands the plan to the c4d-bound builder."""
    if not rig_id:
        raise CinematicPanelError("rig_id is required")
    if radius <= 0:
        raise CinematicPanelError(
            f"orbit radius must be > 0; got {radius}"
        )
    descriptor = CameraRigDescriptor(
        rig_id=rig_id,
        kind=RigKind.ORBIT,
        label=label or rig_id,
        target_position=target,
        radius=radius,
        fov_deg=fov_deg,
    )
    return plan_camera_rig(descriptor)


def create_flyby_rig_action(
    *,
    rig_id: str,
    target: Vec3,
    label: str = "",
    fov_deg: float = 36.0,
) -> RigBuildPlan:
    """Build plan for a flyby rig."""
    if not rig_id:
        raise CinematicPanelError("rig_id is required")
    descriptor = CameraRigDescriptor(
        rig_id=rig_id,
        kind=RigKind.FLYBY,
        label=label or rig_id,
        target_position=target,
        fov_deg=fov_deg,
    )
    return plan_camera_rig(descriptor)


def create_target_follow_rig_action(
    *,
    rig_id: str,
    target: Vec3,
    label: str = "",
    fov_deg: float = 36.0,
) -> RigBuildPlan:
    """Build plan for a target-follow rig."""
    if not rig_id:
        raise CinematicPanelError("rig_id is required")
    descriptor = CameraRigDescriptor(
        rig_id=rig_id,
        kind=RigKind.TARGET_FOLLOW,
        label=label or rig_id,
        target_position=target,
        fov_deg=fov_deg,
    )
    return plan_camera_rig(descriptor)


def create_locked_target_rig_action(
    *,
    rig_id: str,
    target: Vec3,
    label: str = "",
    fov_deg: float = 36.0,
) -> RigBuildPlan:
    """Build plan for a locked-target rig."""
    if not rig_id:
        raise CinematicPanelError("rig_id is required")
    descriptor = CameraRigDescriptor(
        rig_id=rig_id,
        kind=RigKind.LOCKED_TARGET,
        label=label or rig_id,
        target_position=target,
        fov_deg=fov_deg,
    )
    return plan_camera_rig(descriptor)


# ---------------------------------------------------------------------------
# Cinematic smoothing
# ---------------------------------------------------------------------------


def apply_cinematic_smoothing_action(
    *,
    mission,
    mode: SmoothingMode = SmoothingMode.CHAIKIN,
    parameters: Optional[SmoothingParameters] = None,
    densify_segments: int = 0,
):
    """Beautify the active mission's path. Returns
    the v3.6 ``BeautificationReport``; the dialog
    drops the resulting polyline as a preview spline
    if the artist wants to inspect before baking."""
    if mission is None:
        raise CinematicPanelError("no mission supplied")
    return beautify_mission_path(
        mission, mode=mode,
        parameters=parameters,
        densify_segments=densify_segments,
    )


# ---------------------------------------------------------------------------
# Motion preset picker
# ---------------------------------------------------------------------------


@dataclass
class MotionTrackPreview:
    """Pre-computed sample track the dialog renders
    as a preview spline. Pure data."""

    kind: str
    samples: List[Vec3]

    def short_summary(self) -> str:
        return f"{self.kind}: {len(self.samples)} sample(s)"


def preview_orbit_motion(
    *,
    target: Vec3, parameters: OrbitParameters,
    sample_count: int = 64,
) -> MotionTrackPreview:
    samples = orbit_track(
        target=target, sample_count=sample_count,
        parameters=parameters,
    )
    return MotionTrackPreview(kind="orbit", samples=samples)


def preview_flyby_motion(
    *,
    target: Vec3, parameters: FlybyParameters,
    sample_count: int = 64,
) -> MotionTrackPreview:
    samples = flyby_track(
        target=target, sample_count=sample_count,
        parameters=parameters,
    )
    return MotionTrackPreview(kind="flyby", samples=samples)


# ---------------------------------------------------------------------------
# Drift toggle
# ---------------------------------------------------------------------------


def enable_drift_action(
    *,
    seed: int,
    amplitude: float = 0.05,
    frequency: float = 0.4,
) -> DriftParameters:
    """Build a deterministic drift parameter set.
    Always seeded — never random.

    The dialog stores the returned record + applies
    it during the timeline bake by sampling
    ``drift_offset`` per frame."""
    if amplitude < 0:
        raise CinematicPanelError("amplitude must be >= 0")
    if frequency <= 0:
        raise CinematicPanelError("frequency must be > 0")
    return DriftParameters(
        amplitude=float(amplitude),
        frequency=float(frequency),
        seed=int(seed),
    )


# ---------------------------------------------------------------------------
# Framing-preset picker
# ---------------------------------------------------------------------------


def select_framing_preset_action(name: str) -> FramingPreset:
    """Map a free-form name to the matching
    ``FramingPreset``. Tolerant of case + whitespace.
    """
    if not isinstance(name, str) or not name.strip():
        raise CinematicPanelError("framing preset name is empty")
    target = name.strip().lower()
    for preset in FramingPreset:
        if preset.value == target:
            return preset
    raise CinematicPanelError(
        f"unknown framing preset: {name!r}; "
        f"valid: {[p.value for p in FramingPreset]}"
    )
