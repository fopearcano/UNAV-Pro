"""Tests for unav_pro.db.spatial_query (v1.1)."""

from __future__ import annotations

import pytest

from data.schema import CatalogObject, compute_derived_fields
from db.db_manager import DBManager
from db.spatial_query import (
    cone_aabb,
    query_bbox,
    query_cone,
    query_cone_for_navigator,
)


def _seed_db(path, *, count: int = 20) -> DBManager:
    db = DBManager(path)
    db.open()
    db.apply_schema()
    objects = []
    for i in range(count):
        # Spread along +X axis from 1 to count*1 pc.
        o = CatalogObject(
            uid=f"gaia:{i}", catalog_source="Gaia DR3", object_type="star",
            ra_deg=0.0, dec_deg=0.0,
            distance_parsec=float(i + 1),
        )
        compute_derived_fields(o)
        objects.append(o)
    db.insert_objects(objects)
    return db


# ---------------------------------------------------------------------------
# cone_aabb
# ---------------------------------------------------------------------------


def test_cone_aabb_returns_sphere_envelope():
    mn, mx = cone_aabb(
        origin_pc=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
        cone_half_angle_deg=30.0,
        far_pc=10.0,
    )
    assert mn == (-10.0, -10.0, -10.0)
    assert mx == (10.0, 10.0, 10.0)


def test_cone_aabb_pad_inflates_box():
    mn, mx = cone_aabb(
        origin_pc=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
        cone_half_angle_deg=30.0,
        far_pc=10.0, pad_pc=2.0,
    )
    assert mn == (-12.0, -12.0, -12.0)
    assert mx == (12.0, 12.0, 12.0)


def test_cone_aabb_rejects_negative_far():
    with pytest.raises(ValueError):
        cone_aabb((0, 0, 0), (1, 0, 0), 30.0, far_pc=-1.0)


# ---------------------------------------------------------------------------
# query_bbox
# ---------------------------------------------------------------------------


def test_query_bbox_returns_only_inside_points(tmp_path):
    db = _seed_db(str(tmp_path / "u.db"), count=20)
    try:
        result = query_bbox(
            db,
            bbox_min=(0.0, -1.0, -1.0),
            bbox_max=(5.5, 1.0, 1.0),
        )
        # Points at x = 1..5 inclusive (5 rows). Note point[0] is at
        # x=1 (from `i+1`), so we get uids gaia:0..gaia:4.
        assert len(result.objects) == 5
        assert result.candidate_rows == 5
        assert result.elapsed_ms >= 0.0
    finally:
        db.close()


def test_query_bbox_filters_by_source(tmp_path):
    path = str(tmp_path / "u.db")
    db = DBManager(path)
    db.open()
    db.apply_schema()
    objs = []
    for i in range(5):
        o = CatalogObject(
            uid=f"gaia:{i}", catalog_source="Gaia DR3",
            object_type="star", ra_deg=0.0, dec_deg=0.0,
            distance_parsec=10.0,
        )
        compute_derived_fields(o)
        objs.append(o)
    for i in range(5):
        o = CatalogObject(
            uid=f"sdss:{i}", catalog_source="SDSS",
            object_type="galaxy", ra_deg=0.0, dec_deg=0.0,
            distance_parsec=20.0,
        )
        compute_derived_fields(o)
        objs.append(o)
    db.insert_objects(objs)
    try:
        result = query_bbox(
            db,
            bbox_min=(-100.0, -100.0, -100.0),
            bbox_max=(100.0, 100.0, 100.0),
            selected_sources=["SDSS"],
        )
        assert {o.catalog_source for o in result.objects} == {"SDSS"}
    finally:
        db.close()


def test_query_bbox_max_rows_caps_result(tmp_path):
    db = _seed_db(str(tmp_path / "u.db"), count=10)
    try:
        result = query_bbox(
            db,
            bbox_min=(-100.0, -100.0, -100.0),
            bbox_max=(100.0, 100.0, 100.0),
            max_rows=3,
        )
        assert len(result.objects) == 3
    finally:
        db.close()


# ---------------------------------------------------------------------------
# query_cone
# ---------------------------------------------------------------------------


def test_query_cone_returns_only_inside_cone(tmp_path):
    db = _seed_db(str(tmp_path / "u.db"), count=20)
    try:
        # Wide cone facing +X — every point qualifies.
        result = query_cone(
            db,
            origin_pc=(0.0, 0.0, 0.0),
            forward=(1.0, 0.0, 0.0),
            cone_half_angle_deg=89.0,
            far_pc=100.0,
        )
        assert result.kept_rows == 20
        assert result.candidate_rows == 20
    finally:
        db.close()


def test_query_cone_far_clip_rejects_distant_points(tmp_path):
    db = _seed_db(str(tmp_path / "u.db"), count=20)
    try:
        result = query_cone(
            db,
            origin_pc=(0.0, 0.0, 0.0),
            forward=(1.0, 0.0, 0.0),
            cone_half_angle_deg=89.0,
            far_pc=5.0,
        )
        # Only points at x=1..5 survive.
        assert result.kept_rows == 5
    finally:
        db.close()


def test_query_cone_rejects_infinite_far(tmp_path):
    db = _seed_db(str(tmp_path / "u.db"), count=2)
    try:
        with pytest.raises(ValueError, match="far_pc must be finite"):
            query_cone(
                db,
                origin_pc=(0.0, 0.0, 0.0),
                forward=(1.0, 0.0, 0.0),
                far_pc=float("inf"),
            )
    finally:
        db.close()


def test_query_cone_for_navigator_pulls_params(tmp_path):
    from core.navigation_state import NavigationParams
    db = _seed_db(str(tmp_path / "u.db"), count=20)
    try:
        params = NavigationParams(
            far_clip_parsec=8.0,
            cone_angle_deg=45.0,
            selected_catalog_sources=[],  # disable source gate
        )
        result = query_cone_for_navigator(
            db, params, origin_pc=(0.0, 0.0, 0.0), forward=(1.0, 0.0, 0.0),
        )
        assert result.kept_rows == 8
    finally:
        db.close()
