"""UNAV Pro v2.0 procedural overlays.

Pure-Python overlay computation. No Cinema 4D dependency,
no DB, no network. Each overlay is a deterministic function
that turns a small set of parameters into the geometry the
``c4d_objects/overlays_builder`` will materialise as scene
objects.

Overlays are *navigation aids* — coordinate grids, galactic /
ecliptic plane indicators, distance rings, the navigator's
sector cone, the route corridor along a mission path,
waypoint label anchors. None of them participate in the
visible-sector pipeline; they cannot pollute datasets and
cannot interfere with rendering.

Determinism: same settings → byte-identical output. Every
function in this module is pure.

The submodules:

* `overlays.py` (this file) — geometry primitives + the
  `OverlaySettings` dataclass that drives them.
* `dataset_helpers.py` — dataset-derived overlays (bounding
  spheres, source-distribution summaries).

Both are stdlib-only and tested in `test_v20_*`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Constants — astronomical reference values
# ---------------------------------------------------------------------------

#: Obliquity of the ecliptic at J2000 (degrees). Source: IAU
#: 2000A. UNAV uses the simple constant rotation rather than
#: the full IAU 2006 polynomial — the visualisation difference
#: across a few centuries is sub-pixel.
OBLIQUITY_J2000_DEG: float = 23.4392911

#: Galactic-pole direction in ICRS (degrees). Source: Liu et
#: al. 2011 / Hipparcos. The galactic plane is the great
#: circle perpendicular to this pole.
GALACTIC_POLE_RA_DEG: float = 192.8595
GALACTIC_POLE_DEC_DEG: float = 27.1283

#: Position angle of the galactic centre on the celestial
#: sphere (degrees). Used together with the pole to fix the
#: galactic frame's third axis.
GALACTIC_CENTRE_RA_DEG: float = 266.4051
GALACTIC_CENTRE_DEC_DEG: float = -28.9362

#: Default radius (parsec) for the bundled coordinate / plane
#: overlays. The artist overrides via ``OverlaySettings.radius_pc``;
#: 100 pc is a reasonable "local neighbourhood" default.
DEFAULT_OVERLAY_RADIUS_PC: float = 100.0

#: Default segment counts for the curved overlays (planes,
#: distance rings, cone discs). Higher = smoother spline /
#: more polygons; the artist may want to bump for cinematic
#: close-ups.
DEFAULT_SEGMENT_COUNT: int = 64

#: Hard cap on segment count so the artist can't ask for
#: a million-segment ring by accident.
MAX_SEGMENT_COUNT: int = 1024

#: Hard cap on distance-ring count.
MAX_RING_COUNT: int = 64

#: Stable v2.0 overlay-kind identifiers. The C4D builder
#: keys per-overlay scene objects off these strings so a
#: rebuild can find + replace the previous instance.
KIND_GRID: str = "grid"
KIND_GALACTIC_PLANE: str = "galactic_plane"
KIND_ECLIPTIC_PLANE: str = "ecliptic_plane"
KIND_DISTANCE_RINGS: str = "distance_rings"
KIND_SECTOR_CONE: str = "sector_cone"
KIND_ROUTE_CORRIDOR: str = "route_corridor"
KIND_WAYPOINT_LABELS: str = "waypoint_labels"

OVERLAY_KINDS: Tuple[str, ...] = (
    KIND_GRID,
    KIND_GALACTIC_PLANE,
    KIND_ECLIPTIC_PLANE,
    KIND_DISTANCE_RINGS,
    KIND_SECTOR_CONE,
    KIND_ROUTE_CORRIDOR,
    KIND_WAYPOINT_LABELS,
)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@dataclass
class OverlaySettings:
    """Per-project overlay visibility + sizing knobs.

    Persisted via the v0.x project_state sidecar; the dialog's
    "Save UNAV State" / "Load UNAV State" buttons round-trip
    these values along with the navigator + route + datasets.

    Each ``show_*`` flag is independent. The C4D builder
    inserts only the overlays whose flag is True; the rest
    are removed if previously present.
    """

    # Per-overlay visibility.
    show_grid: bool = False
    show_galactic_plane: bool = False
    show_ecliptic_plane: bool = False
    show_distance_rings: bool = False
    show_sector_cone: bool = False
    show_route_corridor: bool = False
    show_waypoint_labels: bool = False

    # Geometry knobs.
    radius_pc: float = DEFAULT_OVERLAY_RADIUS_PC
    segment_count: int = DEFAULT_SEGMENT_COUNT
    grid_step_pc: float = 25.0
    grid_extent_pc: float = 100.0
    distance_ring_radii_pc: List[float] = field(
        default_factory=lambda: [10.0, 25.0, 50.0, 100.0],
    )
    corridor_width_pc: float = 1.0
    label_height_pc: float = 1.5

    # Per-overlay opacity placeholder. Cinema 4D's display
    # tag exposes opacity differently per renderer; v2.0
    # stores the value but the builder treats it as advisory
    # (a future v2.x can apply it via display tags).
    opacity: float = 1.0

    def __post_init__(self) -> None:
        if self.radius_pc <= 0:
            raise ValueError("radius_pc must be > 0")
        if not (0.0 <= self.opacity <= 1.0):
            raise ValueError("opacity must be in [0, 1]")
        if self.segment_count < 4:
            self.segment_count = 4
        if self.segment_count > MAX_SEGMENT_COUNT:
            self.segment_count = MAX_SEGMENT_COUNT
        if self.grid_step_pc <= 0:
            raise ValueError("grid_step_pc must be > 0")
        if self.grid_extent_pc <= 0:
            raise ValueError("grid_extent_pc must be > 0")
        if self.corridor_width_pc < 0:
            raise ValueError("corridor_width_pc must be >= 0")
        if self.label_height_pc < 0:
            raise ValueError("label_height_pc must be >= 0")
        # Distance rings: drop non-positive entries; cap count.
        cleaned: List[float] = []
        for r in self.distance_ring_radii_pc or ():
            try:
                v = float(r)
            except (TypeError, ValueError):
                continue
            if v > 0.0:
                cleaned.append(v)
        cleaned = sorted(set(cleaned))[:MAX_RING_COUNT]
        if not cleaned:
            cleaned = [DEFAULT_OVERLAY_RADIUS_PC]
        self.distance_ring_radii_pc = cleaned

    # ---------------------------------------------------------- predicates
    def any_visible(self) -> bool:
        return any(getattr(self, f"show_{k}") for k in OVERLAY_KINDS)

    def is_visible(self, kind: str) -> bool:
        attr = f"show_{kind}"
        return bool(getattr(self, attr, False))

    # ------------------------------------------------------------ (de)ser
    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, list):
                out[f.name] = list(value)
            else:
                out[f.name] = value
        return out

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "OverlaySettings":
        d = d or {}
        known = {f.name for f in fields(cls)}
        clean: Dict[str, Any] = {}
        for k, v in d.items():
            if k in known:
                clean[k] = v
        try:
            return cls(**clean)
        except (TypeError, ValueError):
            # Fail-closed: corrupt persisted settings → defaults.
            return cls()


# ---------------------------------------------------------------------------
# Geometry types
# ---------------------------------------------------------------------------


Vec3 = Tuple[float, float, float]


@dataclass
class OverlayPolyline:
    """One unjoined sequence of points the C4D builder will
    materialise as a ``c4d.SplineObject``. The builder's name
    convention puts every polyline under
    ``UNAV_Overlays/<overlay_kind>/<polyline_index>`` so a
    rebuild can find + replace cleanly."""

    kind: str
    index: int = 0
    label: str = ""
    points: List[Vec3] = field(default_factory=list)
    closed: bool = False


@dataclass
class OverlayLabel:
    """One waypoint-label anchor. The C4D builder may render
    this as a text spline + extruded mesh, or just as a null
    with the label as its name; v2.0 emits the data and lets
    the builder decide."""

    kind: str = KIND_WAYPOINT_LABELS
    text: str = ""
    position: Vec3 = (0.0, 0.0, 0.0)


@dataclass
class OverlayBundle:
    """Everything one ``OverlaySettings`` produces. The builder
    walks ``polylines`` + ``labels`` to materialise the scene
    objects. ``empty()`` is True when no overlay flag was on."""

    polylines: List[OverlayPolyline] = field(default_factory=list)
    labels: List[OverlayLabel] = field(default_factory=list)

    def empty(self) -> bool:
        return not (self.polylines or self.labels)

    def by_kind(self, kind: str) -> List[OverlayPolyline]:
        return [p for p in self.polylines if p.kind == kind]


# ---------------------------------------------------------------------------
# Coordinate transforms
# ---------------------------------------------------------------------------


def _spherical_to_cartesian(
    ra_deg: float, dec_deg: float, radius: float,
) -> Vec3:
    ra = math.radians(ra_deg)
    dec = math.radians(dec_deg)
    cd = math.cos(dec)
    return (
        radius * cd * math.cos(ra),
        radius * cd * math.sin(ra),
        radius * math.sin(dec),
    )


def _orthonormal_basis_for_plane(
    pole_ra_deg: float, pole_dec_deg: float,
    in_plane_ra_deg: float, in_plane_dec_deg: float,
) -> Tuple[Vec3, Vec3, Vec3]:
    """Build an orthonormal basis (u, v, n) where n is the
    pole direction and (u, v) span the plane perpendicular
    to it. The in-plane reference direction picks out the
    starting orientation of u."""
    n = _spherical_to_cartesian(pole_ra_deg, pole_dec_deg, 1.0)
    # In-plane reference direction: project the second input
    # onto the plane perpendicular to n.
    raw = _spherical_to_cartesian(in_plane_ra_deg, in_plane_dec_deg, 1.0)
    dot = raw[0] * n[0] + raw[1] * n[1] + raw[2] * n[2]
    u_raw = (
        raw[0] - dot * n[0],
        raw[1] - dot * n[1],
        raw[2] - dot * n[2],
    )
    u_len = math.sqrt(sum(c * c for c in u_raw))
    if u_len < 1e-9:
        # Degenerate; pick any axis perpendicular to n.
        if abs(n[0]) < 0.9:
            u_raw = (1.0 - n[0] * n[0], -n[0] * n[1], -n[0] * n[2])
        else:
            u_raw = (-n[1] * n[0], 1.0 - n[1] * n[1], -n[1] * n[2])
        u_len = math.sqrt(sum(c * c for c in u_raw))
    u = (u_raw[0] / u_len, u_raw[1] / u_len, u_raw[2] / u_len)
    # v = n × u
    v = (
        n[1] * u[2] - n[2] * u[1],
        n[2] * u[0] - n[0] * u[2],
        n[0] * u[1] - n[1] * u[0],
    )
    return u, v, n


def _circle_in_basis(
    centre: Vec3,
    radius: float,
    u: Vec3,
    v: Vec3,
    *,
    segments: int,
) -> List[Vec3]:
    """Tessellate a circle in the plane spanned by (u, v) at
    ``centre`` with ``radius``. ``segments`` points around the
    full circle; the last point repeats the first so callers
    can flag the polyline as closed."""
    out: List[Vec3] = []
    for i in range(segments):
        theta = 2.0 * math.pi * i / float(segments)
        ct = math.cos(theta)
        st = math.sin(theta)
        out.append((
            centre[0] + radius * (ct * u[0] + st * v[0]),
            centre[1] + radius * (ct * u[1] + st * v[1]),
            centre[2] + radius * (ct * u[2] + st * v[2]),
        ))
    return out


# ---------------------------------------------------------------------------
# Overlay builders
# ---------------------------------------------------------------------------


def build_grid(settings: OverlaySettings) -> List[OverlayPolyline]:
    """v2.0 coordinate grid. A flat XY grid at z=0 with lines
    every ``grid_step_pc`` over ``[-grid_extent_pc, +grid_extent_pc]``.
    One polyline per grid line so the C4D builder can tag /
    style each independently."""
    out: List[OverlayPolyline] = []
    extent = float(settings.grid_extent_pc)
    step = float(settings.grid_step_pc)
    if step <= 0 or extent <= 0:
        return out
    line_count = 0
    # Build coordinate values [-extent, ..., 0, ..., +extent]
    # rounded to step. Always include the extents so the grid
    # is visually closed.
    n_half = max(1, int(round(extent / step)))
    coords = [-extent + i * step for i in range(2 * n_half + 1)]

    # Lines parallel to Y.
    for x in coords:
        out.append(OverlayPolyline(
            kind=KIND_GRID, index=line_count,
            label=f"x={x:g}",
            points=[(x, -extent, 0.0), (x, +extent, 0.0)],
        ))
        line_count += 1
    # Lines parallel to X.
    for y in coords:
        out.append(OverlayPolyline(
            kind=KIND_GRID, index=line_count,
            label=f"y={y:g}",
            points=[(-extent, y, 0.0), (+extent, y, 0.0)],
        ))
        line_count += 1
    return out


def build_plane_circle(
    settings: OverlaySettings,
    *,
    pole_ra_deg: float,
    pole_dec_deg: float,
    in_plane_ra_deg: float,
    in_plane_dec_deg: float,
    kind: str,
    label: str,
) -> OverlayPolyline:
    """Generic: a great circle in any plane, used by
    galactic + ecliptic plane builders."""
    u, v, _ = _orthonormal_basis_for_plane(
        pole_ra_deg, pole_dec_deg,
        in_plane_ra_deg, in_plane_dec_deg,
    )
    pts = _circle_in_basis(
        (0.0, 0.0, 0.0), float(settings.radius_pc), u, v,
        segments=int(settings.segment_count),
    )
    return OverlayPolyline(
        kind=kind, index=0, label=label, points=pts, closed=True,
    )


def build_galactic_plane(settings: OverlaySettings) -> OverlayPolyline:
    """v2.0 galactic plane: the great circle perpendicular to
    the galactic pole, sampled in ICRS Cartesian parsec."""
    return build_plane_circle(
        settings,
        pole_ra_deg=GALACTIC_POLE_RA_DEG,
        pole_dec_deg=GALACTIC_POLE_DEC_DEG,
        in_plane_ra_deg=GALACTIC_CENTRE_RA_DEG,
        in_plane_dec_deg=GALACTIC_CENTRE_DEC_DEG,
        kind=KIND_GALACTIC_PLANE,
        label="galactic plane",
    )


def build_ecliptic_plane(settings: OverlaySettings) -> OverlayPolyline:
    """v2.0 ecliptic plane: the great circle tilted by the
    obliquity (≈23.44°) about the ICRS +X axis. Sampled in
    ICRS Cartesian parsec."""
    # Pole of the ecliptic in ICRS: (0, 0, 1) rotated about
    # +X by -obliquity. The galactic builder takes RA/Dec, so
    # express the same here for symmetry.
    # Ecliptic pole at RA = 270°, Dec = 90 - obliquity.
    pole_dec = 90.0 - OBLIQUITY_J2000_DEG
    return build_plane_circle(
        settings,
        pole_ra_deg=270.0,
        pole_dec_deg=pole_dec,
        in_plane_ra_deg=0.0,
        in_plane_dec_deg=0.0,
        kind=KIND_ECLIPTIC_PLANE,
        label="ecliptic plane",
    )


def build_distance_rings(settings: OverlaySettings) -> List[OverlayPolyline]:
    """v2.0 distance rings: one circle per radius in
    ``distance_ring_radii_pc``, centred at the origin and
    lying in the XY plane (so they read as concentric
    distance markers from the navigator's home anchor)."""
    out: List[OverlayPolyline] = []
    for i, r in enumerate(settings.distance_ring_radii_pc or ()):
        pts = _circle_in_basis(
            (0.0, 0.0, 0.0), float(r),
            (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
            segments=int(settings.segment_count),
        )
        out.append(OverlayPolyline(
            kind=KIND_DISTANCE_RINGS, index=i,
            label=f"{float(r):g} pc",
            points=pts, closed=True,
        ))
    return out


def build_sector_cone(
    settings: OverlaySettings,
    *,
    origin_pc: Vec3 = (0.0, 0.0, 0.0),
    forward: Vec3 = (1.0, 0.0, 0.0),
    cone_half_angle_deg: float = 30.0,
    near_pc: float = 0.0,
    far_pc: Optional[float] = None,
) -> List[OverlayPolyline]:
    """v2.0 sector cone: two circles (near + far) plus four
    tangent lines marking the cone walls. The C4D builder
    wires them into a wireframe cone the artist can see in
    the viewport.

    ``far_pc`` defaults to ``settings.radius_pc`` when omitted.
    """
    far = float(far_pc) if far_pc is not None else float(settings.radius_pc)
    if far <= 0:
        return []
    if cone_half_angle_deg <= 0 or cone_half_angle_deg > 180:
        return []
    forward_len = math.sqrt(sum(c * c for c in forward))
    if forward_len < 1e-9:
        return []
    fx, fy, fz = (c / forward_len for c in forward)
    forward_n = (fx, fy, fz)

    # Build a basis (u, v, forward) — u is "right", v is "up".
    # Pick u perpendicular to forward.
    if abs(fz) < 0.99:
        u_raw = (
            forward_n[1] * 0.0 - forward_n[2] * 1.0,
            forward_n[2] * 0.0 - forward_n[0] * 0.0,
            forward_n[0] * 1.0 - forward_n[1] * 0.0,
        )
        u_raw = (-forward_n[2], 0.0, forward_n[0])
    else:
        u_raw = (1.0, 0.0, 0.0)
    u_len = math.sqrt(sum(c * c for c in u_raw))
    u = (u_raw[0] / u_len, u_raw[1] / u_len, u_raw[2] / u_len)
    # v = forward × u
    v = (
        forward_n[1] * u[2] - forward_n[2] * u[1],
        forward_n[2] * u[0] - forward_n[0] * u[2],
        forward_n[0] * u[1] - forward_n[1] * u[0],
    )

    # Far disc.
    far_radius = far * math.tan(math.radians(cone_half_angle_deg))
    far_centre = (
        origin_pc[0] + far * forward_n[0],
        origin_pc[1] + far * forward_n[1],
        origin_pc[2] + far * forward_n[2],
    )
    far_pts = _circle_in_basis(
        far_centre, far_radius, u, v,
        segments=int(settings.segment_count),
    )
    out: List[OverlayPolyline] = [OverlayPolyline(
        kind=KIND_SECTOR_CONE, index=0, label="far disc",
        points=far_pts, closed=True,
    )]

    # Optional near disc.
    near = max(0.0, float(near_pc))
    if near > 0:
        near_radius = near * math.tan(math.radians(cone_half_angle_deg))
        near_centre = (
            origin_pc[0] + near * forward_n[0],
            origin_pc[1] + near * forward_n[1],
            origin_pc[2] + near * forward_n[2],
        )
        near_pts = _circle_in_basis(
            near_centre, near_radius, u, v,
            segments=int(settings.segment_count),
        )
        out.append(OverlayPolyline(
            kind=KIND_SECTOR_CONE, index=1, label="near disc",
            points=near_pts, closed=True,
        ))

    # Four edge lines from origin to the far-disc cardinal
    # points (at angle 0, 90, 180, 270 in (u, v)).
    cardinals = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)]
    for i, (cu, cv) in enumerate(cardinals):
        end = (
            far_centre[0] + far_radius * (cu * u[0] + cv * v[0]),
            far_centre[1] + far_radius * (cu * u[1] + cv * v[1]),
            far_centre[2] + far_radius * (cu * u[2] + cv * v[2]),
        )
        out.append(OverlayPolyline(
            kind=KIND_SECTOR_CONE, index=2 + i, label=f"edge {i}",
            points=[origin_pc, end],
        ))
    return out


def build_route_corridor(
    settings: OverlaySettings,
    *,
    waypoints: Sequence[Vec3],
) -> List[OverlayPolyline]:
    """v2.0 route corridor: a centre-line spline through the
    waypoints plus two parallel offset lines at
    ``corridor_width_pc`` to either side. The offsets are
    computed in the locally-perpendicular plane to the
    centre-line tangent at each waypoint, so the corridor
    follows curves naturally for two-or-more waypoint paths.

    Empty / 1-waypoint inputs return an empty list — there's
    no corridor without a direction."""
    pts = [tuple(p) for p in waypoints if p is not None]
    if len(pts) < 2:
        return []
    out: List[OverlayPolyline] = [OverlayPolyline(
        kind=KIND_ROUTE_CORRIDOR, index=0, label="centre",
        points=pts,
    )]
    width = float(settings.corridor_width_pc)
    if width <= 0:
        return out

    # For each waypoint, compute a tangent and pick a stable
    # "up" reference (world +Z when the tangent isn't aligned
    # with it; world +Y otherwise) to derive a side vector.
    side_vectors: List[Vec3] = []
    for i, p in enumerate(pts):
        if i == 0:
            tangent = _vec_sub(pts[1], pts[0])
        elif i == len(pts) - 1:
            tangent = _vec_sub(pts[-1], pts[-2])
        else:
            tangent = _vec_sub(pts[i + 1], pts[i - 1])
        side = _perpendicular(tangent)
        side_vectors.append(side)
    left_pts = [
        (p[0] + width * s[0], p[1] + width * s[1], p[2] + width * s[2])
        for p, s in zip(pts, side_vectors)
    ]
    right_pts = [
        (p[0] - width * s[0], p[1] - width * s[1], p[2] - width * s[2])
        for p, s in zip(pts, side_vectors)
    ]
    out.append(OverlayPolyline(
        kind=KIND_ROUTE_CORRIDOR, index=1, label="left edge",
        points=left_pts,
    ))
    out.append(OverlayPolyline(
        kind=KIND_ROUTE_CORRIDOR, index=2, label="right edge",
        points=right_pts,
    ))
    return out


def _vec_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _perpendicular(v: Vec3) -> Vec3:
    """Return a unit vector perpendicular to ``v``. Picks
    world +Z as the "up" reference unless ``v`` is too close
    to it, in which case +Y is used."""
    length = math.sqrt(sum(c * c for c in v))
    if length < 1e-9:
        return (1.0, 0.0, 0.0)
    n = (v[0] / length, v[1] / length, v[2] / length)
    if abs(n[2]) < 0.99:
        up = (0.0, 0.0, 1.0)
    else:
        up = (0.0, 1.0, 0.0)
    side = (
        n[1] * up[2] - n[2] * up[1],
        n[2] * up[0] - n[0] * up[2],
        n[0] * up[1] - n[1] * up[0],
    )
    s_len = math.sqrt(sum(c * c for c in side))
    if s_len < 1e-9:
        return (1.0, 0.0, 0.0)
    return (side[0] / s_len, side[1] / s_len, side[2] / s_len)


def build_waypoint_labels(
    settings: OverlaySettings,
    *,
    waypoints: Sequence[Tuple[str, Vec3]],
) -> List[OverlayLabel]:
    """v2.0 waypoint label anchors. Each ``(label, position)``
    pair becomes one ``OverlayLabel`` whose position is offset
    by ``label_height_pc`` above the waypoint (along world +Z)
    so the label floats above the point.

    The C4D builder may render this as a text spline or as a
    null whose name carries the label string; either way it
    keys off ``OverlayLabel.text``."""
    out: List[OverlayLabel] = []
    height = float(settings.label_height_pc)
    for label, pos in waypoints:
        if not label:
            continue
        out.append(OverlayLabel(
            text=str(label),
            position=(
                float(pos[0]), float(pos[1]), float(pos[2]) + height,
            ),
        ))
    return out


# ---------------------------------------------------------------------------
# Bundle builder
# ---------------------------------------------------------------------------


def build_overlay_bundle(
    settings: OverlaySettings,
    *,
    sector_origin_pc: Optional[Vec3] = None,
    sector_forward: Optional[Vec3] = None,
    sector_cone_half_angle_deg: Optional[float] = None,
    sector_near_pc: float = 0.0,
    sector_far_pc: Optional[float] = None,
    route_waypoints: Optional[Sequence[Vec3]] = None,
    waypoint_labels: Optional[Sequence[Tuple[str, Vec3]]] = None,
) -> OverlayBundle:
    """Top-level builder. Returns one ``OverlayBundle`` carrying
    every enabled overlay's geometry. Disabled overlays produce
    nothing (the C4D builder removes any previously-materialised
    instance).

    Sector / route / label arguments are optional — the
    corresponding overlays are only built when both the
    settings flag is on *and* the necessary input is supplied.
    """
    bundle = OverlayBundle()

    if settings.show_grid:
        bundle.polylines.extend(build_grid(settings))

    if settings.show_galactic_plane:
        bundle.polylines.append(build_galactic_plane(settings))

    if settings.show_ecliptic_plane:
        bundle.polylines.append(build_ecliptic_plane(settings))

    if settings.show_distance_rings:
        bundle.polylines.extend(build_distance_rings(settings))

    if (
        settings.show_sector_cone
        and sector_origin_pc is not None
        and sector_forward is not None
        and sector_cone_half_angle_deg is not None
    ):
        bundle.polylines.extend(build_sector_cone(
            settings,
            origin_pc=sector_origin_pc,
            forward=sector_forward,
            cone_half_angle_deg=sector_cone_half_angle_deg,
            near_pc=sector_near_pc,
            far_pc=sector_far_pc,
        ))

    if settings.show_route_corridor and route_waypoints:
        bundle.polylines.extend(build_route_corridor(
            settings, waypoints=route_waypoints,
        ))

    if settings.show_waypoint_labels and waypoint_labels:
        bundle.labels.extend(build_waypoint_labels(
            settings, waypoints=waypoint_labels,
        ))

    return bundle
