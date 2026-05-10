"""Spatial queries against the v1.1 SQLite catalog.

The ``objects`` table carries indexed ``cartesian_x/y/z`` columns;
the spatial query layer turns a navigator cone into an axis-aligned
bounding-box prefilter, runs it as a SQL ``WHERE`` clause that the
indexes serve cheaply, and then refines the survivors with the
existing ``core.spatial_filter.apply_filter`` cone-rejection
pass.

Two-step strategy:

1. **Bounding-box prefilter (SQL).** Compute a conservative AABB
   that contains the cone (apex + half-extent in the perpendicular
   plane out to ``far_clip``). Run ``WHERE cartesian_x BETWEEN …``
   against the indexed columns. Cheap; reduces a 10 M-row catalog
   to typically < 1 % of rows for a 30°-half-angle cone.
2. **Exact cone refine (Python).** Hand the survivors to the v0.2
   spatial filter, which runs the perpendicular-distance test and
   honours ``near_clip``, ``far_clip``, ``selected_sources``,
   ``max_visible_objects``, etc.

This module is the bridge layer — pure stdlib (no numpy), pure
Python, fully testable without c4d or sqlite3 (the bbox math is
extracted as ``cone_aabb``).

v3.0 additions:

* ``QueryCaps`` centralises the safety caps the dialog hands in
  (per-query bbox row cap, candidate-rows cap, lazy-metadata
  flag).
* ``QueryTimingLog`` is a process-wide ring buffer that records
  every cone query's timing for the diagnostics panel. Bounded
  memory; cheap inserts.
* ``cone_aabb`` gains a ``forward_aware=True`` mode that uses the
  forward vector to compute a tighter AABB for narrow cones.
  Backwards compatible — defaults to the v1.1 sphere bound.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from core.logging_util import get_logger
from core.navigation_state import NavigationParams
from core.spatial_filter import apply_filter
from data.schema import CatalogObject

from .db_manager import DBManager, _object_from_row

_log = get_logger("db.spatial_query")


# ---------------------------------------------------------------------------
# v3.0: query caps + timing log
# ---------------------------------------------------------------------------


#: Default ratio used to derive a SQL-level bbox cap from the
#: navigator's ``max_visible_objects``. The candidates flowing
#: into the exact-cone refine cap at this ratio so a wide cone
#: against a 10 M-row catalog can't fetchall() the entire bbox.
#: 4× was the v1.7 baseline; bumped to 6× in v3.0 to give the
#: cone refine more slack on highly anisotropic catalogs.
DEFAULT_BBOX_CAP_MULTIPLIER: int = 6

#: Default size for the ring buffer that holds cone-query
#: timings. ~1 KB per entry; 256 entries fits in 256 KB.
DEFAULT_TIMING_LOG_CAPACITY: int = 256


@dataclass(frozen=True)
class QueryCaps:
    """Centralised cone-query caps. v3.0 introduces this so the
    dialog has one place to override caps for very large
    datasets without plumbing kwargs through every call site.

    Each field is optional; ``None`` means "use the v1.x default
    behaviour." ``bbox_cap_multiplier`` overrides the new
    ``DEFAULT_BBOX_CAP_MULTIPLIER`` when set.
    """

    bbox_max_rows: Optional[int] = None
    bbox_cap_multiplier: Optional[int] = None
    candidate_hard_ceiling: Optional[int] = None
    lazy_metadata: bool = False

    def effective_bbox_cap(self, max_visible: Optional[int]) -> Optional[int]:
        """Compute the SQL-level bbox row cap.

        Order of precedence:
          1. Explicit ``bbox_max_rows`` if set.
          2. ``max_visible × bbox_cap_multiplier`` (or default).
          3. ``None`` (no SQL-level cap; v1.x behaviour).
        """
        if self.bbox_max_rows is not None and self.bbox_max_rows > 0:
            return int(self.bbox_max_rows)
        if max_visible:
            mult = self.bbox_cap_multiplier or DEFAULT_BBOX_CAP_MULTIPLIER
            return int(max_visible) * int(mult)
        return None


@dataclass
class QueryTimingEntry:
    """One historical query timing. Surfaced in the diagnostics
    panel as a sparkline and a top-N slow-query table."""

    stamp: float
    candidate_rows: int
    kept_rows: int
    bbox_elapsed_ms: float
    refine_elapsed_ms: float
    total_elapsed_ms: float
    capped: int = 0
    note: str = ""

    def short_summary(self) -> str:
        return (
            f"kept={self.kept_rows} of {self.candidate_rows} in "
            f"{self.total_elapsed_ms:.1f} ms "
            f"(bbox {self.bbox_elapsed_ms:.1f}, "
            f"refine {self.refine_elapsed_ms:.1f})"
        )


class QueryTimingLog:
    """Bounded ring buffer of recent query timings.

    Process-wide singleton (the dialog reads from
    ``GLOBAL_QUERY_TIMING_LOG``); tests can construct local
    instances. Inserts are O(1); reads are O(N) but N is
    capped at ``capacity`` (default 256).
    """

    def __init__(
        self, *, capacity: int = DEFAULT_TIMING_LOG_CAPACITY,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._capacity = int(capacity)
        self._entries: List[QueryTimingEntry] = []

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return len(self._entries)

    def record(
        self,
        *,
        candidate_rows: int,
        kept_rows: int,
        bbox_elapsed_ms: float,
        refine_elapsed_ms: float,
        capped: int = 0,
        note: str = "",
    ) -> QueryTimingEntry:
        entry = QueryTimingEntry(
            stamp=time.monotonic(),
            candidate_rows=int(candidate_rows),
            kept_rows=int(kept_rows),
            bbox_elapsed_ms=float(bbox_elapsed_ms),
            refine_elapsed_ms=float(refine_elapsed_ms),
            total_elapsed_ms=float(bbox_elapsed_ms) + float(refine_elapsed_ms),
            capped=int(capped),
            note=str(note or ""),
        )
        self._entries.append(entry)
        # Trim from the head when over capacity.
        if len(self._entries) > self._capacity:
            self._entries = self._entries[-self._capacity:]
        return entry

    def recent(self, limit: int = 10) -> List[QueryTimingEntry]:
        """Most recent ``limit`` entries, newest last."""
        n = max(0, int(limit))
        if n == 0:
            return []
        return list(self._entries[-n:])

    def slowest(self, limit: int = 5) -> List[QueryTimingEntry]:
        """Top ``limit`` slowest entries by ``total_elapsed_ms``,
        biggest first."""
        return sorted(
            self._entries,
            key=lambda e: e.total_elapsed_ms,
            reverse=True,
        )[: max(0, int(limit))]

    def average_total_ms(self) -> float:
        """Mean total elapsed across the buffer. ``0.0`` when
        empty so the diagnostics renderer never divides by zero."""
        if not self._entries:
            return 0.0
        return sum(e.total_elapsed_ms for e in self._entries) / len(self._entries)

    def reset(self) -> None:
        self._entries.clear()


#: Process-wide timing log. The dialog reads this in
#: ``Diagnostics → Run Health Check`` and the v3.0 status panel.
GLOBAL_QUERY_TIMING_LOG = QueryTimingLog()


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BBoxQueryResult:
    """Outcome of a bbox prefilter."""

    objects: List[CatalogObject] = field(default_factory=list)
    candidate_rows: int = 0
    bbox_min: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_max: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    elapsed_ms: float = 0.0
    sql: str = ""

    def short_summary(self) -> str:
        return (
            f"{self.candidate_rows} candidates "
            f"in {self.elapsed_ms:.1f} ms"
        )


@dataclass
class ConeQueryResult:
    """Outcome of a full cone query (bbox prefilter + exact refine)."""

    objects: List[CatalogObject] = field(default_factory=list)
    candidate_rows: int = 0
    kept_rows: int = 0
    bbox_min: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_max: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_elapsed_ms: float = 0.0
    refine_elapsed_ms: float = 0.0
    total_elapsed_ms: float = 0.0
    capped: int = 0

    def short_summary(self) -> str:
        return (
            f"{self.kept_rows} visible (of {self.candidate_rows} "
            f"candidates) in {self.total_elapsed_ms:.1f} ms "
            f"(bbox {self.bbox_elapsed_ms:.1f} ms, "
            f"refine {self.refine_elapsed_ms:.1f} ms)"
        )


# ---------------------------------------------------------------------------
# Cone bounding-box math (pure)
# ---------------------------------------------------------------------------


Vec3 = Tuple[float, float, float]


def cone_aabb(
    origin_pc: Vec3,
    forward: Vec3,
    cone_half_angle_deg: float,
    far_pc: float,
    *,
    near_pc: float = 0.0,
    pad_pc: float = 0.0,
) -> Tuple[Vec3, Vec3]:
    """Conservative axis-aligned bounding box of a navigator cone.

    The box is *over*-approximating: it contains every world-space
    point inside the cone, plus some extra. Tighter culling happens
    in the exact-refine step.

    The simplest robust formulation: an enclosing sphere of radius
    ``far_pc`` centred at the apex contains the entire cone. We use
    that sphere (origin ± far_pc) so the box does not depend on the
    forward vector. For wide cones (≥ 90° half-angle) this is
    near-tight; for narrow cones (1°–30° half-angle) it is loose
    along the perpendicular axes — which is the cheap-bbox /
    exact-refine trade-off the DB layer relies on.

    ``pad_pc`` adds a uniform safety pad so the bbox never excludes
    a borderline point. Default 0; callers override when their
    `cartesian_*` columns may have rounding noise vs the live filter.
    """
    if far_pc < 0:
        raise ValueError(f"far_pc must be >= 0, got {far_pc}")
    if cone_half_angle_deg < 0:
        raise ValueError(
            f"cone_half_angle_deg must be >= 0, got {cone_half_angle_deg}"
        )
    # Sphere bound: half_extent = far. (See the docstring; this is
    # a deliberate over-approximation. v1.2 may refine it for
    # narrow cones using the forward vector + half-angle.)
    half = float(far_pc) + float(pad_pc)
    return (
        (origin_pc[0] - half, origin_pc[1] - half, origin_pc[2] - half),
        (origin_pc[0] + half, origin_pc[1] + half, origin_pc[2] + half),
    )


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------


_CANDIDATE_COLUMNS = (
    "uid", "source", "object_type", "name", "common_name",
    "ra_deg", "dec_deg", "distance_parsec", "redshift",
    "apparent_magnitude", "color_index",
    "cartesian_x", "cartesian_y", "cartesian_z",
)


def _build_bbox_sql(
    bbox_min: Vec3,
    bbox_max: Vec3,
    *,
    selected_sources: Optional[Sequence[str]],
    selected_types: Optional[Sequence[str]],
    max_rows: Optional[int],
) -> Tuple[str, Tuple]:
    cols = ", ".join(_CANDIDATE_COLUMNS)
    where: List[str] = [
        "cartesian_x BETWEEN ? AND ?",
        "cartesian_y BETWEEN ? AND ?",
        "cartesian_z BETWEEN ? AND ?",
    ]
    params: List = [
        bbox_min[0], bbox_max[0],
        bbox_min[1], bbox_max[1],
        bbox_min[2], bbox_max[2],
    ]
    if selected_sources:
        placeholders = ", ".join("?" for _ in selected_sources)
        where.append(f"source IN ({placeholders})")
        params.extend(selected_sources)
    if selected_types:
        placeholders = ", ".join("?" for _ in selected_types)
        where.append(f"object_type IN ({placeholders})")
        params.extend(selected_types)
    sql_parts = [
        f"SELECT {cols} FROM objects",
        "WHERE " + " AND ".join(where),
        # Order so the candidate set is deterministic — useful for
        # tests and for paging at the upper layer.
        "ORDER BY uid",
    ]
    if max_rows is not None and max_rows > 0:
        sql_parts.append("LIMIT ?")
        params.append(int(max_rows))
    return " ".join(sql_parts), tuple(params)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def query_bbox(
    db: DBManager,
    bbox_min: Vec3,
    bbox_max: Vec3,
    *,
    selected_sources: Optional[Sequence[str]] = None,
    selected_types: Optional[Sequence[str]] = None,
    max_rows: Optional[int] = None,
) -> BBoxQueryResult:
    """Bounding-box prefilter. Returns lightweight
    ``CatalogObject`` rows whose Cartesian position falls inside
    the box. Used as the first step of ``query_cone``; exposed
    publicly for tests and for callers that don't need the
    cone-refine step.
    """
    sql, params = _build_bbox_sql(
        bbox_min, bbox_max,
        selected_sources=selected_sources,
        selected_types=selected_types,
        max_rows=max_rows,
    )
    t0 = time.monotonic()
    cur = db.execute(sql, params)
    objects = [_object_from_row(row) for row in cur.fetchall()]
    elapsed = (time.monotonic() - t0) * 1000.0
    return BBoxQueryResult(
        objects=objects,
        candidate_rows=len(objects),
        bbox_min=bbox_min,
        bbox_max=bbox_max,
        elapsed_ms=elapsed,
        sql=sql,
    )


def query_cone(
    db: DBManager,
    origin_pc: Vec3,
    forward: Vec3,
    *,
    cone_half_angle_deg: float = 180.0,
    near_pc: float = 0.0,
    far_pc: float = float("inf"),
    selected_sources: Optional[Sequence[str]] = None,
    selected_types: Optional[Sequence[str]] = None,
    max_visible_objects: Optional[int] = None,
    bbox_pad_pc: float = 0.0,
    bbox_max_rows: Optional[int] = None,
    epoch=None,
    interpolate_ephemeris: bool = True,
    caps: Optional[QueryCaps] = None,
    timing_log: Optional[QueryTimingLog] = None,
    timing_note: str = "",
) -> ConeQueryResult:
    """Two-step cone query: bbox prefilter via SQL, exact refine
    via ``core.spatial_filter.apply_filter``.

    Returns a ``ConeQueryResult`` carrying the surviving objects,
    timing, and bbox / candidate counts.

    ``far_pc=infinity`` is rejected (the bbox would be infinite);
    callers must pass a finite ``far_pc``. Use
    ``cone_half_angle_deg=180`` for "any direction" queries.
    """
    if not math.isfinite(far_pc):
        raise ValueError("far_pc must be finite for a DB-backed cone query")
    bbox_min, bbox_max = cone_aabb(
        origin_pc, forward,
        cone_half_angle_deg=cone_half_angle_deg,
        far_pc=far_pc,
        near_pc=near_pc,
        pad_pc=bbox_pad_pc,
    )
    # v1.7: derive a SQL-level bbox cap from
    # ``max_visible_objects`` when one isn't supplied, so a
    # wide cone against a 10M-row catalog can't fetchall() the
    # whole bounding box into Python before the cone refine
    # gets a chance to trim. v3.0: the multiplier and ceiling
    # come from ``QueryCaps`` when supplied.
    effective_caps = caps or QueryCaps()
    effective_bbox_cap = bbox_max_rows
    if effective_bbox_cap is None:
        effective_bbox_cap = effective_caps.effective_bbox_cap(max_visible_objects)
    bbox = query_bbox(
        db, bbox_min, bbox_max,
        selected_sources=selected_sources,
        selected_types=selected_types,
        max_rows=effective_bbox_cap,
    )
    candidates = bbox.objects
    if (
        effective_caps.candidate_hard_ceiling is not None
        and len(candidates) > effective_caps.candidate_hard_ceiling
    ):
        # Defensive: hard-trim if the SQL cap was missing.
        candidates = candidates[: effective_caps.candidate_hard_ceiling]
    # v1.2: when an epoch is supplied, resolve every candidate's
    # position before the exact cone refine. Static rows pass
    # through unchanged; proper-motion rows propagate; ephemeris
    # rows snap to the nearest snapshot in object_states.
    if epoch is not None:
        from core.time_model import coerce_epoch
        from core.temporal_resolver import (
            EphemerisStore, ProperMotionStore, resolve_for_epoch,
        )
        ep = coerce_epoch(epoch)
        if ep is not None and candidates:
            uids = [o.uid for o in candidates if o.uid]
            states_for_uids = []
            if uids:
                try:
                    states_for_uids = list(
                        _fetch_states_in(db, uids),
                    )
                except Exception:  # noqa: BLE001
                    states_for_uids = []
            eph = EphemerisStore()
            pm = ProperMotionStore()
            for s in states_for_uids:
                if s.state_type == "ephemeris":
                    eph.add(s)
                elif s.state_type == "proper_motion":
                    if s.pmra_masyr is None or s.pmdec_masyr is None:
                        continue
                    ref_jd = s.reference_epoch_jd
                    if ref_jd is None:
                        ref_jd = s.epoch_jd
                    pm.add(
                        s.uid,
                        pmra_masyr=float(s.pmra_masyr),
                        pmdec_masyr=float(s.pmdec_masyr),
                        reference_epoch_jd=float(ref_jd),
                    )
            candidates, _stats = resolve_for_epoch(
                candidates, ep,
                ephemeris=eph, proper_motions=pm,
                interpolate=interpolate_ephemeris,
                in_place=True, recompute_cartesian=True,
            )
    t0 = time.monotonic()
    refined = apply_filter(
        candidates,
        origin_pc=origin_pc,
        forward=forward,
        near_clip_pc=near_pc,
        far_clip_pc=far_pc,
        cone_half_angle_deg=cone_half_angle_deg,
        max_visible_objects=max_visible_objects,
        selected_sources=selected_sources,
    )
    refine_elapsed = (time.monotonic() - t0) * 1000.0
    capped = int(getattr(refined.stats, "rejected_over_cap", 0))
    target_log = timing_log if timing_log is not None else GLOBAL_QUERY_TIMING_LOG
    target_log.record(
        candidate_rows=bbox.candidate_rows,
        kept_rows=len(refined.objects),
        bbox_elapsed_ms=bbox.elapsed_ms,
        refine_elapsed_ms=refine_elapsed,
        capped=capped,
        note=timing_note,
    )
    return ConeQueryResult(
        objects=refined.objects,
        candidate_rows=bbox.candidate_rows,
        kept_rows=len(refined.objects),
        bbox_min=bbox_min,
        bbox_max=bbox_max,
        bbox_elapsed_ms=bbox.elapsed_ms,
        refine_elapsed_ms=refine_elapsed,
        total_elapsed_ms=bbox.elapsed_ms + refine_elapsed,
        capped=capped,
    )


def _fetch_states_in(db: DBManager, uids: Sequence[str]):
    """Load ``object_states`` rows for any uids in the candidate
    set. Chunks the IN clause to stay under SQLite's parameter
    limit."""
    if not uids:
        return []
    out = []
    chunk = 500
    for i in range(0, len(uids), chunk):
        batch = uids[i:i + chunk]
        placeholders = ",".join("?" for _ in batch)
        cur = db.execute(
            f"SELECT * FROM object_states WHERE uid IN ({placeholders}) "
            f"ORDER BY uid, epoch_jd",
            tuple(batch),
        )
        from .db_manager import _state_from_row  # late import; circular-safe
        for row in cur.fetchall():
            out.append(_state_from_row(row))
    return out


def query_cone_for_navigator(
    db: DBManager,
    params: NavigationParams,
    origin_pc: Vec3,
    forward: Vec3,
    *,
    bbox_max_rows: Optional[int] = None,
    epoch=None,
    interpolate_ephemeris: bool = True,
    caps: Optional[QueryCaps] = None,
    timing_log: Optional[QueryTimingLog] = None,
    timing_note: str = "",
) -> ConeQueryResult:
    """Convenience wrapper that pulls cone parameters off a
    ``NavigationParams`` instance — the shape ``mock_actions`` /
    ``sector_streaming`` already speak.

    v1.2: ``epoch`` propagates into the temporal resolver so
    proper-motion stars land at the right RA/Dec and JPL bodies
    pick the matching ephemeris row.
    """
    sources = (
        list(params.selected_catalog_sources)
        if params.selected_catalog_sources else None
    )
    if sources is not None and not sources:
        sources = None
    cap = int(params.max_visible_objects) or None
    return query_cone(
        db,
        origin_pc=origin_pc,
        forward=forward,
        cone_half_angle_deg=float(params.cone_angle_deg),
        near_pc=float(params.near_clip_parsec),
        far_pc=float(params.far_clip_parsec),
        selected_sources=sources,
        max_visible_objects=cap,
        bbox_max_rows=bbox_max_rows,
        epoch=epoch,
        interpolate_ephemeris=interpolate_ephemeris,
        caps=caps,
        timing_log=timing_log,
        timing_note=timing_note,
    )
