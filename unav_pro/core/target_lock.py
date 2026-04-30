"""Target-lock state for the UNAV navigator.

Pure CPython data layer for the v0.6 "lock the navigator on this
object" workflow:

  * **Acquire** a target by uid via a ``MetadataLookup``: pulls the
    object's parsec-Cartesian and C4D-unit positions, computes the
    forward direction the navigator needs to face from its current
    pose to look at the target, and produces a ``TargetLock`` snapshot.
  * **Compute** the navigator's new pose with optional linear
    interpolation between the current pose and the target — a small
    `t in [0, 1]` parameter the c4d-bound code uses to step the
    navigator gently toward the target rather than teleporting.
  * **Unlock** by clearing the active lock; the navigator is left at
    whatever pose it currently has.

The actual mutation of the C4D ``UNAV_Navigator`` matrix is the job of
``ui/main_dialog.py`` / a ui-side helper; this module's job is to
produce the numbers it needs.

No c4d dependency. Fully unit-tested.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from data.schema import (
    DEFAULT_SCALE_MODE,
    SCALE_MODES,
    CatalogObject,
    compute_derived_fields,
)

#: Linear interpolation `t` value the c4d-bound caller passes for an
#: instant snap. Values < 1.0 step the navigator toward the target;
#: 0.0 is "no movement", 1.0 is "snap to target".
INSTANT_SNAP_T = 1.0


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


Vec3 = Tuple[float, float, float]


@dataclass
class TargetLock:
    """A pose the navigator should hold to keep its forward axis on
    a chosen catalog object.

    Carries:

      * ``uid`` / ``catalog_source`` / ``label`` — identity for the
        UI ("Locked on: Mars [JPL Horizons]").
      * ``position_c4d`` / ``position_pc`` — the target's coordinates
        in C4D world units and parsec respectively. The c4d helper
        uses ``position_c4d`` to set the navigator's `off`. The
        parsec triple is kept for safety / display only.
      * ``distance_c4d`` / ``distance_pc`` — distance from the
        navigator's current origin to the target, computed at
        acquire time. Useful for the panel and for the safety
        warning when the target is past `far_clip_parsec`.
    """

    uid: str
    catalog_source: Optional[str]
    label: str
    position_c4d: Vec3
    position_pc: Optional[Vec3] = None
    distance_c4d: Optional[float] = None
    distance_pc: Optional[float] = None
    object_type: Optional[str] = None

    @property
    def is_resolved(self) -> bool:
        """True iff the lock can be applied (carries a C4D position)."""
        return all(isinstance(v, float) for v in self.position_c4d)


# ---------------------------------------------------------------------------
# Acquire
# ---------------------------------------------------------------------------


def acquire_target(
    uid: str,
    lookup,
    *,
    navigator_position_c4d: Optional[Vec3] = None,
    scale_mode: str = DEFAULT_SCALE_MODE,
) -> Optional[TargetLock]:
    """Resolve ``uid`` into a ``TargetLock`` via ``lookup``.

    Returns ``None`` when:

    * ``uid`` is empty,
    * the lookup has no entry for ``uid``,
    * the resolved object has no usable position even after
      ``compute_derived_fields``.

    The optional ``navigator_position_c4d`` lets the caller record the
    distance from the navigator's current origin to the target at
    acquire time — convenient for the UI ("locked, 12.4 pc away").
    """
    if not uid or lookup is None:
        return None
    if scale_mode not in SCALE_MODES:
        scale_mode = DEFAULT_SCALE_MODE

    obj: Optional[CatalogObject] = lookup.lookup(uid)
    if obj is None:
        return None

    if obj.c4d_x is None or obj.cartesian_x is None:
        try:
            compute_derived_fields(obj, scale_mode=scale_mode)
        except Exception:  # noqa: BLE001 — defensive
            return None

    if obj.c4d_x is None:
        return None

    position_c4d = (float(obj.c4d_x), float(obj.c4d_y), float(obj.c4d_z))
    position_pc: Optional[Vec3] = None
    if (
        obj.cartesian_x is not None
        and obj.cartesian_y is not None
        and obj.cartesian_z is not None
    ):
        position_pc = (
            float(obj.cartesian_x),
            float(obj.cartesian_y),
            float(obj.cartesian_z),
        )

    distance_c4d: Optional[float] = None
    distance_pc: Optional[float] = None
    if navigator_position_c4d is not None:
        distance_c4d = _distance(navigator_position_c4d, position_c4d)
        # Convert to pc when we know the scale.
        scale_units_per_pc = SCALE_MODES.get(scale_mode, 1.0)
        if scale_units_per_pc > 0:
            distance_pc = distance_c4d / scale_units_per_pc

    label = obj.common_name or obj.name or obj.uid
    return TargetLock(
        uid=obj.uid,
        catalog_source=obj.catalog_source,
        label=label,
        position_c4d=position_c4d,
        position_pc=position_pc,
        distance_c4d=distance_c4d,
        distance_pc=distance_pc,
        object_type=obj.object_type,
    )


# ---------------------------------------------------------------------------
# Pose computation
# ---------------------------------------------------------------------------


def interpolate_position(
    current: Vec3, target: Vec3, t: float = INSTANT_SNAP_T,
) -> Vec3:
    """Linear interpolation between two positions.

    ``t = 0`` returns ``current``; ``t = 1`` returns ``target``;
    values in between produce the smoothed step. Out-of-range values
    are clamped (``t < 0`` is treated as `0`, ``t > 1`` as `1`).
    """
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else float(t))
    return (
        current[0] + (target[0] - current[0]) * t,
        current[1] + (target[1] - current[1]) * t,
        current[2] + (target[2] - current[2]) * t,
    )


def compute_focus_pose(
    lock: TargetLock,
    current_position_c4d: Vec3,
    *,
    t: float = INSTANT_SNAP_T,
    place_at_target: bool = False,
    standoff_c4d: float = 0.0,
) -> Tuple[Vec3, Vec3]:
    """Compute (new_navigator_position, target_position) for a focus
    move.

    Two modes:

      * ``place_at_target=False`` (default) — the navigator stays at
        its current origin (or interpolated step toward the target,
        with optional ``standoff_c4d`` so it stops short of the
        target by that many C4D units). The forward direction will
        point at the target — c4d-bound code can derive the rotation
        from ``new_position`` → ``target_position``.
      * ``place_at_target=True`` — the navigator is moved to the
        target's position (still subject to ``t`` for smoothing).
        Useful for "fly to target" workflows.

    Returns a 2-tuple of ``Vec3`` so the c4d helper has both pieces
    in one shot.
    """
    target_pos = lock.position_c4d

    if place_at_target:
        new_pos = interpolate_position(current_position_c4d, target_pos, t)
        return new_pos, target_pos

    if standoff_c4d > 0.0:
        # Stop short of the target along the line from current to it.
        dx = target_pos[0] - current_position_c4d[0]
        dy = target_pos[1] - current_position_c4d[1]
        dz = target_pos[2] - current_position_c4d[2]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist > 0.0 and standoff_c4d < dist:
            f = (dist - standoff_c4d) / dist
            stopped = (
                current_position_c4d[0] + dx * f,
                current_position_c4d[1] + dy * f,
                current_position_c4d[2] + dz * f,
            )
            new_pos = interpolate_position(current_position_c4d, stopped, t)
            return new_pos, target_pos

    # No standoff and no place-at-target: navigator stays put;
    # only the look-at vector changes. Step `t` toward the target
    # is interpreted as a tiny advance for the artist who wants the
    # navigator to "drift toward" the target while still looking at it.
    if t > 0.0 and t < 1.0:
        new_pos = interpolate_position(current_position_c4d, target_pos, t)
        return new_pos, target_pos
    return current_position_c4d, target_pos


def forward_vector(
    from_pos: Vec3, target_pos: Vec3,
) -> Optional[Vec3]:
    """Unit vector pointing from ``from_pos`` to ``target_pos``.

    Returns ``None`` if the two positions coincide (no defined
    direction). The c4d-bound code can plug this into Cinema 4D's
    matrix builder to set the camera's −Z axis on the target.
    """
    dx = target_pos[0] - from_pos[0]
    dy = target_pos[1] - from_pos[1]
    dz = target_pos[2] - from_pos[2]
    norm = math.sqrt(dx * dx + dy * dy + dz * dz)
    if norm == 0.0:
        return None
    return (dx / norm, dy / norm, dz / norm)


# ---------------------------------------------------------------------------
# Safety check vs navigator clip range
# ---------------------------------------------------------------------------


@dataclass
class TargetSafetyReport:
    """Describes whether a lock target is reachable under the active
    navigator's clip range, so the dialog can warn the artist."""

    in_range: bool
    distance_pc: Optional[float]
    near_clip_pc: float
    far_clip_pc: float

    def short_summary(self) -> str:
        if self.distance_pc is None:
            return "distance unknown — pc coords missing on target"
        if self.in_range:
            return (
                f"target {self.distance_pc:.3g} pc away, within clip "
                f"[{self.near_clip_pc}, {self.far_clip_pc}] pc"
            )
        return (
            f"target {self.distance_pc:.3g} pc away, OUTSIDE clip "
            f"[{self.near_clip_pc}, {self.far_clip_pc}] pc — "
            f"adjust far/near_clip_parsec or it will not stream"
        )


def evaluate_target_against_clip(
    lock: TargetLock,
    near_clip_pc: float,
    far_clip_pc: float,
) -> TargetSafetyReport:
    """Compare the locked target's parsec distance to the navigator's
    clip range. Used after a successful `acquire_target` so the
    panel can warn the user when the target is outside the streamed
    cone."""
    distance_pc = lock.distance_pc
    if distance_pc is None and lock.position_pc is not None:
        distance_pc = math.sqrt(sum(c * c for c in lock.position_pc))
    in_range = (
        distance_pc is not None
        and distance_pc >= near_clip_pc
        and distance_pc <= far_clip_pc
    )
    return TargetSafetyReport(
        in_range=bool(in_range),
        distance_pc=distance_pc,
        near_clip_pc=float(near_clip_pc),
        far_clip_pc=float(far_clip_pc),
    )


# ---------------------------------------------------------------------------
# Distance helper
# ---------------------------------------------------------------------------


def _distance(a: Vec3, b: Vec3) -> float:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    dz = b[2] - a[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)
