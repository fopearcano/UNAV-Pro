"""Search panel — c4d-bound glue between the v0.6 search UI and the
``core.search`` data model.

Pure search logic and ``SearchResult`` dataclasses live in
``unav_pro/core/search.py``. This module owns the operations that
need to know about the active C4D document or the active
``MetadataLookup``: running a query against the live lookup, building
a status line for the dialog log, and turning a clicked result into a
focus / bookmark action.

Keeps the c4d guard pattern: imports ``c4d`` defensively so the
formatter helpers stay testable in plain CPython.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False

from core.logging_util import get_logger
from core.metadata_lookup import MetadataLookup, default_lookup
from core.search import (
    DEFAULT_MAX_RESULTS,
    SearchQuery,
    SearchResult,
    render_results,
    search_lookup,
)

_log = get_logger("ui.search_panel")


# ---------------------------------------------------------------------------
# Result of a panel search
# ---------------------------------------------------------------------------


@dataclass
class PanelSearchOutcome:
    """What the dialog needs to render after a Search click.

    Holds the raw results so the panel can act on a click ("focus
    result 3"), the multi-line text rendering for the panel, and a
    short status line for the dialog log.
    """

    query: SearchQuery
    results: List[SearchResult]
    panel_text: str
    status_line: str


def run_search(
    text: str,
    *,
    catalog_source_filter: Optional[str] = None,
    object_type_filter: Optional[str] = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    lookup: Optional[MetadataLookup] = None,
) -> PanelSearchOutcome:
    """Run a search against the active lookup.

    ``lookup=None`` uses the process-wide ``default_lookup()`` so
    the dialog does not have to thread the lookup explicitly.
    """
    query = SearchQuery(
        text=text,
        catalog_source_filter=catalog_source_filter,
        object_type_filter=object_type_filter,
        max_results=max_results,
    )
    table = lookup if lookup is not None else default_lookup()
    results = search_lookup(table, query) if table is not None else []
    panel = render_results(results, query)
    if not query.tokens and not (
        query.catalog_source_filter or query.object_type_filter
    ):
        status = "Search: type a query above and press Search."
    elif not results:
        status = f"Search: no matches for {text!r}."
    elif len(results) == query.max_results:
        status = (
            f"Search: showing {len(results)} (capped) match(es) for {text!r}."
        )
    else:
        status = f"Search: {len(results)} match(es) for {text!r}."
    return PanelSearchOutcome(
        query=query, results=results, panel_text=panel, status_line=status,
    )


# ---------------------------------------------------------------------------
# Per-result actions
# ---------------------------------------------------------------------------


def selected_result(
    outcome: PanelSearchOutcome, index: int,
) -> Optional[SearchResult]:
    """Bounds-checked accessor: returns the ``SearchResult`` at
    ``index`` in ``outcome``, or ``None`` if out of range."""
    if 0 <= index < len(outcome.results):
        return outcome.results[index]
    return None


def empty_panel_text() -> str:
    return (
        "Type a name, uid, or source above and press Search to find "
        "objects in the active datasets."
    )


# ---------------------------------------------------------------------------
# v1.1 — DB-backed search
# ---------------------------------------------------------------------------


def run_db_search(
    db_path: str,
    *,
    text: str = "",
    source_filter: Optional[str] = None,
    object_type_filter: Optional[str] = None,
    magnitude_min: Optional[float] = None,
    magnitude_max: Optional[float] = None,
    redshift_min: Optional[float] = None,
    redshift_max: Optional[float] = None,
    distance_min: Optional[float] = None,
    distance_max: Optional[float] = None,
    limit: int = DEFAULT_MAX_RESULTS,
    offset: int = 0,
) -> PanelSearchOutcome:
    """Run a SQL-backed search against ``db_path``. Returns the
    same ``PanelSearchOutcome`` shape ``run_search`` returns so
    the dialog renders identically — the v1.1 advanced filters
    live on this entry point only."""
    from core.search import search_db
    from db.query_builder import DBSearchQuery

    db_query = DBSearchQuery(
        text=text,
        source_filter=source_filter,
        object_type_filter=object_type_filter,
        magnitude_min=magnitude_min,
        magnitude_max=magnitude_max,
        redshift_min=redshift_min,
        redshift_max=redshift_max,
        distance_min=distance_min,
        distance_max=distance_max,
        limit=int(limit),
        offset=int(offset),
    )
    db_outcome = search_db(db_path, db_query)

    # Compose a panel rendering. Reuses the in-memory renderer for
    # a uniform look; appends the v1.1 timing line so the artist
    # can see the SQL latency.
    legacy_query = SearchQuery(
        text=text,
        catalog_source_filter=source_filter,
        object_type_filter=object_type_filter,
        max_results=limit,
    )
    panel = render_results(db_outcome.results, legacy_query)
    panel += f"\n[SQL] {db_outcome.elapsed_ms:.2f} ms"
    if db_outcome.capped:
        panel += f"  (capped at {db_query.limit})"
    if not db_outcome.results:
        status = (
            f"DB Search: no matches "
            f"({db_outcome.elapsed_ms:.1f} ms)."
        )
    else:
        status = (
            f"DB Search: {len(db_outcome.results)} match(es) "
            f"in {db_outcome.elapsed_ms:.1f} ms."
        )
    return PanelSearchOutcome(
        query=legacy_query,
        results=db_outcome.results,
        panel_text=panel,
        status_line=status,
    )


def render_db_indicator(
    *, db_backed_count: int, total_enabled: int,
) -> str:
    """Short string the dialog can show next to the dataset list:
    ``"3 of 5 datasets DB-backed"``. v1.1's hint that some
    sectors stream via SQL and others through the v0.2 chunks."""
    if total_enabled == 0:
        return "(no datasets enabled)"
    if db_backed_count == 0:
        return f"{total_enabled} JSONL dataset(s)"
    if db_backed_count == total_enabled:
        return f"{total_enabled} DB-backed dataset(s)"
    return (
        f"{db_backed_count} of {total_enabled} DB-backed; "
        f"{total_enabled - db_backed_count} JSONL"
    )
