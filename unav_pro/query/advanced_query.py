"""v3.7 advanced astronomical query engine.

Filters + ranks an iterable of ``CatalogObject``
records against structured criteria. The dialog's
*Advanced Query* panel calls this; the offline CLI
tools can reuse it directly.

Pure stdlib; no Cinema 4D imports. Determinism: same
input + same query → same ranked output, byte-for-
byte. No PRNG anywhere.

Eleven query kinds (mirrors the v3.7 spec):

* ``NEAREST`` — closest objects to a reference point.
* ``BRIGHTEST`` — smallest apparent magnitude
  (i.e. brightest).
* ``HIGHEST_REDSHIFT`` — largest redshift.
* ``DISTANCE_RANGE`` — distance ∈ [min, max].
* ``MAGNITUDE_RANGE`` — apparent magnitude ∈
  [min, max].
* ``REDSHIFT_RANGE`` — redshift ∈ [min, max].
* ``BY_SOURCE`` — match catalog source (any of N).
* ``BY_TYPE`` — match object type (any of N).
* ``WITHIN_VISIBLE_SECTOR`` — restrict to the
  visible-sector uids the navigator most recently
  materialised.
* ``NEAR_SELECTED`` — nearest neighbours of a
  selected uid.
* ``NEAR_ROUTE`` — within a corridor of a
  polyline (handled in :mod:`route_query`; the
  flag is a sentinel here).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any, Callable, Iterable, List, Optional, Sequence, Tuple,
)


# ---------------------------------------------------------------------------
# Query kinds
# ---------------------------------------------------------------------------


class QueryKind(str, Enum):
    """Eleven structured query kinds."""

    NEAREST = "nearest"
    BRIGHTEST = "brightest"
    HIGHEST_REDSHIFT = "highest_redshift"
    DISTANCE_RANGE = "distance_range"
    MAGNITUDE_RANGE = "magnitude_range"
    REDSHIFT_RANGE = "redshift_range"
    BY_SOURCE = "by_source"
    BY_TYPE = "by_type"
    WITHIN_VISIBLE_SECTOR = "within_visible_sector"
    NEAR_SELECTED = "near_selected"
    NEAR_ROUTE = "near_route"


QUERY_KINDS = tuple(QueryKind)


# ---------------------------------------------------------------------------
# Sort orders
# ---------------------------------------------------------------------------


class SortOrder(str, Enum):
    """How the engine ranks survivors."""

    NONE = "none"
    DISTANCE_ASC = "distance_asc"
    MAGNITUDE_ASC = "magnitude_asc"     # brightest first
    REDSHIFT_DESC = "redshift_desc"     # high-z first
    UID_ASC = "uid_asc"                 # deterministic tiebreaker


SORT_ORDERS = tuple(SortOrder)


# ---------------------------------------------------------------------------
# Default sort by query kind
# ---------------------------------------------------------------------------


_DEFAULT_SORT_BY_KIND = {
    QueryKind.NEAREST: SortOrder.DISTANCE_ASC,
    QueryKind.BRIGHTEST: SortOrder.MAGNITUDE_ASC,
    QueryKind.HIGHEST_REDSHIFT: SortOrder.REDSHIFT_DESC,
    QueryKind.DISTANCE_RANGE: SortOrder.DISTANCE_ASC,
    QueryKind.MAGNITUDE_RANGE: SortOrder.MAGNITUDE_ASC,
    QueryKind.REDSHIFT_RANGE: SortOrder.REDSHIFT_DESC,
    QueryKind.BY_SOURCE: SortOrder.UID_ASC,
    QueryKind.BY_TYPE: SortOrder.UID_ASC,
    QueryKind.WITHIN_VISIBLE_SECTOR: SortOrder.UID_ASC,
    QueryKind.NEAR_SELECTED: SortOrder.DISTANCE_ASC,
    QueryKind.NEAR_ROUTE: SortOrder.DISTANCE_ASC,
}


# ---------------------------------------------------------------------------
# Query specification
# ---------------------------------------------------------------------------


Vec3 = Tuple[float, float, float]


#: Sentinel value used by tests + the dialog when the
#: query has no max — use a clearly oversized integer
#: so a user-supplied 0 doesn't accidentally reach it.
DEFAULT_MAX_RESULTS: int = 200


@dataclass
class AdvancedQuery:
    """Declarative query specification.

    Every field is optional except ``kind``. The
    engine applies each populated field as a filter +
    ranks survivors by ``sort_order`` (or the kind's
    default).
    """

    kind: QueryKind
    max_results: int = DEFAULT_MAX_RESULTS

    # Numeric ranges. ``None`` means "no bound on this end."
    distance_min_pc: Optional[float] = None
    distance_max_pc: Optional[float] = None
    magnitude_min: Optional[float] = None
    magnitude_max: Optional[float] = None
    redshift_min: Optional[float] = None
    redshift_max: Optional[float] = None

    # Allow-list filters.
    sources: Tuple[str, ...] = ()
    object_types: Tuple[str, ...] = ()
    visible_sector_uids: Tuple[str, ...] = ()

    # Spatial reference points.
    reference_point_pc: Optional[Vec3] = None
    selected_uid: Optional[str] = None

    # Optional sort override.
    sort_order: SortOrder = SortOrder.NONE

    # v3.7 epoch-awareness placeholder. Engines that
    # honor it advance ephemeris rows; the v3.7
    # baseline is *static-only* (warns when set).
    epoch_jd: Optional[float] = None
    interpolate_ephemeris: bool = False

    def effective_sort_order(self) -> SortOrder:
        if self.sort_order is SortOrder.NONE:
            return _DEFAULT_SORT_BY_KIND.get(self.kind, SortOrder.UID_ASC)
        return self.sort_order

    def short_summary(self) -> str:
        bits = [f"kind={self.kind.value}"]
        if self.sources:
            bits.append("sources=" + ",".join(self.sources))
        if self.object_types:
            bits.append("types=" + ",".join(self.object_types))
        if (
            self.distance_min_pc is not None
            or self.distance_max_pc is not None
        ):
            lo = "" if self.distance_min_pc is None else f"{self.distance_min_pc:g}"
            hi = "" if self.distance_max_pc is None else f"{self.distance_max_pc:g}"
            bits.append(f"d=[{lo},{hi}]")
        if (
            self.magnitude_min is not None
            or self.magnitude_max is not None
        ):
            lo = "" if self.magnitude_min is None else f"{self.magnitude_min:g}"
            hi = "" if self.magnitude_max is None else f"{self.magnitude_max:g}"
            bits.append(f"mag=[{lo},{hi}]")
        if (
            self.redshift_min is not None
            or self.redshift_max is not None
        ):
            lo = "" if self.redshift_min is None else f"{self.redshift_min:g}"
            hi = "" if self.redshift_max is None else f"{self.redshift_max:g}"
            bits.append(f"z=[{lo},{hi}]")
        bits.append(f"max={self.max_results}")
        return " ".join(bits)


# ---------------------------------------------------------------------------
# Query result
# ---------------------------------------------------------------------------


@dataclass
class QueryResult:
    """One ranked match. ``score`` is the rank-driving
    number (smaller = better for ascending orders;
    larger = better for descending). ``distance_pc`` is
    populated when the engine has a reference point;
    otherwise ``None``."""

    uid: str
    catalog_source: str = ""
    object_type: str = ""
    common_name: str = ""
    score: float = 0.0
    distance_pc: Optional[float] = None
    apparent_magnitude: Optional[float] = None
    redshift: Optional[float] = None
    snapshot: Optional[Any] = None  # keep the CatalogObject reference

    def short_summary(self) -> str:
        bits = [f"{self.uid}"]
        if self.common_name:
            bits.append(f"'{self.common_name}'")
        if self.distance_pc is not None:
            bits.append(f"d={self.distance_pc:.2f}pc")
        if self.apparent_magnitude is not None:
            bits.append(f"mag={self.apparent_magnitude:.2f}")
        if self.redshift is not None:
            bits.append(f"z={self.redshift:.4f}")
        return " · ".join(bits)


@dataclass
class QueryReport:
    """Aggregate outcome the dialog renders."""

    query: AdvancedQuery
    results: List[QueryResult] = field(default_factory=list)
    candidates_scanned: int = 0
    matched_before_cap: int = 0
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def returned(self) -> int:
        return len(self.results)

    def short_summary(self) -> str:
        parts = [
            f"{self.returned} result(s) "
            f"of {self.matched_before_cap} match(es)"
            f" in {self.candidates_scanned} scanned"
        ]
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        return "; ".join(parts)


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------


def _is_finite(v: Any) -> bool:
    if v is None:
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return f == f and f not in (float("inf"), float("-inf"))


def _passes_distance_range(
    obj: Any, lo: Optional[float], hi: Optional[float],
) -> bool:
    d = getattr(obj, "distance_parsec", None)
    if not _is_finite(d):
        return lo is None and hi is None
    df = float(d)
    if lo is not None and df < lo:
        return False
    if hi is not None and df > hi:
        return False
    return True


def _passes_magnitude_range(
    obj: Any, lo: Optional[float], hi: Optional[float],
) -> bool:
    m = getattr(obj, "apparent_magnitude", None)
    if not _is_finite(m):
        return lo is None and hi is None
    mf = float(m)
    if lo is not None and mf < lo:
        return False
    if hi is not None and mf > hi:
        return False
    return True


def _passes_redshift_range(
    obj: Any, lo: Optional[float], hi: Optional[float],
) -> bool:
    z = getattr(obj, "redshift", None)
    if not _is_finite(z):
        return lo is None and hi is None
    zf = float(z)
    if lo is not None and zf < lo:
        return False
    if hi is not None and zf > hi:
        return False
    return True


def _passes_sources(obj: Any, sources: Sequence[str]) -> bool:
    if not sources:
        return True
    return str(getattr(obj, "catalog_source", "") or "") in sources


def _passes_types(obj: Any, types: Sequence[str]) -> bool:
    if not types:
        return True
    return str(getattr(obj, "object_type", "") or "") in types


def _passes_visible_sector(
    obj: Any, uids: Sequence[str],
) -> bool:
    if not uids:
        return True
    return str(getattr(obj, "uid", "") or "") in set(uids)


# ---------------------------------------------------------------------------
# Distance helper
# ---------------------------------------------------------------------------


def _object_position_pc(obj: Any) -> Optional[Vec3]:
    """Return the object's parsec-frame Cartesian
    position when available."""
    x = getattr(obj, "cartesian_x", None)
    y = getattr(obj, "cartesian_y", None)
    z = getattr(obj, "cartesian_z", None)
    if not (_is_finite(x) and _is_finite(y) and _is_finite(z)):
        return None
    return (float(x), float(y), float(z))


def _euclidean_distance(a: Vec3, b: Vec3) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _distance_to_reference(
    obj: Any, reference: Vec3,
) -> Optional[float]:
    pos = _object_position_pc(obj)
    if pos is None:
        return None
    return _euclidean_distance(pos, reference)


# ---------------------------------------------------------------------------
# Sort key resolver
# ---------------------------------------------------------------------------


def _sort_key(
    result: QueryResult,
    *,
    order: SortOrder,
) -> Tuple:
    """Stable sort key. Two results that tie on the
    primary key fall back to uid for determinism."""
    if order is SortOrder.DISTANCE_ASC:
        return (
            result.distance_pc if result.distance_pc is not None else float("inf"),
            result.uid,
        )
    if order is SortOrder.MAGNITUDE_ASC:
        return (
            result.apparent_magnitude
            if result.apparent_magnitude is not None
            else float("inf"),
            result.uid,
        )
    if order is SortOrder.REDSHIFT_DESC:
        return (
            -(result.redshift if result.redshift is not None else float("-inf")),
            result.uid,
        )
    return (result.uid,)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def _build_result(
    obj: Any, distance_pc: Optional[float],
) -> QueryResult:
    return QueryResult(
        uid=str(getattr(obj, "uid", "") or ""),
        catalog_source=str(getattr(obj, "catalog_source", "") or ""),
        object_type=str(getattr(obj, "object_type", "") or ""),
        common_name=str(
            getattr(obj, "common_name", None)
            or getattr(obj, "name", "")
            or ""
        ),
        distance_pc=distance_pc,
        apparent_magnitude=(
            float(getattr(obj, "apparent_magnitude", 0.0))
            if _is_finite(getattr(obj, "apparent_magnitude", None))
            else None
        ),
        redshift=(
            float(getattr(obj, "redshift", 0.0))
            if _is_finite(getattr(obj, "redshift", None))
            else None
        ),
        snapshot=obj,
    )


def _resolve_reference(
    query: AdvancedQuery, candidates: Sequence[Any],
) -> Optional[Vec3]:
    """Pick the reference point for distance ranking."""
    if query.reference_point_pc is not None:
        return tuple(float(x) for x in query.reference_point_pc)  # type: ignore[return-value]
    if query.kind is QueryKind.NEAR_SELECTED and query.selected_uid:
        for obj in candidates:
            if str(getattr(obj, "uid", "")) == query.selected_uid:
                pos = _object_position_pc(obj)
                if pos is not None:
                    return pos
    return None


def run_query(
    query: AdvancedQuery,
    candidates: Iterable[Any],
) -> QueryReport:
    """Apply the query against ``candidates`` and
    produce a ranked + capped result list.

    The function never mutates the input objects.
    """
    if query.max_results <= 0:
        raise ValueError(
            f"max_results must be > 0; got {query.max_results}"
        )
    materialised = list(candidates)
    report = QueryReport(query=query)
    report.candidates_scanned = len(materialised)
    if query.epoch_jd is not None and not query.interpolate_ephemeris:
        report.warnings.append(
            "epoch_jd set but interpolate_ephemeris=False; "
            "v3.7 query engine evaluates positions statically. "
            "Ephemeris rows will keep their stored coordinates."
        )
    if query.epoch_jd is not None and query.interpolate_ephemeris:
        report.notes.append(
            "epoch-aware evaluation requested; the v3.7 "
            "engine respects metadata_json['epoch_jd'] but "
            "does not propagate proper motion. See "
            "docs/EPOCH_AWARE_QUERY_LIMITATIONS.md."
        )
    reference = _resolve_reference(query, materialised)
    if (
        query.kind in (
            QueryKind.NEAREST, QueryKind.NEAR_SELECTED,
            QueryKind.NEAR_ROUTE,
        )
        and reference is None
        and query.kind is not QueryKind.NEAR_ROUTE
    ):
        report.warnings.append(
            f"{query.kind.value}: no reference point; "
            "results fall back to uid-sorted order."
        )

    # Filter pass.
    survivors: List[QueryResult] = []
    for obj in materialised:
        if not _passes_distance_range(
            obj, query.distance_min_pc, query.distance_max_pc,
        ):
            continue
        if not _passes_magnitude_range(
            obj, query.magnitude_min, query.magnitude_max,
        ):
            continue
        if not _passes_redshift_range(
            obj, query.redshift_min, query.redshift_max,
        ):
            continue
        if not _passes_sources(obj, query.sources):
            continue
        if not _passes_types(obj, query.object_types):
            continue
        if (
            query.kind is QueryKind.WITHIN_VISIBLE_SECTOR
            and not _passes_visible_sector(
                obj, query.visible_sector_uids,
            )
        ):
            continue
        d = (
            _distance_to_reference(obj, reference)
            if reference is not None else None
        )
        survivors.append(_build_result(obj, distance_pc=d))

    # Kind-specific tightening (the filters above are
    # the *user-supplied* criteria; some kinds carry
    # implicit additional constraints).
    survivors = _kind_specific_filter(survivors, query)

    report.matched_before_cap = len(survivors)

    # Rank.
    survivors.sort(
        key=lambda r: _sort_key(r, order=query.effective_sort_order()),
    )

    report.results = survivors[: query.max_results]
    return report


def _kind_specific_filter(
    survivors: List[QueryResult],
    query: AdvancedQuery,
) -> List[QueryResult]:
    """Per-kind narrowing on top of the user's
    filters."""
    if query.kind is QueryKind.BRIGHTEST:
        return [
            r for r in survivors if r.apparent_magnitude is not None
        ]
    if query.kind is QueryKind.HIGHEST_REDSHIFT:
        return [r for r in survivors if r.redshift is not None]
    if (
        query.kind in (QueryKind.NEAREST, QueryKind.NEAR_SELECTED)
        and query.reference_point_pc is None
        and query.selected_uid is None
    ):
        # Without a reference, the kind degrades to a
        # uid-sorted scan. Keep all survivors.
        return survivors
    if query.kind is QueryKind.NEAR_SELECTED:
        # Drop the selected object itself from its own
        # neighbours list.
        sel = str(query.selected_uid or "")
        if sel:
            return [r for r in survivors if r.uid != sel]
    return survivors
