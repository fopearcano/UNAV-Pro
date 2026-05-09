"""v1.9 route analytics — pre-animation route inspection.

Given a ``Mission``, return a structured analytics report:

* per-segment Euclidean distances (parsec when available),
* total distance,
* "X waypoints have unknown distance" warnings,
* placeholder estimated travel time,
* object-type histogram,
* catalog-source histogram,
* epoch-consistency warnings.

Pure stdlib. No Cinema 4D, no DB, no network. The dialog's
"Route Analytics" panel renders the report verbatim; tests
drive the analytics module directly without spinning up the
host.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .mission import Mission, MissionWaypoint, PATH_CONTRIBUTING_KINDS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: A placeholder "speed" for the v1.9 estimated-travel-time
#: number. The plugin doesn't model relativistic travel; this
#: figure is purely cosmetic — the artist can divide the
#: returned ETA by their narrative speed-of-flight to get
#: anything meaningful. Default: 1 parsec per second so the
#: ETA reads back the total distance directly.
DEFAULT_TRAVEL_SPEED_PC_PER_S: float = 1.0

#: Threshold for the epoch-consistency warning: when the
#: spread between any two waypoint epochs exceeds this many
#: Julian Years, the analytics layer flags it. The artist's
#: cinematic may be intentional ("from J2016 to J2026") but
#: it should be a conscious decision, not an accident.
EPOCH_SPREAD_WARN_THRESHOLD_DAYS: float = 365.25 * 50.0  # 50 years


# ---------------------------------------------------------------------------
# Report data
# ---------------------------------------------------------------------------


@dataclass
class SegmentMetric:
    """One leg of the route. ``distance_pc`` is None when
    either endpoint lacks a parsec position; the dialog
    surfaces this as the "X waypoints have unknown distance"
    warning."""

    from_index: int
    to_index: int
    from_label: str
    to_label: str
    distance_pc: Optional[float] = None
    distance_c4d: Optional[float] = None


@dataclass
class RouteAnalytics:
    """Aggregate analytics for one mission. The dialog's
    Route Analytics panel renders this verbatim via
    ``render_text``."""

    segments: List[SegmentMetric] = field(default_factory=list)
    total_distance_pc: Optional[float] = None
    total_distance_c4d: float = 0.0
    waypoints_with_unknown_distance: List[int] = field(default_factory=list)
    estimated_travel_seconds: Optional[float] = None
    object_type_counts: Dict[str, int] = field(default_factory=dict)
    catalog_source_counts: Dict[str, int] = field(default_factory=dict)
    waypoint_kind_counts: Dict[str, int] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    epoch_min_jd: Optional[float] = None
    epoch_max_jd: Optional[float] = None
    epoch_spread_days: Optional[float] = None
    epoch_spread_warning: Optional[str] = None
    waypoints_without_epoch: List[int] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    # ------------------------------------------------------------ predicates
    def has_unknown_distances(self) -> bool:
        return bool(self.waypoints_with_unknown_distance)

    def has_epoch_warning(self) -> bool:
        return self.epoch_spread_warning is not None

    # ------------------------------------------------------------ rendering
    def render_text(self) -> str:
        """Multi-line plain-text report. The dialog drops this
        into its analytics panel verbatim."""
        lines: List[str] = []
        lines.append("=== Route Analytics ===")
        lines.append(f"Segments       : {len(self.segments)}")
        lines.append(
            f"Total (C4D)    : {self.total_distance_c4d:.4g} C4D units"
        )
        if self.total_distance_pc is not None:
            lines.append(
                f"Total (pc)     : {self.total_distance_pc:.4g} pc"
            )
        else:
            lines.append("Total (pc)     : (unknown — see warnings)")
        if self.estimated_travel_seconds is not None:
            lines.append(
                f"Travel ETA     : {self.estimated_travel_seconds:.3g} s "
                f"(at {DEFAULT_TRAVEL_SPEED_PC_PER_S:g} pc/s)"
            )
        lines.append("")
        lines.append("--- Waypoint Kinds ---")
        for kind, count in sorted(self.waypoint_kind_counts.items()):
            lines.append(f"  {kind:14}: {count}")
        if self.object_type_counts:
            lines.append("")
            lines.append("--- Object Types ---")
            for otype, count in sorted(self.object_type_counts.items()):
                lines.append(f"  {otype:14}: {count}")
        if self.catalog_source_counts:
            lines.append("")
            lines.append("--- Catalog Sources ---")
            for src, count in sorted(self.catalog_source_counts.items()):
                lines.append(f"  {src:18}: {count}")
        if self.tags:
            lines.append("")
            lines.append("--- Tags ---")
            lines.append("  " + ", ".join(self.tags))
        if self.epoch_min_jd is not None and self.epoch_max_jd is not None:
            lines.append("")
            lines.append("--- Epoch Range ---")
            lines.append(
                f"  JD {self.epoch_min_jd:.3f} → {self.epoch_max_jd:.3f} "
                f"(spread {self.epoch_spread_days:.1f} days)"
            )
        warnings: List[str] = []
        if self.has_unknown_distances():
            warnings.append(
                f"{len(self.waypoints_with_unknown_distance)} waypoint(s) "
                "have no parsec position; total parsec distance is "
                "incomplete."
            )
        if self.epoch_spread_warning:
            warnings.append(self.epoch_spread_warning)
        # Only flag the missing-epoch warning when the mission
        # is *partially* timed: every waypoint missing an epoch
        # in a non-temporal mission is the design (no warning).
        if self.waypoints_without_epoch and self.epoch_min_jd is not None:
            warnings.append(
                f"{len(self.waypoints_without_epoch)} path-contributing "
                "waypoint(s) have no explicit epoch; the resolver will "
                "fall through to the previous waypoint's epoch."
            )
        if warnings:
            lines.append("")
            lines.append("--- Warnings ---")
            for w in warnings:
                lines.append(f"  ! {w}")
        for note in self.notes:
            lines.append(f"  i {note}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _euclidean_pc(
    a: MissionWaypoint, b: MissionWaypoint,
) -> Optional[float]:
    if not (a.has_pc_position() and b.has_pc_position()):
        return None
    dx = float(a.x_pc) - float(b.x_pc)
    dy = float(a.y_pc) - float(b.y_pc)
    dz = float(a.z_pc) - float(b.z_pc)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _euclidean_c4d(
    a: MissionWaypoint, b: MissionWaypoint,
) -> Optional[float]:
    if not (a.has_c4d_position() and b.has_c4d_position()):
        return None
    dx = float(a.x_c4d) - float(b.x_c4d)
    dy = float(a.y_c4d) - float(b.y_c4d)
    dz = float(a.z_c4d) - float(b.z_c4d)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def analyse_route(
    mission: Mission,
    *,
    travel_speed_pc_per_s: float = DEFAULT_TRAVEL_SPEED_PC_PER_S,
) -> RouteAnalytics:
    """Build a ``RouteAnalytics`` for ``mission``.

    Annotation waypoints are excluded from segment math
    (they have no position) but they *are* counted in the
    waypoint-kind histogram.
    """
    rpt = RouteAnalytics()

    # --- Kind / type / source histograms ---
    rpt.waypoint_kind_counts = dict(
        Counter(w.kind for w in mission.waypoints)
    )
    rpt.object_type_counts = dict(
        Counter(w.object_type for w in mission.waypoints if w.object_type)
    )
    rpt.catalog_source_counts = dict(
        Counter(
            w.catalog_source for w in mission.waypoints if w.catalog_source
        )
    )

    # --- Tags (mission-level + waypoint-level union) ---
    tag_set = set(mission.tags or [])
    for w in mission.waypoints:
        tag_set.update(w.tags or [])
    rpt.tags = sorted(tag_set)

    # --- Path-contributing waypoints for the segment walk ---
    contributing: List[Tuple[int, MissionWaypoint]] = [
        (i, w) for i, w in enumerate(mission.waypoints)
        if w.kind in PATH_CONTRIBUTING_KINDS
    ]

    unknown_distance_indices: List[int] = []
    no_epoch_indices: List[int] = []
    epochs: List[float] = []
    total_pc = 0.0
    total_c4d = 0.0
    have_any_pc_segment = False
    all_segments_have_pc = True

    for i, w in contributing:
        if w.epoch_jd is None:
            no_epoch_indices.append(i)
        else:
            epochs.append(float(w.epoch_jd))
        if not w.has_pc_position():
            unknown_distance_indices.append(i)

    for (i_a, wp_a), (i_b, wp_b) in zip(contributing, contributing[1:]):
        seg = SegmentMetric(
            from_index=i_a, to_index=i_b,
            from_label=wp_a.display_label(),
            to_label=wp_b.display_label(),
            distance_pc=_euclidean_pc(wp_a, wp_b),
            distance_c4d=_euclidean_c4d(wp_a, wp_b),
        )
        rpt.segments.append(seg)
        if seg.distance_pc is not None:
            total_pc += seg.distance_pc
            have_any_pc_segment = True
        else:
            all_segments_have_pc = False
        if seg.distance_c4d is not None:
            total_c4d += seg.distance_c4d

    rpt.total_distance_c4d = total_c4d
    if have_any_pc_segment and all_segments_have_pc:
        rpt.total_distance_pc = total_pc
        if travel_speed_pc_per_s > 0:
            rpt.estimated_travel_seconds = (
                total_pc / float(travel_speed_pc_per_s)
            )
    else:
        rpt.total_distance_pc = None
        rpt.estimated_travel_seconds = None

    rpt.waypoints_with_unknown_distance = unknown_distance_indices
    rpt.waypoints_without_epoch = no_epoch_indices

    # --- Epoch consistency ---
    if epochs:
        rpt.epoch_min_jd = min(epochs)
        rpt.epoch_max_jd = max(epochs)
        rpt.epoch_spread_days = rpt.epoch_max_jd - rpt.epoch_min_jd
        if rpt.epoch_spread_days > EPOCH_SPREAD_WARN_THRESHOLD_DAYS:
            rpt.epoch_spread_warning = (
                f"epoch spread is {rpt.epoch_spread_days:.0f} days "
                f"(> {EPOCH_SPREAD_WARN_THRESHOLD_DAYS:.0f} day "
                "threshold); the cinematic crosses a long temporal "
                "range — verify this is intentional."
            )

    return rpt
