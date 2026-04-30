"""Step-based navigation controller.

A small pure-Python helper for "drive the navigator forward / back
along its current heading." Intentionally simple: linear translation
along a unit forward vector, with a configurable step size and an
optional acceleration multiplier.

This module deliberately leaves out:

  * **Animation timelines** — no per-frame stepping; one click =
    one step. The c4d-bound caller is free to drive it from a
    timer if it wants smoother motion.
  * **Relativistic physics** — distances are pure linear (Euclidean)
    additions; no time dilation, no light-travel time.
  * **Rotation** — the heading is an input. The c4d-bound code
    derives forward from the navigator's matrix; this module trusts
    whatever vector it is handed.

What it does provide:

  * ``StepSpeed`` — a small dataclass that holds the per-step
    distance and the acceleration multiplier, with sane validation
    so a typo in the dialog can't produce a 0-pc-per-step setting
    that silently locks the navigator in place.
  * ``step_position`` — the math: ``new_pos = current_pos + forward
    * (signed) * speed * accel``.
  * ``forward_from_yaw_pitch`` — a tiny utility for tests and for
    code paths that derive forward from spherical inputs (no c4d
    matrix required).
  * ``check_step_safety`` — looks at the proposed step distance
    versus the navigator's clip range and reports whether the
    artist is about to fly past `far_clip_parsec` (so the dialog
    can warn / auto-extend).

All distances are in **parsec** so the helper composes cleanly with
the rest of UNAV's data model. The c4d caller scales to C4D world
units via ``data.schema.SCALE_MODES``.

No c4d dependency. Fully unit-tested.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

#: Default step distance in parsec. Picked to be large enough to
#: visibly move the navigator in a Gaia-scale scene but small enough
#: that the artist still has fine control.
DEFAULT_STEP_DISTANCE_PC = 1.0

#: Default acceleration multiplier. Modifies the step distance for
#: a "shift to go fast" workflow in the dialog. ``1.0`` is normal,
#: ``> 1`` is faster, ``< 1`` is finer.
DEFAULT_ACCELERATION = 1.0

#: Hard floor for the step distance to keep the controller safe.
MIN_STEP_DISTANCE_PC = 1.0e-6

#: Hard ceiling for the step distance — past this, an artist almost
#: certainly meant to "place at target" instead of step. Cap rather
#: than refuse so the artist sees the cap reflected in the dialog.
MAX_STEP_DISTANCE_PC = 1.0e6


Vec3 = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# Speed model
# ---------------------------------------------------------------------------


@dataclass
class StepSpeed:
    """Step distance + acceleration multiplier.

    The effective step is ``step_distance_pc * acceleration``.
    Negative values are rejected at construction; a backward step is
    expressed via ``step_position(..., direction=-1)``, not via a
    negative speed.
    """

    step_distance_pc: float = DEFAULT_STEP_DISTANCE_PC
    acceleration: float = DEFAULT_ACCELERATION

    def __post_init__(self) -> None:
        if self.step_distance_pc <= 0:
            raise ValueError("step_distance_pc must be > 0")
        if self.acceleration <= 0:
            raise ValueError("acceleration must be > 0")
        if self.step_distance_pc < MIN_STEP_DISTANCE_PC:
            self.step_distance_pc = MIN_STEP_DISTANCE_PC
        if self.step_distance_pc > MAX_STEP_DISTANCE_PC:
            self.step_distance_pc = MAX_STEP_DISTANCE_PC

    @property
    def effective_step_pc(self) -> float:
        return self.step_distance_pc * self.acceleration


# ---------------------------------------------------------------------------
# Stepping
# ---------------------------------------------------------------------------


def _normalize(v: Vec3) -> Optional[Vec3]:
    norm = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if norm == 0.0:
        return None
    return (v[0] / norm, v[1] / norm, v[2] / norm)


def step_position(
    current_pc: Vec3,
    forward: Vec3,
    speed: StepSpeed,
    *,
    direction: int = 1,
) -> Vec3:
    """Advance ``current_pc`` along ``forward`` by ``speed`` × sign.

    ``forward`` should be a unit vector; if it is not, the helper
    normalizes it first. Zero-length vectors leave the position
    unchanged (the controller has no defined heading).

    ``direction`` is ``+1`` for forward, ``-1`` for backward. Any
    other value is treated as the sign of ``direction`` (so ``-3``
    is backward, ``2`` is forward).
    """
    sign = 1 if direction >= 0 else -1
    unit = _normalize(forward)
    if unit is None:
        return current_pc
    step = speed.effective_step_pc * sign
    return (
        current_pc[0] + unit[0] * step,
        current_pc[1] + unit[1] * step,
        current_pc[2] + unit[2] * step,
    )


def forward_from_yaw_pitch(
    yaw_deg: float, pitch_deg: float,
) -> Vec3:
    """Build a unit forward vector from yaw/pitch (degrees).

    Convention matches the navigator null: yaw rotates around +Y,
    pitch tilts up/down. ``yaw=0, pitch=0`` returns ``(0, 0, -1)`` —
    i.e. the camera's −Z look direction at rest.
    """
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    # Start facing -Z, apply pitch (around X) then yaw (around Y).
    fx = -sy * cp
    fy = sp
    fz = -cy * cp
    return (fx, fy, fz)


# ---------------------------------------------------------------------------
# Safety check vs clip range
# ---------------------------------------------------------------------------


@dataclass
class StepSafetyReport:
    """Describes whether a proposed step is safe under the active
    navigator's clip range. Used by the panel to warn before the
    artist commits the move."""

    proposed_distance_from_origin_pc: float
    near_clip_pc: float
    far_clip_pc: float
    in_range: bool

    def short_summary(self) -> str:
        if self.in_range:
            return (
                f"step keeps navigator at "
                f"{self.proposed_distance_from_origin_pc:.3g} pc — within "
                f"clip [{self.near_clip_pc}, {self.far_clip_pc}] pc"
            )
        return (
            f"step would put navigator at "
            f"{self.proposed_distance_from_origin_pc:.3g} pc — OUTSIDE "
            f"clip [{self.near_clip_pc}, {self.far_clip_pc}] pc; widen "
            "far_clip_parsec to keep streaming"
        )


def check_step_safety(
    proposed_position_pc: Vec3,
    *,
    near_clip_pc: float,
    far_clip_pc: float,
) -> StepSafetyReport:
    """Compare the proposed post-step navigator distance from the
    barycentric origin to the active clip range."""
    d = math.sqrt(sum(c * c for c in proposed_position_pc))
    in_range = (d >= near_clip_pc) and (d <= far_clip_pc)
    return StepSafetyReport(
        proposed_distance_from_origin_pc=d,
        near_clip_pc=float(near_clip_pc),
        far_clip_pc=float(far_clip_pc),
        in_range=bool(in_range),
    )


# ---------------------------------------------------------------------------
# High-level controller wrapper
# ---------------------------------------------------------------------------


@dataclass
class NavigationController:
    """Stateful step controller used by the dialog.

    Keeps the active ``StepSpeed`` so the dialog doesn't have to
    rebuild it per click, plus a counter the panel can show
    ("12 steps taken since last reset") and a ``last_summary``
    for the status log.
    """

    speed: StepSpeed = None  # type: ignore[assignment]
    steps_taken: int = 0
    last_summary: str = ""

    def __post_init__(self) -> None:
        if self.speed is None:
            self.speed = StepSpeed()

    # ------------------------------------------------------------ controls
    def set_speed(
        self, step_distance_pc: float, acceleration: float = 1.0,
    ) -> None:
        self.speed = StepSpeed(
            step_distance_pc=step_distance_pc, acceleration=acceleration,
        )

    def reset(self) -> None:
        self.steps_taken = 0
        self.last_summary = ""

    # -------------------------------------------------------------- moves
    def step_forward(self, current_pc: Vec3, forward: Vec3) -> Vec3:
        """Advance one step. Increments ``steps_taken`` on success."""
        new_pos = step_position(current_pc, forward, self.speed, direction=1)
        if new_pos != current_pc:
            self.steps_taken += 1
            self.last_summary = (
                f"forward {self.speed.effective_step_pc:.3g} pc — at "
                f"({new_pos[0]:.3g}, {new_pos[1]:.3g}, {new_pos[2]:.3g})"
            )
        return new_pos

    def step_backward(self, current_pc: Vec3, forward: Vec3) -> Vec3:
        """Step opposite the forward vector. Increments
        ``steps_taken`` on success."""
        new_pos = step_position(current_pc, forward, self.speed, direction=-1)
        if new_pos != current_pc:
            self.steps_taken += 1
            self.last_summary = (
                f"backward {self.speed.effective_step_pc:.3g} pc — at "
                f"({new_pos[0]:.3g}, {new_pos[1]:.3g}, {new_pos[2]:.3g})"
            )
        return new_pos
