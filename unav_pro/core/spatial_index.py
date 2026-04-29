"""Chunked spatial index for UNAV catalogs.

The plugin's read path must scale to catalogs with millions of rows
without ever loading the whole thing into memory. This module builds
a coarse cubic grid over the catalog's parsec-Cartesian extent,
buckets objects into cells, and writes one or more JSONL **chunks**
per non-empty cell. Cell metadata is collected into a single
``index.json`` manifest.

At query time the navigator's cone is intersected with each cell's
AABB; only the chunks of surviving cells are loaded from disk and
handed to ``core.spatial_filter.apply_filter`` for exact rejection.

This is the simplest workable spatial-index strategy. It is not
HEALPix; it is not a BVH; it is a uniform grid. That is intentional:

  * It is correct under any catalog distribution.
  * It is two pages of code.
  * It maps cleanly to the eventual production index
    (``UNAV_PRO_DATA_PIPELINE.md`` §8: HEALPix tiles + distance shells).

The on-disk layout

::

    <output_dir>/
      index.json
      chunks/
        cell_<i>_<j>_<k>/
          chunk_00.jsonl
          chunk_01.jsonl
          ...

is intentionally human-inspectable: a developer can ``cat`` any
chunk and see canonical catalog rows. Future backends (SQLite,
DuckDB, Parquet, HDF5) will fit behind the same ``query_index`` /
``SpatialIndex`` API; see ``docs/SPATIAL_INDEXING_AND_CHUNKING.md``
for the migration plan.

No c4d dependency. No numpy dependency. Pure stdlib so the index
builds offline in any Python.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

from core.logging_util import get_logger
from data.catalog_io import load_catalog, write_catalog
from data.schema import CatalogObject, compute_derived_fields

from . import spatial_filter as sf

_log = get_logger("core.spatial_index")

INDEX_FILENAME = "index.json"
INDEX_SCHEMA_VERSION = 1
DEFAULT_CHUNK_SIZE = 5000
#: Floor for cell size so a tightly-clustered catalog doesn't produce a
#: degenerate single cell collapsed to zero size.
_MIN_CELL_SIZE_PC = 1.0e-3


# ---------------------------------------------------------------------------
# Index dataclasses
# ---------------------------------------------------------------------------


@dataclass
class IndexCell:
    """One cell of the uniform grid. The cell holds the AABB plus a
    list of relative paths to the JSONL chunk files that make up its
    contents."""

    cell: Tuple[int, int, int]
    bbox_min_pc: Tuple[float, float, float]
    bbox_max_pc: Tuple[float, float, float]
    chunk_paths: List[str]
    object_count: int

    def to_dict(self) -> dict:
        return {
            "cell": list(self.cell),
            "bbox_min_pc": list(self.bbox_min_pc),
            "bbox_max_pc": list(self.bbox_max_pc),
            "chunk_paths": list(self.chunk_paths),
            "object_count": int(self.object_count),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IndexCell":
        return cls(
            cell=tuple(d["cell"]),  # type: ignore[arg-type]
            bbox_min_pc=tuple(d["bbox_min_pc"]),  # type: ignore[arg-type]
            bbox_max_pc=tuple(d["bbox_max_pc"]),  # type: ignore[arg-type]
            chunk_paths=list(d["chunk_paths"]),
            object_count=int(d["object_count"]),
        )


@dataclass
class SpatialIndex:
    """Top-level index manifest, persisted to ``index.json``."""

    schema_version: int = INDEX_SCHEMA_VERSION
    cell_size_pc: float = 0.0
    chunk_size: int = DEFAULT_CHUNK_SIZE
    grid_origin_pc: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_min_pc: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_max_pc: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    total_objects: int = 0
    sources: List[str] = field(default_factory=list)
    cells: List[IndexCell] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "cell_size_pc": self.cell_size_pc,
            "chunk_size": self.chunk_size,
            "grid_origin_pc": list(self.grid_origin_pc),
            "bbox_min_pc": list(self.bbox_min_pc),
            "bbox_max_pc": list(self.bbox_max_pc),
            "total_objects": self.total_objects,
            "sources": list(self.sources),
            "cells": [c.to_dict() for c in self.cells],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpatialIndex":
        return cls(
            schema_version=int(d.get("schema_version", INDEX_SCHEMA_VERSION)),
            cell_size_pc=float(d.get("cell_size_pc", 0.0)),
            chunk_size=int(d.get("chunk_size", DEFAULT_CHUNK_SIZE)),
            grid_origin_pc=tuple(d.get("grid_origin_pc", (0, 0, 0))),  # type: ignore[arg-type]
            bbox_min_pc=tuple(d.get("bbox_min_pc", (0, 0, 0))),  # type: ignore[arg-type]
            bbox_max_pc=tuple(d.get("bbox_max_pc", (0, 0, 0))),  # type: ignore[arg-type]
            total_objects=int(d.get("total_objects", 0)),
            sources=list(d.get("sources", [])),
            cells=[IndexCell.from_dict(c) for c in d.get("cells", [])],
        )

    # ------------------------------------------------------------------ I/O
    def save(self, index_dir: str) -> str:
        """Write ``index.json`` into ``index_dir``. Returns the path."""
        os.makedirs(index_dir, exist_ok=True)
        path = os.path.join(index_dir, INDEX_FILENAME)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, sort_keys=True)
        _log.info("Wrote spatial index to %s (%d cells, %d objects).",
                  path, len(self.cells), self.total_objects)
        return path

    @classmethod
    def load(cls, index_dir_or_path: str) -> "SpatialIndex":
        if os.path.isdir(index_dir_or_path):
            path = os.path.join(index_dir_or_path, INDEX_FILENAME)
        else:
            path = index_dir_or_path
        if not os.path.isfile(path):
            raise FileNotFoundError(f"spatial index not found: {path}")
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return cls.from_dict(d)


# ---------------------------------------------------------------------------
# Grid math (pure)
# ---------------------------------------------------------------------------


def cell_index_for(
    point_pc: Tuple[float, float, float],
    grid_origin_pc: Tuple[float, float, float],
    cell_size_pc: float,
) -> Tuple[int, int, int]:
    """Return the (i, j, k) cell that contains ``point_pc``."""
    if cell_size_pc <= 0:
        raise ValueError("cell_size_pc must be > 0")
    return (
        int(math.floor((point_pc[0] - grid_origin_pc[0]) / cell_size_pc)),
        int(math.floor((point_pc[1] - grid_origin_pc[1]) / cell_size_pc)),
        int(math.floor((point_pc[2] - grid_origin_pc[2]) / cell_size_pc)),
    )


def cell_bbox(
    cell: Tuple[int, int, int],
    grid_origin_pc: Tuple[float, float, float],
    cell_size_pc: float,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Return the (min_pc, max_pc) AABB of a cell."""
    i, j, k = cell
    bmin = (
        grid_origin_pc[0] + i * cell_size_pc,
        grid_origin_pc[1] + j * cell_size_pc,
        grid_origin_pc[2] + k * cell_size_pc,
    )
    bmax = (
        bmin[0] + cell_size_pc,
        bmin[1] + cell_size_pc,
        bmin[2] + cell_size_pc,
    )
    return bmin, bmax


def _aabb_min_distance(
    p: Tuple[float, float, float],
    bmin: Tuple[float, float, float],
    bmax: Tuple[float, float, float],
) -> float:
    """Closest distance from ``p`` to the AABB. Zero if ``p`` is inside."""
    dx = max(bmin[0] - p[0], 0.0, p[0] - bmax[0])
    dy = max(bmin[1] - p[1], 0.0, p[1] - bmax[1])
    dz = max(bmin[2] - p[2], 0.0, p[2] - bmax[2])
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _aabb_max_distance(
    p: Tuple[float, float, float],
    bmin: Tuple[float, float, float],
    bmax: Tuple[float, float, float],
) -> float:
    """Farthest distance from ``p`` to the AABB (worst corner)."""
    dx = max(abs(p[0] - bmin[0]), abs(p[0] - bmax[0]))
    dy = max(abs(p[1] - bmin[1]), abs(p[1] - bmax[1]))
    dz = max(abs(p[2] - bmin[2]), abs(p[2] - bmax[2]))
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _aabb_corners(
    bmin: Tuple[float, float, float],
    bmax: Tuple[float, float, float],
) -> List[Tuple[float, float, float]]:
    return [
        (bmin[0], bmin[1], bmin[2]),
        (bmin[0], bmin[1], bmax[2]),
        (bmin[0], bmax[1], bmin[2]),
        (bmin[0], bmax[1], bmax[2]),
        (bmax[0], bmin[1], bmin[2]),
        (bmax[0], bmin[1], bmax[2]),
        (bmax[0], bmax[1], bmin[2]),
        (bmax[0], bmax[1], bmax[2]),
    ]


def aabb_intersects_cone(
    bbox_min_pc: Tuple[float, float, float],
    bbox_max_pc: Tuple[float, float, float],
    origin_pc: Tuple[float, float, float],
    forward: Tuple[float, float, float],
    cone_half_angle_deg: float,
    near_pc: float = 0.0,
    far_pc: float = float("inf"),
) -> bool:
    """Conservative test: could the AABB contain any point inside the
    navigator cone? Returns True for "maybe", False for "definitely
    not". Designed to never produce a false negative — the exact filter
    runs afterwards on the surviving candidates.

    Tests applied in cheap-to-expensive order:

      1. Distance shell against AABB extreme distances.
      2. "Entirely behind" against forward-axis projection of all
         eight corners.
    """
    near_dist = _aabb_min_distance(origin_pc, bbox_min_pc, bbox_max_pc)
    far_dist = _aabb_max_distance(origin_pc, bbox_min_pc, bbox_max_pc)
    if far_dist < near_pc:
        return False
    if near_dist > far_pc:
        return False

    fwd = sf._normalize(forward)
    if fwd is None or cone_half_angle_deg >= 180.0:
        return True

    # Projections of all 8 corners onto the forward axis. If they are
    # all <= 0, the entire AABB lies in the rear hemisphere.
    any_forward = False
    for c in _aabb_corners(bbox_min_pc, bbox_max_pc):
        proj = (
            (c[0] - origin_pc[0]) * fwd[0]
            + (c[1] - origin_pc[1]) * fwd[1]
            + (c[2] - origin_pc[2]) * fwd[2]
        )
        if proj > 0.0:
            any_forward = True
            break
    if not any_forward:
        return False

    return True


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def _auto_cell_size_pc(
    bbox_min: Tuple[float, float, float],
    bbox_max: Tuple[float, float, float],
    n_objects: int,
) -> float:
    """Heuristic cell size: keep cells per axis between 2 and ~50.
    Aims for roughly N**(1/3) cells per axis, clamped."""
    extents = (
        bbox_max[0] - bbox_min[0],
        bbox_max[1] - bbox_min[1],
        bbox_max[2] - bbox_min[2],
    )
    longest = max(extents)
    if longest <= 0.0:
        return _MIN_CELL_SIZE_PC
    target_per_axis = max(2, min(50, round(n_objects ** (1 / 3))))
    return max(longest / float(target_per_axis), _MIN_CELL_SIZE_PC)


def _global_bbox(
    objects: Sequence[CatalogObject],
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    if not objects:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    bx_min = by_min = bz_min = math.inf
    bx_max = by_max = bz_max = -math.inf
    for obj in objects:
        pos = sf._position_pc(obj)
        if pos is None:
            continue
        bx_min = min(bx_min, pos[0])
        by_min = min(by_min, pos[1])
        bz_min = min(bz_min, pos[2])
        bx_max = max(bx_max, pos[0])
        by_max = max(by_max, pos[1])
        bz_max = max(bz_max, pos[2])
    if bx_min == math.inf:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    return (bx_min, by_min, bz_min), (bx_max, by_max, bz_max)


def _cell_dir_name(cell: Tuple[int, int, int]) -> str:
    return f"cell_{cell[0]}_{cell[1]}_{cell[2]}"


def _write_cell_chunks(
    output_dir: str,
    cell: Tuple[int, int, int],
    objects: Sequence[CatalogObject],
    chunk_size: int,
) -> List[str]:
    """Write the objects of one cell into one or more JSONL chunks.
    Returns the list of relative paths (relative to ``output_dir``)."""
    rel_dir = os.path.join("chunks", _cell_dir_name(cell))
    abs_dir = os.path.join(output_dir, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    rel_paths: List[str] = []
    n = max(1, chunk_size)
    for chunk_idx, start in enumerate(range(0, len(objects), n)):
        rel = os.path.join(rel_dir, f"chunk_{chunk_idx:02d}.jsonl")
        abs_path = os.path.join(output_dir, rel)
        write_catalog(
            objects[start:start + n], abs_path, fmt="jsonl",
            compute_derived=False,  # already populated above
        )
        rel_paths.append(rel.replace(os.sep, "/"))
    return rel_paths


def build_index(
    objects: Sequence[CatalogObject],
    output_dir: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    cell_size_pc: Optional[float] = None,
) -> SpatialIndex:
    """Bucket ``objects`` into a uniform grid, write per-cell JSONL
    chunks, and persist ``index.json`` to ``output_dir``.

    Returns the in-memory ``SpatialIndex``. Existing files in
    ``output_dir`` are not deleted; the index just adds / overwrites.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")

    objects = list(objects)
    n = len(objects)
    _log.info("Building spatial index for %d objects -> %s", n, output_dir)

    # Make sure every object has Cartesian coordinates we can read
    # without recomputing them inside the loop.
    for obj in objects:
        if (
            obj.cartesian_x is None
            or obj.cartesian_y is None
            or obj.cartesian_z is None
        ):
            try:
                compute_derived_fields(obj)
            except Exception:  # noqa: BLE001
                _log.warning("Skipping object with un-computable position: uid=%r",
                             getattr(obj, "uid", None))

    bbox_min, bbox_max = _global_bbox(objects)
    if cell_size_pc is None:
        cell_size_pc = _auto_cell_size_pc(bbox_min, bbox_max, n)
    if cell_size_pc <= 0.0:
        cell_size_pc = _MIN_CELL_SIZE_PC

    # Pad the grid origin so all cell indices are >= 0 and the max cell
    # contains the max bbox corner.
    grid_origin_pc = (
        bbox_min[0] - 1e-6,
        bbox_min[1] - 1e-6,
        bbox_min[2] - 1e-6,
    )

    # Bucket.
    buckets: dict = {}
    skipped = 0
    for obj in objects:
        pos = sf._position_pc(obj)
        if pos is None:
            skipped += 1
            continue
        cell = cell_index_for(pos, grid_origin_pc, cell_size_pc)
        buckets.setdefault(cell, []).append(obj)

    # Write chunks + collect cell metadata.
    cells: List[IndexCell] = []
    sources_seen: set = set()
    for cell, cell_objects in sorted(buckets.items()):
        rel_paths = _write_cell_chunks(
            output_dir, cell, cell_objects, chunk_size=chunk_size
        )
        bmin, bmax = cell_bbox(cell, grid_origin_pc, cell_size_pc)
        cells.append(IndexCell(
            cell=cell,
            bbox_min_pc=bmin,
            bbox_max_pc=bmax,
            chunk_paths=rel_paths,
            object_count=len(cell_objects),
        ))
        for obj in cell_objects:
            sources_seen.add(obj.catalog_source)

    index = SpatialIndex(
        schema_version=INDEX_SCHEMA_VERSION,
        cell_size_pc=float(cell_size_pc),
        chunk_size=int(chunk_size),
        grid_origin_pc=grid_origin_pc,
        bbox_min_pc=bbox_min,
        bbox_max_pc=bbox_max,
        total_objects=n - skipped,
        sources=sorted(sources_seen),
        cells=cells,
    )
    index.save(output_dir)
    if skipped:
        _log.warning("Skipped %d objects with no usable position.", skipped)
    return index


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def query_cells_intersecting_cone(
    index: SpatialIndex,
    origin_pc: Tuple[float, float, float],
    forward: Tuple[float, float, float],
    cone_half_angle_deg: float,
    near_pc: float = 0.0,
    far_pc: float = float("inf"),
) -> List[IndexCell]:
    """Return every cell whose AABB might overlap the navigator cone.

    Conservative (no false negatives). The exact rejection happens
    later inside ``apply_filter``.
    """
    out: List[IndexCell] = []
    for cell in index.cells:
        if aabb_intersects_cone(
            cell.bbox_min_pc, cell.bbox_max_pc,
            origin_pc, forward, cone_half_angle_deg,
            near_pc=near_pc, far_pc=far_pc,
        ):
            out.append(cell)
    return out


def _load_chunks_for_cells(
    index_dir: str, cells: Iterable[IndexCell],
) -> List[CatalogObject]:
    objects: List[CatalogObject] = []
    for cell in cells:
        for rel in cell.chunk_paths:
            abs_path = os.path.join(index_dir, rel)
            objects.extend(load_catalog(abs_path))
    return objects


def query_index(
    index_dir: str,
    origin_pc: Tuple[float, float, float],
    forward: Tuple[float, float, float],
    cone_half_angle_deg: float,
    near_pc: float = 0.0,
    far_pc: float = float("inf"),
    max_visible_objects: Optional[int] = None,
    selected_sources: Optional[Sequence[str]] = None,
    selected_types: Optional[Sequence[str]] = None,
    rank_by: str = "distance",
) -> Tuple[sf.FilterResult, dict]:
    """End-to-end query: load the index, intersect the cone with the
    grid, load only the surviving cells' chunks, and apply the exact
    filter.

    Returns ``(filter_result, query_meta)`` where ``query_meta`` is a
    small dict describing how much I/O the query did:

    ::

        {
          "candidate_cells": int,
          "total_cells":     int,
          "candidate_objects": int,
        }
    """
    index = SpatialIndex.load(index_dir)
    candidate_cells = query_cells_intersecting_cone(
        index, origin_pc, forward, cone_half_angle_deg,
        near_pc=near_pc, far_pc=far_pc,
    )
    candidates = _load_chunks_for_cells(index_dir, candidate_cells)
    result = sf.apply_filter(
        candidates,
        origin_pc=origin_pc,
        forward=forward,
        near_clip_pc=near_pc,
        far_clip_pc=far_pc,
        cone_half_angle_deg=cone_half_angle_deg,
        max_visible_objects=max_visible_objects,
        selected_sources=selected_sources,
        selected_types=selected_types,
        rank_by=rank_by,
    )
    meta = {
        "candidate_cells": len(candidate_cells),
        "total_cells": len(index.cells),
        "candidate_objects": len(candidates),
    }
    return result, meta
