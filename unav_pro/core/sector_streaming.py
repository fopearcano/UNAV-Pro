"""Sector streaming — load only the chunks the navigator's cone touches.

The headline workflow for v0.2: instead of reading every catalog
file into memory before filtering (the v0.1 path), each registered
dataset is queried through its spatial index. Only the chunks of
candidate cells reach the plugin; everything else stays on disk.

This module is the bridge:

* Resolves a ``DatasetEntry`` to either a ``query_index`` call
  (when ``entry.index_path`` is populated and readable) or a
  fall-back ``load_catalog`` (with a warning when the catalog is
  over the safety threshold).
* Aggregates results across every enabled dataset in a
  ``DatasetRegistry`` with namespaced uids, respecting the
  navigator's ``max_visible_objects`` cap globally.
* Returns a structured ``StreamResult`` carrying the I/O
  footprint, advisory warnings, and the merged candidate list
  ready for ``build_starfield`` / ``sync_visible_sector``.

No c4d dependency. Pure CPython, fully unit-tested.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.dataset_registry import DatasetEntry, DatasetRegistry
from core.logging_util import get_logger
from core.navigation_state import NavigationParams
from core.spatial_filter import filter_for_navigator
from core.spatial_index import INDEX_FILENAME, query_index
from data.catalog_io import CatalogIOError, load_catalog
from data.connectors._normalize import to_int as _to_int  # noqa: F401  (placeholder)
from data.schema import CatalogObject

_log = get_logger("core.sector_streaming")

#: Above this many rows in an unindexed dataset, surface an explicit
#: warning telling the user to build the index. Aligned with
#: ``SafetyLimits.dataset_size_warning`` but exposed here so the
#: streaming path doesn't have to import the safety module.
DEFAULT_DATASET_SIZE_WARNING = 1_000_000

#: Hard cap on rows a single full-catalog fallback will load, even
#: when the user has the warning silenced. Beyond this, the streamer
#: refuses outright — load_catalog into a Python list at this scale
#: is the failure mode the safety system exists to prevent.
HARD_FULL_LOAD_CEILING = 5_000_000


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class DatasetStreamResult:
    """Outcome of streaming one dataset for one navigator pose.

    v1.1 added ``used_db`` and timing fields so the dialog can
    distinguish chunk-streamed entries from SQL-backed entries
    and surface query latency in the status panel.
    """

    name: str
    objects: List[CatalogObject] = field(default_factory=list)
    used_index: bool = False
    used_db: bool = False
    candidate_cells: Optional[int] = None
    total_cells: Optional[int] = None
    candidate_objects: Optional[int] = None
    fallback_reason: Optional[str] = None
    warning: Optional[str] = None
    error: Optional[str] = None
    # v1.1 — query timing.
    bbox_elapsed_ms: Optional[float] = None
    refine_elapsed_ms: Optional[float] = None

    @property
    def kept(self) -> int:
        return len(self.objects)


@dataclass
class StreamResult:
    """Merged outcome across every enabled dataset."""

    objects: List[CatalogObject] = field(default_factory=list)
    per_dataset: List[DatasetStreamResult] = field(default_factory=list)
    duplicates_skipped: int = 0
    total_kept: int = 0
    total_candidates: int = 0
    capped: int = 0

    def short_summary(self) -> str:
        parts = [
            f"{self.total_kept} visible "
            f"(of {self.total_candidates} candidates)"
        ]
        if self.duplicates_skipped:
            parts.append(f"{self.duplicates_skipped} dupes")
        if self.capped:
            parts.append(f"{self.capped} capped")
        warn = [r for r in self.per_dataset if r.warning]
        if warn:
            parts.append(f"{len(warn)} warning(s)")
        err = [r for r in self.per_dataset if r.error]
        if err:
            parts.append(f"{len(err)} error(s)")
        return "; ".join(parts)

    def warnings(self) -> List[str]:
        return [r.warning for r in self.per_dataset if r.warning]

    def errors(self) -> List[str]:
        return [
            f"{r.name}: {r.error}" for r in self.per_dataset if r.error
        ]


# ---------------------------------------------------------------------------
# Per-dataset streaming
# ---------------------------------------------------------------------------


def _entry_index_dir(entry: DatasetEntry) -> Optional[str]:
    """Return the index directory if ``entry.index_path`` is usable
    (directory exists and contains the manifest), else None."""
    path = entry.index_path
    if not path or not os.path.isdir(path):
        return None
    if not os.path.isfile(os.path.join(path, INDEX_FILENAME)):
        return None
    return path


def _namespace(entry: DatasetEntry, uid: str) -> str:
    """Apply the registry's namespacing rule. Mirrors
    ``DatasetRegistry.merge_active``."""
    if not entry.namespace:
        return uid
    return f"{entry.name}:{uid}"


def stream_sector_for_dataset(
    entry: DatasetEntry,
    params: NavigationParams,
    origin_c4d: Tuple[float, float, float],
    forward: Tuple[float, float, float],
    *,
    dataset_size_warning: int = DEFAULT_DATASET_SIZE_WARNING,
    hard_full_load_ceiling: int = HARD_FULL_LOAD_CEILING,
    epoch=None,
) -> DatasetStreamResult:
    """Return the visible-sector candidates from ``entry`` under
    ``params`` + the navigator's pose.

    Prefers the spatial index when ``entry.index_path`` is set and
    the manifest is readable. Falls back to a full
    ``load_catalog`` + ``apply_filter`` pass with a warning when no
    index exists; refuses outright when the unindexed catalog is
    above ``hard_full_load_ceiling`` rows.
    """
    out = DatasetStreamResult(name=entry.name)

    # Translate the navigator's C4D-units origin into parsec, the
    # frame the spatial index and the filter both speak.
    from core.spatial_filter import c4d_units_to_pc

    try:
        origin_pc = c4d_units_to_pc(origin_c4d, scale_mode=params.c4d_scale)
    except ValueError as exc:
        out.error = f"bad scale_mode: {exc}"
        _log.warning("Stream %s: %s", entry.name, out.error)
        return out

    cone = float(params.cone_angle_deg)
    near_pc = float(params.near_clip_parsec)
    far_pc = float(params.far_clip_parsec)
    cap = int(params.max_visible_objects) or None

    sources_filter = (
        list(params.selected_catalog_sources)
        if params.selected_catalog_sources else None
    )
    if sources_filter is not None and not sources_filter:
        sources_filter = None

    # ---- DB-backed path (v1.1) -------------------------------------------
    if entry.is_db_backed:
        try:
            from db.db_manager import DBManager
            from db.spatial_query import query_cone_for_navigator
        except ImportError as exc:  # pragma: no cover — defensive
            out.error = f"db package unavailable: {exc}"
            _log.exception("Stream %s: db import failed", entry.name)
            return out
        try:
            # v1.1 used read_only; v1.2 keeps the DB read-only here
            # because the resolver only fetches state rows. Native
            # writes happen elsewhere (importer / time-series CLI).
            with DBManager(entry.db_path or "", read_only=True) as db:
                cone = query_cone_for_navigator(
                    db, params, origin_pc, forward, epoch=epoch,
                )
        except Exception as exc:  # noqa: BLE001 — boundary
            out.error = f"db cone query failed: {exc!r}"
            _log.exception("Stream %s: db query failed", entry.name)
            return out
        out.used_db = True
        out.candidate_objects = cone.candidate_rows
        out.bbox_elapsed_ms = cone.bbox_elapsed_ms
        out.refine_elapsed_ms = cone.refine_elapsed_ms
        for obj in cone.objects:
            obj.uid = _namespace(entry, obj.uid or "")
        out.objects = cone.objects
        return out

    index_dir = _entry_index_dir(entry)

    if index_dir is not None:
        # ---- streamed path ------------------------------------------------
        try:
            result, meta = query_index(
                index_dir,
                origin_pc=origin_pc,
                forward=forward,
                cone_half_angle_deg=cone,
                near_pc=near_pc,
                far_pc=far_pc,
                max_visible_objects=cap,
                selected_sources=sources_filter,
            )
        except Exception as exc:  # noqa: BLE001 — boundary
            out.error = f"index query failed: {exc!r}"
            _log.exception("Stream %s: index query failed", entry.name)
            return out
        out.used_index = True
        out.candidate_cells = meta["candidate_cells"]
        out.total_cells = meta["total_cells"]
        out.candidate_objects = meta["candidate_objects"]
        for obj in result.objects:
            obj.uid = _namespace(entry, obj.uid or "")
        out.objects = result.objects
        return out

    # ---- fallback path ----------------------------------------------------
    out.fallback_reason = "no spatial index"

    row_count = (
        entry.stats.object_count
        if entry.stats is not None and entry.stats.object_count is not None
        else None
    )

    if row_count is not None and row_count > hard_full_load_ceiling:
        out.error = (
            f"refused to full-load {row_count} rows above the "
            f"{hard_full_load_ceiling} ceiling — build the spatial "
            "index first"
        )
        _log.warning("Stream %s: %s", entry.name, out.error)
        return out

    if row_count is not None and row_count >= dataset_size_warning:
        out.warning = (
            f"dataset '{entry.name}' has {row_count} rows and is not "
            f"indexed; loading the whole file. Build Index in the "
            f"Dataset Manager for sector-streaming I/O."
        )
        _log.warning("%s", out.warning)
    elif row_count is None:
        out.warning = (
            f"dataset '{entry.name}' has no scanned stats and is not "
            f"indexed; full-load fallback active."
        )

    try:
        objects = load_catalog(entry.path)
    except (CatalogIOError, FileNotFoundError, OSError) as exc:
        out.error = f"could not load: {exc}"
        return out

    out.candidate_objects = len(objects)
    filtered = filter_for_navigator(
        objects, origin_c4d=origin_c4d, forward=forward, params=params,
    )
    for obj in filtered.objects:
        obj.uid = _namespace(entry, obj.uid or "")
    out.objects = filtered.objects
    return out


# ---------------------------------------------------------------------------
# Multi-dataset aggregation
# ---------------------------------------------------------------------------


def stream_sector_for_active_datasets(
    registry: DatasetRegistry,
    params: NavigationParams,
    origin_c4d: Tuple[float, float, float],
    forward: Tuple[float, float, float],
    *,
    global_cap: Optional[int] = None,
    dataset_size_warning: int = DEFAULT_DATASET_SIZE_WARNING,
    epoch=None,
) -> StreamResult:
    """Aggregate streamed candidates across every enabled dataset.

    Uids are namespaced by the streaming path; the merge here only
    de-duplicates across datasets (same namespaced uid present in two
    enabled entries) and applies a global cap on the final list. The
    cap is the *navigator's* ``max_visible_objects`` unless the
    caller overrides via ``global_cap``.
    """
    enabled = registry.enabled_entries()
    cap = global_cap if global_cap is not None else int(params.max_visible_objects)

    merged = StreamResult()
    seen: set = set()
    for entry in enabled:
        per = stream_sector_for_dataset(
            entry, params, origin_c4d, forward,
            dataset_size_warning=dataset_size_warning,
            epoch=epoch,
        )
        merged.per_dataset.append(per)
        if per.candidate_objects is not None:
            merged.total_candidates += per.candidate_objects
        for obj in per.objects:
            uid = obj.uid or ""
            if not uid:
                continue
            if uid in seen:
                merged.duplicates_skipped += 1
                continue
            seen.add(uid)
            merged.objects.append(obj)

    if cap and cap > 0 and len(merged.objects) > cap:
        merged.capped = len(merged.objects) - cap
        merged.objects = merged.objects[:cap]

    merged.total_kept = len(merged.objects)
    return merged


# ---------------------------------------------------------------------------
# Workflow-step helper
# ---------------------------------------------------------------------------


def workflow_step(
    *,
    enabled_dataset_count: int,
    any_dataset_indexed: bool,
    has_navigator: bool,
    visible_sector_count: int,
) -> Tuple[int, str]:
    """Pure helper used by the dialog's workflow strip. Returns
    ``(step_number, hint_text)``.

    The five steps:
      1. Select dataset.
      2. Build / load index.
      3. Create navigator.
      4. Sync visible sector.
      5. Inspect object metadata.
    """
    if enabled_dataset_count <= 0:
        return 1, (
            "Step 1/5 — open Dataset Manager… and add or enable a "
            "catalog file."
        )
    if not any_dataset_indexed:
        return 2, (
            "Step 2/5 — Build Index for the active dataset (Dataset "
            "Manager → Build Index). Required for sector-streaming I/O."
        )
    if not has_navigator:
        return 3, (
            "Step 3/5 — Create Navigation Null. Position and rotate it "
            "where you want the scene centered."
        )
    if visible_sector_count <= 0:
        return 4, (
            "Step 4/5 — Sync Visible Sector. Loads only chunks the "
            "navigator's cone touches."
        )
    return 5, (
        "Step 5/5 — click any UNAV object → Inspect Selected Object."
    )
