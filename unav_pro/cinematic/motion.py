"""v3.6 cinematic camera motion helpers.

Pure-Python sample generators for cinematic camera
movement. Every generator is **deterministic** —
identical inputs always produce identical samples.
The "drift" generator that simulates handheld noise
takes an explicit ``seed`` so two runs with the same
seed produce identical motion.

Five families:

* **Drift** — a deterministic Perlin-style sin/cos
  modulation that mimics handheld noise. Tunable
  amplitude + frequency + seed.
* **Orbit** — circular orbit around a target. Tunable
  axis + radius + speed.
* **Flyby** — straight-line approach + pass-by + depart
  past a target. Tunable approach distance + offset
  vector.
* **Approach / depart** — half-flyby variants used as
  scene openers / closers.
* **Cinematic easing** — six classic easing curves
  (linear / ease-in / ease-out / ease-in-out / step /
  cubic-bezier-friendly) the path interpolator can
  apply to ``t``.

All math is plain stdlib + ``math``. No NumPy. No
threading. No randomness without a seed. No physics
— motion is a pure function of time + parameters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable, List, Optional, Tuple


Vec3 = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# Easing presets
# ---------------------------------------------------------------------------


class Easing(str, Enum):
    """Standard cinematic easing curves. ``str`` base so
    serialisation just works."""

    LINEAR = "linear"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"
    STEP = "step"
    SLOW_SETTLE = "slow_settle"  # quintic ease-out — used for "slow stop on target"


EASING_PRESETS = tuple(Easing)


def apply_easing(t: float, easing: Easing) -> float:
    """Map a linear parameter ``t ∈ [0, 1]`` through an
    easing curve. ``t`` clamps to ``[0, 1]``."""
    t = max(0.0, min(1.0, float(t)))
    if easing is Easing.LINEAR:
        return t
    if easing is Easing.EASE_IN:
        return t * t
    if easing is Easing.EASE_OUT:
        return 1.0 - (1.0 - t) ** 2
    if easing is Easing.EASE_IN_OUT:
        if t < 0.5:
            return 2.0 * t * t
        return 1.0 - (-2.0 * t + 2.0) ** 2 / 2.0
    if easing is Easing.STEP:
        return 1.0 if t >= 1.0 else 0.0
    if easing is Easing.SLOW_SETTLE:
        return 1.0 - (1.0 - t) ** 5
    return t


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DriftParameters:
    """Parameters for the deterministic drift generator.

    The drift is a sum of sin / cos waves at three
    frequencies per axis, scaled by ``amplitude``. The
    ``seed`` shifts the phase deterministically so two
    drifts with different seeds look different but
    still reproduce identically given the same seed."""

    amplitude: float = 0.05
    frequency: float = 0.4
    seed: int = 0


def drift_offset(
    *,
    t_seconds: float,
    parameters: DriftParameters = DriftParameters(),
) -> Vec3:
    """Return a drift offset vector at time ``t_seconds``.

    Pure deterministic function — no PRNG, no global
    state. The same ``(t_seconds, parameters)`` always
    produces the same offset."""
    if parameters.amplitude == 0.0:
        return (0.0, 0.0, 0.0)
    s = float(parameters.seed)
    f = parameters.frequency
    # Three independent axes, each driven by a unique
    # set of phase shifts derived from the seed. Using
    # math.sin/math.cos keeps the result smooth +
    # bounded.
    x = parameters.amplitude * (
        math.sin(2.0 * math.pi * f * t_seconds + 0.13 * s)
        + 0.5 * math.sin(2.0 * math.pi * f * 2.7 * t_seconds + 1.31 * s)
    )
    y = parameters.amplitude * (
        math.cos(2.0 * math.pi * f * 1.1 * t_seconds + 0.21 * s + 1.0)
        + 0.5 * math.cos(2.0 * math.pi * f * 1.9 * t_seconds + 0.73 * s + 2.0)
    )
    z = parameters.amplitude * (
        math.sin(2.0 * math.pi * f * 0.7 * t_seconds + 0.41 * s + 3.0)
        + 0.5 * math.cos(2.0 * math.pi * f * 1.3 * t_seconds + 0.91 * s)
    )
    return (x, y, z)


def drift_track(
    *,
    duration_seconds: float,
    sample_count: int,
    parameters: DriftParameters = DriftParameters(),
) -> List[Vec3]:
    """Pre-compute ``sample_count`` drift offsets evenly
    spaced across ``duration_seconds``. Useful for
    baking drift into the timeline."""
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be > 0")
    if sample_count <= 0:
        raise ValueError("sample_count must be > 0")
    if sample_count == 1:
        return [drift_offset(t_seconds=0.0, parameters=parameters)]
    out: List[Vec3] = []
    step = duration_seconds / float(sample_count - 1)
    for i in range(sample_count):
        out.append(drift_offset(
            t_seconds=i * step, parameters=parameters,
        ))
    return out


# ---------------------------------------------------------------------------
# Orbit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrbitParameters:
    """Parameters for an orbital camera track around a
    target."""

    radius: float = 10.0
    revolutions: float = 1.0
    axis: Vec3 = (0.0, 1.0, 0.0)
    start_angle_deg: float = 0.0


def orbit_position(
    *,
    target: Vec3,
    t: float,
    parameters: OrbitParameters,
) -> Vec3:
    """Return the camera position at parameter
    ``t ∈ [0, 1]`` for a circular orbit around
    ``target``.

    The orbit lies in the plane perpendicular to
    ``parameters.axis``. ``revolutions`` controls how
    many full circles the orbit walks across the
    parameter range.
    """
    t = max(0.0, min(1.0, float(t)))
    angle = (
        math.radians(parameters.start_angle_deg)
        + 2.0 * math.pi * parameters.revolutions * t
    )
    # Build an orthonormal basis (u, v) in the orbit
    # plane. ``u`` is whichever axis is most
    # perpendicular to the orbit axis; ``v`` is the
    # cross product.
    ax, ay, az = parameters.axis
    n = math.sqrt(ax * ax + ay * ay + az * az)
    if n == 0.0:
        ax, ay, az, n = 0.0, 1.0, 0.0, 1.0
    axis = (ax / n, ay / n, az / n)
    # Pick a reference vector that isn't parallel to
    # the axis.
    ref = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    # u = normalize(ref × axis)
    ux = ref[1] * axis[2] - ref[2] * axis[1]
    uy = ref[2] * axis[0] - ref[0] * axis[2]
    uz = ref[0] * axis[1] - ref[1] * axis[0]
    un = math.sqrt(ux * ux + uy * uy + uz * uz)
    if un == 0.0:
        ux, uy, uz, un = 1.0, 0.0, 0.0, 1.0
    u = (ux / un, uy / un, uz / un)
    # v = axis × u (already unit since axis ⊥ u)
    v = (
        axis[1] * u[2] - axis[2] * u[1],
        axis[2] * u[0] - axis[0] * u[2],
        axis[0] * u[1] - axis[1] * u[0],
    )
    cosA = math.cos(angle)
    sinA = math.sin(angle)
    r = parameters.radius
    return (
        target[0] + r * (cosA * u[0] + sinA * v[0]),
        target[1] + r * (cosA * u[1] + sinA * v[1]),
        target[2] + r * (cosA * u[2] + sinA * v[2]),
    )


def orbit_track(
    *,
    target: Vec3,
    sample_count: int,
    parameters: OrbitParameters,
) -> List[Vec3]:
    """Pre-compute ``sample_count`` orbit positions
    evenly spaced across the parameter range."""
    if sample_count <= 0:
        raise ValueError("sample_count must be > 0")
    if sample_count == 1:
        return [orbit_position(target=target, t=0.0, parameters=parameters)]
    out: List[Vec3] = []
    for i in range(sample_count):
        t = i / float(sample_count - 1)
        out.append(orbit_position(
            target=target, t=t, parameters=parameters,
        ))
    return out


# ---------------------------------------------------------------------------
# Flyby + approach / depart
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlybyParameters:
    """Parameters for a straight-line flyby past a
    target.

    The camera starts at ``target + approach_axis ·
    approach_distance``, passes through ``target +
    miss_offset`` at ``t = 0.5``, and ends at
    ``target + depart_axis · depart_distance``.
    """

    approach_axis: Vec3 = (0.0, 0.0, 1.0)
    depart_axis: Vec3 = (0.0, 0.0, -1.0)
    approach_distance: float = 50.0
    depart_distance: float = 50.0
    miss_offset: Vec3 = (5.0, 0.0, 0.0)
    easing: Easing = Easing.EASE_IN_OUT


def _vec_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vec_scale(v: Vec3, s: float) -> Vec3:
    return (v[0] * s, v[1] * s, v[2] * s)


def _vec_lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return (
        a[0] + t * (b[0] - a[0]),
        a[1] + t * (b[1] - a[1]),
        a[2] + t * (b[2] - a[2]),
    )


def flyby_position(
    *,
    target: Vec3,
    t: float,
    parameters: FlybyParameters,
) -> Vec3:
    """Return the camera position at ``t ∈ [0, 1]``
    for a flyby. The interpolation passes through the
    waypoint ``target + miss_offset`` at ``t = 0.5``."""
    t = max(0.0, min(1.0, float(t)))
    eased = apply_easing(t, parameters.easing)
    start = _vec_add(
        target, _vec_scale(parameters.approach_axis, parameters.approach_distance),
    )
    pass_point = _vec_add(target, parameters.miss_offset)
    end = _vec_add(
        target, _vec_scale(parameters.depart_axis, parameters.depart_distance),
    )
    if eased <= 0.5:
        return _vec_lerp(start, pass_point, eased * 2.0)
    return _vec_lerp(pass_point, end, (eased - 0.5) * 2.0)


def flyby_track(
    *,
    target: Vec3,
    sample_count: int,
    parameters: FlybyParameters,
) -> List[Vec3]:
    if sample_count <= 0:
        raise ValueError("sample_count must be > 0")
    if sample_count == 1:
        return [flyby_position(target=target, t=0.5, parameters=parameters)]
    out: List[Vec3] = []
    for i in range(sample_count):
        t = i / float(sample_count - 1)
        out.append(flyby_position(target=target, t=t, parameters=parameters))
    return out


@dataclass(frozen=True)
class ApproachDepartParameters:
    """Half-flyby variant: the camera approaches the
    target (``mode="approach"``) or departs from it
    (``mode="depart"``)."""

    mode: str = "approach"  # "approach" or "depart"
    axis: Vec3 = (0.0, 0.0, 1.0)
    distance: float = 50.0
    settle_distance: float = 5.0
    easing: Easing = Easing.SLOW_SETTLE


def approach_depart_position(
    *,
    target: Vec3,
    t: float,
    parameters: ApproachDepartParameters,
) -> Vec3:
    """One-direction motion either toward or away from
    the target. ``approach`` goes from the far point at
    ``t=0`` to ``target + axis · settle_distance`` at
    ``t=1``; ``depart`` is the reverse."""
    t = max(0.0, min(1.0, float(t)))
    eased = apply_easing(t, parameters.easing)
    far = _vec_add(target, _vec_scale(parameters.axis, parameters.distance))
    near = _vec_add(target, _vec_scale(parameters.axis, parameters.settle_distance))
    if parameters.mode == "approach":
        return _vec_lerp(far, near, eased)
    if parameters.mode == "depart":
        return _vec_lerp(near, far, eased)
    raise ValueError(
        f"approach_depart mode must be 'approach' or 'depart', "
        f"got {parameters.mode!r}"
    )


def approach_depart_track(
    *,
    target: Vec3,
    sample_count: int,
    parameters: ApproachDepartParameters,
) -> List[Vec3]:
    if sample_count <= 0:
        raise ValueError("sample_count must be > 0")
    if sample_count == 1:
        return [approach_depart_position(
            target=target, t=0.5, parameters=parameters,
        )]
    out: List[Vec3] = []
    for i in range(sample_count):
        t = i / float(sample_count - 1)
        out.append(approach_depart_position(
            target=target, t=t, parameters=parameters,
        ))
    return out


# ---------------------------------------------------------------------------
# Determinism guarantee
# ---------------------------------------------------------------------------


def determinism_signature(
    *,
    target: Vec3,
    parameters: object,
    samples: int = 8,
) -> Tuple[Vec3, ...]:
    """Pure helper: produce a stable signature tuple
    by sampling the appropriate generator at fixed
    points. Tests use this to assert that two runs
    against the same parameters produce identical
    output."""
    if isinstance(parameters, OrbitParameters):
        return tuple(orbit_track(
            target=target, sample_count=samples, parameters=parameters,
        ))
    if isinstance(parameters, FlybyParameters):
        return tuple(flyby_track(
            target=target, sample_count=samples, parameters=parameters,
        ))
    if isinstance(parameters, ApproachDepartParameters):
        return tuple(approach_depart_track(
            target=target, sample_count=samples, parameters=parameters,
        ))
    if isinstance(parameters, DriftParameters):
        return tuple(drift_track(
            duration_seconds=1.0, sample_count=samples, parameters=parameters,
        ))
    raise TypeError(
        f"unknown parameters type: {type(parameters).__name__}"
    )
