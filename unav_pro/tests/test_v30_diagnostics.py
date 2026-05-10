"""v3.0 diagnostics-helper tests.

Covers ``core/diagnostics.py``:

* Dataset memory estimate from row count vs file size.
* Visible-sector estimate solid-angle math.
* Long-operation severity classifier.
* Render helpers for cache + timing log + queue.
* Layer-counting helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pytest

from core.diagnostics import (
    APPROX_BYTES_PER_OBJECT,
    LongOperationWarning,
    build_diagnostics_report,
    classify_operation,
    count_active_overlays,
    count_active_science_layers,
    estimate_dataset_memory_bytes,
    estimate_visible_sector_objects,
    render_cache_usage,
    render_query_timing_history,
    render_task_queue_line,
)
from core.task_queue import TaskQueue
from db.spatial_query import QueryTimingLog
from db.streaming import ChunkReuseCache, make_cache_key


# ---------------------------------------------------------------------------
# estimate_dataset_memory_bytes
# ---------------------------------------------------------------------------


def test_estimate_uses_object_count_when_supplied():
    est = estimate_dataset_memory_bytes(object_count=1000)
    assert est.rows == 1000
    assert est.in_memory_bytes == 1000 * APPROX_BYTES_PER_OBJECT
    assert est.rows_known is True


def test_estimate_extrapolates_from_file_size():
    est = estimate_dataset_memory_bytes(file_size_bytes=300_000)
    assert est.rows > 0
    assert est.rows_known is False


def test_estimate_handles_no_inputs():
    est = estimate_dataset_memory_bytes()
    assert est.rows == 0
    assert est.rows_known is False


def test_estimate_short_summary_includes_units():
    est = estimate_dataset_memory_bytes(object_count=10_000)
    s = est.short_summary()
    assert "rows" in s
    assert "MB" in s


# ---------------------------------------------------------------------------
# estimate_visible_sector_objects
# ---------------------------------------------------------------------------


def test_visible_sector_zero_total_returns_zero():
    est = estimate_visible_sector_objects(
        total_objects=0,
        cone_half_angle_deg=30.0,
    )
    assert est.estimated_objects == 0


def test_visible_sector_full_sky_returns_total():
    est = estimate_visible_sector_objects(
        total_objects=1000,
        cone_half_angle_deg=180.0,
        far_pc=1000.0, dataset_extent_pc=1000.0,
    )
    assert est.sky_fraction == 1.0
    assert est.estimated_objects == 1000


def test_visible_sector_narrow_cone_yields_small_fraction():
    est = estimate_visible_sector_objects(
        total_objects=1_000_000,
        cone_half_angle_deg=10.0,
    )
    assert est.estimated_objects < 100_000


def test_visible_sector_depth_fraction_clamps():
    est = estimate_visible_sector_objects(
        total_objects=1000,
        cone_half_angle_deg=180.0,
        far_pc=500.0, dataset_extent_pc=1000.0,
    )
    assert 0.4 <= est.depth_fraction <= 0.6


def test_visible_sector_summary_string():
    est = estimate_visible_sector_objects(
        total_objects=1000, cone_half_angle_deg=30.0,
    )
    s = est.short_summary()
    assert "objects" in s
    assert "%" in s


# ---------------------------------------------------------------------------
# classify_operation
# ---------------------------------------------------------------------------


def test_classify_zero_is_ok():
    w = classify_operation(0)
    assert w.severity == "ok"


def test_classify_small_workload():
    w = classify_operation(10_000)
    assert w.severity == "ok"


def test_classify_medium_warns():
    # Above 250k → "warn" (the medium-workload tier).
    w = classify_operation(500_000)
    assert w.severity == "warn"


def test_classify_very_large_blocks():
    w = classify_operation(10_000_000)
    assert w.severity == "block"


def test_classify_returns_warning_dataclass():
    w = classify_operation(500)
    assert isinstance(w, LongOperationWarning)
    assert w.headline


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def test_render_query_timing_history_empty_log():
    log = QueryTimingLog()
    assert "no queries" in render_query_timing_history(log)


def test_render_query_timing_history_with_data():
    log = QueryTimingLog()
    log.record(candidate_rows=10, kept_rows=5,
               bbox_elapsed_ms=1.0, refine_elapsed_ms=2.0)
    text = render_query_timing_history(log)
    assert "queries recorded" in text
    assert "recent" in text


def test_render_query_timing_history_handles_none():
    assert "(no timing data)" in render_query_timing_history(None)


def test_render_cache_usage_with_data():
    cache = ChunkReuseCache()
    text = render_cache_usage(cache)
    assert "entries" in text
    assert "hits" in text


def test_render_cache_usage_handles_none():
    assert "(no cache active)" in render_cache_usage(None)


def test_render_task_queue_line_with_queue():
    q = TaskQueue()
    text = render_task_queue_line(q)
    assert "pending" in text


def test_render_task_queue_line_handles_none():
    assert "no queue" in render_task_queue_line(None)


# ---------------------------------------------------------------------------
# Layer counts
# ---------------------------------------------------------------------------


@dataclass
class FakeOverlays:
    show_grid: bool = True
    show_galactic_plane: bool = True
    show_ecliptic_plane: bool = False
    show_distance_rings: bool = False
    show_sector_cone: bool = False
    show_route_corridor: bool = False
    show_waypoint_labels: bool = False


@dataclass
class FakeScience:
    show_distance_shells: bool = True
    show_redshift_shells: bool = False
    show_magnitude_shells: bool = True
    show_motion_vectors: bool = False
    show_catalog_source_regions: bool = False
    show_solar_system_orbits: bool = False
    show_constellation_boundaries: bool = False
    show_object_density_volume: bool = False


def test_count_overlays():
    assert count_active_overlays(FakeOverlays()) == 2


def test_count_science_layers():
    assert count_active_science_layers(FakeScience()) == 2


def test_count_overlays_handles_none():
    assert count_active_overlays(None) == 0


def test_count_science_layers_handles_none():
    assert count_active_science_layers(None) == 0


# ---------------------------------------------------------------------------
# build_diagnostics_report
# ---------------------------------------------------------------------------


def test_build_diagnostics_report_minimal():
    rep = build_diagnostics_report()
    text = rep.render()
    assert "UNAV Pro Diagnostics" in text
    assert "Active overlays: 0" in text


def test_build_diagnostics_report_with_dataset_lines():
    est = estimate_dataset_memory_bytes(object_count=1000)
    rep = build_diagnostics_report(
        dataset_estimates=[("gaia_demo", est)],
    )
    text = rep.render()
    assert "gaia_demo" in text


def test_build_diagnostics_report_with_cache_and_log():
    cache = ChunkReuseCache()
    log = QueryTimingLog()
    log.record(candidate_rows=1, kept_rows=1,
               bbox_elapsed_ms=1.0, refine_elapsed_ms=1.0)
    rep = build_diagnostics_report(
        cache=cache, timing_log=log,
        overlay_settings=FakeOverlays(),
        science_settings=FakeScience(),
        task_queue=TaskQueue(),
    )
    text = rep.render()
    assert "Cone cache" in text
    assert "Query timings" in text
    assert "Active overlays: 2" in text
    assert "Active science layers: 2" in text
