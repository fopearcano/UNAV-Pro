"""v3.0 dataset streaming tests.

Covers ``db/streaming.py``: pagination, cache reuse,
cache key construction, invalidation, and the
``cached_cone_lookup`` convenience wrapper.
"""

from __future__ import annotations

from typing import List

import pytest

from data.schema import CatalogObject
from db.spatial_query import ConeQueryResult
from db.streaming import (
    DEFAULT_CACHE_MAX_ENTRIES,
    DEFAULT_PAGE_SIZE,
    CacheEntry,
    CacheKey,
    CataloguePage,
    ChunkReuseCache,
    RepeatedQueryStats,
    cached_cone_lookup,
    iter_paged_cone,
    iter_paged_objects,
    make_cache_key,
)


def _objs(n: int) -> List[CatalogObject]:
    return [
        CatalogObject(
            uid=f"obj:{i}", catalog_source="Test",
            object_type="star", ra_deg=0.0, dec_deg=0.0,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_iter_paged_objects_yields_full_pages():
    pages = list(iter_paged_objects(_objs(12), page_size=5))
    assert [p.size for p in pages] == [5, 5, 2]
    assert pages[-1].is_last
    assert not pages[0].is_last


def test_iter_paged_objects_handles_empty_input():
    pages = list(iter_paged_objects([]))
    assert len(pages) == 1
    assert pages[0].size == 0
    assert pages[0].is_last


def test_iter_paged_objects_respects_page_size_default():
    objs = _objs(DEFAULT_PAGE_SIZE + 100)
    pages = list(iter_paged_objects(objs))
    assert pages[0].size == DEFAULT_PAGE_SIZE
    assert pages[-1].size == 100
    assert pages[-1].is_last


def test_iter_paged_objects_rejects_zero_page_size():
    with pytest.raises(ValueError):
        list(iter_paged_objects(_objs(3), page_size=0))


def test_iter_paged_objects_page_indices_are_zero_based():
    pages = list(iter_paged_objects(_objs(7), page_size=3))
    assert [p.page_index for p in pages] == [0, 1, 2]


def test_iter_paged_cone_paginates_cone_result():
    objs = _objs(11)
    result = ConeQueryResult(objects=objs, candidate_rows=11, kept_rows=11)
    pages = list(iter_paged_cone(result, page_size=4))
    assert sum(p.size for p in pages) == 11
    assert pages[-1].is_last


# ---------------------------------------------------------------------------
# Cache key construction
# ---------------------------------------------------------------------------


def test_make_cache_key_quantises_pose():
    """Sub-quantum pose jitter produces the same key."""
    k1 = make_cache_key(
        "ds", (1.0, 2.0, 3.0), (0.0, 0.0, 1.0),
        cone_half_angle_deg=30.0, near_pc=0.0, far_pc=500.0,
    )
    k2 = make_cache_key(
        "ds", (1.0 + 1e-6, 2.0 + 1e-6, 3.0 - 1e-6), (0.0, 0.0, 1.0),
        cone_half_angle_deg=30.0, near_pc=0.0, far_pc=500.0,
    )
    assert k1 == k2


def test_make_cache_key_distinguishes_distinct_poses():
    k1 = make_cache_key("ds", (0, 0, 0), (0, 0, 1),
                        cone_half_angle_deg=30, near_pc=0, far_pc=500)
    k2 = make_cache_key("ds", (10, 0, 0), (0, 0, 1),
                        cone_half_angle_deg=30, near_pc=0, far_pc=500)
    assert k1 != k2


def test_make_cache_key_distinguishes_dataset_id():
    base = dict(
        origin_pc=(0, 0, 0), forward=(0, 0, 1),
        cone_half_angle_deg=30, near_pc=0, far_pc=500,
    )
    assert make_cache_key("a", **base) != make_cache_key("b", **base)


def test_make_cache_key_normalises_source_lists():
    """Source lists are sorted before hashing so order doesn't
    affect the key."""
    base = dict(
        dataset_id="ds", origin_pc=(0, 0, 0), forward=(0, 0, 1),
        cone_half_angle_deg=30, near_pc=0, far_pc=500,
    )
    a = make_cache_key(**base, selected_sources=["Gaia DR3", "SDSS"])
    b = make_cache_key(**base, selected_sources=["SDSS", "Gaia DR3"])
    assert a == b


def test_make_cache_key_handles_non_finite_components():
    """Non-finite values snap to 0 rather than raising."""
    k = make_cache_key(
        "ds",
        (float("inf"), 0.0, float("nan")), (0, 0, 1),
        cone_half_angle_deg=30, near_pc=0, far_pc=500,
    )
    assert isinstance(k, CacheKey)


# ---------------------------------------------------------------------------
# ChunkReuseCache: insert, hit, evict
# ---------------------------------------------------------------------------


def _entry(name: str, n: int = 5, dataset: str = "ds") -> CacheEntry:
    key = make_cache_key(
        dataset, (float(hash(name) % 1000), 0, 0), (0, 0, 1),
        cone_half_angle_deg=30, near_pc=0, far_pc=500,
    )
    return CacheEntry(key=key, objects=_objs(n), candidate_rows=n)


def test_cache_get_miss_then_hit():
    cache = ChunkReuseCache()
    e = _entry("a")
    assert cache.get(e.key) is None
    assert cache.stats.misses == 1
    cache.put(e)
    got = cache.get(e.key)
    assert got is not None
    assert cache.stats.hits == 1


def test_cache_evicts_lru_when_full():
    cache = ChunkReuseCache(max_entries=2)
    a, b, c = _entry("a"), _entry("b"), _entry("c")
    cache.put(a)
    cache.put(b)
    cache.put(c)  # evicts a
    assert cache.size == 2
    assert cache.get(a.key) is None
    assert cache.stats.evictions == 1


def test_cache_get_bumps_recency():
    cache = ChunkReuseCache(max_entries=2)
    a, b, c = _entry("a"), _entry("b"), _entry("c")
    cache.put(a)
    cache.put(b)
    cache.get(a.key)  # bump a
    cache.put(c)  # should evict b, not a
    assert cache.get(a.key) is not None
    assert cache.get(b.key) is None


def test_cache_skips_too_large_entries():
    cache = ChunkReuseCache(max_rows_per_entry=10)
    big = _entry("big", n=100)
    inserted = cache.put(big)
    assert inserted is False
    assert cache.stats.skipped_too_large == 1
    assert cache.size == 0


def test_cache_size_and_row_count():
    cache = ChunkReuseCache()
    cache.put(_entry("a", n=3))
    cache.put(_entry("b", n=4))
    assert cache.size == 2
    assert cache.estimated_row_count() == 7


def test_cache_default_max_entries_is_reasonable():
    """The DEFAULT_CACHE_MAX_ENTRIES baseline must stay small
    enough to keep memory bounded but large enough to cover
    the common artist scrubbing pattern (~5–10 poses)."""
    assert 8 <= DEFAULT_CACHE_MAX_ENTRIES <= 64


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------


def test_cache_invalidate_all():
    cache = ChunkReuseCache()
    cache.put(_entry("a"))
    cache.put(_entry("b"))
    n = cache.invalidate_all()
    assert n == 2
    assert cache.size == 0


def test_cache_invalidate_for_dataset_drops_only_matching():
    cache = ChunkReuseCache()
    cache.put(_entry("a", dataset="gaia"))
    cache.put(_entry("b", dataset="gaia"))
    cache.put(_entry("c", dataset="sdss"))
    n = cache.invalidate_for_dataset("gaia")
    assert n == 2
    assert cache.size == 1


def test_cache_invalidate_for_epoch_drops_stale():
    cache = ChunkReuseCache()
    base = dict(origin_pc=(0, 0, 0), forward=(0, 0, 1),
                cone_half_angle_deg=30, near_pc=0, far_pc=500)
    e1 = CacheEntry(
        key=make_cache_key("ds", **base, epoch="2026-01-01"),
        objects=_objs(2),
    )
    e2 = CacheEntry(
        key=make_cache_key("ds", **base, epoch="2027-01-01"),
        objects=_objs(2),
    )
    cache.put(e1)
    cache.put(e2)
    n = cache.invalidate_for_epoch("2026-01-01")
    assert n == 1  # drop the non-matching one
    assert cache.size == 1


def test_cache_invalidate_predicate():
    cache = ChunkReuseCache()
    cache.put(_entry("a", dataset="gaia"))
    cache.put(_entry("b", dataset="sdss"))
    n = cache.invalidate_predicate(lambda k: k.dataset_id == "sdss")
    assert n == 1
    assert cache.size == 1


# ---------------------------------------------------------------------------
# cached_cone_lookup
# ---------------------------------------------------------------------------


def test_cached_cone_lookup_runs_fresh_on_miss():
    cache = ChunkReuseCache()
    key = make_cache_key("ds", (0, 0, 0), (0, 0, 1),
                        cone_half_angle_deg=30, near_pc=0, far_pc=500)
    calls = {"n": 0}

    def fresh():
        calls["n"] += 1
        return ConeQueryResult(
            objects=_objs(3), candidate_rows=3, kept_rows=3,
        )

    out = cached_cone_lookup(cache, key, fresh)
    assert out.hit is False
    assert calls["n"] == 1
    assert len(out.objects) == 3


def test_cached_cone_lookup_serves_from_cache_on_hit():
    cache = ChunkReuseCache()
    key = make_cache_key("ds", (0, 0, 0), (0, 0, 1),
                        cone_half_angle_deg=30, near_pc=0, far_pc=500)

    fresh_calls = {"n": 0}

    def fresh():
        fresh_calls["n"] += 1
        return ConeQueryResult(objects=_objs(3), candidate_rows=3, kept_rows=3)

    cached_cone_lookup(cache, key, fresh)  # miss
    out = cached_cone_lookup(cache, key, fresh)  # hit
    assert out.hit is True
    assert fresh_calls["n"] == 1


# ---------------------------------------------------------------------------
# RepeatedQueryStats
# ---------------------------------------------------------------------------


def test_repeated_query_stats_observes_and_tops():
    stats = RepeatedQueryStats()
    k1 = make_cache_key("ds", (0, 0, 0), (0, 0, 1),
                        cone_half_angle_deg=30, near_pc=0, far_pc=500)
    k2 = make_cache_key("ds", (1, 0, 0), (0, 0, 1),
                        cone_half_angle_deg=30, near_pc=0, far_pc=500)
    for _ in range(5):
        stats.observe(k1)
    stats.observe(k2)
    top = stats.top(2)
    assert top[0][0] == k1
    assert top[0][1] == 5


def test_repeated_query_stats_reset():
    stats = RepeatedQueryStats()
    k = make_cache_key("ds", (0, 0, 0), (0, 0, 1),
                       cone_half_angle_deg=30, near_pc=0, far_pc=500)
    stats.observe(k)
    stats.reset()
    assert stats.top(5) == []
