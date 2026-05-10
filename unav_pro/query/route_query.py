"""v3.7 route-aware queries.

Helpers that reason about a route (or mission) as a
*polyline corridor* through the catalog:

* ``find_objects_near_route`` — every catalog row
  within a corridor radius of any route segment.
* ``find_objects_between_waypoints`` — within a
  corridor of one specific segment.
* ``closest_object_to_each_waypoint`` — for each
  waypoint, the single closest catalog row.
* ``summarise_route_distribution`` — counts +
  per-source / per-type breakdown for the
  near-route population.

Every helper is a pure function over polylines + a
``CatalogObject`` iterable. No Cinema 4D, no
network. Endpoint preservation, deterministic
ordering, never mutates inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import (
    Any, Dict, Iterable, List, Optional, Sequence, Tuple,
)

from .advanced_query import (
    QueryResult, _build_result, _is_finite,
    _object_position_pc,
)


Vec3 = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _vec_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vec_dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vec_length(v: Vec3) -> float:
    return math.sqrt(_vec_dot(v, v))


def distance_point_to_segment(
    point: Vec3, a: Vec3, b: Vec3,
) -> float:
    """Pure geometry: shortest distance between
    ``point`` and the line segment ``[a, b]`` in 3D.

    Returns the Euclidean distance from ``point`` to
    its closest projection onto the segment."""
    ab = _vec_sub(b, a)
    ab2 = _vec_dot(ab, ab)
    if ab2 == 0.0:
        # Degenerate segment.
        return _vec_length(_vec_sub(point, a))
    ap = _vec_sub(point, a)
    t = _vec_dot(ap, ab) / ab2
    t_clamped = max(0.0, min(1.0, t))
    proj = (
        a[0] + t_clamped * ab[0],
        a[1] + t_clamped * ab[1],
        a[2] + t_clamped * ab[2],
    )
    return _vec_length(_vec_sub(point, proj))


def distance_point_to_polyline(
    point: Vec3, polyline: Sequence[Vec3],
) -> float:
    """Shortest distance between ``point`` and the
    polyline. Returns ``inf`` for an empty polyline,
    direct Euclidean distance for a single-point
    polyline."""
    if not polyline:
        return float("inf")
    if len(polyline) == 1:
        return _vec_length(_vec_sub(point, polyline[0]))
    best = float("inf")
    for i in range(len(polyline) - 1):
        d = distance_point_to_segment(
            point, polyline[i], polyline[i + 1],
        )
        if d < best:
            best = d
    return best


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class RouteQueryReport:
    """Outcome of a route-aware query."""

    corridor_radius_pc: float
    polyline_point_count: int
    candidates_scanned: int = 0
    matched_before_cap: int = 0
    results: List[QueryResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def returned(self) -> int:
        return len(self.results)

    def short_summary(self) -> str:
        return (
            f"route query: {self.returned} result(s) within "
            f"{self.corridor_radius_pc:g} pc of "
            f"{self.polyline_point_count}-point polyline"
        )


@dataclass
class RouteSummary:
    """Aggregate distribution of objects near a route."""

    corridor_radius_pc: float
    total: int = 0
    per_source: Dict[str, int] = field(default_factory=dict)
    per_type: Dict[str, int] = field(default_factory=dict)

    def short_summary(self) -> str:
        bits = [f"{self.total} object(s) near route"]
        if self.per_source:
            sources = ", ".join(
                f"{s}:{n}" for s, n in sorted(self.per_source.items())
            )
            bits.append(f"sources={sources}")
        if self.per_type:
            types = ", ".join(
                f"{t}:{n}" for t, n in sorted(self.per_type.items())
            )
            bits.append(f"types={types}")
        return " · ".join(bits)


# ---------------------------------------------------------------------------
# Polyline extraction
# ---------------------------------------------------------------------------


def polyline_from_waypoints(
    waypoints: Iterable[Any],
) -> List[Vec3]:
    """Pure helper: extract the C4D-coordinate
    polyline from any iterable of objects with
    ``x_c4d`` / ``y_c4d`` / ``z_c4d`` attributes."""
    out: List[Vec3] = []
    for wp in waypoints:
        x = getattr(wp, "x_c4d", None)
        y = getattr(wp, "y_c4d", None)
        z = getattr(wp, "z_c4d", None)
        if (
            _is_finite(x) and _is_finite(y) and _is_finite(z)
        ):
            out.append((float(x), float(y), float(z)))
    return out


# ---------------------------------------------------------------------------
# Near-route queries
# ---------------------------------------------------------------------------


DEFAULT_CORRIDOR_RADIUS_PC: float = 5.0


def find_objects_near_route(
    *,
    polyline: Sequence[Vec3],
    candidates: Iterable[Any],
    corridor_radius_pc: float = DEFAULT_CORRIDOR_RADIUS_PC,
    max_results: int = 200,
) -> RouteQueryReport:
    """Every object whose Cartesian-pc position is
    within ``corridor_radius_pc`` of any segment of
    ``polyline``."""
    if corridor_radius_pc <= 0:
        raise ValueError("corridor_radius_pc must be > 0")
    if max_results <= 0:
        raise ValueError("max_results must be > 0")
    materialised = list(candidates)
    report = RouteQueryReport(
        corridor_radius_pc=corridor_radius_pc,
        polyline_point_count=len(polyline),
    )
    report.candidates_scanned = len(materialised)
    if not polyline:
        report.warnings.append(
            "route polyline is empty; returning no results."
        )
        return report
    survivors: List[QueryResult] = []
    for obj in materialised:
        pos = _object_position_pc(obj)
        if pos is None:
            continue
        d = distance_point_to_polyline(pos, polyline)
        if d > corridor_radius_pc:
            continue
        survivors.append(_build_result(obj, distance_pc=d))
    report.matched_before_cap = len(survivors)
    survivors.sort(
        key=lambda r: (
            r.distance_pc if r.distance_pc is not None else float("inf"),
            r.uid,
        ),
    )
    report.results = survivors[:max_results]
    return report


def find_objects_between_waypoints(
    *,
    a: Vec3,
    b: Vec3,
    candidates: Iterable[Any],
    corridor_radius_pc: float = DEFAULT_CORRIDOR_RADIUS_PC,
    max_results: int = 200,
) -> RouteQueryReport:
    """Variant restricted to one segment ``[a, b]``."""
    return find_objects_near_route(
        polyline=[a, b],
        candidates=candidates,
        corridor_radius_pc=corridor_radius_pc,
        max_results=max_results,
    )


# ---------------------------------------------------------------------------
# Closest-per-waypoint
# ---------------------------------------------------------------------------


@dataclass
class ClosestPerWaypoint:
    """One waypoint's closest catalog match."""

    waypoint_index: int
    waypoint_position: Vec3
    closest: Optional[QueryResult] = None
    distance_pc: Optional[float] = None


def closest_object_to_each_waypoint(
    *,
    waypoints: Sequence[Vec3],
    candidates: Iterable[Any],
) -> List[ClosestPerWaypoint]:
    """For each waypoint, return the single closest
    catalog row in ``candidates``. Pure helper; the
    dialog uses this to suggest "did you mean to
    snap your waypoint to <object>?"."""
    materialised = list(candidates)
    out: List[ClosestPerWaypoint] = []
    for i, wp in enumerate(waypoints):
        best_obj = None
        best_d = float("inf")
        for obj in materialised:
            pos = _object_position_pc(obj)
            if pos is None:
                continue
            dx = pos[0] - wp[0]
            dy = pos[1] - wp[1]
            dz = pos[2] - wp[2]
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if d < best_d:
                best_d = d
                best_obj = obj
        result = (
            _build_result(best_obj, distance_pc=best_d)
            if best_obj is not None else None
        )
        out.append(ClosestPerWaypoint(
            waypoint_index=i,
            waypoint_position=tuple(wp),  # type: ignore[arg-type]
            closest=result,
            distance_pc=(
                best_d if best_obj is not None else None
            ),
        ))
    return out


# ---------------------------------------------------------------------------
# Route summary
# ---------------------------------------------------------------------------


def summarise_route_distribution(
    *,
    polyline: Sequence[Vec3],
    candidates: Iterable[Any],
    corridor_radius_pc: float = DEFAULT_CORRIDOR_RADIUS_PC,
) -> RouteSummary:
    """Aggregate per-source + per-type counts of
    objects near the route."""
    rep = find_objects_near_route(
        polyline=polyline,
        candidates=candidates,
        corridor_radius_pc=corridor_radius_pc,
        max_results=10_000_000,  # effectively uncapped for the summary
    )
    summary = RouteSummary(
        corridor_radius_pc=corridor_radius_pc,
        total=rep.matched_before_cap,
    )
    for r in rep.results:
        if r.catalog_source:
            summary.per_source[r.catalog_source] = (
                summary.per_source.get(r.catalog_source, 0) + 1
            )
        if r.object_type:
            summary.per_type[r.object_type] = (
                summary.per_type.get(r.object_type, 0) + 1
            )
    return summary
