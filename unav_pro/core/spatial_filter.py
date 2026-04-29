"""Spatial filtering for UNAV catalog objects.

This is the gate that keeps the C4D scene small. The plugin must never
materialize the full universe; instead it filters the catalog against
a navigator's pose and a small parameter set, and only the survivors
become C4D objects.

Filter pipeline (order matters)
-------------------------------

For each input object:

  1. **Source / type cuts** — drop objects not in
     ``selected_sources`` or ``selected_types`` if those filters are
     active.
  2. **Distance from origin** — reject if the parsec distance from
     ``origin_pc`` is outside ``[near_clip_pc, far_clip_pc]``.
  3. **Forward-hemisphere** — reject if the displacement from origin
     points behind the navigator (dot product with ``forward`` ≤ 0).
  4. **Cone half-angle** — reject if the angle between displacement
     and ``forward`` exceeds ``cone_half_angle_deg``.
  5. **Max-object cap** — sort the survivors and keep the best
     ``max_visible_objects``. Default ranking is *closest first*; pass
     ``rank_by="brightness"`` to keep the visually brightest instead.

Each rejection is counted by reason so the UI can report a useful
status line ("kept 312 of 100 000; 84 312 outside cone, ...").

Coordinate frame
----------------

All inputs are in the **same** coordinate space — UNAV chooses ICRS
Cartesian parsec, matching the schema's ``cartesian_x/y/z`` fields. The
navigator's world position and forward vector must be converted back
to parsec before calling this module; that conversion is done by the
C4D-side filter glue, not here. Keeping this layer pure-pc means it is
unit-tested without c4d and stays a candidate for native acceleration
later (see ``UNAV_PRO_ARCHITECTURE.md`` §5).

No c4d dependency. No numpy dependency. The MVP loop is a Python for
loop; for sizes above ~ 100 k it is the first thing the C++ migration
should replace (see ``RAY_CONE_FILTERING.md``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

from data.schema import (
    DEFAULT_SCALE_MODE,
    SCALE_MODES,
    CatalogObject,
    compute_derived_fields,
)

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class FilterStats:
    """Per-reason rejection counters returned by ``apply_filter``.

    ``kept`` plus every ``rejected_*`` field equals ``total``.
    """

    total: int = 0
    kept: int = 0
    rejected_source: int = 0
    rejected_type: int = 0
    rejected_no_position: int = 0
    rejected_near_clip: int = 0
    rejected_far_clip: int = 0
    rejected_behind: int = 0
    rejected_outside_cone: int = 0
    rejected_over_cap: int = 0

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "kept": self.kept,
            "rejected_source": self.rejected_source,
            "rejected_type": self.rejected_type,
            "rejected_no_position": self.rejected_no_position,
            "rejected_near_clip": self.rejected_near_clip,
            "rejected_far_clip": self.rejected_far_clip,
            "rejected_behind": self.rejected_behind,
            "rejected_outside_cone": self.rejected_outside_cone,
            "rejected_over_cap": self.rejected_over_cap,
        }

    def short_summary(self) -> str:
        """Render a one-line human-friendly summary for the status log."""
        parts: List[str] = [f"kept {self.kept}/{self.total}"]
        for label, value in (
            ("source", self.rejected_source),
            ("type", self.rejected_type),
            ("no-pos", self.rejected_no_position),
            ("near", self.rejected_near_clip),
            ("far", self.rejected_far_clip),
            ("behind", self.rejected_behind),
            ("outside cone", self.rejected_outside_cone),
            ("over cap", self.rejected_over_cap),
        ):
            if value:
                parts.append(f"{value} {label}")
        return "; ".join(parts)


@dataclass
class FilterResult:
    objects: List[CatalogObject] = field(default_factory=list)
    stats: FilterStats = field(default_factory=FilterStats)


# Sentinels for argument-as-disabled.
_DEFAULT_FAR = float("inf")


# ---------------------------------------------------------------------------
# Pure math helpers
# ---------------------------------------------------------------------------


def _dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(v: Tuple[float, float, float]) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _normalize(
    v: Tuple[float, float, float]
) -> Optional[Tuple[float, float, float]]:
    n = _length(v)
    if n == 0.0:
        return None
    return v[0] / n, v[1] / n, v[2] / n


def _cos_half_angle(cone_half_angle_deg: float) -> float:
    """Cosine threshold for a cone of given half-angle (in degrees).

    Clamped to the valid range so a half-angle of 0 is a pure ray and
    one of >= 90 disables the cone test entirely.
    """
    if cone_half_angle_deg <= 0.0:
        return 1.0
    if cone_half_angle_deg >= 180.0:
        return -1.0
    return math.cos(math.radians(cone_half_angle_deg))


def cone_contains(
    origin_pc: Tuple[float, float, float],
    forward: Tuple[float, float, float],
    cone_half_angle_deg: float,
    point_pc: Tuple[float, float, float],
    near_pc: float = 0.0,
    far_pc: float = _DEFAULT_FAR,
) -> bool:
    """Return True if ``point_pc`` lies inside the cone defined by
    ``(origin_pc, forward, cone_half_angle_deg)`` and within the
    ``[near_pc, far_pc]`` distance shell."""
    dx = point_pc[0] - origin_pc[0]
    dy = point_pc[1] - origin_pc[1]
    dz = point_pc[2] - origin_pc[2]

    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    if dist < near_pc or dist > far_pc:
        return False

    fwd = _normalize(forward)
    if fwd is None or dist == 0.0:
        # No direction or zero displacement — call it "inside" if we
        # passed the distance gate (covers a navigator looking at its
        # own location).
        return True

    cos_threshold = _cos_half_angle(cone_half_angle_deg)
    cos_angle = (dx * fwd[0] + dy * fwd[1] + dz * fwd[2]) / dist
    if cos_angle <= 0.0 and cos_threshold >= 0.0:
        return False
    return cos_angle >= cos_threshold


# ---------------------------------------------------------------------------
# Object position extraction
# ---------------------------------------------------------------------------


def _position_pc(obj: CatalogObject) -> Optional[Tuple[float, float, float]]:
    """Return the parsec Cartesian position of ``obj``.

    Uses the cached ``cartesian_x/y/z`` if populated; otherwise calls
    ``compute_derived_fields`` to populate them. Returns None if the
    object has no usable RA/Dec (defensive — schema validation should
    have caught this earlier)."""
    if (
        obj.cartesian_x is not None
        and obj.cartesian_y is not None
        and obj.cartesian_z is not None
    ):
        return float(obj.cartesian_x), float(obj.cartesian_y), float(obj.cartesian_z)
    try:
        compute_derived_fields(obj)
    except Exception:
        return None
    if (
        obj.cartesian_x is None
        or obj.cartesian_y is None
        or obj.cartesian_z is None
    ):
        return None
    return float(obj.cartesian_x), float(obj.cartesian_y), float(obj.cartesian_z)


# ---------------------------------------------------------------------------
# Sort keys
# ---------------------------------------------------------------------------


_RANK_DISTANCE = "distance"
_RANK_BRIGHTNESS = "brightness"
RANK_MODES: Tuple[str, ...] = (_RANK_DISTANCE, _RANK_BRIGHTNESS)


def _sort_key(rank_by: str):
    if rank_by == _RANK_BRIGHTNESS:
        # Brighter == lower magnitude. Unknown magnitude sorts last.
        def key(item):
            _idx, _obj, dist, mag = item
            mag_value = mag if mag is not None else 99.0
            return (mag_value, dist)
        return key

    # Default: closest first. Tie-break on brightness when known.
    def key(item):
        _idx, _obj, dist, mag = item
        return (dist, mag if mag is not None else 99.0)
    return key


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_filter(
    objects: Iterable[CatalogObject],
    origin_pc: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    forward: Tuple[float, float, float] = (0.0, 0.0, -1.0),
    *,
    near_clip_pc: float = 0.0,
    far_clip_pc: float = _DEFAULT_FAR,
    cone_half_angle_deg: float = 180.0,
    max_visible_objects: Optional[int] = None,
    selected_sources: Optional[Sequence[str]] = None,
    selected_types: Optional[Sequence[str]] = None,
    rank_by: str = _RANK_DISTANCE,
) -> FilterResult:
    """Filter ``objects`` against the navigator pose + parameter set.

    Returns a ``FilterResult`` carrying the surviving objects and a
    structured ``FilterStats`` count of rejections. The function never
    raises for bad inputs — invalid numeric ranges are clamped, and
    objects with un-computable positions are counted under
    ``rejected_no_position``.

    Use ``selected_sources`` / ``selected_types`` to gate by catalog
    source or by ``object_type``; pass ``None`` (default) to disable
    those filters.
    """
    if rank_by not in RANK_MODES:
        rank_by = _RANK_DISTANCE
    if near_clip_pc < 0.0:
        near_clip_pc = 0.0
    if far_clip_pc <= near_clip_pc:
        far_clip_pc = _DEFAULT_FAR
    cos_threshold = _cos_half_angle(cone_half_angle_deg)
    fwd = _normalize(forward)

    sources_set = (
        set(selected_sources)
        if selected_sources is not None
        else None
    )
    types_set = (
        set(selected_types)
        if selected_types is not None
        else None
    )

    stats = FilterStats()
    survivors: List[Tuple[int, CatalogObject, float, Optional[float]]] = []

    for idx, obj in enumerate(objects):
        stats.total += 1

        if sources_set is not None and obj.catalog_source not in sources_set:
            stats.rejected_source += 1
            continue
        if types_set is not None and obj.object_type not in types_set:
            stats.rejected_type += 1
            continue

        pos = _position_pc(obj)
        if pos is None:
            stats.rejected_no_position += 1
            continue

        dx = pos[0] - origin_pc[0]
        dy = pos[1] - origin_pc[1]
        dz = pos[2] - origin_pc[2]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)

        if dist < near_clip_pc:
            stats.rejected_near_clip += 1
            continue
        if dist > far_clip_pc:
            stats.rejected_far_clip += 1
            continue

        # Cone test only meaningful with a usable forward and non-zero
        # displacement. Zero displacement (object at origin) passes —
        # filter on distance only.
        if fwd is not None and dist > 0.0 and cos_threshold > -1.0:
            cos_angle = (dx * fwd[0] + dy * fwd[1] + dz * fwd[2]) / dist
            if cos_angle <= 0.0:
                # Behind hemisphere is reported separately from cone.
                stats.rejected_behind += 1
                continue
            if cos_angle < cos_threshold:
                stats.rejected_outside_cone += 1
                continue

        survivors.append((idx, obj, dist, obj.apparent_magnitude))

    # --- max-object cap --------------------------------------------------
    if max_visible_objects is not None and max_visible_objects >= 0:
        if len(survivors) > max_visible_objects:
            survivors.sort(key=_sort_key(rank_by))
            stats.rejected_over_cap = len(survivors) - max_visible_objects
            survivors = survivors[:max_visible_objects]
    elif rank_by == _RANK_BRIGHTNESS:
        # No cap, but caller still asked for brightness-ordered output.
        survivors.sort(key=_sort_key(rank_by))

    stats.kept = len(survivors)
    return FilterResult(objects=[s[1] for s in survivors], stats=stats)


# ---------------------------------------------------------------------------
# Conversions: navigator state (C4D world units) → parsec inputs
# ---------------------------------------------------------------------------


def c4d_units_to_pc(
    xyz_c4d: Tuple[float, float, float], scale_mode: str = DEFAULT_SCALE_MODE
) -> Tuple[float, float, float]:
    """Inverse of ``schema.pc_to_c4d_units``. Used by the C4D-side
    glue to turn the navigator's world position into parsec for the
    filter."""
    if scale_mode not in SCALE_MODES:
        raise ValueError(
            f"unknown scale_mode '{scale_mode}'; "
            f"valid: {', '.join(SCALE_MODES.keys())}"
        )
    s = SCALE_MODES[scale_mode]
    if s == 0.0:
        raise ValueError(f"scale_mode '{scale_mode}' has zero factor")
    return xyz_c4d[0] / s, xyz_c4d[1] / s, xyz_c4d[2] / s


def filter_for_navigator(
    objects: Iterable[CatalogObject],
    origin_c4d: Tuple[float, float, float],
    forward: Tuple[float, float, float],
    params,
) -> FilterResult:
    """Convenience wrapper that takes the navigator's world-space
    position (in C4D units) plus a ``NavigationParams`` and runs the
    filter in parsec space.

    ``forward`` is direction-only and unitless, so it does not need
    rescaling.
    """
    # Imported here to avoid a circular import at module load time.
    from core.navigation_state import NavigationParams  # noqa: F401

    scale = getattr(params, "c4d_scale", DEFAULT_SCALE_MODE)
    origin_pc = c4d_units_to_pc(origin_c4d, scale_mode=scale)

    sources = getattr(params, "selected_catalog_sources", None) or None
    if sources is not None and len(sources) == 0:
        sources = None  # empty list == "no filter"

    return apply_filter(
        objects,
        origin_pc=origin_pc,
        forward=forward,
        near_clip_pc=float(getattr(params, "near_clip_parsec", 0.0)),
        far_clip_pc=float(getattr(params, "far_clip_parsec", _DEFAULT_FAR)),
        cone_half_angle_deg=float(getattr(params, "cone_angle_deg", 180.0)),
        max_visible_objects=int(getattr(params, "max_visible_objects", 0)) or None,
        selected_sources=sources,
    )
