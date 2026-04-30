"""Tests for unav_pro.core.temporal_resolver (v1.2)."""

from __future__ import annotations

import pytest

from core.temporal_resolver import (
    EphemerisStore,
    ProperMotionStore,
    ProperMotionOverride,
    ResolveStats,
    resolve_for_epoch,
    stores_from_db_states,
)
from core.time_model import (
    DAYS_PER_JULIAN_YEAR, J2000_JD, J2016_JD, Epoch,
)
from data.schema import CatalogObject, compute_derived_fields
from db.db_manager import (
    ObjectState, STATE_TYPE_EPHEMERIS, STATE_TYPE_PROPER_MOTION,
)


def _star(uid: str, *, pmra=None, pmdec=None) -> CatalogObject:
    o = CatalogObject(
        uid=uid, catalog_source="Gaia DR3", object_type="star",
        ra_deg=10.0, dec_deg=0.0, distance_parsec=10.0,
        proper_motion_ra=pmra, proper_motion_dec=pmdec,
    )
    compute_derived_fields(o)
    return o


def _planet(uid: str) -> CatalogObject:
    o = CatalogObject(
        uid=uid, catalog_source="JPL Horizons", object_type="planet",
        ra_deg=0.0, dec_deg=0.0, distance_parsec=1.0e-5,  # ~AU scale
    )
    compute_derived_fields(o)
    return o


# ---------------------------------------------------------------------------
# No-op / static path
# ---------------------------------------------------------------------------


def test_resolve_with_none_epoch_passes_through():
    objs = [_star("gaia:1"), _star("gaia:2")]
    out, stats = resolve_for_epoch(objs, None)
    assert len(out) == 2
    assert stats.static == 2
    assert stats.propagated == 0


def test_static_objects_pass_through_with_clone():
    obj = _star("gaia:1")
    out, stats = resolve_for_epoch([obj], Epoch.from_jd(J2016_JD))
    # Cloned by default; same uid.
    assert out[0].uid == "gaia:1"
    assert stats.static == 1


def test_in_place_returns_same_instance():
    obj = _star("gaia:1")
    out, _ = resolve_for_epoch(
        [obj], Epoch.from_jd(J2016_JD), in_place=True,
    )
    assert out[0] is obj


# ---------------------------------------------------------------------------
# Proper-motion path
# ---------------------------------------------------------------------------


def test_proper_motion_propagates_one_year():
    """Star with pmdec = 1 deg/yr should move 1° in 1 year."""
    obj = _star("gaia:1", pmra=0.0, pmdec=3.6e6)
    target = Epoch.from_jd(J2016_JD + DAYS_PER_JULIAN_YEAR)
    out, stats = resolve_for_epoch([obj], target)
    assert stats.propagated == 1
    assert out[0].dec_deg == pytest.approx(1.0, abs=1e-9)


def test_proper_motion_override_takes_precedence():
    """Override via ProperMotionStore must win over the row's own pm."""
    obj = _star("gaia:1", pmra=0.0, pmdec=0.0)
    pm = ProperMotionStore()
    pm.add(
        "gaia:1",
        pmra_masyr=0.0, pmdec_masyr=3.6e6,
        reference_epoch_jd=J2016_JD,
    )
    target = Epoch.from_jd(J2016_JD + DAYS_PER_JULIAN_YEAR)
    out, _ = resolve_for_epoch(
        [obj], target, proper_motions=pm,
    )
    assert out[0].dec_deg == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Ephemeris path
# ---------------------------------------------------------------------------


def _ephem_state(uid: str, jd: float, x: float, y: float, z: float):
    return ObjectState(
        uid=uid, epoch_jd=jd, state_type=STATE_TYPE_EPHEMERIS,
        x=x, y=y, z=z,
    )


def test_ephemeris_exact_match_returns_snapshot():
    obj = _planet("jpl:Mars:2026-01-01")
    eph = EphemerisStore()
    eph.add(_ephem_state(obj.uid, J2016_JD, 1.0, 2.0, 3.0))
    eph.add(_ephem_state(obj.uid, J2016_JD + 30.0, 1.5, 2.5, 3.5))
    out, stats = resolve_for_epoch(
        [obj], Epoch.from_jd(J2016_JD),
        ephemeris=eph,
    )
    assert stats.ephemeris_exact == 1
    assert out[0].cartesian_x == pytest.approx(1.0)
    assert out[0].cartesian_y == pytest.approx(2.0)
    assert out[0].cartesian_z == pytest.approx(3.0)


def test_ephemeris_interpolates_between_snapshots():
    obj = _planet("jpl:Mars:2026-01-01")
    eph = EphemerisStore()
    eph.add(_ephem_state(obj.uid, J2016_JD, 0.0, 0.0, 0.0))
    eph.add(_ephem_state(obj.uid, J2016_JD + 10.0, 10.0, 0.0, 0.0))
    out, stats = resolve_for_epoch(
        [obj], Epoch.from_jd(J2016_JD + 5.0),
        ephemeris=eph, interpolate=True,
    )
    assert stats.ephemeris_interpolated == 1
    # Halfway between t=0 and t=10 → x = 5.
    assert out[0].cartesian_x == pytest.approx(5.0)


def test_ephemeris_nearest_when_interpolate_false():
    obj = _planet("jpl:Mars:2026-01-01")
    eph = EphemerisStore()
    eph.add(_ephem_state(obj.uid, J2016_JD, 0.0, 0.0, 0.0))
    eph.add(_ephem_state(obj.uid, J2016_JD + 10.0, 10.0, 0.0, 0.0))
    out, stats = resolve_for_epoch(
        [obj], Epoch.from_jd(J2016_JD + 4.0),
        ephemeris=eph, interpolate=False,
    )
    assert stats.ephemeris_nearest == 1
    # Closer to the t=0 snapshot.
    assert out[0].cartesian_x == pytest.approx(0.0)


def test_ephemeris_target_outside_range_picks_endpoint():
    obj = _planet("jpl:Mars:2026-01-01")
    eph = EphemerisStore()
    eph.add(_ephem_state(obj.uid, J2016_JD, 1.0, 0.0, 0.0))
    eph.add(_ephem_state(obj.uid, J2016_JD + 10.0, 11.0, 0.0, 0.0))
    out, _ = resolve_for_epoch(
        [obj], Epoch.from_jd(J2016_JD + 100.0),
        ephemeris=eph,
    )
    # Past the last snapshot — picks the last one.
    assert out[0].cartesian_x == pytest.approx(11.0)


def test_ephemeris_takes_priority_over_proper_motion():
    """A uid in BOTH stores resolves through the ephemeris path
    because that's the higher-fidelity model."""
    obj = _star("gaia:1", pmra=3.6e6, pmdec=0.0)
    eph = EphemerisStore()
    eph.add(_ephem_state(obj.uid, J2016_JD, 7.0, 0.0, 0.0))
    out, stats = resolve_for_epoch(
        [obj], Epoch.from_jd(J2016_JD + DAYS_PER_JULIAN_YEAR),
        ephemeris=eph,
    )
    assert stats.ephemeris_nearest + stats.ephemeris_exact == 1
    assert stats.propagated == 0


# ---------------------------------------------------------------------------
# Mixed bag
# ---------------------------------------------------------------------------


def test_mixed_dataset_classifies_each_row():
    objs = [
        _star("gaia:1", pmra=15.0, pmdec=-3.0),
        _star("gaia:2"),  # static (no pm)
        _planet("jpl:Mars:2026-01-01"),
    ]
    eph = EphemerisStore()
    eph.add(_ephem_state("jpl:Mars:2026-01-01", J2016_JD, 0.5, 0.0, 0.0))
    out, stats = resolve_for_epoch(
        objs, Epoch.from_jd(J2016_JD + DAYS_PER_JULIAN_YEAR),
        ephemeris=eph,
    )
    assert stats.propagated == 1
    assert stats.static == 1
    assert stats.ephemeris_exact + stats.ephemeris_nearest >= 1
    assert len(out) == 3


# ---------------------------------------------------------------------------
# stores_from_db_states
# ---------------------------------------------------------------------------


def test_stores_from_db_states_splits_by_type():
    states = [
        ObjectState(
            uid="gaia:1", epoch_jd=J2016_JD,
            state_type=STATE_TYPE_PROPER_MOTION,
            pmra_masyr=10.0, pmdec_masyr=-5.0,
            reference_epoch_jd=J2016_JD,
        ),
        ObjectState(
            uid="jpl:Mars", epoch_jd=J2016_JD,
            state_type=STATE_TYPE_EPHEMERIS,
            x=1.0, y=2.0, z=3.0,
        ),
    ]
    eph, pm = stores_from_db_states(states)
    assert "gaia:1" in pm.overrides
    assert "jpl:Mars" in eph.by_uid


def test_stores_from_db_states_skips_proper_motion_with_missing_components():
    states = [
        ObjectState(
            uid="gaia:1", epoch_jd=J2016_JD,
            state_type=STATE_TYPE_PROPER_MOTION,
            pmra_masyr=None, pmdec_masyr=10.0,
        ),
    ]
    _, pm = stores_from_db_states(states)
    assert "gaia:1" not in pm.overrides
