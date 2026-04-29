"""Route waypoint data model.

Visual route planning only — this module knows nothing about orbital
mechanics, propulsion, or relativistic travel times. It is a list of
waypoints with enough information to:

  * draw a C4D spline through them,
  * report total path length in C4D units,
  * report total path length in parsec when every waypoint resolves
    to a parsec-Cartesian position,
  * focus the navigator on any one of them.

Three waypoint kinds are supported:

  * ``object`` — references a catalog ``uid``. The resolver looks it
    up via ``MetadataLookup`` to get parsec coordinates.
  * ``coordinate`` — a free 3D point in C4D world units.
  * ``named`` — a label-only entry; useful for "Earth", "Solar
    Apex", "Sgr A*" etc. Position is optional; if absent the
    waypoint contributes only labelling.

No c4d dependency. Pure CPython, fully unit-tested.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, fields
from typing import Any, Callable, Dict, List, Optional, Tuple

from data.schema import (
    DEFAULT_SCALE_MODE,
    SCALE_MODES,
    CatalogObject,
    compute_derived_fields,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WAYPOINT_KINDS: Tuple[str, ...] = ("object", "coordinate", "named")
ROUTE_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Resolved position
# ---------------------------------------------------------------------------


@dataclass
class ResolvedPosition:
    """Output of a ``PositionResolver``.

    ``c4d_*`` coordinates are required (a position the route can draw
    in the viewport). ``pc_*`` are optional and only present for
    catalog-backed waypoints; without them the route still renders,
    but parsec totals will skip the corresponding segments.
    """

    x_c4d: float
    y_c4d: float
    z_c4d: float
    x_pc: Optional[float] = None
    y_pc: Optional[float] = None
    z_pc: Optional[float] = None

    def has_pc(self) -> bool:
        return (
            self.x_pc is not None
            and self.y_pc is not None
            and self.z_pc is not None
        )


# ---------------------------------------------------------------------------
# Waypoint
# ---------------------------------------------------------------------------


@dataclass
class Waypoint:
    """A single point on a UNAV route.

    Only ``kind`` is required at construction; the validation in
    ``__post_init__`` enforces the per-kind rules. ``label`` is the
    human-readable name shown in the route panel and on the C4D
    spline marker.

    Catalog-backed waypoints (``kind="object"``) also carry the
    ``uid`` and the optional source / type tags so the route can
    survive without an active ``MetadataLookup`` — i.e. the panel
    still labels rows correctly even when the catalog has not been
    loaded.
    """

    kind: str
    label: str = ""

    # Object-kind fields.
    uid: Optional[str] = None
    catalog_source: Optional[str] = None
    object_type: Optional[str] = None

    # Cached position. Optional for "named" waypoints.
    x_c4d: Optional[float] = None
    y_c4d: Optional[float] = None
    z_c4d: Optional[float] = None
    x_pc: Optional[float] = None
    y_pc: Optional[float] = None
    z_pc: Optional[float] = None

    def __post_init__(self) -> None:
        if self.kind not in WAYPOINT_KINDS:
            raise ValueError(
                f"unknown waypoint kind '{self.kind}'; "
                f"valid: {', '.join(WAYPOINT_KINDS)}"
            )
        if self.kind == "object" and not self.uid:
            raise ValueError("object waypoint requires non-empty uid")
        if self.kind == "coordinate" and not self.has_c4d_position():
            raise ValueError("coordinate waypoint requires x/y/z_c4d")

    # ---------------------------------------------------------- predicates
    def has_c4d_position(self) -> bool:
        return (
            self.x_c4d is not None
            and self.y_c4d is not None
            and self.z_c4d is not None
        )

    def has_pc_position(self) -> bool:
        return (
            self.x_pc is not None
            and self.y_pc is not None
            and self.z_pc is not None
        )

    # ------------------------------------------------------------- friendly
    def display_label(self) -> str:
        if self.label:
            return self.label
        if self.kind == "object" and self.uid:
            return self.uid
        return f"<{self.kind}>"

    # -------------------------------------------------------------- (de)ser
    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"kind": self.kind, "label": self.label}
        for k in (
            "uid", "catalog_source", "object_type",
            "x_c4d", "y_c4d", "z_c4d",
            "x_pc", "y_pc", "z_pc",
        ):
            v = getattr(self, k)
            if v is not None:
                out[k] = v
        return out

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Waypoint":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (d or {}).items() if k in known}
        return cls(**clean)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@dataclass
class Route:
    """An ordered list of waypoints plus a friendly name."""

    name: str = "UNAV Route"
    waypoints: List[Waypoint] = field(default_factory=list)

    # ----------------------------------------------------------------- size
    def __len__(self) -> int:
        return len(self.waypoints)

    def __iter__(self):
        return iter(self.waypoints)

    # ---------------------------------------------------------------- write
    def add(self, waypoint: Waypoint) -> "Waypoint":
        self.waypoints.append(waypoint)
        return waypoint

    def remove_at(self, index: int) -> Optional[Waypoint]:
        if 0 <= index < len(self.waypoints):
            return self.waypoints.pop(index)
        return None

    def clear(self) -> int:
        n = len(self.waypoints)
        self.waypoints.clear()
        return n

    def last(self) -> Optional[Waypoint]:
        return self.waypoints[-1] if self.waypoints else None

    # ----------------------------------------------------------------- json
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": ROUTE_SCHEMA_VERSION,
            "name": self.name,
            "waypoints": [wp.to_dict() for wp in self.waypoints],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Route":
        d = d or {}
        return cls(
            name=d.get("name", "UNAV Route"),
            waypoints=[Waypoint.from_dict(w) for w in d.get("waypoints", [])],
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    @classmethod
    def from_json(cls, s: str) -> "Route":
        try:
            return cls.from_dict(json.loads(s or "{}"))
        except (TypeError, ValueError):
            return cls()


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


PositionResolver = Callable[[Waypoint], Optional[ResolvedPosition]]


def passthrough_resolver(waypoint: Waypoint) -> Optional[ResolvedPosition]:
    """Default resolver: trust whatever positions the waypoint
    already carries. Returns None if there are no usable C4D coords."""
    if not waypoint.has_c4d_position():
        return None
    return ResolvedPosition(
        x_c4d=float(waypoint.x_c4d),
        y_c4d=float(waypoint.y_c4d),
        z_c4d=float(waypoint.z_c4d),
        x_pc=waypoint.x_pc,
        y_pc=waypoint.y_pc,
        z_pc=waypoint.z_pc,
    )


def make_lookup_resolver(
    lookup,
    scale_mode: str = DEFAULT_SCALE_MODE,
) -> PositionResolver:
    """Build a resolver that consults a ``MetadataLookup`` for
    object-kind waypoints whose cached position is missing.

    Coordinate and named waypoints fall through to the
    ``passthrough_resolver`` semantics.
    """

    def _resolve(waypoint: Waypoint) -> Optional[ResolvedPosition]:
        # Already-cached coords win.
        cached = passthrough_resolver(waypoint)
        if cached is not None and (
            cached.has_pc() or waypoint.kind != "object"
        ):
            return cached

        if waypoint.kind != "object" or not waypoint.uid:
            return cached  # may still be None

        if lookup is None:
            return cached

        obj = lookup.lookup(waypoint.uid)
        if obj is None:
            return cached  # can still be a c4d-only position

        # Make sure the schema's derived fields are populated.
        if (
            obj.cartesian_x is None
            or obj.cartesian_y is None
            or obj.cartesian_z is None
            or obj.c4d_x is None
        ):
            try:
                compute_derived_fields(obj, scale_mode=scale_mode)
            except Exception:  # noqa: BLE001 — defensive
                return cached

        if obj.c4d_x is None:
            return cached
        return ResolvedPosition(
            x_c4d=float(obj.c4d_x),
            y_c4d=float(obj.c4d_y),
            z_c4d=float(obj.c4d_z),
            x_pc=obj.cartesian_x,
            y_pc=obj.cartesian_y,
            z_pc=obj.cartesian_z,
        )

    return _resolve


# ---------------------------------------------------------------------------
# Distance computation
# ---------------------------------------------------------------------------


@dataclass
class RouteSegment:
    """One leg of the route, from waypoint ``from_idx`` to
    ``to_idx``."""

    from_idx: int
    to_idx: int
    distance_c4d: Optional[float] = None
    distance_pc: Optional[float] = None

    @property
    def is_complete(self) -> bool:
        return self.distance_c4d is not None


@dataclass
class RouteSummary:
    """The shape the route panel renders."""

    waypoint_count: int = 0
    resolved_count: int = 0
    segments: List[RouteSegment] = field(default_factory=list)
    total_distance_c4d: float = 0.0
    total_distance_pc: Optional[float] = None
    incomplete_segments: int = 0
    incomplete_pc_segments: int = 0


def _segment_distance(
    a: ResolvedPosition, b: ResolvedPosition
) -> Tuple[float, Optional[float]]:
    """Straight-line distance between two resolved positions, in C4D
    units and (when both endpoints carry pc coords) in parsec."""
    dx = b.x_c4d - a.x_c4d
    dy = b.y_c4d - a.y_c4d
    dz = b.z_c4d - a.z_c4d
    d_c4d = math.sqrt(dx * dx + dy * dy + dz * dz)

    d_pc: Optional[float] = None
    if a.has_pc() and b.has_pc():
        ddx = b.x_pc - a.x_pc
        ddy = b.y_pc - a.y_pc
        ddz = b.z_pc - a.z_pc
        d_pc = math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz)
    return d_c4d, d_pc


def compute_route(
    route: Route,
    resolver: PositionResolver = passthrough_resolver,
) -> RouteSummary:
    """Resolve every waypoint, sum segment distances, and return a
    summary suitable for the route panel."""
    resolved: List[Optional[ResolvedPosition]] = [
        resolver(wp) for wp in route.waypoints
    ]
    resolved_count = sum(1 for p in resolved if p is not None)

    segments: List[RouteSegment] = []
    total_c4d = 0.0
    total_pc = 0.0
    pc_known = True
    incomplete = 0
    incomplete_pc = 0

    for i in range(len(resolved) - 1):
        a, b = resolved[i], resolved[i + 1]
        if a is None or b is None:
            incomplete += 1
            incomplete_pc += 1
            pc_known = False
            segments.append(RouteSegment(from_idx=i, to_idx=i + 1))
            continue
        d_c4d, d_pc = _segment_distance(a, b)
        total_c4d += d_c4d
        if d_pc is None:
            incomplete_pc += 1
            pc_known = False
        else:
            total_pc += d_pc
        segments.append(
            RouteSegment(
                from_idx=i, to_idx=i + 1,
                distance_c4d=d_c4d, distance_pc=d_pc,
            )
        )

    return RouteSummary(
        waypoint_count=len(route.waypoints),
        resolved_count=resolved_count,
        segments=segments,
        total_distance_c4d=total_c4d,
        total_distance_pc=total_pc if pc_known and segments else None,
        incomplete_segments=incomplete,
        incomplete_pc_segments=incomplete_pc,
    )


# ---------------------------------------------------------------------------
# Pretty rendering for the panel
# ---------------------------------------------------------------------------


def _fmt_pc(pc: Optional[float]) -> str:
    if pc is None:
        return "—"
    if pc < 1.0:
        # Sub-parsec: show in AU for legibility.
        au = pc * 206_264.806
        return f"{au:.3g} AU"
    if pc >= 1.0e6:
        return f"{pc / 1.0e6:.3g} Mpc"
    if pc >= 1.0e3:
        return f"{pc / 1.0e3:.3g} kpc"
    return f"{pc:.3g} pc"


def _fmt_c4d(units: float) -> str:
    return f"{units:.3g}"


def render_summary(route: Route, summary: RouteSummary) -> str:
    """Multi-line text rendering for the dialog's route panel."""
    if summary.waypoint_count == 0:
        return (
            "No waypoints yet. Select an UNAV object and click "
            "'Add Selected Object as Waypoint'."
        )
    lines: List[str] = []
    lines.append(f"=== {route.name} ===")
    lines.append(
        f"Waypoints       : {summary.waypoint_count} "
        f"({summary.resolved_count} resolved)"
    )
    lines.append(f"Total (C4D)     : {_fmt_c4d(summary.total_distance_c4d)} units")
    if summary.total_distance_pc is not None:
        lines.append(
            f"Total (parsec)  : {_fmt_pc(summary.total_distance_pc)}"
        )
    elif summary.incomplete_pc_segments and summary.segments:
        lines.append(
            "Total (parsec)  : — "
            f"({summary.incomplete_pc_segments} segment(s) without parsec coords)"
        )
    if summary.incomplete_segments:
        lines.append(
            f"Incomplete      : {summary.incomplete_segments} segment(s) "
            "had unresolved waypoints"
        )
    lines.append("")
    lines.append("Waypoints:")
    for i, wp in enumerate(route.waypoints):
        line = f"  [{i}] {wp.display_label()}  ({wp.kind})"
        details = []
        if wp.catalog_source:
            details.append(wp.catalog_source)
        if wp.object_type:
            details.append(wp.object_type)
        if details:
            line += "  — " + ", ".join(details)
        lines.append(line)
    return "\n".join(lines)
