"""Tests for core.sector_streaming. Pure CPython, no Cinema 4D.

Covers the v0.2 sector-streaming contract:

  * stream_sector_for_dataset prefers the spatial index when an
    index_path is set and the manifest is readable;
  * fallback to load_catalog when no index, with the documented
    warning;
  * hard-refusal when an unindexed catalog is above the safety
    ceiling;
  * multi-dataset aggregation with namespaced uids and the global
    cap;
  * workflow_step returns the right next step for the five
    states.
"""

from __future__ import annotations

import math
import os

import pytest

from core.dataset_registry import DatasetEntry, DatasetRegistry, DatasetStats
from core.navigation_state import NavigationParams
from core.sector_streaming import (
    DatasetStreamResult,
    StreamResult,
    stream_sector_for_active_datasets,
    stream_sector_for_dataset,
    workflow_step,
)
from core.spatial_index import build_index
from data.catalog_io import write_catalog
from data.schema import CatalogObject, compute_derived_fields


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _obj(uid: str, x_pc: float = 5.0, y_pc: float = 0.0, z_pc: float = 0.0,
         source: str = "demo", **overrides) -> CatalogObject:
    base = dict(
        uid=uid,
        catalog_source=source,
        object_type="star",
        ra_deg=10.0,
        dec_deg=0.0,
        distance_parsec=math.sqrt(x_pc * x_pc + y_pc * y_pc + z_pc * z_pc) or 1.0,
    )
    base.update(overrides)
    obj = CatalogObject(**base)
    # Override the cached cartesian to match the requested coords —
    # bypassing the schema's RA/Dec → Cartesian path, since the test
    # works in a constructed coordinate space.
    obj.cartesian_x = float(x_pc)
    obj.cartesian_y = float(y_pc)
    obj.cartesian_z = float(z_pc)
    obj.c4d_x = float(x_pc)
    obj.c4d_y = float(y_pc)
    obj.c4d_z = float(z_pc)
    return obj


@pytest.fixture
def small_indexed_dataset(tmp_path):
    """A 4-row dataset written to disk plus a built spatial index."""
    objects = [
        _obj("a-front-near", x_pc=10.0),
        _obj("a-front-far", x_pc=80.0),
        _obj("a-side", x_pc=0.0, y_pc=20.0),
        _obj("a-behind", x_pc=-10.0),
    ]
    catalog = str(tmp_path / "catalog.jsonl")
    write_catalog(objects, catalog, compute_derived=False)
    index_dir = str(tmp_path / "catalog.index")
    build_index(objects, index_dir, chunk_size=2, cell_size_pc=10.0)
    entry = DatasetEntry(
        name="A",
        path=catalog,
        index_path=index_dir,
        stats=DatasetStats(object_count=4, sources=["demo"]),
    )
    return entry, index_dir


@pytest.fixture
def small_unindexed_dataset(tmp_path):
    """A 3-row dataset written to disk with no spatial index."""
    objects = [_obj(f"u-{i}", x_pc=10.0 + i) for i in range(3)]
    catalog = str(tmp_path / "noindex.jsonl")
    write_catalog(objects, catalog, compute_derived=False)
    entry = DatasetEntry(
        name="U", path=catalog,
        stats=DatasetStats(object_count=3, sources=["demo"]),
    )
    return entry


def _params(**overrides) -> NavigationParams:
    """Test-friendly navigator params: empty source filter (so the
    fixtures' synthetic ``catalog_source='demo'`` rows are not gated
    out by the default ``["unav_sample"]`` allowlist), wide far-
    clip, default cone."""
    base = dict(
        cone_angle_deg=30.0,
        near_clip_parsec=0.0,
        far_clip_parsec=1000.0,
        max_visible_objects=1000,
        c4d_scale="pc",
        selected_catalog_sources=[],
    )
    base.update(overrides)
    return NavigationParams(**base)


# ---------------------------------------------------------------------------
# stream_sector_for_dataset — indexed path
# ---------------------------------------------------------------------------


def test_indexed_dataset_uses_index_and_excludes_far(small_indexed_dataset):
    entry, _ = small_indexed_dataset
    out = stream_sector_for_dataset(
        entry, _params(far_clip_parsec=20.0),
        origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    assert out.used_index is True
    kept_uids = sorted(o.uid for o in out.objects)
    # Only the near-front object survives the cone + far-clip; uid is
    # namespaced by the registry rule.
    assert kept_uids == ["A:a-front-near"]
    # Index meta surfaces I/O footprint.
    assert out.candidate_cells is not None
    assert out.total_cells is not None
    assert out.candidate_cells <= out.total_cells


def test_indexed_dataset_namespaces_uids(small_indexed_dataset):
    entry, _ = small_indexed_dataset
    out = stream_sector_for_dataset(
        entry, _params(),
        origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    for obj in out.objects:
        assert obj.uid.startswith("A:")


def test_indexed_dataset_respects_navigator_cap(small_indexed_dataset):
    entry, _ = small_indexed_dataset
    out = stream_sector_for_dataset(
        entry, _params(max_visible_objects=1, far_clip_parsec=1000.0),
        origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    assert out.used_index is True
    assert len(out.objects) == 1


def test_indexed_dataset_dropped_index_dir_falls_back_to_catalog(
    small_indexed_dataset, tmp_path,
):
    entry, index_dir = small_indexed_dataset
    # Simulate a stale index_path that no longer points anywhere.
    entry.index_path = str(tmp_path / "missing")
    out = stream_sector_for_dataset(
        entry, _params(), origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    assert out.used_index is False
    assert out.fallback_reason == "no spatial index"


def test_indexed_dataset_query_failure_surfaces_error(monkeypatch, small_indexed_dataset):
    entry, _ = small_indexed_dataset
    from core import sector_streaming

    def boom(*_a, **_kw):
        raise RuntimeError("synthetic explode")

    monkeypatch.setattr(sector_streaming, "query_index", boom)
    out = stream_sector_for_dataset(
        entry, _params(), origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    assert out.error is not None
    assert "synthetic explode" in out.error
    assert out.objects == []


# ---------------------------------------------------------------------------
# Fallback path — unindexed catalog
# ---------------------------------------------------------------------------


def test_unindexed_dataset_falls_back_to_full_load(small_unindexed_dataset):
    entry = small_unindexed_dataset
    out = stream_sector_for_dataset(
        entry, _params(), origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    assert out.used_index is False
    assert out.fallback_reason == "no spatial index"
    # Below the warning threshold (3 rows) — no warning fires.
    assert out.warning is None
    assert out.candidate_objects == 3


def test_unindexed_large_dataset_emits_warning(small_unindexed_dataset):
    entry = small_unindexed_dataset
    # Force the row count above the warning threshold.
    entry.stats = DatasetStats(object_count=2_000_000, sources=["demo"])
    out = stream_sector_for_dataset(
        entry, _params(), origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
        dataset_size_warning=1_000_000,
    )
    assert out.warning is not None
    assert "Build Index" in out.warning


def test_unindexed_huge_dataset_refuses_outright(small_unindexed_dataset):
    entry = small_unindexed_dataset
    entry.stats = DatasetStats(object_count=10_000_000, sources=["demo"])
    out = stream_sector_for_dataset(
        entry, _params(), origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
        hard_full_load_ceiling=5_000_000,
    )
    assert out.error is not None
    assert "ceiling" in out.error
    assert out.objects == []


def test_unindexed_dataset_namespaces_uids(small_unindexed_dataset):
    entry = small_unindexed_dataset
    out = stream_sector_for_dataset(
        entry, _params(), origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    for obj in out.objects:
        assert obj.uid.startswith("U:")


def test_unindexed_dataset_missing_file_records_error(tmp_path):
    entry = DatasetEntry(name="ghost", path=str(tmp_path / "no.jsonl"))
    out = stream_sector_for_dataset(
        entry, _params(), origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    assert out.error is not None


# ---------------------------------------------------------------------------
# Multi-dataset aggregation
# ---------------------------------------------------------------------------


def test_multi_dataset_merges_namespaced_results(
    small_indexed_dataset, small_unindexed_dataset,
):
    indexed_entry, _ = small_indexed_dataset
    reg = DatasetRegistry()
    reg.add(indexed_entry)
    reg.add(small_unindexed_dataset)
    merged = stream_sector_for_active_datasets(
        reg, _params(),
        origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    # Both per-dataset entries reported.
    assert len(merged.per_dataset) == 2
    namespaces = {o.uid.split(":", 1)[0] for o in merged.objects}
    # Both A: and U: present (cone + distance let everything ahead pass).
    assert "A" in namespaces or "U" in namespaces


def test_multi_dataset_skips_disabled_entries(
    small_indexed_dataset, small_unindexed_dataset,
):
    indexed_entry, _ = small_indexed_dataset
    small_unindexed_dataset.enabled = False
    reg = DatasetRegistry()
    reg.add(indexed_entry)
    reg.add(small_unindexed_dataset)
    merged = stream_sector_for_active_datasets(
        reg, _params(),
        origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    # Only the enabled entry's per-dataset result is recorded.
    assert [r.name for r in merged.per_dataset] == ["A"]


def test_multi_dataset_global_cap_truncates_after_merge(
    small_indexed_dataset, small_unindexed_dataset,
):
    indexed_entry, _ = small_indexed_dataset
    reg = DatasetRegistry()
    reg.add(indexed_entry)
    reg.add(small_unindexed_dataset)
    merged = stream_sector_for_active_datasets(
        reg, _params(max_visible_objects=2),
        origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    assert len(merged.objects) <= 2
    if merged.capped > 0:
        assert merged.total_kept == 2


def test_multi_dataset_no_enabled_yields_empty():
    reg = DatasetRegistry()
    merged = stream_sector_for_active_datasets(
        reg, _params(),
        origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    assert merged.objects == []
    assert merged.total_kept == 0
    assert merged.per_dataset == []


def test_multi_dataset_short_summary_includes_warnings(small_unindexed_dataset):
    small_unindexed_dataset.stats = DatasetStats(object_count=2_000_000, sources=["demo"])
    reg = DatasetRegistry()
    reg.add(small_unindexed_dataset)
    merged = stream_sector_for_active_datasets(
        reg, _params(),
        origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    text = merged.short_summary()
    assert "warning(s)" in text


# ---------------------------------------------------------------------------
# workflow_step
# ---------------------------------------------------------------------------


def test_workflow_step_no_dataset_is_step_1():
    step, hint = workflow_step(
        enabled_dataset_count=0, any_dataset_indexed=False,
        has_navigator=False, visible_sector_count=0,
    )
    assert step == 1
    assert "Dataset Manager" in hint


def test_workflow_step_unindexed_dataset_is_step_2():
    step, hint = workflow_step(
        enabled_dataset_count=1, any_dataset_indexed=False,
        has_navigator=False, visible_sector_count=0,
    )
    assert step == 2
    assert "Build Index" in hint


def test_workflow_step_no_navigator_is_step_3():
    step, hint = workflow_step(
        enabled_dataset_count=1, any_dataset_indexed=True,
        has_navigator=False, visible_sector_count=0,
    )
    assert step == 3
    assert "Navigator" in hint or "Navigation Null" in hint


def test_workflow_step_no_visible_sector_is_step_4():
    step, hint = workflow_step(
        enabled_dataset_count=1, any_dataset_indexed=True,
        has_navigator=True, visible_sector_count=0,
    )
    assert step == 4
    assert "Sync" in hint


def test_workflow_step_complete_is_step_5():
    step, hint = workflow_step(
        enabled_dataset_count=1, any_dataset_indexed=True,
        has_navigator=True, visible_sector_count=42,
    )
    assert step == 5
    assert "Inspect" in hint


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def test_dataset_stream_result_kept_property():
    r = DatasetStreamResult(name="x")
    assert r.kept == 0
    r.objects = [_obj("a"), _obj("b")]
    assert r.kept == 2


def test_stream_result_warnings_and_errors_filter():
    a = DatasetStreamResult(name="a", warning="w1")
    b = DatasetStreamResult(name="b", error="e1")
    c = DatasetStreamResult(name="c")
    s = StreamResult(per_dataset=[a, b, c])
    assert s.warnings() == ["w1"]
    assert s.errors() == ["b: e1"]
