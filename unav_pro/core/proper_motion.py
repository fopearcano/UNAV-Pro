"""Approximate proper-motion propagation for the v1.2 temporal layer.

The minimum-viable model: given a Gaia (or other catalog) row's
position at the source's *reference epoch*, plus its proper-motion
components, return the position at any *target epoch*. The result
is good enough to put the star within a few mas of its actual
sky position over a decade or so — matching Gaia DR3's quoted
``pmra`` / ``pmdec`` precision while staying readable.

What this module does NOT do:

* **No parallax / parallactic motion.** The Earth-orbit annual
  wobble is below the ~mas precision floor at typical UNAV
  display scales.
* **No radial-velocity-driven distance update.** Stars move in
  3D; v1.2 propagates the angular position only. Distance
  stays at the catalog value.
* **No general-relativistic corrections.** No solar-system
  light-bending; no aberration of starlight.
* **No coordinate-system transformations.** Inputs and outputs
  are ICRS RA/Dec.
* **No covariance handling.** ``pmra_error`` and ``pmdec_error``
  are NOT propagated; the output is a point estimate.

The math is the linear tangent-plane approximation:

    Δra_deg  = (pmra  / 3.6e6) * Δyears  / cos(dec)
    Δdec_deg = (pmdec / 3.6e6) * Δyears

where ``pmra`` / ``pmdec`` are in mas/yr, the ``cos(dec)`` factor
removes the convention that ``pmra`` is already a great-circle
displacement (it is on the Gaia ICRS reference; on some older
sources it isn't).

For the limitations doc see
``docs/GAIA_PROPER_MOTION_LIMITATIONS.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from core.time_model import (
    DAYS_PER_JULIAN_YEAR,
    DEFAULT_REFERENCE_EPOCH_JD,
    J2016_JD,
    years_between,
)
from data.schema import CatalogObject

#: Conversion: 1 mas (milliarcsecond) = 1/3.6e6 degree.
MAS_PER_DEG: float = 3_600_000.0


@dataclass
class ProperMotionState:
    """Inputs to ``propagate_position``: where the star was at
    its reference epoch + how it's moving."""

    ra_deg: float
    dec_deg: float
    pmra_masyr: float          # ICRS great-circle convention (already cos(dec)-corrected on Gaia)
    pmdec_masyr: float
    reference_epoch_jd: float = DEFAULT_REFERENCE_EPOCH_JD


def propagate_position(
    state: ProperMotionState,
    target_epoch_jd: float,
) -> Tuple[float, float]:
    """Return ``(ra_deg, dec_deg)`` at ``target_epoch_jd``.

    Linear in time. Wraps RA into ``[0, 360)`` and clamps Dec
    into ``[-90, 90]``. For Δyears == 0 the inputs are returned
    unchanged.
    """
    delta_years = years_between(state.reference_epoch_jd, target_epoch_jd)
    if delta_years == 0.0:
        return float(state.ra_deg), float(state.dec_deg)

    # Gaia / ICRS convention: pmra is a great-circle motion,
    # i.e. already includes cos(dec). For the angular ra
    # increment we therefore divide by cos(dec).
    cos_dec = math.cos(math.radians(float(state.dec_deg)))
    if abs(cos_dec) < 1e-12:
        # At the celestial pole the great-circle convention
        # becomes singular. Fall back to "no RA change."
        d_ra = 0.0
    else:
        d_ra = (
            float(state.pmra_masyr) / MAS_PER_DEG * delta_years / cos_dec
        )
    d_dec = float(state.pmdec_masyr) / MAS_PER_DEG * delta_years

    new_ra = (float(state.ra_deg) + d_ra) % 360.0
    new_dec = float(state.dec_deg) + d_dec
    if new_dec > 90.0:
        new_dec = 90.0
    elif new_dec < -90.0:
        new_dec = -90.0
    return new_ra, new_dec


def propagate_object(
    obj: CatalogObject,
    target_epoch_jd: float,
    *,
    reference_epoch_jd: Optional[float] = None,
    in_place: bool = False,
) -> CatalogObject:
    """Apply ``propagate_position`` to a ``CatalogObject``'s
    ``proper_motion_ra`` / ``proper_motion_dec``.

    ``reference_epoch_jd`` overrides the default (J2016 for
    Gaia DR3 rows). ``in_place=True`` mutates the input
    instead of cloning.

    Rows without a usable ``pmra`` or ``pmdec`` are returned
    untouched — the function is a no-op for objects that don't
    have proper-motion data, so callers can run it on every
    row in a mixed dataset.
    """
    pmra = obj.proper_motion_ra
    pmdec = obj.proper_motion_dec
    if pmra is None or pmdec is None:
        return obj if in_place else _shallow_clone(obj)

    state = ProperMotionState(
        ra_deg=float(obj.ra_deg),
        dec_deg=float(obj.dec_deg),
        pmra_masyr=float(pmra),
        pmdec_masyr=float(pmdec),
        reference_epoch_jd=(
            float(reference_epoch_jd)
            if reference_epoch_jd is not None
            else DEFAULT_REFERENCE_EPOCH_JD
        ),
    )
    new_ra, new_dec = propagate_position(state, float(target_epoch_jd))

    target = obj if in_place else _shallow_clone(obj)
    target.ra_deg = new_ra
    target.dec_deg = new_dec
    # Cartesian / c4d derivatives must be recomputed by callers
    # (compute_derived_fields). We deliberately don't redo them
    # here so the temporal layer can decide whether to recompute
    # (the visible-sector path does; the search path doesn't).
    target.cartesian_x = None
    target.cartesian_y = None
    target.cartesian_z = None
    target.c4d_x = None
    target.c4d_y = None
    target.c4d_z = None
    return target


def _shallow_clone(obj: CatalogObject) -> CatalogObject:
    """Per-field clone. ``copy.deepcopy`` is overkill for a
    POD dataclass; this is faster and avoids dragging in
    implementation details of nested objects."""
    return CatalogObject(**{k: v for k, v in obj.to_dict().items()
                            if k in {f.name for f in CatalogObject.__dataclass_fields__.values()}})


# ---------------------------------------------------------------------------
# Helpers used by the temporal resolver
# ---------------------------------------------------------------------------


def is_propagatable(obj: CatalogObject) -> bool:
    """True iff the object carries the bare-minimum proper-motion
    fields the propagator needs."""
    return (
        obj.proper_motion_ra is not None
        and obj.proper_motion_dec is not None
    )


def reference_epoch_for(obj: CatalogObject) -> float:
    """Best guess at a row's reference epoch.

    Gaia DR3 / DR2 rows reference J2016.0; SDSS / DESI / JPL rows
    don't supply one. v1.2 falls back to J2016.0 for catalog
    rows whose ``catalog_source`` looks Gaia-ish, J2000.0
    otherwise — the latter is a defensible default for static-
    looking catalogs that are not propagatable anyway.
    """
    src = (obj.catalog_source or "").lower()
    if src.startswith("gaia"):
        return J2016_JD
    return DEFAULT_REFERENCE_EPOCH_JD
