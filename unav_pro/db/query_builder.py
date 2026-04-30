"""SQL query builder for the v1.1 search panel.

Produces parameterised SQL against the ``objects`` table the
``DBManager`` owns. The builder is deliberately narrow — only the
filters the UNAV search panel exposes are translatable into SQL —
so the surface stays under tight test coverage.

Design choices:

* **Parameterised everywhere.** No string concatenation of
  user-typed values into SQL. The builder always emits ``?``
  placeholders matched against a parallel ``params`` tuple.
* **Lightweight ``QueryResult``.** SQL returns the columns the
  search panel renders; the metadata blob stays in the parallel
  ``metadata`` table and is fetched only when the artist clicks
  Inspect.
* **Stable ordering.** Results sort by ``apparent_magnitude``
  ascending (brightest first), then ``uid`` for determinism.
  Callers can override.
* **Pagination.** ``limit`` + ``offset`` honoured at the SQL
  level. The dialog tracks the current page in
  ``DBSearchQuery.offset``.

No c4d / sqlite3 imports here — the module is pure data + string
construction. The actual execution lives in
``DBManager.execute(sql, params)`` and the search wrapper in
``unav_pro/core/search.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple


#: Default page size for ``DBSearchQuery``. The hard cap mirrors
#: ``core.search.HARD_MAX_RESULTS`` so SQL paths and in-memory
#: paths obey the same UI ceiling.
DEFAULT_LIMIT: int = 50
HARD_LIMIT: int = 500

#: Stable column projection. Driving the SELECT off this list
#: means a schema add does not silently change what the panel
#: receives.
SEARCH_COLUMNS: Tuple[str, ...] = (
    "uid", "source", "object_type", "name", "common_name",
    "ra_deg", "dec_deg", "distance_parsec", "redshift",
    "apparent_magnitude",
)

#: Allowed sort columns (whitelist; anything else is rejected).
SORT_COLUMNS: Tuple[str, ...] = (
    "apparent_magnitude", "distance_parsec", "redshift",
    "ra_deg", "dec_deg", "uid", "name",
)

#: Allowed sort directions.
SORT_DIRECTIONS: Tuple[str, ...] = ("asc", "desc")


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


@dataclass
class DBSearchQuery:
    """Typed parameters for a SQL-backed search.

    Every filter is optional. ``None`` (or an empty range) means
    "no filter on that field." The ``text`` field is split on
    whitespace and matched as a case-insensitive substring against
    ``name``, ``common_name``, and ``uid`` — every token must hit
    at least one column (AND semantics matching the v0.6
    in-memory search).
    """

    text: str = ""
    source_filter: Optional[str] = None
    object_type_filter: Optional[str] = None
    magnitude_min: Optional[float] = None
    magnitude_max: Optional[float] = None
    redshift_min: Optional[float] = None
    redshift_max: Optional[float] = None
    distance_min: Optional[float] = None
    distance_max: Optional[float] = None
    limit: int = DEFAULT_LIMIT
    offset: int = 0
    sort_column: str = "apparent_magnitude"
    sort_direction: str = "asc"

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError("limit must be > 0")
        if self.limit > HARD_LIMIT:
            self.limit = HARD_LIMIT
        if self.offset < 0:
            raise ValueError("offset must be >= 0")
        if self.sort_column not in SORT_COLUMNS:
            raise ValueError(
                f"unknown sort_column '{self.sort_column}'; "
                f"valid: {SORT_COLUMNS}"
            )
        sd = (self.sort_direction or "asc").lower()
        if sd not in SORT_DIRECTIONS:
            raise ValueError(
                f"unknown sort_direction '{self.sort_direction}'"
            )
        self.sort_direction = sd
        # Range sanity. Inverted ranges fail closed — UI can detect.
        for low, high, name in (
            (self.magnitude_min, self.magnitude_max, "magnitude"),
            (self.redshift_min, self.redshift_max, "redshift"),
            (self.distance_min, self.distance_max, "distance"),
        ):
            if low is not None and high is not None and low > high:
                raise ValueError(
                    f"{name}_min ({low}) > {name}_max ({high})"
                )

    @property
    def tokens(self) -> List[str]:
        """Lower-cased, whitespace-split tokens (AND semantics)."""
        return [t for t in (self.text or "").lower().split() if t]


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class QueryResult:
    """One row in the SQL search result. Deliberately mirrors
    ``core.search.SearchResult`` so the UI panel can render either
    transparently."""

    uid: str
    source: str = ""
    object_type: str = ""
    name: Optional[str] = None
    common_name: Optional[str] = None
    ra_deg: Optional[float] = None
    dec_deg: Optional[float] = None
    distance_parsec: Optional[float] = None
    redshift: Optional[float] = None
    apparent_magnitude: Optional[float] = None

    def display_label(self) -> str:
        return self.common_name or self.name or self.uid


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class QueryBuilder:
    """Fluent-ish SQL builder for ``DBSearchQuery``. Internal use
    only; ``build_select_sql(query)`` is the public entry point.

    Implementation note: ``QueryBuilder`` is paranoid by default.
    Token-substring filters use explicit lower-cased columns
    (matching the indexes in ``schema.sql``); range filters bind
    explicit numeric parameters; sort columns / directions are
    whitelisted in the dataclass.
    """

    def __init__(self, query: DBSearchQuery) -> None:
        self.query = query
        self._where: List[str] = []
        self._params: List[Any] = []

    # ----------------------------------------------------- helpers
    def _add(self, fragment: str, *params: Any) -> None:
        self._where.append(fragment)
        self._params.extend(params)

    def _add_text_tokens(self) -> None:
        for token in self.query.tokens:
            # AND across tokens, OR across columns.
            self._where.append(
                "(LOWER(name) LIKE ? OR LOWER(common_name) LIKE ? "
                "OR LOWER(uid) LIKE ?)"
            )
            wild = f"%{token}%"
            self._params.extend((wild, wild, wild))

    def _add_categorical(self) -> None:
        if self.query.source_filter is not None:
            self._add("source = ?", self.query.source_filter)
        if self.query.object_type_filter is not None:
            self._add("object_type = ?", self.query.object_type_filter)

    def _add_range(
        self, column: str,
        low: Optional[float], high: Optional[float],
    ) -> None:
        if low is not None:
            self._add(f"{column} IS NOT NULL AND {column} >= ?", float(low))
        if high is not None:
            self._add(f"{column} IS NOT NULL AND {column} <= ?", float(high))

    # ----------------------------------------------------- assembly
    def build(self) -> Tuple[str, Tuple[Any, ...]]:
        self._add_text_tokens()
        self._add_categorical()
        self._add_range(
            "apparent_magnitude",
            self.query.magnitude_min, self.query.magnitude_max,
        )
        self._add_range(
            "redshift",
            self.query.redshift_min, self.query.redshift_max,
        )
        self._add_range(
            "distance_parsec",
            self.query.distance_min, self.query.distance_max,
        )

        cols = ", ".join(SEARCH_COLUMNS)
        sql_parts: List[str] = [
            f"SELECT {cols} FROM objects",
        ]
        if self._where:
            sql_parts.append("WHERE " + " AND ".join(self._where))
        # Stable order: primary sort (whitelisted), then uid.
        sort = self.query.sort_column
        direction = self.query.sort_direction.upper()
        sql_parts.append(
            f"ORDER BY {sort} {direction} NULLS LAST, uid ASC"
        )
        sql_parts.append("LIMIT ? OFFSET ?")
        self._params.extend((int(self.query.limit), int(self.query.offset)))
        return " ".join(sql_parts), tuple(self._params)


def build_select_sql(query: DBSearchQuery) -> Tuple[str, Tuple[Any, ...]]:
    """Public entry point: render ``query`` into ``(sql, params)``."""
    return QueryBuilder(query).build()


# ---------------------------------------------------------------------------
# Row → QueryResult adapter
# ---------------------------------------------------------------------------


def query_result_from_row(row) -> QueryResult:
    """Adapt a ``sqlite3.Row`` (or any subscriptable mapping) to
    a ``QueryResult``. Keyed by the column names ``SEARCH_COLUMNS``
    pins."""
    return QueryResult(
        uid=row["uid"],
        source=row["source"] or "",
        object_type=row["object_type"] or "",
        name=row["name"],
        common_name=row["common_name"],
        ra_deg=row["ra_deg"],
        dec_deg=row["dec_deg"],
        distance_parsec=row["distance_parsec"],
        redshift=row["redshift"],
        apparent_magnitude=row["apparent_magnitude"],
    )


def render_query_results(
    results: Sequence[QueryResult],
    *,
    capped: bool = False,
    elapsed_ms: Optional[float] = None,
) -> str:
    """Multi-line text rendering for the dialog's SQL search panel.

    Mirrors ``core.search.render_results`` so the dialog can
    swap renderers when the active dataset is DB-backed."""
    if not results:
        return "No matches. Adjust filters or widen ranges."
    lines: List[str] = []
    head = f"=== {len(results)} match(es)"
    if capped:
        head += " (capped)"
    if elapsed_ms is not None:
        head += f" — {elapsed_ms:.1f} ms"
    lines.append(head + " ===")
    for i, r in enumerate(results):
        bits: List[str] = [r.display_label()]
        tag: List[str] = []
        if r.source:
            tag.append(r.source)
        if r.object_type:
            tag.append(r.object_type)
        if tag:
            bits.append(f"[{'/'.join(tag)}]")
        if r.ra_deg is not None and r.dec_deg is not None:
            bits.append(f"({r.ra_deg:.3f}, {r.dec_deg:+.3f})")
        if r.apparent_magnitude is not None:
            bits.append(f"mag {r.apparent_magnitude:.2f}")
        lines.append(f"  [{i}] " + "  ".join(bits))
    return "\n".join(lines)
