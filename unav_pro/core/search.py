"""Search across loaded UNAV catalogs.

Pure CPython data layer for the v0.6 search panel. Given any sequence
of ``CatalogObject`` (typically the contents of a ``MetadataLookup``),
the search returns lightweight ``SearchResult`` rows ranked by match
quality, capped to a configurable max so the UI never balloons.

Design
------

  * **Lightweight results.** ``SearchResult`` carries only what the
    panel needs to render a one-line entry plus the uid handle for a
    later "Focus" / "Bookmark" / "Inspect" click. The full
    ``CatalogObject`` stays in the lookup; the panel pulls it on
    demand.
  * **No live HTTP.** The search is in-memory; a future tile-aware
    search can plug into the same ``Iterable[CatalogObject]`` input.
  * **Mode-agnostic match.** Callers compose a ``SearchQuery`` with
    text + optional source / type filters; the helper splits the
    text into tokens and case-insensitively matches against
    ``name``, ``common_name``, ``uid``, and ``catalog_source``.
  * **Stable scoring.** Ties break on uid for deterministic output.

No c4d dependency. Fully unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from data.schema import CatalogObject

#: Default max number of results returned. The dialog can override at
#: query time; the cap exists so a one-character query never produces
#: a 100k-row list.
DEFAULT_MAX_RESULTS = 50

#: Hard ceiling on how many results we ever return, regardless of the
#: caller's request. Above this, the user should narrow the query.
HARD_MAX_RESULTS = 500

#: Search fields, in display order. The query matches against any of
#: these; the field-of-match is recorded in the result for the panel.
SEARCH_FIELDS: Tuple[str, ...] = (
    "name",
    "common_name",
    "uid",
    "catalog_source",
    "object_type",
)


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


@dataclass
class SearchQuery:
    """Parameters for one search invocation.

    ``text`` is the raw user input. The matcher splits on whitespace
    and treats every token as a required substring (AND semantics) so
    ``"sirius gaia"`` only matches rows whose searchable fields
    contain both ``sirius`` and ``gaia``.

    ``catalog_source_filter`` and ``object_type_filter`` are optional
    exact-match filters. ``None`` (the default) means "any value".
    """

    text: str = ""
    catalog_source_filter: Optional[str] = None
    object_type_filter: Optional[str] = None
    max_results: int = DEFAULT_MAX_RESULTS

    def __post_init__(self) -> None:
        if self.max_results <= 0:
            raise ValueError("max_results must be > 0")
        if self.max_results > HARD_MAX_RESULTS:
            self.max_results = HARD_MAX_RESULTS

    @property
    def tokens(self) -> List[str]:
        """Lower-cased query tokens. Empty query → empty list."""
        return [t for t in (self.text or "").lower().split() if t]


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """One row in the search results panel.

    Lightweight on purpose — never carries the full
    ``metadata_json`` blob; the inspector pulls that via the lookup
    when the user actually clicks. Contains exactly what the panel
    needs to render a sortable, one-line entry.
    """

    uid: str
    name: Optional[str] = None
    common_name: Optional[str] = None
    catalog_source: Optional[str] = None
    object_type: Optional[str] = None
    ra_deg: Optional[float] = None
    dec_deg: Optional[float] = None
    distance_parsec: Optional[float] = None
    score: float = 0.0
    match_field: str = ""

    def display_label(self) -> str:
        """Friendliest label available for the panel row."""
        return self.common_name or self.name or self.uid

    def short_summary(self) -> str:
        """One-line summary: ``label  [source/type]  ra,dec``."""
        bits = [self.display_label()]
        tag: List[str] = []
        if self.catalog_source:
            tag.append(self.catalog_source)
        if self.object_type:
            tag.append(self.object_type)
        if tag:
            bits.append(f"[{'/'.join(tag)}]")
        if self.ra_deg is not None and self.dec_deg is not None:
            bits.append(f"({self.ra_deg:.3f}, {self.dec_deg:+.3f})")
        return "  ".join(bits)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _haystack(obj: CatalogObject) -> Dict[str, str]:
    """Build a per-field lower-case haystack for ``obj``."""
    return {
        "name": (obj.name or "").lower(),
        "common_name": (obj.common_name or "").lower(),
        "uid": (obj.uid or "").lower(),
        "catalog_source": (obj.catalog_source or "").lower(),
        "object_type": (obj.object_type or "").lower(),
    }


def _score_token_match(field: str, value: str, token: str) -> float:
    """Score a single token's match against one field's value.

    Heuristic, not magic:

      * exact-equal field → 100
      * starts-with → 50
      * contained-substring → 25

    A field-priority weight (name > common_name > uid > source > type)
    nudges name-style hits above source/type hits at the same
    substring-strength.
    """
    if not value or not token:
        return 0.0
    base = 0.0
    if value == token:
        base = 100.0
    elif value.startswith(token):
        base = 50.0
    elif token in value:
        base = 25.0
    else:
        return 0.0

    weight = {
        "name":           1.00,
        "common_name":    0.95,
        "uid":            0.85,
        "catalog_source": 0.55,
        "object_type":    0.50,
    }.get(field, 0.5)
    return base * weight


def _score_object(
    obj: CatalogObject, query: SearchQuery,
) -> Tuple[float, str]:
    """Total score for ``obj`` under ``query``.

    Tokens use AND semantics: every query token must hit at least one
    field, otherwise score is 0. The returned ``match_field`` is the
    field that produced the *highest* per-field score across all
    tokens, so the panel can label "matched on uid" / "matched on
    name" intuitively.
    """
    if query.catalog_source_filter is not None:
        if obj.catalog_source != query.catalog_source_filter:
            return 0.0, ""
    if query.object_type_filter is not None:
        if obj.object_type != query.object_type_filter:
            return 0.0, ""

    tokens = query.tokens
    if not tokens:
        # Empty text + filters means "list everything that passes the
        # filters." Score is uniform so ordering falls back to uid.
        return 1.0, ""

    haystack = _haystack(obj)
    total = 0.0
    best_field_score = -1.0
    best_field = ""
    for token in tokens:
        any_hit = False
        for field, value in haystack.items():
            s = _score_token_match(field, value, token)
            if s <= 0.0:
                continue
            any_hit = True
            total += s
            if s > best_field_score:
                best_field_score = s
                best_field = field
        if not any_hit:
            return 0.0, ""

    return total, best_field


def _result_from(
    obj: CatalogObject, score: float, match_field: str,
) -> SearchResult:
    return SearchResult(
        uid=obj.uid,
        name=obj.name,
        common_name=obj.common_name,
        catalog_source=obj.catalog_source,
        object_type=obj.object_type,
        ra_deg=obj.ra_deg,
        dec_deg=obj.dec_deg,
        distance_parsec=obj.distance_parsec,
        score=score,
        match_field=match_field,
    )


# ---------------------------------------------------------------------------
# Top-level entry points
# ---------------------------------------------------------------------------


def search_objects(
    objects: Iterable[CatalogObject], query: SearchQuery,
) -> List[SearchResult]:
    """Search ``objects`` and return ranked results, capped at
    ``query.max_results``. Stable (ties break on uid)."""
    scored: List[Tuple[float, str, CatalogObject]] = []
    for obj in objects:
        score, field = _score_object(obj, query)
        if score > 0.0:
            scored.append((score, field, obj))
    scored.sort(key=lambda t: (-t[0], t[2].uid or ""))
    return [
        _result_from(obj, score, field)
        for score, field, obj in scored[: query.max_results]
    ]


def search_lookup(
    lookup, query: SearchQuery,
) -> List[SearchResult]:
    """Convenience: search a ``MetadataLookup`` directly."""
    if lookup is None:
        return []
    if hasattr(lookup, "_index"):
        objects: Iterable[CatalogObject] = lookup._index.values()
    elif hasattr(lookup, "uids"):
        objects = (lookup.lookup(u) for u in lookup.uids())
        objects = (o for o in objects if o is not None)
    else:
        objects = ()
    return search_objects(objects, query)


# ---------------------------------------------------------------------------
# Pretty rendering for the panel
# ---------------------------------------------------------------------------


def render_results(
    results: Sequence[SearchResult],
    query: Optional[SearchQuery] = None,
) -> str:
    """Multi-line text rendering for the dialog's search panel."""
    if not results:
        if query is not None and (query.text or query.catalog_source_filter
                                  or query.object_type_filter):
            return "No matches. Try a shorter or differently-spelled query."
        return "Type a name, uid, or source above and press Search."
    lines: List[str] = []
    if query is not None:
        head = f"=== {len(results)} match(es)"
        if len(results) == query.max_results:
            head += f" (capped at {query.max_results})"
        lines.append(head + " ===")
    for i, r in enumerate(results):
        line = f"  [{i}] {r.short_summary()}"
        if r.match_field:
            line += f"  · matched {r.match_field}"
        lines.append(line)
    return "\n".join(lines)
