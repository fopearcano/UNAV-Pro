"""Tests for unav_pro.core.proper_motion (v1.2)."""

from __future__ import annotations

import pytest

from core.proper_motion import (
    MAS_PER_DEG,
    ProperMotionState,
    is_propagatable,
    propagate_object,
    propagate_position,
    reference_epoch_for,
)
from core.time_model import (
    DAYS_PER_JULIAN_YEAR, J2000_JD, J2016_JD,
)
from data.schema import CatalogObject, compute_derived_fields


def _gaia_obj(uid: str = "gaia:1", **kw) -> CatalogObject:
    base = dict(
        uid=uid,
        catalog_source="Gaia DR3",
        object_type="star",
        ra_deg=10.0,
        dec_deg=20.0,
        distance_parsec=10.0,
        proper_motion_ra=15.0,    # mas/yr (great-circle convention)
        proper_motion_dec=-3.0,
    )
    base.update(kw)
    o = CatalogObject(**base)
    compute_derived_fields(o)
    return o


# ---------------------------------------------------------------------------
# propagate_position math
# ---------------------------------------------------------------------------


def test_propagate_zero_delta_returns_input_unchanged():
    state = ProperMotionState(
        ra_deg=180.0, dec_deg=10.0,
        pmra_masyr=15.0, pmdec_masyr=5.0,
        reference_epoch_jd=J2016_JD,
    )
    out_ra, out_dec = propagate_position(state, J2016_JD)
    assert out_ra == pytest.approx(180.0)
    assert out_dec == pytest.approx(10.0)


def test_propagate_one_year_dec_change_matches_pm():
    state = ProperMotionState(
        ra_deg=10.0, dec_deg=0.0,
        pmra_masyr=0.0, pmdec_masyr=3.6e6,  # 1 deg/year
        reference_epoch_jd=J2016_JD,
    )
    out_ra, out_dec = propagate_position(
        state, J2016_JD + DAYS_PER_JULIAN_YEAR,
    )
    assert out_ra == pytest.approx(10.0)
    assert out_dec == pytest.approx(1.0, abs=1e-9)


def test_propagate_ra_corrects_for_cos_dec():
    """At dec=60° the cos(dec) factor halves the apparent RA gain."""
    state = ProperMotionState(
        ra_deg=10.0, dec_deg=60.0,
        pmra_masyr=3.6e6, pmdec_masyr=0.0,  # 1 deg/yr great-circle
        reference_epoch_jd=J2016_JD,
    )
    out_ra, out_dec = propagate_position(
        state, J2016_JD + DAYS_PER_JULIAN_YEAR,
    )
    # great-circle 1° at dec=60° ⇒ delta-ra ≈ 1°/cos(60°) = 2°.
    assert (out_ra - 10.0) % 360.0 == pytest.approx(2.0, abs=1e-6)
    assert out_dec == pytest.approx(60.0)


def test_propagate_at_pole_does_not_explode():
    """cos(90°) is 0; the propagator must clamp instead of raising."""
    state = ProperMotionState(
        ra_deg=0.0, dec_deg=90.0,
        pmra_masyr=1.0, pmdec_masyr=0.0,
        reference_epoch_jd=J2016_JD,
    )
    out_ra, out_dec = propagate_position(
        state, J2016_JD + 365 * 100.0,  # 100 yr
    )
    assert out_ra == pytest.approx(0.0)
    # Dec stays clamped to <= 90.
    assert out_dec == pytest.approx(90.0)


def test_propagate_clamps_dec_inside_180():
    state = ProperMotionState(
        ra_deg=0.0, dec_deg=89.0,
        pmra_masyr=0.0, pmdec_masyr=10 * MAS_PER_DEG,  # 10 deg/yr
        reference_epoch_jd=J2000_JD,
    )
    _, out_dec = propagate_position(
        state, J2000_JD + DAYS_PER_JULIAN_YEAR,
    )
    assert out_dec == 90.0


def test_propagate_negative_pmra_is_signed():
    state = ProperMotionState(
        ra_deg=10.0, dec_deg=0.0,
        pmra_masyr=-3.6e6, pmdec_masyr=0.0,
        reference_epoch_jd=J2016_JD,
    )
    out_ra, _ = propagate_position(
        state, J2016_JD + DAYS_PER_JULIAN_YEAR,
    )
    # 10° - 1° = 9°.
    assert out_ra == pytest.approx(9.0)


def test_propagate_ra_wraps_at_360():
    state = ProperMotionState(
        ra_deg=359.5, dec_deg=0.0,
        pmra_masyr=3.6e6, pmdec_masyr=0.0,
        reference_epoch_jd=J2016_JD,
    )
    out_ra, _ = propagate_position(
        state, J2016_JD + DAYS_PER_JULIAN_YEAR,
    )
    # 359.5 + 1.0 = 360.5 → 0.5
    assert out_ra == pytest.approx(0.5, abs=1e-6)


# ---------------------------------------------------------------------------
# propagate_object — clones + Cartesian invalidation
# ---------------------------------------------------------------------------


def test_propagate_object_clones_by_default():
    obj = _gaia_obj()
    target_jd = J2016_JD + 10 * DAYS_PER_JULIAN_YEAR
    out = propagate_object(obj, target_jd)
    # Original untouched.
    assert obj.ra_deg == pytest.approx(10.0)
    # Output moved.
    assert out.ra_deg != obj.ra_deg


def test_propagate_object_in_place_mutates():
    obj = _gaia_obj()
    target_jd = J2016_JD + 10 * DAYS_PER_JULIAN_YEAR
    out = propagate_object(obj, target_jd, in_place=True)
    assert out is obj
    assert obj.ra_deg != 10.0


def test_propagate_object_invalidates_cartesian():
    obj = _gaia_obj()
    assert obj.cartesian_x is not None
    out = propagate_object(obj, J2016_JD + DAYS_PER_JULIAN_YEAR)
    assert out.cartesian_x is None
    assert out.c4d_x is None


def test_propagate_object_no_op_when_pm_missing():
    obj = _gaia_obj(proper_motion_ra=None)
    out = propagate_object(obj, J2016_JD + DAYS_PER_JULIAN_YEAR)
    assert out.ra_deg == pytest.approx(10.0)


def test_is_propagatable_requires_both_components():
    obj = _gaia_obj()
    assert is_propagatable(obj)
    obj.proper_motion_ra = None
    assert not is_propagatable(obj)


def test_reference_epoch_picks_j2016_for_gaia():
    obj = _gaia_obj()
    assert reference_epoch_for(obj) == J2016_JD


def test_reference_epoch_falls_back_for_non_gaia():
    obj = CatalogObject(
        uid="sdss:1", catalog_source="SDSS", object_type="galaxy",
        ra_deg=0.0, dec_deg=0.0,
    )
    # SDSS rows fall to the default J2016 — there's no per-source
    # reference epoch in the schema.
    assert reference_epoch_for(obj) == J2016_JD or reference_epoch_for(obj) == J2000_JD
