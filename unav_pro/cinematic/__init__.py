"""UNAV Pro v3.6 cinematic helpers package.

Pure-Python helpers for camera choreography:

* :mod:`framing` — auto-look-at, framing presets,
  smooth look-at blending.
* :mod:`motion` — drift / orbit / flyby /
  approach-depart sample generators with
  deterministic output.
* :mod:`route_beautify` — Chaikin + Gaussian
  smoothing that preserves the original mission
  data.

No Cinema 4D imports at the package level. Tests
exercise everything without a host.
"""

from __future__ import annotations

from .framing import (
    DEFAULT_HORIZONTAL_FOV_DEG,
    FRAMING_PRESETS,
    IDENTITY_QUAT,
    PRESET_TABLE,
    CameraPose,
    FramingParameters,
    FramingPreset,
    WaypointFraming,
    blend_look_at,
    compose_look_at_pose,
    framing_distance_for_subject_size,
    look_at_quaternion,
    parameters_for,
)
from .motion import (
    EASING_PRESETS,
    ApproachDepartParameters,
    DriftParameters,
    Easing,
    FlybyParameters,
    OrbitParameters,
    apply_easing,
    approach_depart_position,
    approach_depart_track,
    determinism_signature,
    drift_offset,
    drift_track,
    flyby_position,
    flyby_track,
    orbit_position,
    orbit_track,
)
from .route_beautify import (
    SMOOTHING_MODES,
    BeautificationReport,
    SmoothingMode,
    SmoothingParameters,
    beautify_mission_path,
    beautify_polyline,
    beautify_route_path,
    chaikin_smooth,
    detect_sharp_angles,
    gaussian_smooth,
    interpolate_waypoints,
)

__all__ = [
    # framing
    "FramingPreset", "FramingParameters", "FRAMING_PRESETS",
    "PRESET_TABLE", "parameters_for",
    "DEFAULT_HORIZONTAL_FOV_DEG", "IDENTITY_QUAT",
    "CameraPose", "WaypointFraming",
    "framing_distance_for_subject_size",
    "look_at_quaternion", "compose_look_at_pose",
    "blend_look_at",
    # motion
    "Easing", "EASING_PRESETS", "apply_easing",
    "DriftParameters", "drift_offset", "drift_track",
    "OrbitParameters", "orbit_position", "orbit_track",
    "FlybyParameters", "flyby_position", "flyby_track",
    "ApproachDepartParameters",
    "approach_depart_position", "approach_depart_track",
    "determinism_signature",
    # route beautify
    "SmoothingMode", "SMOOTHING_MODES",
    "SmoothingParameters", "BeautificationReport",
    "chaikin_smooth", "gaussian_smooth",
    "interpolate_waypoints",
    "beautify_polyline",
    "beautify_mission_path", "beautify_route_path",
    "detect_sharp_angles",
]
