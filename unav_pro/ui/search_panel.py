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
