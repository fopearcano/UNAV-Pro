"""v3.6 cinematic framing helpers.

Pure-Python math for choosing where the camera should sit
relative to a target so the target appears at a desired
on-screen size, plus a five-preset *framing* picker
(close / medium / wide / extreme).

This module is **rendering-agnostic**. It doesn't draw
anything; it produces ``CameraPose`` records the existing
v1.4 ``CameraPath`` builder + the v1.8 timeline baker can
consume directly.

Key surfaces:

* ``FRAMING_PRESETS`` — ``CLOSE`` / ``MEDIUM`` / ``WIDE``
  / ``EXTREME`` parameters.
* ``framing_distance_for_subject_size`` — pure trig:
  given a desired apparent angular size and the camera's
  horizontal field of view, return the distance to put
  the subject at that size.
* ``compose_look_at_pose`` — given the subject position
  + camera position + an up vector, compose a
  ``CameraPose`` with orientation looking at the subject
  (right-handed, Y-up; matches the v1.4 camera path
  convention).
* ``blend_look_at`` — slerp-friendly interpolation
  between two look-at orientations for *smooth*
  framing transitions.

Pure stdlib + math; no Cinema 4D, no rendering, no
randomness without a seed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


Vec3 = Tuple[float, float, float]
Quaternion = Tuple[float, float, float, float]
"""``(w, x, y, z)`` quaternion. Matches the v1.4
``camera_path.IDENTITY_QUAT`` convention."""

IDENTITY_QUAT: Quaternion = (1.0, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Framing presets
# ---------------------------------------------------------------------------


class FramingPreset(str, Enum):
    """Five canonical framing presets the cinematic
    panel exposes. ``str`` base so dataclass equality +
    JSON serialisation just work."""

    CLOSE = "close"            # subject fills ~60% of the frame
    MEDIUM = "medium"          # subject fills ~30%
    WIDE = "wide"              # subject fills ~12%
    EXTREME_WIDE = "extreme_wide"  # subject is a speck (~3%)
    EXTREME_SCALE = "extreme_scale"  # subject is a fraction of a pixel — used for "you are here, the universe is huge" shots


FRAMING_PRESETS = tuple(FramingPreset)


@dataclass(frozen=True)
class FramingParameters:
    """Parameters for one preset.

    ``apparent_angular_fraction`` is the desired ratio
    of *subject angular diameter* to *camera horizontal
    FOV*. ``min_distance`` / ``max_distance`` clamp the
    computed distance to a sensible range so a tiny
    subject doesn't push the camera into the geometry.
    """

    name: FramingPreset
    apparent_angular_fraction: float
    min_distance: float
    max_distance: float


PRESET_TABLE = {
    FramingPreset.CLOSE: FramingParameters(
        name=FramingPreset.CLOSE,
        apparent_angular_fraction=0.60,
        min_distance=0.5,
        max_distance=1e6,
    ),
    FramingPreset.MEDIUM: FramingParameters(
        name=FramingPreset.MEDIUM,
        apparent_angular_fraction=0.30,
        min_distance=1.0,
        max_distance=1e7,
    ),
    FramingPreset.WIDE: FramingParameters(
        name=FramingPreset.WIDE,
        apparent_angular_fraction=0.12,
        min_distance=2.0,
        max_distance=1e8,
    ),
    FramingPreset.EXTREME_WIDE: FramingParameters(
        name=FramingPreset.EXTREME_WIDE,
        apparent_angular_fraction=0.03,
        min_distance=10.0,
        max_distance=1e10,
    ),
    FramingPreset.EXTREME_SCALE: FramingParameters(
        name=FramingPreset.EXTREME_SCALE,
        apparent_angular_fraction=0.005,
        min_distance=100.0,
        max_distance=1e15,
    ),
}


def parameters_for(preset: FramingPreset) -> FramingParameters:
    """Look up the parameters for ``preset``. Raises
    ``KeyError`` on unknown values so a typo at the call
    site fails fast at test time."""
    return PRESET_TABLE[preset]


# ---------------------------------------------------------------------------
# Framing math
# ---------------------------------------------------------------------------


DEFAULT_HORIZONTAL_FOV_DEG: float = 36.0


def framing_distance_for_subject_size(
    *,
    subject_extent: float,
    camera_horizontal_fov_deg: float = DEFAULT_HORIZONTAL_FOV_DEG,
    preset: FramingPreset = FramingPreset.MEDIUM,
) -> float:
    """Pure trig: given a subject extent (parsec /
    C4D world units / whatever scale the navigator uses)
    and the camera's horizontal FOV in degrees, return
    the distance that puts the subject at the preset's
    apparent fraction of the frame.

    The math:

        apparent_subject_fov = 2 · atan(extent / 2d)
        apparent_subject_fov = preset_fraction · camera_fov
        ⇒ d = extent / (2 · tan(preset_fraction · camera_fov / 2))

    The result is clamped to ``[preset.min_distance,
    preset.max_distance]`` so callers never get a
    distance that puts the camera inside the subject
    or absurdly far away.
    """
    if subject_extent <= 0:
        raise ValueError(
            f"subject_extent must be > 0, got {subject_extent}"
        )
    if camera_horizontal_fov_deg <= 0 or camera_horizontal_fov_deg >= 180:
        raise ValueError(
            f"camera_horizontal_fov_deg must be in (0, 180), "
            f"got {camera_horizontal_fov_deg}"
        )
    params = parameters_for(preset)
    target_apparent_deg = (
        params.apparent_angular_fraction * camera_horizontal_fov_deg
    )
    half_apparent_rad = math.radians(target_apparent_deg / 2.0)
    if half_apparent_rad <= 0:
        return params.max_distance
    distance = subject_extent / (2.0 * math.tan(half_apparent_rad))
    return max(
        params.min_distance, min(params.max_distance, distance),
    )


# ---------------------------------------------------------------------------
# Look-at pose
# ---------------------------------------------------------------------------


def _vec_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vec_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vec_scale(v: Vec3, s: float) -> Vec3:
    return (v[0] * s, v[1] * s, v[2] * s)


def _vec_length(v: Vec3) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _vec_normalise(v: Vec3) -> Vec3:
    n = _vec_length(v)
    if n == 0.0:
        return (0.0, 0.0, 1.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def _vec_cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _vec_dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


@dataclass
class CameraPose:
    """One camera pose. Compatible with the v1.4
    ``CameraSample`` consumer; the orientation is a
    quaternion in ``(w, x, y, z)`` order."""

    position: Vec3
    target: Vec3
    orientation: Quaternion = IDENTITY_QUAT
    fov_deg: float = DEFAULT_HORIZONTAL_FOV_DEG

    def look_direction(self) -> Vec3:
        """Unit vector from camera to target. ``(0, 0, 1)``
        when the camera and target coincide (defensive)."""
        v = _vec_sub(self.target, self.position)
        if _vec_length(v) == 0.0:
            return (0.0, 0.0, 1.0)
        return _vec_normalise(v)


def look_at_quaternion(
    *,
    camera_position: Vec3,
    target: Vec3,
    world_up: Vec3 = (0.0, 1.0, 0.0),
) -> Quaternion:
    """Compose a quaternion whose negative Z (Cinema
    4D's camera forward) points from ``camera_position``
    at ``target``, with the supplied ``world_up`` as
    the up reference.

    Pure math; no Cinema 4D imports. Returns identity
    when the camera + target coincide (degenerate).
    """
    forward = _vec_sub(target, camera_position)
    if _vec_length(forward) == 0.0:
        return IDENTITY_QUAT
    forward = _vec_normalise(forward)
    # In Cinema 4D the camera's local -Z is forward.
    # We compose a right-handed basis (right, up, -forward)
    # and convert it to a quaternion.
    up_ref = _vec_normalise(world_up)
    if abs(_vec_dot(forward, up_ref)) > 0.9999:
        # Forward parallel to world up — pick a stable
        # alternative.
        up_ref = (0.0, 0.0, 1.0)
    right = _vec_normalise(_vec_cross(up_ref, forward))
    up = _vec_cross(forward, right)
    # Build a 3x3 rotation matrix (column vectors right,
    # up, -forward). Convert to quaternion via Shepperd's
    # method.
    m00, m01, m02 = right[0], up[0], -forward[0]
    m10, m11, m12 = right[1], up[1], -forward[1]
    m20, m21, m22 = right[2], up[2], -forward[2]
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = 0.5 / math.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (m21 - m12) * s
        y = (m02 - m20) * s
        z = (m10 - m01) * s
    elif m00 > m11 and m00 > m22:
        s = 2.0 * math.sqrt(1.0 + m00 - m11 - m22)
        w = (m21 - m12) / s
        x = 0.25 * s
        y = (m01 + m10) / s
        z = (m02 + m20) / s
    elif m11 > m22:
        s = 2.0 * math.sqrt(1.0 + m11 - m00 - m22)
        w = (m02 - m20) / s
        x = (m01 + m10) / s
        y = 0.25 * s
        z = (m12 + m21) / s
    else:
        s = 2.0 * math.sqrt(1.0 + m22 - m00 - m11)
        w = (m10 - m01) / s
        x = (m02 + m20) / s
        y = (m12 + m21) / s
        z = 0.25 * s
    return _normalise_quat((w, x, y, z))


def _normalise_quat(q: Quaternion) -> Quaternion:
    n = math.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2 + q[3] ** 2)
    if n == 0.0:
        return IDENTITY_QUAT
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


def compose_look_at_pose(
    *,
    target: Vec3,
    camera_position: Optional[Vec3] = None,
    subject_extent: Optional[float] = None,
    preset: FramingPreset = FramingPreset.MEDIUM,
    camera_horizontal_fov_deg: float = DEFAULT_HORIZONTAL_FOV_DEG,
    pull_back_axis: Vec3 = (0.0, 0.0, 1.0),
    world_up: Vec3 = (0.0, 1.0, 0.0),
    target_offset: Vec3 = (0.0, 0.0, 0.0),
) -> CameraPose:
    """Compose a ``CameraPose`` looking at ``target``.

    * If ``camera_position`` is supplied, use it.
    * Otherwise compute the framing distance via
      ``framing_distance_for_subject_size`` (requires
      ``subject_extent``) and pull the camera back along
      ``pull_back_axis`` from the target.

    ``target_offset`` is applied to the look-at point so
    the target sits *off-centre* in the frame (a
    cinematographer's third-of-frame offset).
    """
    framed_target: Vec3 = _vec_add(target, target_offset)
    if camera_position is None:
        if subject_extent is None:
            raise ValueError(
                "compose_look_at_pose: either camera_position "
                "or subject_extent must be supplied"
            )
        distance = framing_distance_for_subject_size(
            subject_extent=subject_extent,
            camera_horizontal_fov_deg=camera_horizontal_fov_deg,
            preset=preset,
        )
        unit = _vec_normalise(pull_back_axis)
        camera_position = _vec_sub(
            framed_target, _vec_scale(unit, distance),
        )
    orientation = look_at_quaternion(
        camera_position=camera_position,
        target=framed_target,
        world_up=world_up,
    )
    return CameraPose(
        position=camera_position,
        target=framed_target,
        orientation=orientation,
        fov_deg=camera_horizontal_fov_deg,
    )


# ---------------------------------------------------------------------------
# Look-at smoothing (slerp)
# ---------------------------------------------------------------------------


def blend_look_at(
    a: Quaternion,
    b: Quaternion,
    t: float,
) -> Quaternion:
    """Spherical interpolation between two look-at
    quaternions. ``t`` clamps to ``[0, 1]``.

    Used by the cinematic helper to **smoothly rotate**
    between two framing poses across N frames so a hard
    look-at change becomes a glide.
    """
    if t <= 0.0:
        return _normalise_quat(a)
    if t >= 1.0:
        return _normalise_quat(b)
    a = _normalise_quat(a)
    b = _normalise_quat(b)
    dot = (
        a[0] * b[0] + a[1] * b[1]
        + a[2] * b[2] + a[3] * b[3]
    )
    if dot < 0.0:
        b = (-b[0], -b[1], -b[2], -b[3])
        dot = -dot
    if dot > 0.9995:
        # Near-parallel — linear blend, then renorm.
        result = (
            a[0] + t * (b[0] - a[0]),
            a[1] + t * (b[1] - a[1]),
            a[2] + t * (b[2] - a[2]),
            a[3] + t * (b[3] - a[3]),
        )
        return _normalise_quat(result)
    theta_0 = math.acos(dot)
    theta = theta_0 * t
    sin_theta = math.sin(theta)
    sin_theta_0 = math.sin(theta_0)
    s0 = math.cos(theta) - dot * sin_theta / sin_theta_0
    s1 = sin_theta / sin_theta_0
    return _normalise_quat((
        a[0] * s0 + b[0] * s1,
        a[1] * s0 + b[1] * s1,
        a[2] * s0 + b[2] * s1,
        a[3] * s0 + b[3] * s1,
    ))


# ---------------------------------------------------------------------------
# Waypoint framing
# ---------------------------------------------------------------------------


@dataclass
class WaypointFraming:
    """Framing applied to a v1.4 mission waypoint.

    Pure data; the cinematic panel reads this when
    auto-framing a mission step.
    """

    waypoint_index: int
    preset: FramingPreset = FramingPreset.MEDIUM
    target_offset: Vec3 = (0.0, 0.0, 0.0)
    pull_back_axis: Vec3 = (0.0, 0.0, 1.0)
    fov_deg: float = DEFAULT_HORIZONTAL_FOV_DEG

    def short_summary(self) -> str:
        return (
            f"WP{self.waypoint_index:03d} "
            f"preset={self.preset.value} "
            f"fov={self.fov_deg:.1f}°"
        )
