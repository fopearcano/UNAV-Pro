"""Tests for core.spatial_index. Runs without Cinema 4D."""

from __future__ import annotations

import json
import os

import pytest

from core import spatial_index as si
from core.spatial_index import (
    DEFAULT_CHUNK_SIZE,
    INDEX_FILENAME,
    INDEX_SCHEMA_VERSION,
    SpatialIndex,
    aabb_intersects_cone,
    build_index,
    cell_bbox,
    cell_index_for,
    query_cells_intersecting_cone,
    query_index,
)
from data.schema import CatalogObject


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _obj_at(x, y, z, **overrides):
    base = dict(
        uid=f"o-{x:.3f}-{y:.3f}-{z:.3f}",
        catalog_source="unav_sample",
        object_type="star",
        ra_deg=0.0,
        dec_deg=0.0,
    )
    base.update(overrides)
    obj = CatalogObject(**base)
    obj.cartesian_x = float(x)
    obj.cartesian_y = float(y)
    obj.cartesian_z = float(z)
    return obj


def _grid_objects(extent=10.0, step=1.0):
    """Generate a regular cube of objects from -extent to +extent."""
    out = []
    n = int(round(extent / step))
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            for k in range(-n, n + 1):
                out.append(_obj_at(i * step, j * step, k * step))
    return out


# ---------------------------------------------------------------------------
# Cell math
# ---------------------------------------------------------------------------


def test_cell_index_for_picks_correct_cell():
    assert cell_index_for((0, 0, 0), (0, 0, 0), 1.0) == (0, 0, 0)
    assert cell_index_for((1.5, 2.5, -0.5), (0, 0, 0), 1.0) == (1, 2, -1)


def test_cell_index_rejects_zero_size():
    with pytest.raises(ValueError):
        cell_index_for((0, 0, 0), (0, 0, 0), 0.0)


def test_cell_bbox_round_trip():
    bmin, bmax = cell_bbox((2, 3, -1), (0.5, 0.5, 0.5), 1.0)
    assert bmin == (2.5, 3.5, -0.5)
    assert bmax == (3.5, 4.5, 0.5)


# ---------------------------------------------------------------------------
# AABB-vs-cone gate
# ---------------------------------------------------------------------------


def test_aabb_intersects_cone_inside_far_clip():
    bmin, bmax = (1.0, -1.0, -1.0), (3.0, 1.0, 1.0)
    # Origin at zero, looking +x, far clip at 100 — AABB intersects.
    assert aabb_intersects_cone(
        bmin, bmax, (0, 0, 0), (1, 0, 0), 30.0,
        near_pc=0.0, far_pc=100.0,
    )


def test_aabb_intersects_cone_rejects_too_far():
    bmin, bmax = (200.0, -1.0, -1.0), (210.0, 1.0, 1.0)
    assert not aabb_intersects_cone(
        bmin, bmax, (0, 0, 0), (1, 0, 0), 30.0, far_pc=50.0,
    )


def test_aabb_intersects_cone_rejects_too_close():
    bmin, bmax = (-0.5, -0.5, -0.5), (0.5, 0.5, 0.5)
    # AABB encloses origin: max distance < near_pc means rejection.
    assert not aabb_intersects_cone(
        bmin, bmax, (0, 0, 0), (1, 0, 0), 30.0, near_pc=10.0,
    )


def test_aabb_intersects_cone_rejects_entirely_behind():
    # AABB centered on -x; forward = +x. All corners project to <= 0.
    bmin, bmax = (-10.0, -1.0, -1.0), (-5.0, 1.0, 1.0)
    assert not aabb_intersects_cone(
        bmin, bmax, (0, 0, 0), (1, 0, 0), 30.0, far_pc=100.0,
    )


def test_aabb_intersects_cone_partially_in_front_kept():
    # AABB straddles the y-z plane.
    bmin, bmax = (-1.0, -1.0, -1.0), (5.0, 1.0, 1.0)
    assert aabb_intersects_cone(
        bmin, bmax, (0, 0, 0), (1, 0, 0), 30.0, far_pc=100.0,
    )


def test_aabb_intersects_cone_disabled_by_full_sphere():
    # half-angle >= 180 disables the cone test entirely.
    bmin, bmax = (-10.0, -1.0, -1.0), (-5.0, 1.0, 1.0)
    assert aabb_intersects_cone(
        bmin, bmax, (0, 0, 0), (1, 0, 0), 180.0, far_pc=100.0,
    )


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------


def test_build_index_creates_chunks_and_metadata(tmp_path):
    objs = _grid_objects(extent=2.0, step=1.0)  # 5*5*5 = 125 objects
    index = build_index(objs, str(tmp_path), chunk_size=20)

    # index.json exists with expected fields.
    index_path = tmp_path / INDEX_FILENAME
    assert index_path.exists()
    raw = json.loads(index_path.read_text())
    assert raw["schema_version"] == INDEX_SCHEMA_VERSION
    assert raw["chunk_size"] == 20
    assert raw["total_objects"] == len(objs)
    assert isinstance(raw["cells"], list)
    assert raw["cells"], "expected at least one non-empty cell"

    # Object accounting: every object is in exactly one cell's chunks.
    total_in_cells = sum(c["object_count"] for c in raw["cells"])
    assert total_in_cells == len(objs)

    # Every chunk path resolves to an existing JSONL file.
    for c in raw["cells"]:
        for rel in c["chunk_paths"]:
            assert (tmp_path / rel).exists(), rel


def test_build_index_respects_chunk_size(tmp_path):
    # 50 objects into a single point — they all land in one cell.
    objs = [_obj_at(0.1 * i, 0, 0) for i in range(50)]
    index = build_index(
        objs, str(tmp_path), chunk_size=10, cell_size_pc=100.0,
    )
    assert len(index.cells) == 1
    cell = index.cells[0]
    # ceil(50/10) = 5 chunk files.
    assert len(cell.chunk_paths) == 5
    assert cell.object_count == 50


def test_build_index_records_sources(tmp_path):
    objs = [
        _obj_at(0, 0, 0, catalog_source="gaia_dr3"),
        _obj_at(1, 0, 0, catalog_source="sdss_dr18"),
        _obj_at(2, 0, 0, catalog_source="gaia_dr3"),
    ]
    index = build_index(objs, str(tmp_path), chunk_size=10)
    assert sorted(index.sources) == ["gaia_dr3", "sdss_dr18"]


def test_build_index_handles_unbounded_far_corner(tmp_path):
    # Single object — bbox is degenerate (zero extent). Builder must
    # not divide by zero.
    objs = [_obj_at(5, 5, 5)]
    index = build_index(objs, str(tmp_path), chunk_size=1)
    assert index.total_objects == 1
    assert len(index.cells) == 1


def test_build_index_rejects_bad_chunk_size(tmp_path):
    with pytest.raises(ValueError):
        build_index([_obj_at(0, 0, 0)], str(tmp_path), chunk_size=0)


# ---------------------------------------------------------------------------
# SpatialIndex roundtrip
# ---------------------------------------------------------------------------


def test_spatial_index_save_load_round_trip(tmp_path):
    objs = _grid_objects(extent=2.0, step=1.0)
    built = build_index(objs, str(tmp_path), chunk_size=20)

    loaded = SpatialIndex.load(str(tmp_path))
    assert loaded.total_objects == built.total_objects
    assert loaded.chunk_size == built.chunk_size
    assert len(loaded.cells) == len(built.cells)
    # Cell metadata round-trips.
    a = built.cells[0]
    b = loaded.cells[0]
    assert a.cell == b.cell
    assert a.bbox_min_pc == b.bbox_min_pc
    assert a.object_count == b.object_count


def test_spatial_index_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        SpatialIndex.load(str(tmp_path))


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def test_query_cells_filters_by_cone(tmp_path):
    # Two clusters: one ahead at +x, one behind at -x.
    objs = []
    for i in range(20):
        objs.append(_obj_at(10 + i * 0.1, 0, 0, uid=f"front-{i}"))
        objs.append(_obj_at(-10 - i * 0.1, 0, 0, uid=f"back-{i}"))
    index = build_index(objs, str(tmp_path), chunk_size=10)

    cells = query_cells_intersecting_cone(
        index, origin_pc=(0, 0, 0), forward=(1, 0, 0),
        cone_half_angle_deg=20.0, near_pc=0.0, far_pc=1000.0,
    )
    # The back cluster's cells must be excluded.
    for cell in cells:
        # No surviving cell may have its bbox entirely behind x=0.
        assert cell.bbox_max_pc[0] > 0.0


def test_query_index_returns_filter_result(tmp_path):
    objs = []
    # 5 objects clustered straight ahead, 5 to the side.
    for i in range(5):
        objs.append(_obj_at(10 + i, 0, 0, uid=f"front-{i}"))
        objs.append(_obj_at(0, 10 + i, 0, uid=f"side-{i}"))
    build_index(objs, str(tmp_path), chunk_size=10)

    result, meta = query_index(
        str(tmp_path),
        origin_pc=(0, 0, 0),
        forward=(1, 0, 0),
        cone_half_angle_deg=15.0,
        near_pc=0.0,
        far_pc=100.0,
    )
    kept_uids = sorted(o.uid for o in result.objects)
    assert all(uid.startswith("front-") for uid in kept_uids)
    assert len(kept_uids) == 5
    # Query metadata reports the I/O footprint.
    assert meta["candidate_cells"] >= 1
    assert meta["candidate_objects"] >= len(kept_uids)


def test_query_index_respects_max_visible_cap(tmp_path):
    objs = [_obj_at(10 + i * 0.1, 0, 0) for i in range(20)]
    build_index(objs, str(tmp_path), chunk_size=5)

    result, _ = query_index(
        str(tmp_path),
        origin_pc=(0, 0, 0),
        forward=(1, 0, 0),
        cone_half_angle_deg=30.0,
        near_pc=0.0,
        far_pc=1000.0,
        max_visible_objects=3,
    )
    assert result.stats.kept == 3
    assert result.stats.rejected_over_cap == 17


def test_query_index_excludes_far_cells_from_io(tmp_path):
    # Place a small cluster at x=10 and another at x=10000. With a
    # near far-clip, only the near cluster's cells should be loaded.
    near_cluster = [_obj_at(10 + i, 0, 0, uid=f"near-{i}") for i in range(5)]
    far_cluster = [_obj_at(10_000 + i, 0, 0, uid=f"far-{i}") for i in range(5)]
    build_index(
        near_cluster + far_cluster, str(tmp_path),
        chunk_size=10, cell_size_pc=10.0,
    )

    _result, meta = query_index(
        str(tmp_path),
        origin_pc=(0, 0, 0),
        forward=(1, 0, 0),
        cone_half_angle_deg=30.0,
        near_pc=0.0,
        far_pc=100.0,
    )
    # The far-cluster cells must not contribute to the I/O.
    assert meta["candidate_objects"] == 5
    assert meta["candidate_cells"] < meta["total_cells"]
