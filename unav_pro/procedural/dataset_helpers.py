"""v2.0 dataset-derived overlay helpers.

Pure-Python helpers that turn a sequence of ``CatalogObject``
into overlay-ready summaries:

* ``compute_bounding_sphere`` — centroid + max-distance for
  a dataset, suitable for an "active dataset bounding sphere"
  overlay the artist can drop into the scene.
* ``compute_source_distribution`` — histogram of catalog
  sources / object types / distance bins.
* ``compute_density_heatmap_placeholder`` — an empty bin
  array sized for a future v2.x density-heatmap overlay.
* ``compute_redshift_shells_placeholder`` — proxy parsec
  radii for a future v2.x redshift-shell overlay.

The two placeholder functions return well-typed empty /
zero-filled outputs so the dialog can wire to them today and
the v2.x implementation can drop in without changing the
call-sites.

Stdlib-only. Tested without Cinema 4D.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Bounding sphere
# ---------------------------------------------------------------------------


@dataclass
class BoundingSphere:
    """Centroid-centred bounding sphere over a sequence of
    catalog objects with known parsec positions.

    ``count`` is the number of objects that contributed (i.e.
    that had a parsec position; rows without one are silently
    skipped). ``radius_pc`` is the L2 distance from the
    centroid to the farthest contributing point — a *worst-
    case* bound, not the minimum-enclosing sphere.
    """

    count: int = 0
    centre_pc: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius_pc: float = 0.0


def compute_bounding_sphere(objects: Iterable) -> BoundingSphere:
    """Centroid + farthest-point radius. Objects must expose
    ``cartesian_x/y/z`` attributes (the v0.2+ schema does
    this via ``compute_derived_fields``); rows without are
    skipped.

    Empty input → zero-radius sphere at the origin.
    """
    xs: List[float] = []
    ys: List[float] = []
    zs: List[float] = []
    for obj in objects:
        x = getattr(obj, "cartesian_x", None)
        y = getattr(obj, "cartesian_y", None)
        z = getattr(obj, "cartesian_z", None)
        if x is None or y is None or z is None:
            continue
        xs.append(float(x))
        ys.append(float(y))
        zs.append(float(z))
    n = len(xs)
    if n == 0:
        return BoundingSphere()
    cx = sum(xs) / n
    cy = sum(ys) / n
    cz = sum(zs) / n
    radius_sq = 0.0
    for x, y, z in zip(xs, ys, zs):
        dx = x - cx
        dy = y - cy
        dz = z - cz
        d2 = dx * dx + dy * dy + dz * dz
        if d2 > radius_sq:
            radius_sq = d2
    return BoundingSphere(
        count=n,
        centre_pc=(cx, cy, cz),
        radius_pc=math.sqrt(radius_sq),
    )


# ---------------------------------------------------------------------------
# Source distribution summary
# ---------------------------------------------------------------------------


@dataclass
class SourceDistribution:
    """Per-source / per-type histograms + overall counts.

    Useful for the dialog's "active dataset summary" panel
    and for the route-analytics layer's "this voyage spans
    N catalog sources" sentence.
    """

    total: int = 0
    by_catalog_source: Dict[str, int] = field(default_factory=dict)
    by_object_type: Dict[str, int] = field(default_factory=dict)

    def render_text(self) -> str:
        if self.total == 0:
            return "No objects in dataset."
        lines: List[str] = [f"=== Dataset summary ({self.total} objects) ==="]
        if self.by_catalog_source:
            lines.append("--- Catalog sources ---")
            for src, count in sorted(self.by_catalog_source.items()):
                lines.append(f"  {src or '<unspecified>':18}: {count}")
        if self.by_object_type:
            lines.append("--- Object types ---")
            for typ, count in sorted(self.by_object_type.items()):
                lines.append(f"  {typ or '<unspecified>':14}: {count}")
        return "\n".join(lines)


def compute_source_distribution(objects: Iterable) -> SourceDistribution:
    rows = list(objects)
    summary = SourceDistribution(total=len(rows))
    summary.by_catalog_source = dict(
        Counter(
            (getattr(o, "catalog_source", "") or "<unspecified>")
            for o in rows
        )
    )
    summary.by_object_type = dict(
        Counter(
            (getattr(o, "object_type", "") or "<unspecified>")
            for o in rows
        )
    )
    return summary


# ---------------------------------------------------------------------------
# Density heatmap placeholder
# ---------------------------------------------------------------------------


@dataclass
class DensityHeatmap:
    """Placeholder result for the v2.x density-heatmap
    overlay. v2.0 returns a zero-filled grid sized for the
    requested bin count; the dialog can wire its UI today
    and the v2.x implementation populates the cells later.

    ``bins`` is the per-axis bin count; ``cells`` is a flat
    list of ``bins**3`` floats (row-major; index =
    ((ix * bins) + iy) * bins + iz)."""

    bins: int = 0
    extent_pc: float = 0.0
    cells: List[float] = field(default_factory=list)
    is_placeholder: bool = True

    def cell_index(self, ix: int, iy: int, iz: int) -> int:
        return ((ix * self.bins) + iy) * self.bins + iz


def compute_density_heatmap_placeholder(
    objects: Iterable,
    *,
    bins: int = 8,
    extent_pc: float = 100.0,
) -> DensityHeatmap:
    """Allocate the heatmap grid + reserve the slot for a
    future v2.x density estimator. v2.0 fills every cell with
    0.0 and sets ``is_placeholder=True`` so the dialog can
    surface "(awaiting v2.x density estimator)".

    The signature consumes ``objects`` so the v2.x estimator
    can drop in without changing the call-site."""
    bins = max(1, min(int(bins), 64))
    if extent_pc <= 0:
        extent_pc = 1.0
    cell_count = bins * bins * bins
    return DensityHeatmap(
        bins=bins,
        extent_pc=float(extent_pc),
        cells=[0.0] * cell_count,
        is_placeholder=True,
    )


# ---------------------------------------------------------------------------
# Redshift shell placeholder
# ---------------------------------------------------------------------------


@dataclass
class RedshiftShells:
    """Placeholder result for the v2.x redshift-shell
    overlay. v2.0 returns the requested shell radii (parsec)
    using the v0.5 Hubble-law proxy at a small bundled set
    of redshifts; v2.x will plug a real cosmology engine
    behind the same API.

    Each shell has ``z`` (redshift) + ``radius_pc`` (proxy
    distance in parsec)."""

    shells: List[Tuple[float, float]] = field(default_factory=list)
    is_placeholder: bool = True

    def render_text(self) -> str:
        if not self.shells:
            return "No redshift shells."
        lines: List[str] = []
        if self.is_placeholder:
            lines.append("(redshift shells use the v0.5 Hubble proxy)")
        for z, r in self.shells:
            lines.append(f"  z = {z:.3f}  →  {r:.4g} pc")
        return "\n".join(lines)


# Hubble's constant in km/s/Mpc (Planck 2018).
HUBBLE_KM_S_MPC: float = 67.4
SPEED_OF_LIGHT_KM_S: float = 299_792.458
DEFAULT_SHELL_REDSHIFTS: Tuple[float, ...] = (0.01, 0.05, 0.1, 0.5, 1.0)


def compute_redshift_shells_placeholder(
    redshifts: Optional[Sequence[float]] = None,
) -> RedshiftShells:
    """Allocate redshift-shell radii using the v0.5 Hubble-
    law proxy: ``d_pc ≈ (c·z / H₀) × 1e6`` (linear regime).

    ``redshifts`` defaults to a small bundled ladder
    (``DEFAULT_SHELL_REDSHIFTS``); the dialog can pass any
    increasing sequence. Negative or zero redshifts are
    dropped silently."""
    rs = list(redshifts) if redshifts is not None else list(DEFAULT_SHELL_REDSHIFTS)
    out: List[Tuple[float, float]] = []
    for z in rs:
        try:
            zf = float(z)
        except (TypeError, ValueError):
            continue
        if zf <= 0.0:
            continue
        # d_Mpc = c * z / H0; d_pc = d_Mpc * 1e6.
        d_mpc = SPEED_OF_LIGHT_KM_S * zf / HUBBLE_KM_S_MPC
        out.append((zf, d_mpc * 1.0e6))
    return RedshiftShells(shells=out, is_placeholder=True)
