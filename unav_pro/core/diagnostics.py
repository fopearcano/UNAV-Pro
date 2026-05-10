"""v3.0 dataset + scene diagnostics.

Pure helpers the dialog renders into the diagnostics panel
and into the status log when a long operation is about to
run. Every function in this module is **read-only**: nothing
here mutates Cinema 4D state, the registry, or the cache. The
output is plain dataclasses and strings the UI converts into
panel rows or warning popups.

What lives here:

* ``estimate_dataset_memory_bytes`` — rough on-disk +
  in-memory footprint estimate so the dialog can warn before
  loading a multi-GB catalog.
* ``estimate_visible_sector_objects`` — extrapolation of how
  many objects the current navigator pose would surface
  through the cone, based on dataset density.
* ``LongOperationWarning`` + ``classify_operation`` —
  threshold-driven "this might take a while" copy the dialog
  shows before kicking off a long sync / bake / export.
* ``render_query_timing_history`` — formatted multi-line text
  for the diagnostics panel's timing-history section, sourced
  from ``db.spatial_query.GLOBAL_QUERY_TIMING_LOG``.
* ``render_cache_usage`` — same idea for the chunk-reuse
  cache.
* ``count_active_overlays`` / ``count_active_science_layers``
  — counts the artist sees in the diagnostics panel header.

No c4d, no DB, no I/O. Pure stdlib; safe to import from
tests, the CLI, and Cinema 4D alike.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Dataset memory + sector estimation
# ---------------------------------------------------------------------------


#: Approximate per-row in-memory cost of a fully-hydrated
#: ``CatalogObject``. Empirically ~600 bytes for a Gaia row
#: with all metadata; the proxy here is conservative.
APPROX_BYTES_PER_OBJECT: int = 700

#: Approximate per-row on-disk cost of a JSONL row.
APPROX_BYTES_PER_JSONL_ROW: int = 300


@dataclass
class DatasetMemoryEstimate:
    """Outcome of a dataset memory probe.

    ``rows_known`` is True when the source supplied a row
    count; False when we're extrapolating from a file size.
    """

    rows: int
    on_disk_bytes: int
    in_memory_bytes: int
    rows_known: bool = True

    def short_summary(self) -> str:
        return (
            f"{self.rows:,} rows · "
            f"{self.on_disk_bytes / 1024 / 1024:.1f} MB on disk · "
            f"≈{self.in_memory_bytes / 1024 / 1024:.1f} MB in memory"
        )


def estimate_dataset_memory_bytes(
    *,
    object_count: Optional[int] = None,
    file_size_bytes: Optional[int] = None,
    bytes_per_row: int = APPROX_BYTES_PER_OBJECT,
    bytes_per_jsonl_row: int = APPROX_BYTES_PER_JSONL_ROW,
) -> DatasetMemoryEstimate:
    """Estimate on-disk + in-memory cost of a dataset.

    When ``object_count`` is supplied (the registry stats
    case), use it directly. Otherwise estimate rows from the
    file size using ``bytes_per_jsonl_row`` as the divisor.
    Returns zero-rows when both inputs are missing rather than
    raising — a missing-stats dataset still wants a panel row.
    """
    if object_count is not None and object_count >= 0:
        rows = int(object_count)
        on_disk = (
            int(file_size_bytes) if file_size_bytes is not None
            else rows * int(bytes_per_jsonl_row)
        )
        return DatasetMemoryEstimate(
            rows=rows,
            on_disk_bytes=int(on_disk),
            in_memory_bytes=rows * int(bytes_per_row),
            rows_known=True,
        )
    if file_size_bytes is not None and file_size_bytes >= 0:
        rows = int(file_size_bytes) // max(1, int(bytes_per_jsonl_row))
        return DatasetMemoryEstimate(
            rows=rows,
            on_disk_bytes=int(file_size_bytes),
            in_memory_bytes=rows * int(bytes_per_row),
            rows_known=False,
        )
    return DatasetMemoryEstimate(
        rows=0, on_disk_bytes=0, in_memory_bytes=0, rows_known=False,
    )


@dataclass
class VisibleSectorEstimate:
    """Extrapolation of how many objects the navigator's cone
    would currently surface, computed from the dataset density
    and the cone's solid-angle / depth fraction.

    Pure proxy — the actual sync goes through the cone refine
    and may differ. The estimate exists so the dialog can warn
    "this sync is going to be ~120 K objects, expect ~3 s."
    """

    estimated_objects: int
    sky_fraction: float
    depth_fraction: float
    note: str = ""

    def short_summary(self) -> str:
        return (
            f"≈{self.estimated_objects:,} objects "
            f"({self.sky_fraction * 100:.1f}% sky × "
            f"{self.depth_fraction * 100:.1f}% depth)"
        )


def _solid_angle_fraction(half_angle_deg: float) -> float:
    """Fraction of the full sky covered by a cone of given
    half-angle. ``half_angle_deg=180`` → 1.0; 0 → 0."""
    import math
    h = max(0.0, min(180.0, float(half_angle_deg)))
    if h <= 0.0:
        return 0.0
    if h >= 180.0:
        return 1.0
    return (1.0 - math.cos(math.radians(h))) / 2.0


def estimate_visible_sector_objects(
    *,
    total_objects: int,
    cone_half_angle_deg: float,
    near_pc: float = 0.0,
    far_pc: float = 1000.0,
    dataset_extent_pc: float = 1000.0,
) -> VisibleSectorEstimate:
    """Coarse estimator. Treats the dataset as uniformly
    distributed across an extent of ``dataset_extent_pc``
    (parsec) and a 4π solid angle, then multiplies by the
    cone's solid-angle and depth fractions.

    Real catalogs are anisotropic (Gaia is heavy along the
    galactic plane; SDSS is patchy) so the estimate can be
    off by a factor of a few — but the order of magnitude
    is right, which is what the warning needs.
    """
    if total_objects <= 0:
        return VisibleSectorEstimate(
            estimated_objects=0,
            sky_fraction=0.0,
            depth_fraction=0.0,
            note="empty dataset",
        )
    sky = _solid_angle_fraction(cone_half_angle_deg)
    depth = 1.0
    if dataset_extent_pc > 0 and far_pc > 0 and far_pc < dataset_extent_pc:
        # Use a depth ratio (far - near) / extent.
        d = max(0.0, float(far_pc) - max(0.0, float(near_pc)))
        depth = max(0.0, min(1.0, d / float(dataset_extent_pc)))
    estimated = int(round(total_objects * sky * depth))
    return VisibleSectorEstimate(
        estimated_objects=estimated,
        sky_fraction=sky,
        depth_fraction=depth,
        note="uniform-distribution proxy; real catalogs differ",
    )


# ---------------------------------------------------------------------------
# Long-operation warnings
# ---------------------------------------------------------------------------


#: Object count thresholds for the warning classifier. Each
#: tier maps to a one-line "this will take a while" string.
LONG_OP_THRESHOLDS: Tuple[Tuple[int, str], ...] = (
    (50_000, "small"),
    (250_000, "medium"),
    (1_000_000, "large"),
    (5_000_000, "very large"),
)


@dataclass
class LongOperationWarning:
    """Suggested warning + recommendation for an upcoming
    long operation. Returned by ``classify_operation``."""

    severity: str  # "ok" | "info" | "warn" | "block"
    object_count: int
    headline: str
    recommendation: str

    def short_summary(self) -> str:
        if self.severity == "ok":
            return f"{self.object_count:,} objects — should be quick"
        return f"{self.headline} — {self.recommendation}"


def classify_operation(
    object_count: int,
    *,
    operation: str = "sync",
) -> LongOperationWarning:
    """Map a candidate object count onto a warning tier.

    Used by the dialog before kicking off a sync / bake /
    export. The returned headline is a short friendly string
    the artist sees in the status log; ``recommendation``
    suggests what to do (lower the cap, narrow the cone,
    use an indexed source, etc.).
    """
    n = max(0, int(object_count))
    if n < LONG_OP_THRESHOLDS[0][0]:
        return LongOperationWarning(
            severity="ok",
            object_count=n,
            headline=f"{operation}: {n:,} objects",
            recommendation="should complete instantly.",
        )
    if n < LONG_OP_THRESHOLDS[1][0]:
        return LongOperationWarning(
            severity="info",
            object_count=n,
            headline=f"{operation}: {n:,} objects (small workload)",
            recommendation="usually under a few seconds.",
        )
    if n < LONG_OP_THRESHOLDS[2][0]:
        return LongOperationWarning(
            severity="warn",
            object_count=n,
            headline=f"{operation}: {n:,} objects (medium workload)",
            recommendation=(
                "expect a few seconds; the UI may stutter. Consider "
                "narrowing the cone or lowering max_visible_objects."
            ),
        )
    if n < LONG_OP_THRESHOLDS[3][0]:
        return LongOperationWarning(
            severity="warn",
            object_count=n,
            headline=f"{operation}: {n:,} objects (large workload)",
            recommendation=(
                "expect tens of seconds; UI will block. Consider the "
                "instances or point-cloud render mode."
            ),
        )
    return LongOperationWarning(
        severity="block",
        object_count=n,
        headline=f"{operation}: {n:,} objects (very large workload)",
        recommendation=(
            "this may exhaust memory. Lower max_visible_objects, "
            "narrow the cone, or run the operation in chunks via the "
            "task queue."
        ),
    )


# ---------------------------------------------------------------------------
# Query timing renderer
# ---------------------------------------------------------------------------


def render_query_timing_history(
    timing_log: Any,
    *,
    recent: int = 5,
    slowest: int = 3,
) -> str:
    """Render a ``QueryTimingLog`` as a multi-line block for
    the diagnostics panel.

    Defensive against unfamiliar log shapes (returns
    "(no timing data)" rather than raising) so the diagnostics
    panel stays robust if the log ever gains new methods.
    """
    if timing_log is None:
        return "(no timing data)"
    try:
        recent_entries = list(timing_log.recent(recent))
        slowest_entries = list(timing_log.slowest(slowest))
        avg = float(timing_log.average_total_ms())
        n = len(timing_log)
    except Exception:  # noqa: BLE001
        return "(timing log unavailable)"
    if n == 0:
        return "(no queries recorded yet)"
    lines: List[str] = []
    lines.append(f"queries recorded: {n}; mean total: {avg:.1f} ms")
    if recent_entries:
        lines.append("recent:")
        for e in recent_entries:
            lines.append(f"  · {e.short_summary()}")
    if slowest_entries:
        lines.append("slowest:")
        for e in slowest_entries:
            lines.append(f"  · {e.short_summary()}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cache usage renderer
# ---------------------------------------------------------------------------


def render_cache_usage(cache: Any) -> str:
    """Format a ``ChunkReuseCache`` for the diagnostics panel.

    Reports cache size / capacity / row footprint / hit
    ratio. Returns "(no cache active)" when ``cache`` is
    ``None``.
    """
    if cache is None:
        return "(no cache active)"
    try:
        size = int(cache.size)
        cap = int(cache.max_entries)
        rows = int(cache.estimated_row_count())
        stats = cache.stats
    except Exception:  # noqa: BLE001
        return "(cache snapshot unavailable)"
    return (
        f"entries: {size}/{cap}; rows cached: {rows:,}; "
        f"{stats.short_summary()}"
    )


# ---------------------------------------------------------------------------
# Layer counts
# ---------------------------------------------------------------------------


def count_active_overlays(settings: Any) -> int:
    """Count how many overlay kinds are currently visible.

    Reads the v2.0 ``OverlaySettings.show_*`` fields. Returns
    0 for ``None`` so the diagnostics panel shows a single
    "0" rather than blank when no overlays are configured.
    """
    if settings is None:
        return 0
    fields_to_check = (
        "show_grid", "show_galactic_plane", "show_ecliptic_plane",
        "show_distance_rings", "show_sector_cone",
        "show_route_corridor", "show_waypoint_labels",
    )
    return sum(
        1 for f in fields_to_check
        if bool(getattr(settings, f, False))
    )


def count_active_science_layers(settings: Any) -> int:
    """Same as ``count_active_overlays`` for v2.1 science layers."""
    if settings is None:
        return 0
    fields_to_check = (
        "show_distance_shells", "show_redshift_shells",
        "show_magnitude_shells", "show_motion_vectors",
        "show_catalog_source_regions", "show_solar_system_orbits",
        "show_constellation_boundaries", "show_object_density_volume",
    )
    return sum(
        1 for f in fields_to_check
        if bool(getattr(settings, f, False))
    )


# ---------------------------------------------------------------------------
# Aggregate report
# ---------------------------------------------------------------------------


@dataclass
class DiagnosticsReport:
    """Top-level snapshot the dialog renders into the
    Diagnostics panel. Every field is human-readable text so
    the panel doesn't need any formatting logic of its own.
    """

    dataset_lines: List[str] = field(default_factory=list)
    visible_sector_line: str = ""
    cache_line: str = ""
    timing_block: str = ""
    overlay_count: int = 0
    science_layer_count: int = 0
    task_queue_line: str = ""

    def render(self) -> str:
        out: List[str] = []
        out.append("=== UNAV Pro Diagnostics ===")
        if self.dataset_lines:
            out.append("Datasets:")
            for line in self.dataset_lines:
                out.append(f"  · {line}")
        if self.visible_sector_line:
            out.append(f"Visible sector estimate: {self.visible_sector_line}")
        out.append(f"Active overlays: {self.overlay_count}")
        out.append(f"Active science layers: {self.science_layer_count}")
        if self.cache_line:
            out.append(f"Cone cache: {self.cache_line}")
        if self.task_queue_line:
            out.append(f"Task queue: {self.task_queue_line}")
        if self.timing_block:
            out.append("Query timings:")
            for line in self.timing_block.splitlines():
                out.append(f"  {line}")
        return "\n".join(out)


def render_task_queue_line(queue: Any) -> str:
    """Render a one-liner for ``TaskQueue`` state. Defensive
    against missing methods so the panel stays robust under
    future task-queue changes."""
    if queue is None:
        return "(no queue)"
    try:
        pending = len(queue.pending())
        running = len(queue.running())
        terminal = len(queue.terminal())
        stats = queue.stats
    except Exception:  # noqa: BLE001
        return "(queue snapshot unavailable)"
    return (
        f"pending: {pending}; running: {running}; done: {terminal}; "
        f"completed lifetime: {stats.completed}; failed: {stats.failed}"
    )


def build_diagnostics_report(
    *,
    dataset_estimates: Optional[Sequence[Tuple[str, DatasetMemoryEstimate]]] = None,
    visible_sector: Optional[VisibleSectorEstimate] = None,
    cache: Any = None,
    timing_log: Any = None,
    overlay_settings: Any = None,
    science_settings: Any = None,
    task_queue: Any = None,
) -> DiagnosticsReport:
    """Assemble the report. Every argument is optional; the
    renderer skips sections whose source is missing."""
    rep = DiagnosticsReport()
    if dataset_estimates:
        rep.dataset_lines = [
            f"{name}: {est.short_summary()}"
            for (name, est) in dataset_estimates
        ]
    if visible_sector is not None:
        rep.visible_sector_line = visible_sector.short_summary()
    rep.cache_line = render_cache_usage(cache)
    rep.timing_block = render_query_timing_history(timing_log)
    rep.overlay_count = count_active_overlays(overlay_settings)
    rep.science_layer_count = count_active_science_layers(science_settings)
    rep.task_queue_line = render_task_queue_line(task_queue)
    return rep
