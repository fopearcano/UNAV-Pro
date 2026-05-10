"""v3.0 query-cap + timing-log tests.

Exercises ``QueryCaps.effective_bbox_cap`` decision logic
and the bounded ``QueryTimingLog`` ring buffer.
"""

from __future__ import annotations

import pytest

from db.spatial_query import (
    DEFAULT_BBOX_CAP_MULTIPLIER,
    DEFAULT_TIMING_LOG_CAPACITY,
    GLOBAL_QUERY_TIMING_LOG,
    QueryCaps,
    QueryTimingEntry,
    QueryTimingLog,
)


# ---------------------------------------------------------------------------
# QueryCaps
# ---------------------------------------------------------------------------


def test_query_caps_default_returns_none_with_no_visible():
    caps = QueryCaps()
    assert caps.effective_bbox_cap(None) is None
    assert caps.effective_bbox_cap(0) is None


def test_query_caps_default_multiplier_applies_to_visible():
    caps = QueryCaps()
    cap = caps.effective_bbox_cap(1_000)
    assert cap == 1_000 * DEFAULT_BBOX_CAP_MULTIPLIER


def test_query_caps_explicit_bbox_max_rows_overrides_multiplier():
    caps = QueryCaps(bbox_max_rows=50_000, bbox_cap_multiplier=2)
    cap = caps.effective_bbox_cap(1_000)
    assert cap == 50_000


def test_query_caps_custom_multiplier_applies():
    caps = QueryCaps(bbox_cap_multiplier=10)
    cap = caps.effective_bbox_cap(500)
    assert cap == 5_000


def test_query_caps_default_multiplier_is_reasonable():
    """The v3.0 default multiplier was bumped from 4 (v1.7)
    to 6. Anything below 4 is too tight for anisotropic
    catalogs; anything over 16 wastes memory."""
    assert 4 <= DEFAULT_BBOX_CAP_MULTIPLIER <= 16


def test_query_caps_lazy_metadata_default_is_false():
    caps = QueryCaps()
    assert caps.lazy_metadata is False


def test_query_caps_is_frozen():
    """Caps are configuration; nothing should mutate them
    after construction."""
    caps = QueryCaps()
    with pytest.raises((TypeError, AttributeError)):
        caps.bbox_max_rows = 1234  # type: ignore[misc]


# ---------------------------------------------------------------------------
# QueryTimingLog
# ---------------------------------------------------------------------------


def test_timing_log_records_and_retrieves():
    log = QueryTimingLog(capacity=10)
    log.record(
        candidate_rows=100, kept_rows=50,
        bbox_elapsed_ms=2.0, refine_elapsed_ms=3.0,
    )
    assert len(log) == 1
    entry = log.recent(1)[0]
    assert entry.candidate_rows == 100
    assert entry.kept_rows == 50
    assert entry.total_elapsed_ms == pytest.approx(5.0)


def test_timing_log_trims_to_capacity():
    log = QueryTimingLog(capacity=3)
    for i in range(10):
        log.record(
            candidate_rows=i, kept_rows=i,
            bbox_elapsed_ms=float(i), refine_elapsed_ms=0.0,
        )
    assert len(log) == 3
    # The most-recent three should be kept.
    rows = [e.candidate_rows for e in log.recent(10)]
    assert rows == [7, 8, 9]


def test_timing_log_slowest_returns_top_n_by_total():
    log = QueryTimingLog(capacity=10)
    for ms in (1.0, 5.0, 2.0, 9.0, 4.0):
        log.record(candidate_rows=1, kept_rows=1,
                   bbox_elapsed_ms=ms, refine_elapsed_ms=0.0)
    slowest = log.slowest(3)
    assert [e.bbox_elapsed_ms for e in slowest] == [9.0, 5.0, 4.0]


def test_timing_log_average_handles_empty():
    log = QueryTimingLog()
    assert log.average_total_ms() == 0.0


def test_timing_log_average_computes_mean():
    log = QueryTimingLog()
    log.record(candidate_rows=1, kept_rows=1,
               bbox_elapsed_ms=1.0, refine_elapsed_ms=2.0)
    log.record(candidate_rows=1, kept_rows=1,
               bbox_elapsed_ms=4.0, refine_elapsed_ms=3.0)
    assert log.average_total_ms() == pytest.approx(5.0)


def test_timing_log_reset_clears_entries():
    log = QueryTimingLog()
    log.record(candidate_rows=1, kept_rows=1,
               bbox_elapsed_ms=1.0, refine_elapsed_ms=1.0)
    log.reset()
    assert len(log) == 0


def test_timing_log_recent_handles_oversized_limit():
    log = QueryTimingLog()
    log.record(candidate_rows=1, kept_rows=1,
               bbox_elapsed_ms=1.0, refine_elapsed_ms=1.0)
    out = log.recent(1000)
    assert len(out) == 1


def test_timing_log_rejects_zero_capacity():
    with pytest.raises(ValueError):
        QueryTimingLog(capacity=0)


def test_global_timing_log_exists_and_is_a_log():
    assert isinstance(GLOBAL_QUERY_TIMING_LOG, QueryTimingLog)


def test_default_timing_log_capacity_is_bounded():
    assert 32 <= DEFAULT_TIMING_LOG_CAPACITY <= 4096
