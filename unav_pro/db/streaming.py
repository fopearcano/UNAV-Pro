"""v3.0 dataset streaming + query-result reuse.

The v1.1 ``db.spatial_query`` layer turns a navigator pose
into one ``ConeQueryResult``. For very large catalogs the
artist's workflow is a *sequence* of similar queries — they
nudge the navigator, sync, re-sync, scrub the timeline.
v3.0 adds three pieces around the existing query layer:

1. **Paged loading.** ``iter_paged_cone`` yields pages of a
   single cone query so a 250 000-row sector can stream into
   the C4D scene one page at a time without ever
   materialising the whole list. The page size is configurable
   (default 5 000, matching SQLite's default insert batch).
2. **Chunk reuse cache.** ``ChunkReuseCache`` is an LRU keyed
   by a *signature* derived from the cone parameters
   (origin / forward / cone / clips / sources / epoch). When
   the navigator returns to a recently-seen pose, the cache
   serves the previous result rather than re-running the
   bbox prefilter + cone refine.
3. **Safe invalidation.** The cache exposes
   ``invalidate_for_dataset``, ``invalidate_for_epoch``, and
   ``invalidate_all`` so the dialog can drop stale entries
   when the user adds a dataset, edits the time navigator,
   or saves a project.

No threading, no Cinema 4D, no network. Pure stdlib;
fully unit-tested.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Dict, Iterable, Iterator, List, Optional,
    Sequence, Tuple,
)

from core.logging_util import get_logger
from data.schema import CatalogObject

from .spatial_query import ConeQueryResult

_log = get_logger("db.streaming")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


#: Default rows per page when streaming a cone result. Picked
#: to match the v1.1 ``DEFAULT_INSERT_BATCH_SIZE`` so the page
#: size is "the same chunk the importer already trusts."
DEFAULT_PAGE_SIZE: int = 5_000

#: Maximum entries the chunk-reuse cache holds before evicting
#: the least-recently-used entry. Each entry is a list of
#: CatalogObject refs (the underlying objects are shared with
#: the navigator's snapshot, so the cache footprint is roughly
#: 1–2 KB per row × max-entries × max-rows-per-entry).
DEFAULT_CACHE_MAX_ENTRIES: int = 16

#: Hard cap on a single cached result. Above this many rows,
#: caching is skipped — the artist's intent is "stream this
#: huge sector once," not "remember it forever."
DEFAULT_CACHE_MAX_ROWS_PER_ENTRY: int = 250_000

#: Quantisation step for cone-pose signatures. Two queries
#: whose origin / forward components differ by less than this
#: are considered "the same pose" for cache purposes.
#: Aligned with the v1.7 navigator-debounce step so a
#: frame-to-frame timeline scrub doesn't blow up the cache.
DEFAULT_POSE_QUANTUM_PC: float = 0.001
DEFAULT_FORWARD_QUANTUM: float = 0.0001


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


@dataclass
class CataloguePage:
    """One page of a paged cone-query result.

    ``page_index`` is zero-based. ``is_last`` is True for the
    final page (so a UI progress bar can stop without peeking).
    """

    page_index: int
    objects: List[CatalogObject] = field(default_factory=list)
    is_last: bool = False

    @property
    def size(self) -> int:
        return len(self.objects)


def iter_paged_objects(
    objects: Sequence[CatalogObject],
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Iterator[CataloguePage]:
    """Yield ``CataloguePage`` instances of ``page_size`` rows
    each. Bounded-memory streaming for very large sectors;
    callers can dispatch each page to the scene builder + yield
    control to the UI between pages.
    """
    if page_size <= 0:
        raise ValueError(f"page_size must be > 0, got {page_size}")
    n = len(objects)
    if n == 0:
        yield CataloguePage(page_index=0, objects=[], is_last=True)
        return
    total_pages = (n + page_size - 1) // page_size
    for i in range(total_pages):
        start = i * page_size
        end = min(start + page_size, n)
        yield CataloguePage(
            page_index=i,
            objects=list(objects[start:end]),
            is_last=(i == total_pages - 1),
        )


def iter_paged_cone(
    result: ConeQueryResult,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Iterator[CataloguePage]:
    """Convenience wrapper that pages an existing
    ``ConeQueryResult``. The result's ``objects`` list is
    treated as authoritative (already cone-refined and
    cap-honoured)."""
    yield from iter_paged_objects(result.objects, page_size=page_size)


# ---------------------------------------------------------------------------
# Chunk-reuse cache
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CacheKey:
    """Stable signature of a cone query.

    Built from quantised pose + cone parameters + filter sets +
    epoch. Two near-identical poses produce the same key, which
    is what makes the cache useful for a scrubbing artist.
    """

    dataset_id: str
    origin_q: Tuple[int, int, int]
    forward_q: Tuple[int, int, int]
    cone_half_angle_q: int
    near_q: int
    far_q: int
    sources_key: Tuple[str, ...]
    types_key: Tuple[str, ...]
    cap_q: int
    epoch_key: str


def _quantise(value: float, step: float) -> int:
    """Round ``value`` to the nearest multiple of ``step`` and
    return the integer multiple. Tolerates non-finite values
    by snapping them to 0 — a non-finite cache key would never
    match anyway and only inflates the cache."""
    if step <= 0:
        return 0
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0
    if f != f or f in (float("inf"), float("-inf")):
        return 0
    return int(round(f / step))


def make_cache_key(
    dataset_id: str,
    origin_pc: Tuple[float, float, float],
    forward: Tuple[float, float, float],
    *,
    cone_half_angle_deg: float,
    near_pc: float,
    far_pc: float,
    selected_sources: Optional[Sequence[str]] = None,
    selected_types: Optional[Sequence[str]] = None,
    max_visible_objects: Optional[int] = None,
    epoch: Optional[Any] = None,
    pose_quantum_pc: float = DEFAULT_POSE_QUANTUM_PC,
    forward_quantum: float = DEFAULT_FORWARD_QUANTUM,
) -> CacheKey:
    """Build a stable cache key. The same arguments — modulo
    sub-quantum jitter — always produce the same key.
    """
    return CacheKey(
        dataset_id=str(dataset_id or ""),
        origin_q=(
            _quantise(origin_pc[0], pose_quantum_pc),
            _quantise(origin_pc[1], pose_quantum_pc),
            _quantise(origin_pc[2], pose_quantum_pc),
        ),
        forward_q=(
            _quantise(forward[0], forward_quantum),
            _quantise(forward[1], forward_quantum),
            _quantise(forward[2], forward_quantum),
        ),
        cone_half_angle_q=_quantise(cone_half_angle_deg, 0.01),
        near_q=_quantise(near_pc, 0.01),
        far_q=_quantise(far_pc, 0.01),
        sources_key=tuple(sorted(str(s) for s in (selected_sources or ()))),
        types_key=tuple(sorted(str(t) for t in (selected_types or ()))),
        cap_q=int(max_visible_objects or 0),
        epoch_key=("" if epoch is None else repr(epoch)),
    )


@dataclass
class CacheEntry:
    """One cached cone-query result. ``stamp`` is the wall
    clock at insertion (used for diagnostics, not eviction)."""

    key: CacheKey
    objects: List[CatalogObject] = field(default_factory=list)
    candidate_rows: int = 0
    bbox_elapsed_ms: float = 0.0
    refine_elapsed_ms: float = 0.0
    stamp: float = field(default_factory=time.monotonic)

    @property
    def kept_rows(self) -> int:
        return len(self.objects)


@dataclass
class CacheStats:
    """Aggregate cache counters surfaced in the diagnostics
    panel."""

    hits: int = 0
    misses: int = 0
    inserts: int = 0
    evictions: int = 0
    invalidations: int = 0
    skipped_too_large: int = 0

    @property
    def lookups(self) -> int:
        return self.hits + self.misses

    @property
    def hit_ratio(self) -> float:
        return self.hits / self.lookups if self.lookups else 0.0

    def short_summary(self) -> str:
        return (
            f"hits={self.hits} misses={self.misses} "
            f"inserts={self.inserts} evictions={self.evictions} "
            f"hit_ratio={self.hit_ratio:.0%}"
        )


class ChunkReuseCache:
    """LRU cache for cone-query results.

    Keyed by ``CacheKey``; values are ``CacheEntry`` snapshots.
    Inserts above ``max_rows_per_entry`` are skipped (the
    expectation is the artist asked for a one-shot huge sync;
    caching wouldn't help). Eviction is least-recently-used.
    Reads update recency.

    The cache is **process-local**, in-memory, and disposable —
    losing it costs at most one re-query, never correctness.
    """

    def __init__(
        self,
        *,
        max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        max_rows_per_entry: int = DEFAULT_CACHE_MAX_ROWS_PER_ENTRY,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be > 0")
        if max_rows_per_entry <= 0:
            raise ValueError("max_rows_per_entry must be > 0")
        self._max_entries = int(max_entries)
        self._max_rows_per_entry = int(max_rows_per_entry)
        self._entries: "OrderedDict[CacheKey, CacheEntry]" = OrderedDict()
        self.stats = CacheStats()

    # ---------------------------------------------------- diagnostics
    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def max_entries(self) -> int:
        return self._max_entries

    @property
    def max_rows_per_entry(self) -> int:
        return self._max_rows_per_entry

    def estimated_row_count(self) -> int:
        """Total rows currently cached. Useful for the
        diagnostics panel's 'cache usage' line."""
        return sum(e.kept_rows for e in self._entries.values())

    def keys(self) -> List[CacheKey]:
        """Snapshot of the current keys (oldest first). Useful
        for tests and for a future cache inspector."""
        return list(self._entries.keys())

    # ---------------------------------------------------- core API
    def get(self, key: CacheKey) -> Optional[CacheEntry]:
        """Look up ``key`` and bump its recency. Returns the
        cached entry on hit, ``None`` on miss."""
        entry = self._entries.get(key)
        if entry is None:
            self.stats.misses += 1
            return None
        # Bump recency.
        self._entries.move_to_end(key)
        self.stats.hits += 1
        return entry

    def put(self, entry: CacheEntry) -> bool:
        """Insert ``entry`` at the most-recent end. Returns
        True on insert, False when skipped (too large)."""
        if entry.kept_rows > self._max_rows_per_entry:
            self.stats.skipped_too_large += 1
            return False
        # If the key already exists, move it; otherwise insert.
        if entry.key in self._entries:
            self._entries.move_to_end(entry.key)
            self._entries[entry.key] = entry
            return True
        self._entries[entry.key] = entry
        self.stats.inserts += 1
        # Evict oldest until we're back within budget.
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
            self.stats.evictions += 1
        return True

    def put_from_cone_result(
        self,
        key: CacheKey,
        result: ConeQueryResult,
    ) -> bool:
        """Convenience: convert a ``ConeQueryResult`` into a
        ``CacheEntry`` and ``put`` it. Returns the result of
        the underlying ``put`` call."""
        return self.put(CacheEntry(
            key=key,
            objects=list(result.objects),
            candidate_rows=int(result.candidate_rows),
            bbox_elapsed_ms=float(result.bbox_elapsed_ms),
            refine_elapsed_ms=float(result.refine_elapsed_ms),
        ))

    # ---------------------------------------------------- invalidation
    def invalidate_all(self) -> int:
        """Drop everything. Returns the number of entries
        removed. Use when the user saves the project, switches
        documents, or hits "Reset Cache"."""
        n = len(self._entries)
        self._entries.clear()
        self.stats.invalidations += n
        return n

    def invalidate_for_dataset(self, dataset_id: str) -> int:
        """Drop every entry whose ``CacheKey.dataset_id``
        matches. Used when a dataset is added, removed,
        re-indexed, or has its filters changed."""
        target = str(dataset_id or "")
        victims = [k for k in self._entries.keys() if k.dataset_id == target]
        for k in victims:
            self._entries.pop(k, None)
        self.stats.invalidations += len(victims)
        return len(victims)

    def invalidate_for_epoch(self, epoch: Optional[Any]) -> int:
        """Drop every entry whose epoch signature differs from
        ``epoch``. Used when the time navigator advances.

        ``epoch`` is the same value ``make_cache_key`` receives;
        the function applies the same ``repr(...)`` transform
        so the comparison is symmetric.
        """
        target = "" if epoch is None else repr(epoch)
        victims = [
            k for k in self._entries.keys() if k.epoch_key != target
        ]
        for k in victims:
            self._entries.pop(k, None)
        self.stats.invalidations += len(victims)
        return len(victims)

    def invalidate_predicate(
        self, predicate: Callable[[CacheKey], bool],
    ) -> int:
        """General-purpose invalidation. Drops every entry the
        predicate matches. Returns the count removed."""
        victims = [k for k in self._entries.keys() if predicate(k)]
        for k in victims:
            self._entries.pop(k, None)
        self.stats.invalidations += len(victims)
        return len(victims)


# ---------------------------------------------------------------------------
# Cached cone-query convenience wrapper
# ---------------------------------------------------------------------------


@dataclass
class CachedConeResult:
    """The output of ``cached_cone_lookup``. ``hit`` is True
    when the result came from the cache; the caller can use
    that to log "served from cache" vs "computed fresh"."""

    objects: List[CatalogObject] = field(default_factory=list)
    candidate_rows: int = 0
    bbox_elapsed_ms: float = 0.0
    refine_elapsed_ms: float = 0.0
    hit: bool = False
    key: Optional[CacheKey] = None


def cached_cone_lookup(
    cache: ChunkReuseCache,
    key: CacheKey,
    fresh_query: Callable[[], ConeQueryResult],
) -> CachedConeResult:
    """Look up ``key`` in ``cache``; on miss, run
    ``fresh_query`` and insert the result.

    ``fresh_query`` is a zero-arg callable so the wrapper
    stays decoupled from the concrete query function (we don't
    want to plumb every ``query_cone`` keyword through the
    cache). The dialog typically wraps a partial:

        result = cached_cone_lookup(
            cache, key,
            lambda: query_cone_for_navigator(db, params, ...),
        )
    """
    hit = cache.get(key)
    if hit is not None:
        return CachedConeResult(
            objects=list(hit.objects),
            candidate_rows=hit.candidate_rows,
            bbox_elapsed_ms=hit.bbox_elapsed_ms,
            refine_elapsed_ms=hit.refine_elapsed_ms,
            hit=True,
            key=key,
        )
    fresh = fresh_query()
    cache.put_from_cone_result(key, fresh)
    return CachedConeResult(
        objects=list(fresh.objects),
        candidate_rows=int(fresh.candidate_rows),
        bbox_elapsed_ms=float(fresh.bbox_elapsed_ms),
        refine_elapsed_ms=float(fresh.refine_elapsed_ms),
        hit=False,
        key=key,
    )


# ---------------------------------------------------------------------------
# Repeated-query detector
# ---------------------------------------------------------------------------


@dataclass
class RepeatedQueryStats:
    """How often the same key has been looked up. Surfaced in
    diagnostics so the artist can tell when their workflow is
    re-asking for the same sector dozens of times."""

    counts: Dict[CacheKey, int] = field(default_factory=dict)

    def observe(self, key: CacheKey) -> int:
        """Record one lookup of ``key``. Returns the new
        count."""
        n = self.counts.get(key, 0) + 1
        self.counts[key] = n
        return n

    def top(self, limit: int = 5) -> List[Tuple[CacheKey, int]]:
        """Most-repeated keys, biggest first. Useful for the
        diagnostics panel."""
        items = sorted(
            self.counts.items(), key=lambda kv: kv[1], reverse=True,
        )
        return items[: max(0, int(limit))]

    def reset(self) -> None:
        self.counts.clear()
