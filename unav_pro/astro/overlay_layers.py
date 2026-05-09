"""v2.1 astrophysical overlay layers.

Each layer is a pure-Python builder that turns a settings
struct + (optionally) a sequence of catalog objects into the
``OverlayPolyline`` / ``OverlayLabel`` records that the v2.0
C4D builder materialises as scene objects.

Six layer kinds:

* ``distance_shells`` — concentric shells at user-specified
  parsec radii. Conceptually a richer version of the v2.0
  ``distance_rings`` overlay (great circles in three planes
  rather than one ring per radius).
* ``redshift_shells`` — concentric shells whose radii come
  from the v0.5 Hubble-law proxy. Tagged ``approximate``.
* ``magnitude_shells`` — concentric shells whose radii come
  from absolute-vs-apparent magnitude reasoning, sized for
  the dataset's brightness range.
* ``motion_vectors`` — short line segments that visualise
  each star's proper-motion direction (Gaia rows) or
  radial-velocity sign (any row that carries one).
* ``catalog_source_regions`` — bounding spheres / boxes
  around the per-source object groups (e.g. one box for
  Gaia, one for SDSS) so the artist sees how the catalogs
  occupy space.
* ``solar_system_orbits`` — placeholder rings at each JPL
  body's heliocentric distance. v2.x will plug a real
  orbital propagator behind the same builder.

Pure stdlib. No Cinema 4D, no DB, no network. Tests drive
this module directly.

The C4D applier lives in ``c4d_objects/overlays_builder``;
this module produces the data the applier consumes.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from procedural.overlays import (
    OverlayLabel,
    OverlayPolyline,
    Vec3,
    _circle_in_basis,
    _orthonormal_basis_for_plane,
)
from procedural.dataset_helpers import (
    HUBBLE_KM_S_MPC,
    SPEED_OF_LIGHT_KM_S,
)

# ---------------------------------------------------------------------------
# Stable layer identifiers
# ---------------------------------------------------------------------------

#: v2.1 stable layer IDs. The C4D builder keys per-layer
#: containers off these strings; renaming them would break
#: every saved scene state.
LAYER_DISTANCE_SHELLS: str = "distance_shells"
LAYER_REDSHIFT_SHELLS: str = "redshift_shells"
LAYER_MAGNITUDE_SHELLS: str = "magnitude_shells"
LAYER_MOTION_VECTORS: str = "motion_vectors"
LAYER_CATALOG_SOURCE_REGIONS: str = "catalog_source_regions"
LAYER_SOLAR_SYSTEM_ORBITS: str = "solar_system_orbits"
LAYER_CONSTELLATION_BOUNDARIES: str = "constellation_boundaries"
LAYER_OBJECT_DENSITY_VOLUME: str = "object_density_volume"

SCIENCE_LAYER_IDS: Tuple[str, ...] = (
    LAYER_DISTANCE_SHELLS,
    LAYER_REDSHIFT_SHELLS,
    LAYER_MAGNITUDE_SHELLS,
    LAYER_MOTION_VECTORS,
    LAYER_CATALOG_SOURCE_REGIONS,
    LAYER_SOLAR_SYSTEM_ORBITS,
    LAYER_CONSTELLATION_BOUNDARIES,
    LAYER_OBJECT_DENSITY_VOLUME,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Hard cap on motion-vector lines emitted per build pass.
#: A million-row Gaia subset would otherwise produce a
#: million tiny scene objects.
MAX_MOTION_VECTORS: int = 5_000

#: Conversion factor: arcsec/yr → C4D units/year given the
#: catalog's parsec position. ``v_tan_pc_per_yr ≈ pmra_masyr ×
#: distance_pc × π / (180 × 3.6e6 × 1)``. The v2.1 motion-
#: vector layer uses a much coarser scaling so the artist
#: actually sees the vector in the viewport — see the
#: ``MotionVectorSettings.scale_pc_per_masyr`` knob.
DEFAULT_PM_VECTOR_SCALE_PC: float = 0.05

#: Distance fallback (parsec) for a row whose distance can't
#: be resolved. Used by motion-vector / source-region
#: builders when they need to anchor a vector somewhere; the
#: number is intentionally far so the artist sees the row
#: lives "far away" and can fix the underlying data.
UNRESOLVED_DISTANCE_PC: float = 1.0e5


# ---------------------------------------------------------------------------
# Per-layer settings
# ---------------------------------------------------------------------------


@dataclass
class DistanceShellSettings:
    """Concentric distance shells.

    ``radii_pc`` is the list of radii. Each radius produces
    three orthogonal great circles (XY / XZ / YZ planes) so
    the shell reads as an actual spherical shell rather than
    a single ring."""

    enabled: bool = False
    radii_pc: List[float] = field(
        default_factory=lambda: [10.0, 50.0, 100.0, 1000.0],
    )
    segment_count: int = 64

    def __post_init__(self) -> None:
        cleaned: List[float] = []
        for r in self.radii_pc or ():
            try:
                v = float(r)
            except (TypeError, ValueError):
                continue
            if v > 0.0:
                cleaned.append(v)
        cleaned = sorted(set(cleaned))[:32]
        self.radii_pc = cleaned or [100.0]
        if self.segment_count < 8:
            self.segment_count = 8
        if self.segment_count > 1024:
            self.segment_count = 1024


@dataclass
class RedshiftShellSettings:
    """Hubble-law proxy redshift shells. Tagged
    ``approximate`` — see SCIENCE_LAYER_LIMITATIONS.md."""

    enabled: bool = False
    redshifts: List[float] = field(
        default_factory=lambda: [0.01, 0.05, 0.1, 0.5, 1.0],
    )
    segment_count: int = 64

    def __post_init__(self) -> None:
        cleaned: List[float] = []
        for z in self.redshifts or ():
            try:
                v = float(z)
            except (TypeError, ValueError):
                continue
            if v > 0.0:
                cleaned.append(v)
        cleaned = sorted(set(cleaned))[:16]
        self.redshifts = cleaned or [0.1]
        if self.segment_count < 8:
            self.segment_count = 8


@dataclass
class MagnitudeShellSettings:
    """Concentric shells in apparent-magnitude space.

    The v2.1 layer maps magnitudes to parsec radii by a
    closed-form scale: shells at 5, 8, 11, 14 mag map to
    radii of 50, 250, 1000, 5000 pc respectively (rough
    visual stand-ins; the layer is not a luminosity-distance
    converter). The mapping is the same across all
    datasets; per-row absolute magnitude is *not* used."""

    enabled: bool = False
    magnitudes: List[float] = field(
        default_factory=lambda: [5.0, 8.0, 11.0, 14.0],
    )
    segment_count: int = 64

    def __post_init__(self) -> None:
        cleaned: List[float] = []
        for m in self.magnitudes or ():
            try:
                v = float(m)
            except (TypeError, ValueError):
                continue
            cleaned.append(v)
        cleaned = sorted(set(cleaned))[:16]
        self.magnitudes = cleaned or [5.0]
        if self.segment_count < 8:
            self.segment_count = 8


@dataclass
class MotionVectorSettings:
    """Per-row motion vectors. Two flavours, both optional:

    * **Proper motion.** Drawn as a short line in the
      tangent plane at the row's position. Length is
      ``hypot(pmra, pmdec)`` × ``scale_pc_per_masyr``.
    * **Radial velocity.** Drawn as a short line *along the
      line of sight*, with sign indicating receding (away
      from origin) or approaching. Length is
      ``|rv_kms|`` × ``rv_scale_pc_per_kms``.

    Both flavours obey the global cap (``MAX_MOTION_VECTORS``)
    so an enormous Gaia subset can't blow up the scene."""

    enabled: bool = False
    show_proper_motion: bool = True
    show_radial_velocity: bool = False
    scale_pc_per_masyr: float = DEFAULT_PM_VECTOR_SCALE_PC
    rv_scale_pc_per_kms: float = 0.001
    max_vectors: int = MAX_MOTION_VECTORS
    min_pm_masyr: float = 0.0

    def __post_init__(self) -> None:
        if self.scale_pc_per_masyr <= 0:
            raise ValueError("scale_pc_per_masyr must be > 0")
        if self.rv_scale_pc_per_kms <= 0:
            raise ValueError("rv_scale_pc_per_kms must be > 0")
        if self.max_vectors < 1:
            self.max_vectors = 1
        if self.max_vectors > MAX_MOTION_VECTORS:
            self.max_vectors = MAX_MOTION_VECTORS
        if self.min_pm_masyr < 0:
            self.min_pm_masyr = 0.0


@dataclass
class CatalogSourceRegionSettings:
    """Per-catalog-source bounding region.

    For each distinct ``catalog_source`` in the dataset the
    layer emits one bounding sphere (centre + three
    orthogonal great circles)."""

    enabled: bool = False
    segment_count: int = 32
    label_each_region: bool = True


@dataclass
class SolarSystemOrbitSettings:
    """Heliocentric orbital placeholder rings.

    For each row whose catalog_source starts with "JPL" or
    "Horizons", the layer emits a circle at the row's
    heliocentric distance in the ecliptic plane.

    v2.1 is a *placeholder* — the rings are circles at the
    instantaneous heliocentric distance, not the actual
    orbital ellipse. v2.x will plug an osculating-elements
    propagator behind the same builder."""

    enabled: bool = False
    segment_count: int = 64
    label_each_orbit: bool = True


@dataclass
class ConstellationBoundarySettings:
    """v2.1 placeholder. The IAU constellation boundaries
    are 89 closed polygons in B1875 equatorial coordinates;
    UNAV does not yet ship the boundary data. The layer is
    declared so the dialog can wire the toggle today and the
    v2.x boundary data drops in without an API change."""

    enabled: bool = False


@dataclass
class ObjectDensityVolumeSettings:
    """v2.1 placeholder. v2.x will plug the
    ``compute_density_heatmap_placeholder`` output behind the
    same builder."""

    enabled: bool = False


# ---------------------------------------------------------------------------
# Layer build outputs
# ---------------------------------------------------------------------------


@dataclass
class LayerBuildResult:
    """One layer's contribution to a science bundle.

    ``polylines`` and ``labels`` reuse the v2.0 overlay types
    so the C4D applier can consume both v2.0 and v2.1
    outputs through one code path. ``warnings`` are
    human-readable strings the dialog appends to the log
    when the layer can't fully build (missing fields,
    unsupported dataset, etc.).
    """

    layer_id: str
    polylines: List[OverlayPolyline] = field(default_factory=list)
    labels: List[OverlayLabel] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    item_count: int = 0


# ---------------------------------------------------------------------------
# Helpers — three-plane shell construction
# ---------------------------------------------------------------------------


def _three_plane_shell_polylines(
    radius: float,
    *,
    centre: Vec3 = (0.0, 0.0, 0.0),
    segments: int = 64,
    layer_id: str,
    label_prefix: str,
    base_index: int,
) -> List[OverlayPolyline]:
    """Build three orthogonal great circles at ``radius``
    around ``centre``. Returns three closed polylines tagged
    with the supplied ``layer_id`` so the C4D builder
    groups them together."""
    out: List[OverlayPolyline] = []
    bases = (
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), "XY"),
        ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), "XZ"),
        ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), "YZ"),
    )
    for i, (u, v, plane_label) in enumerate(bases):
        pts = _circle_in_basis(centre, float(radius), u, v, segments=segments)
        out.append(OverlayPolyline(
            kind=layer_id,
            index=base_index + i,
            label=f"{label_prefix} ({plane_label})",
            points=pts,
            closed=True,
        ))
    return out


# ---------------------------------------------------------------------------
# Layer builders
# ---------------------------------------------------------------------------


def build_distance_shells(
    settings: DistanceShellSettings,
) -> LayerBuildResult:
    res = LayerBuildResult(layer_id=LAYER_DISTANCE_SHELLS)
    if not settings.enabled:
        return res
    next_index = 0
    for r in settings.radii_pc:
        polys = _three_plane_shell_polylines(
            float(r),
            segments=int(settings.segment_count),
            layer_id=LAYER_DISTANCE_SHELLS,
            label_prefix=f"{r:g} pc",
            base_index=next_index,
        )
        res.polylines.extend(polys)
        next_index += len(polys)
        res.item_count += 1
    return res


def build_redshift_shells(
    settings: RedshiftShellSettings,
) -> LayerBuildResult:
    """Hubble-law proxy: r_pc ≈ (c · z / H₀) × 1e6.
    Tagged ``approximate`` in the polyline label."""
    res = LayerBuildResult(layer_id=LAYER_REDSHIFT_SHELLS)
    if not settings.enabled:
        return res
    if not settings.redshifts:
        res.warnings.append(
            "redshift_shells: no z values configured."
        )
        return res
    res.warnings.append(
        "redshift_shells use the v0.5 Hubble-law proxy "
        "(coarse; not for cosmology)."
    )
    next_index = 0
    for z in settings.redshifts:
        d_pc = (SPEED_OF_LIGHT_KM_S * float(z) / HUBBLE_KM_S_MPC) * 1.0e6
        polys = _three_plane_shell_polylines(
            d_pc,
            segments=int(settings.segment_count),
            layer_id=LAYER_REDSHIFT_SHELLS,
            label_prefix=f"z={z:.3f} ≈ {d_pc:.3g} pc (approximate)",
            base_index=next_index,
        )
        res.polylines.extend(polys)
        next_index += len(polys)
        res.item_count += 1
    return res


# Cosmetic mapping from apparent magnitude to a parsec-scale
# shell radius. The v2.1 magnitude layer is a *visual*
# stand-in, not a flux-distance converter — the artist sees
# concentric shells whose radii grow with magnitude and
# eyeballs the dataset's brightness distribution against
# them.
def _magnitude_to_proxy_pc(mag: float) -> float:
    # 5 mag → 50 pc; each additional 3 mag multiplies the
    # radius by 5 (so 8 mag → 250 pc, 11 mag → 1250 pc, etc.).
    base_mag = 5.0
    base_pc = 50.0
    return base_pc * (5.0 ** ((float(mag) - base_mag) / 3.0))


def build_magnitude_shells(
    settings: MagnitudeShellSettings,
) -> LayerBuildResult:
    res = LayerBuildResult(layer_id=LAYER_MAGNITUDE_SHELLS)
    if not settings.enabled:
        return res
    if not settings.magnitudes:
        res.warnings.append(
            "magnitude_shells: no magnitude values configured."
        )
        return res
    res.warnings.append(
        "magnitude_shells use a cosmetic mag→radius mapping "
        "(visual aid only; not a flux-distance converter)."
    )
    next_index = 0
    for mag in settings.magnitudes:
        r_pc = _magnitude_to_proxy_pc(mag)
        polys = _three_plane_shell_polylines(
            r_pc,
            segments=int(settings.segment_count),
            layer_id=LAYER_MAGNITUDE_SHELLS,
            label_prefix=f"mag {mag:g} ≈ {r_pc:.3g} pc (cosmetic)",
            base_index=next_index,
        )
        res.polylines.extend(polys)
        next_index += len(polys)
        res.item_count += 1
    return res


def _has_proper_motion(obj: Any) -> bool:
    return (
        getattr(obj, "proper_motion_ra", None) is not None
        or getattr(obj, "proper_motion_dec", None) is not None
    )


def _is_gaia_source(obj: Any) -> bool:
    src = (getattr(obj, "catalog_source", "") or "").lower()
    return src.startswith("gaia")


def _is_jpl_source(obj: Any) -> bool:
    src = (getattr(obj, "catalog_source", "") or "").lower()
    return src.startswith("jpl") or src.startswith("horizons")


def _is_extragalactic_source(obj: Any) -> bool:
    src = (getattr(obj, "catalog_source", "") or "").lower()
    return src.startswith("sdss") or src.startswith("desi")


def _row_position(obj: Any) -> Optional[Vec3]:
    x = getattr(obj, "cartesian_x", None)
    y = getattr(obj, "cartesian_y", None)
    z = getattr(obj, "cartesian_z", None)
    if x is None or y is None or z is None:
        return None
    return (float(x), float(y), float(z))


def build_motion_vectors(
    settings: MotionVectorSettings,
    *,
    objects: Iterable[Any],
) -> LayerBuildResult:
    """Per-row motion vectors. Skips rows without parsec
    position; respects the global vector cap."""
    res = LayerBuildResult(layer_id=LAYER_MOTION_VECTORS)
    if not settings.enabled:
        return res
    rows = list(objects or ())
    if not rows:
        res.warnings.append(
            "motion_vectors: no rows in active dataset."
        )
        return res

    # Filter rows that contribute.
    pm_rows: List[Any] = []
    rv_rows: List[Any] = []
    for obj in rows:
        if _row_position(obj) is None:
            continue
        if settings.show_proper_motion and _has_proper_motion(obj):
            pmra = float(getattr(obj, "proper_motion_ra", 0.0) or 0.0)
            pmdec = float(getattr(obj, "proper_motion_dec", 0.0) or 0.0)
            mag = math.hypot(pmra, pmdec)
            if mag >= settings.min_pm_masyr:
                pm_rows.append((obj, pmra, pmdec))
        if settings.show_radial_velocity and \
                getattr(obj, "radial_velocity_kms", None) is not None:
            rv_rows.append((obj, float(obj.radial_velocity_kms)))

    # Cap.
    cap = int(settings.max_vectors)
    truncated_pm = max(0, len(pm_rows) - cap)
    truncated_rv = max(0, len(rv_rows) - cap)
    pm_rows = pm_rows[:cap]
    rv_rows = rv_rows[:cap]
    if truncated_pm:
        res.warnings.append(
            f"motion_vectors: capped proper-motion rows "
            f"({truncated_pm} dropped)."
        )
    if truncated_rv:
        res.warnings.append(
            f"motion_vectors: capped radial-velocity rows "
            f"({truncated_rv} dropped)."
        )

    next_index = 0

    # Proper motion: short tangent-plane vectors.
    for obj, pmra, pmdec in pm_rows:
        pos = _row_position(obj)
        if pos is None:
            continue
        # Build a tangent-plane basis at the row position.
        # The "outward" vector is just the position direction.
        r = math.sqrt(pos[0] ** 2 + pos[1] ** 2 + pos[2] ** 2)
        if r < 1e-9:
            continue
        outward = (pos[0] / r, pos[1] / r, pos[2] / r)
        # East = (-sin(ra), +cos(ra), 0). RA is recoverable
        # from outward.
        ra = math.atan2(outward[1], outward[0])
        east = (-math.sin(ra), math.cos(ra), 0.0)
        # North = outward × east.
        north = (
            outward[1] * east[2] - outward[2] * east[1],
            outward[2] * east[0] - outward[0] * east[2],
            outward[0] * east[1] - outward[1] * east[0],
        )
        scale = settings.scale_pc_per_masyr
        dx = scale * (pmra * east[0] + pmdec * north[0])
        dy = scale * (pmra * east[1] + pmdec * north[1])
        dz = scale * (pmra * east[2] + pmdec * north[2])
        end = (pos[0] + dx, pos[1] + dy, pos[2] + dz)
        res.polylines.append(OverlayPolyline(
            kind=LAYER_MOTION_VECTORS, index=next_index,
            label=f"pm:{getattr(obj, 'uid', '')}",
            points=[pos, end],
        ))
        next_index += 1
        res.item_count += 1

    # Radial velocity: along the line-of-sight direction.
    for obj, rv in rv_rows:
        pos = _row_position(obj)
        if pos is None:
            continue
        r = math.sqrt(pos[0] ** 2 + pos[1] ** 2 + pos[2] ** 2)
        if r < 1e-9:
            continue
        outward = (pos[0] / r, pos[1] / r, pos[2] / r)
        # Positive rv = receding → arrow points outward.
        sign = 1.0 if rv >= 0 else -1.0
        length = abs(rv) * settings.rv_scale_pc_per_kms * sign
        end = (
            pos[0] + outward[0] * length,
            pos[1] + outward[1] * length,
            pos[2] + outward[2] * length,
        )
        res.polylines.append(OverlayPolyline(
            kind=LAYER_MOTION_VECTORS, index=next_index,
            label=f"rv:{getattr(obj, 'uid', '')}",
            points=[pos, end],
        ))
        next_index += 1
        res.item_count += 1

    if not res.polylines:
        res.warnings.append(
            "motion_vectors: no rows in active dataset carry "
            "proper-motion or radial-velocity fields."
        )
    return res


def build_catalog_source_regions(
    settings: CatalogSourceRegionSettings,
    *,
    objects: Iterable[Any],
) -> LayerBuildResult:
    """One bounding sphere per distinct catalog_source.

    Uses the v2.0 ``compute_bounding_sphere`` formula but
    grouped by source."""
    res = LayerBuildResult(layer_id=LAYER_CATALOG_SOURCE_REGIONS)
    if not settings.enabled:
        return res
    rows = list(objects or ())
    if not rows:
        res.warnings.append(
            "catalog_source_regions: no rows in active dataset."
        )
        return res

    # Group rows by source.
    by_source: Dict[str, List[Any]] = defaultdict(list)
    for obj in rows:
        src = (getattr(obj, "catalog_source", "") or "<unspecified>")
        by_source[str(src)].append(obj)

    next_index = 0
    sources_with_positions = 0
    for source, group in sorted(by_source.items()):
        positions: List[Vec3] = []
        for obj in group:
            pos = _row_position(obj)
            if pos is not None:
                positions.append(pos)
        if not positions:
            continue
        cx = sum(p[0] for p in positions) / len(positions)
        cy = sum(p[1] for p in positions) / len(positions)
        cz = sum(p[2] for p in positions) / len(positions)
        radius_sq = 0.0
        for p in positions:
            d2 = (p[0] - cx) ** 2 + (p[1] - cy) ** 2 + (p[2] - cz) ** 2
            if d2 > radius_sq:
                radius_sq = d2
        radius = math.sqrt(radius_sq)
        if radius < 1e-9:
            radius = 1.0  # at least one visible ring
        polys = _three_plane_shell_polylines(
            radius,
            centre=(cx, cy, cz),
            segments=int(settings.segment_count),
            layer_id=LAYER_CATALOG_SOURCE_REGIONS,
            label_prefix=f"{source} (n={len(positions)})",
            base_index=next_index,
        )
        res.polylines.extend(polys)
        next_index += len(polys)
        if settings.label_each_region:
            res.labels.append(OverlayLabel(
                kind=LAYER_CATALOG_SOURCE_REGIONS,
                text=f"{source} (n={len(positions)})",
                position=(cx, cy, cz),
            ))
        sources_with_positions += 1
        res.item_count += 1

    if sources_with_positions == 0:
        res.warnings.append(
            "catalog_source_regions: no catalog_source group "
            "in the dataset has any parsec position; nothing "
            "to draw."
        )
    return res


def build_solar_system_orbits(
    settings: SolarSystemOrbitSettings,
    *,
    objects: Iterable[Any],
) -> LayerBuildResult:
    """Heliocentric placeholder rings — one ring per JPL row,
    in the XY plane at the row's distance.

    This is the v2.1 placeholder (instantaneous radius, not
    the true orbit). The layer is dataset-aware: rows whose
    ``catalog_source`` doesn't start with "JPL" / "Horizons"
    are silently skipped."""
    res = LayerBuildResult(layer_id=LAYER_SOLAR_SYSTEM_ORBITS)
    if not settings.enabled:
        return res
    rows = list(objects or ())
    if not rows:
        res.warnings.append(
            "solar_system_orbits: no rows in active dataset."
        )
        return res
    res.warnings.append(
        "solar_system_orbits is a placeholder — rings sit at "
        "the row's instantaneous heliocentric distance, not "
        "the true orbital ellipse."
    )
    next_index = 0
    seen_uids: set = set()
    for obj in rows:
        if not _is_jpl_source(obj):
            continue
        pos = _row_position(obj)
        if pos is None:
            continue
        # De-duplicate by uid prefix (v0.4 uids encode the
        # epoch; we only want one ring per body).
        uid = (getattr(obj, "uid", "") or "")
        body = uid.split(":")[1] if ":" in uid else uid
        if body in seen_uids:
            continue
        seen_uids.add(body)
        radius = math.sqrt(pos[0] ** 2 + pos[1] ** 2 + pos[2] ** 2)
        if radius < 1e-9:
            continue
        # Single XY-plane ring per body.
        ring_pts = _circle_in_basis(
            (0.0, 0.0, 0.0), radius,
            (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
            segments=int(settings.segment_count),
        )
        res.polylines.append(OverlayPolyline(
            kind=LAYER_SOLAR_SYSTEM_ORBITS,
            index=next_index,
            label=f"{body} ≈ {radius:.4g} pc (placeholder)",
            points=ring_pts,
            closed=True,
        ))
        next_index += 1
        if settings.label_each_orbit:
            res.labels.append(OverlayLabel(
                kind=LAYER_SOLAR_SYSTEM_ORBITS,
                text=body,
                position=pos,
            ))
        res.item_count += 1

    if res.item_count == 0:
        res.warnings.append(
            "solar_system_orbits: active dataset has no JPL "
            "Horizons rows; layer is empty."
        )
    return res


def build_constellation_boundaries(
    settings: ConstellationBoundarySettings,
) -> LayerBuildResult:
    """v2.1 placeholder — emits no polylines and a single
    informational warning so the dialog can render the toggle
    today."""
    res = LayerBuildResult(layer_id=LAYER_CONSTELLATION_BOUNDARIES)
    if settings.enabled:
        res.warnings.append(
            "constellation_boundaries: v2.1 placeholder — IAU "
            "boundary data lands in v2.x."
        )
    return res


def build_object_density_volume(
    settings: ObjectDensityVolumeSettings,
) -> LayerBuildResult:
    """v2.1 placeholder — see CONSTELLATION_BOUNDARIES."""
    res = LayerBuildResult(layer_id=LAYER_OBJECT_DENSITY_VOLUME)
    if settings.enabled:
        res.warnings.append(
            "object_density_volume: v2.1 placeholder — "
            "density estimator lands in v2.x."
        )
    return res
