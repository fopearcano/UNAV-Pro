"""Tests for the v1.2 ``object_states`` schema + DBManager helpers."""

from __future__ import annotations

import pytest

from core.navigation_state import NavigationParams
from core.time_model import (
    DAYS_PER_JULIAN_YEAR, J2000_JD, J2016_JD, Epoch,
)
from data.schema import CatalogObject, compute_derived_fields
from db.db_manager import (
    DBManager, ObjectState, SCHEMA_VERSION,
    STATE_TYPE_EPHEMERIS, STATE_TYPE_PROPER_MOTION, STATE_TYPE_STATIC,
)
from db.spatial_query import query_cone, query_cone_for_navigator


def _seed_objects_db(tmp_path):
    db_path = str(tmp_path / "u.db")
    db = DBManager(db_path)
    db.open()
    db.apply_schema()
    objects = []
    for i in range(5):
        o = CatalogObject(
            uid=f"gaia:{i}", catalog_source="Gaia DR3",
            object_type="star",
            ra_deg=0.0, dec_deg=0.0,
            distance_parsec=10.0 + float(i),
            proper_motion_ra=0.0, proper_motion_dec=0.0,
        )
        compute_derived_fields(o)
        objects.append(o)
    db.insert_objects(objects)
    return db_path, db, objects


# ---------------------------------------------------------------------------
# Schema bootstrap (v2)
# ---------------------------------------------------------------------------


def test_schema_version_bumped_to_two():
    assert SCHEMA_VERSION == 2


def test_apply_schema_creates_object_states_table(tmp_path):
    db_path, db, _ = _seed_objects_db(tmp_path)
    try:
        cur = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='object_states'"
        )
        assert cur.fetchone() is not None
    finally:
        db.close()


def test_v1_to_v2_migration_bumps_version(tmp_path):
    db_path = str(tmp_path / "v1.db")
    # Hand-craft a v1 layout: just objects + unav_meta=1.
    db = DBManager(db_path)
    db.open()
    db.execute(
        "CREATE TABLE unav_meta (key TEXT PRIMARY KEY, value TEXT)"
    )
    db.execute(
        "INSERT INTO unav_meta (key, value) VALUES ('schema_version', '1')"
    )
    db.execute(
        "CREATE TABLE objects (uid TEXT PRIMARY KEY, source TEXT, "
        "object_type TEXT, name TEXT, common_name TEXT, "
        "ra_deg REAL, dec_deg REAL, distance_parsec REAL, "
        "redshift REAL, apparent_magnitude REAL, color_index REAL, "
        "cartesian_x REAL, cartesian_y REAL, cartesian_z REAL)"
    )
    db.conn.commit()
    db.close()
    # Now reopen + apply schema → the migration must:
    # 1. add object_states,
    # 2. bump unav_meta.schema_version to 2.
    with DBManager(db_path) as db:
        db.apply_schema()
        cur = db.execute(
            "SELECT value FROM unav_meta WHERE key='schema_version'"
        )
        assert int(cur.fetchone()[0]) == 2
        cur = db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='object_states'"
        )
        assert cur.fetchone() is not None


# ---------------------------------------------------------------------------
# ObjectState insert / fetch
# ---------------------------------------------------------------------------


def test_object_state_rejects_unknown_type():
    with pytest.raises(ValueError):
        ObjectState(uid="x", epoch_jd=0.0, state_type="garbage")


def test_insert_states_returns_count(tmp_path):
    db_path, db, _ = _seed_objects_db(tmp_path)
    try:
        states = [
            ObjectState(
                uid="gaia:0", epoch_jd=J2016_JD,
                state_type=STATE_TYPE_PROPER_MOTION,
                pmra_masyr=15.0, pmdec_masyr=-3.0,
                reference_epoch_jd=J2016_JD,
            ),
            ObjectState(
                uid="gaia:1", epoch_jd=J2016_JD,
                state_type=STATE_TYPE_EPHEMERIS,
                x=1.0, y=0.0, z=0.0,
            ),
        ]
        n = db.insert_states(states)
        assert n == 2
        assert db.state_count() == 2
    finally:
        db.close()


def test_fetch_states_for_returns_per_uid_rows(tmp_path):
    db_path, db, _ = _seed_objects_db(tmp_path)
    try:
        db.insert_states([
            ObjectState(
                uid="gaia:0", epoch_jd=J2016_JD,
                state_type=STATE_TYPE_EPHEMERIS,
                x=1.0, y=2.0, z=3.0,
            ),
            ObjectState(
                uid="gaia:0", epoch_jd=J2016_JD + 30.0,
                state_type=STATE_TYPE_EPHEMERIS,
                x=4.0, y=5.0, z=6.0,
            ),
            ObjectState(
                uid="gaia:1", epoch_jd=J2016_JD,
                state_type=STATE_TYPE_PROPER_MOTION,
                pmra_masyr=10.0, pmdec_masyr=-2.0,
            ),
        ])
        gaia0 = db.fetch_states_for("gaia:0")
        assert len(gaia0) == 2
        assert gaia0[0].epoch_jd < gaia0[1].epoch_jd  # sorted
    finally:
        db.close()


def test_fetch_states_at_epoch_uses_tolerance(tmp_path):
    db_path, db, _ = _seed_objects_db(tmp_path)
    try:
        db.insert_states([
            ObjectState(
                uid="gaia:0", epoch_jd=J2016_JD,
                state_type=STATE_TYPE_EPHEMERIS,
                x=0.0, y=0.0, z=0.0,
            ),
        ])
        in_range = db.fetch_states_at_epoch(J2016_JD + 0.1, tolerance_days=1.0)
        out_of_range = db.fetch_states_at_epoch(J2016_JD + 5.0, tolerance_days=1.0)
        assert len(in_range) == 1
        assert len(out_of_range) == 0
    finally:
        db.close()


def test_delete_uid_cascades_to_states(tmp_path):
    db_path, db, _ = _seed_objects_db(tmp_path)
    try:
        db.insert_states([
            ObjectState(
                uid="gaia:0", epoch_jd=J2016_JD,
                state_type=STATE_TYPE_EPHEMERIS,
                x=0.0, y=0.0, z=0.0,
            ),
        ])
        assert db.state_count() == 1
        db.delete_uid("gaia:0")
        # FK ON DELETE CASCADE must wipe the matching state row.
        assert db.state_count() == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Epoch-aware spatial query (DB ↔ resolver integration)
# ---------------------------------------------------------------------------


def test_query_cone_with_epoch_uses_proper_motion_state(tmp_path):
    """A row whose ``object_states`` carries pmra/pmdec must be
    propagated when ``query_cone`` is called with an epoch."""
    db_path, db, _ = _seed_objects_db(tmp_path)
    try:
        # Seed a proper-motion state for one row (1 deg/yr in dec).
        db.insert_states([
            ObjectState(
                uid="gaia:0", epoch_jd=J2016_JD,
                state_type=STATE_TYPE_PROPER_MOTION,
                pmra_masyr=0.0, pmdec_masyr=3.6e6,  # 1 deg/yr
                reference_epoch_jd=J2016_JD,
            ),
        ])
        # Query 1 year in the future. The bbox is wide enough that
        # all rows pass the prefilter.
        result = query_cone(
            db,
            origin_pc=(0.0, 0.0, 0.0),
            forward=(1.0, 0.0, 0.0),
            cone_half_angle_deg=180.0,
            far_pc=100.0,
            epoch=Epoch.from_jd(J2016_JD + DAYS_PER_JULIAN_YEAR),
        )
        gaia0 = next(o for o in result.objects if o.uid == "gaia:0")
        # Dec moved by ~1 deg.
        assert gaia0.dec_deg == pytest.approx(1.0, abs=1e-3)
        # Other rows stay at dec=0.
        gaia1 = next(o for o in result.objects if o.uid == "gaia:1")
        assert gaia1.dec_deg == pytest.approx(0.0, abs=1e-9)
    finally:
        db.close()


def test_query_cone_without_epoch_keeps_static_positions(tmp_path):
    """No epoch passed in → no temporal resolution; positions
    come straight from the row."""
    db_path, db, _ = _seed_objects_db(tmp_path)
    try:
        db.insert_states([
            ObjectState(
                uid="gaia:0", epoch_jd=J2016_JD,
                state_type=STATE_TYPE_PROPER_MOTION,
                pmra_masyr=0.0, pmdec_masyr=3.6e6,
                reference_epoch_jd=J2016_JD,
            ),
        ])
        result = query_cone(
            db,
            origin_pc=(0.0, 0.0, 0.0), forward=(1.0, 0.0, 0.0),
            cone_half_angle_deg=180.0, far_pc=100.0,
        )
        # epoch=None → no propagation.
        gaia0 = next(o for o in result.objects if o.uid == "gaia:0")
        assert gaia0.dec_deg == pytest.approx(0.0)
    finally:
        db.close()


def test_query_cone_for_navigator_threads_epoch(tmp_path):
    db_path, db, _ = _seed_objects_db(tmp_path)
    try:
        db.insert_states([
            ObjectState(
                uid="gaia:0", epoch_jd=J2016_JD,
                state_type=STATE_TYPE_PROPER_MOTION,
                pmra_masyr=0.0, pmdec_masyr=3.6e6,
                reference_epoch_jd=J2016_JD,
            ),
        ])
        params = NavigationParams(
            far_clip_parsec=100.0,
            cone_angle_deg=180.0,
            selected_catalog_sources=[],
        )
        result = query_cone_for_navigator(
            db, params,
            origin_pc=(0.0, 0.0, 0.0), forward=(1.0, 0.0, 0.0),
            epoch=Epoch.from_jd(J2016_JD + DAYS_PER_JULIAN_YEAR),
        )
        gaia0 = next(o for o in result.objects if o.uid == "gaia:0")
        assert gaia0.dec_deg == pytest.approx(1.0, abs=1e-3)
    finally:
        db.close()
