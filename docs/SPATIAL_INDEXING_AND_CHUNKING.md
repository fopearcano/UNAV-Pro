# UNAV Pro — Spatial Indexing and Chunking

How UNAV Pro stays usable as catalogs grow from 100 to millions of
rows: by never loading the whole catalog, by partitioning it into
small on-disk **chunks**, and by querying only the chunks whose
bounding cells could possibly intersect the navigator's view cone.

Companion to:

  * `UNAV_PRO_DATA_PIPELINE.md` §8 (production HEALPix tiling).
  * `RAY_CONE_FILTERING.md` (the exact filter that runs after
    indexing).
  * `POINT_CLOUD_GENERATION.md` (the consumer of filtered points).

---

## 1. Why a spatial index at all

The Cinema 4D scene must only ever contain the **current view sector**
— the small subset of catalog objects that the navigator can
plausibly see. Three reasons that drive every design choice in this
module:

  * **C4D file size.** A `.c4d` containing one million nulls is a
    crash on save and a multi-second redraw on load.
  * **Viewport latency.** Even at MVP scales, every additional
    ``BaseObject`` adds GIL-bound Python work to selection, undo,
    and viewport refresh.
  * **Memory.** Loading a 1.8 B-row Gaia subset into a Python list is
    not a feature; it is an out-of-memory error.

The spatial index is the gate that makes all three problems
manageable. It provides O(active-cells) read cost, where
``active-cells`` is bounded by the size of the cone, not the size of
the catalog.

---

## 2. Design at a glance

Implementation: `unav_pro/core/spatial_index.py`.

  * **Grid.** A uniform cubic grid in parsec-Cartesian space.
    Cell size is either auto-chosen from the global bbox + object
    count or set explicitly via the CLI's ``--cell-size-pc``.
  * **Bucket.** Each object lands in exactly one cell, computed by
    ``cell_index_for(point_pc, grid_origin, cell_size)``.
  * **Chunk.** Each non-empty cell is written to one or more JSONL
    files of at most ``chunk_size`` rows. Chunks live under
    ``chunks/cell_<i>_<j>_<k>/chunk_NN.jsonl``.
  * **Manifest.** ``index.json`` collects per-cell metadata:
    ``(i, j, k)``, the cell's AABB, ``object_count``, and the
    relative paths of its chunks.

Queries:

  1. ``query_cells_intersecting_cone`` walks ``index.cells``, applies
     ``aabb_intersects_cone`` (a conservative AABB-vs-cone test), and
     returns the surviving cells.
  2. ``_load_chunks_for_cells`` reads only those cells' JSONL files.
  3. ``apply_filter`` (from ``spatial_filter.py``) does the exact
     per-object rejection.

Total I/O per query is bounded by the cone size, not the catalog
size.

---

## 3. The cone-vs-AABB gate

`aabb_intersects_cone` is intentionally conservative: it must produce
**no false negatives**. False positives are caught by the exact
filter that runs afterward and cost only a small amount of extra work
on already-loaded chunks.

Tests applied, in cheap-to-expensive order:

  1. **Closest distance from origin to AABB > far_clip** → reject.
  2. **Farthest distance from origin to AABB < near_clip** → reject.
  3. **All eight corners project ≤ 0 onto forward axis** → reject
     (entire AABB lies in the rear hemisphere).
  4. Otherwise → accept.

The sphere-vs-cone "lateral angle" tightening is intentionally not
implemented in the MVP — the exact filter handles cone-angle
rejection for free, and the AABB extent makes a tight lateral test
non-trivial near the apex. This is documented as a future tightening
in the migration plan below.

---

## 4. On-disk layout

```
<cache>/
  index.json
  chunks/
    cell_-3_2_0/
      chunk_00.jsonl
      chunk_01.jsonl
    cell_-3_2_1/
      chunk_00.jsonl
    ...
```

Properties of this layout:

  * **Inspectable.** Any chunk is a normal JSONL file; ``cat`` works.
  * **Portable.** All paths in ``index.json`` are relative — the
    cache can be moved or copied.
  * **Resumable.** A failed build leaves valid partial chunks; a
    rerun overwrites them.
  * **Stable.** Cell directory names embed the integer grid
    coordinates, so the same object lands in the same path on every
    rebuild for a fixed ``cell_size_pc`` and ``grid_origin_pc``.

`index.json` schema (v1):

```json
{
  "schema_version": 1,
  "cell_size_pc": 5.0,
  "chunk_size": 5000,
  "grid_origin_pc": [-100.0, -100.0, -100.0],
  "bbox_min_pc": [-99.5, -99.5, -99.5],
  "bbox_max_pc": [ 99.5,  99.5,  99.5],
  "total_objects": 1234567,
  "sources": ["unav_sample", "gaia_dr3"],
  "cells": [
    {
      "cell": [0, 1, 2],
      "bbox_min_pc": [...],
      "bbox_max_pc": [...],
      "chunk_paths": ["chunks/cell_0_1_2/chunk_00.jsonl"],
      "object_count": 4231
    },
    ...
  ]
}
```

---

## 5. Building the index — the CLI

`tools/build_spatial_index.py` runs without Cinema 4D. It is the
preprocessing tool that artists or pipeline scripts call once per
release:

```bash
python tools/build_spatial_index.py \
    --input  unav_pro/data/samples/sample_catalog_100.jsonl \
    --output cache \
    --chunk-size 5000
```

Flags:

| Flag                | Default              | Notes                                                       |
|---------------------|----------------------|-------------------------------------------------------------|
| `--input`           | required             | A UNAV catalog JSONL or CSV file.                           |
| `--output`          | required             | Output directory; `index.json` and `chunks/` go here.       |
| `--chunk-size`      | 5000                 | Max rows per JSONL chunk.                                   |
| `--cell-size-pc`    | auto from bbox + N   | Override the auto-chosen cell size, in parsec.              |
| `--quiet`           | off                  | Suppress the build summary line.                            |

The same call signature drives the in-process Python API:
``core.spatial_index.build_index(objects, output_dir, ...)``.

---

## 6. Why the C4D scene must contain only the current view-sector

Even with an index, materializing 1 M nulls in C4D is not viable
(see `POINT_CLOUD_GENERATION.md` §2). The index lets the plugin
keep that constraint *honest*: at any moment the active document
contains only the points that survived the navigator's filter, plus
the navigator hierarchy and the catalog references.

The "view sector" is defined by the navigator's pose plus its filter
parameters:

  * `near_clip_parsec` / `far_clip_parsec` bound the distance shell.
  * `cone_angle_deg` bounds the angular extent.
  * `max_visible_objects` bounds the per-rebuild cardinality.

Changing any of these parameters and clicking **Regenerate Visible
Field** runs the index query, swaps the starfield, and the user is
back in business — without ever touching the parts of the catalog
that fall outside the new view sector. This is what makes a 1 M-row
Gaia subset workable inside Cinema 4D on a laptop.

---

## 7. Known limitations of the MVP grid

These are deliberate trade-offs, not bugs:

  * **Uniform grid.** Catalogs are not uniformly distributed; cells
    in the galactic plane will vastly outweigh polar cells. A
    HEALPix-based sky tiling (production plan,
    `UNAV_PRO_DATA_PIPELINE.md` §8) handles that without an artist
    seeing it.
  * **No distance shells.** Point distributions span 11 orders of
    magnitude (sub-parsec stars to gigaparsec quasars). A single
    cubic cell size cannot be optimal for both ends; the production
    index combines HEALPix sky cells with log-spaced distance
    shells.
  * **No LOD.** Each cell stores full-precision rows. The production
    plan writes multiple decimations per tile (L0/L1/L2/L3); the
    plugin picks the coarsest level that meets a per-pixel density
    target.
  * **JSONL only.** Text format makes builds slow at large scale and
    skips columnar predicate pushdown. The migration plan in §8
    addresses this.
  * **Single-threaded build.** ``build_index`` is a serial Python
    loop. Acceptable for ≤ 1 M rows; production runs need parallel
    bucket-and-write.

The architecture, however, does not need to change to fix any of
these. The query API is ``query_index(index_dir, origin_pc, forward,
…) → (FilterResult, meta)``; everything below it is a swappable
backend.

---

## 8. Future migration: storage backends

The same ``query_index`` surface above will fit any of the following:

  * **SQLite (catalog manifest + small metadata).** Already on the
    roadmap for the production cache (see
    `UNAV_PRO_DATA_PIPELINE.md` §3.3). Index gets a transactional
    manifest; chunks remain on disk but the lookup table is queryable
    by SQL.
  * **DuckDB (analytics queries on the cache).** Lets pipeline tools
    run ad-hoc SELECTs (counts per source, per shell, per object
    type) without touching Python. DuckDB reads Parquet directly.
  * **Parquet (production columnar tiles).** Columnar compression,
    predicate pushdown (`WHERE distance_pc < far_clip` reads only
    the rows whose row-group statistics overlap the filter), and
    zero-copy mmap into numpy via ``pyarrow``. This is the canonical
    production format from `UNAV_PRO_DATA_PIPELINE.md`.
  * **HDF5 (large dense scientific arrays).** Useful when a future
    UNAV variant ingests image cubes / spectra rather than sparse
    point catalogs. Same query surface; different backend.
  * **Custom binary (engine-internal, packed).** A flat
    ``uid[u64], x[f32], y[f32], z[f32], color[u32], size[f16]``
    buffer mmap-ready for direct draw. The engine protocol from
    `UNAV_PRO_ARCHITECTURE.md` §3.10 already returns this shape;
    moving the index to write it directly skips the JSONL parse step
    on every query.

The migration sequence will be: JSONL → Parquet (production tiles)
→ SQLite manifest + Parquet (with HEALPix tiling) → optional
mmap-friendly binary for the hottest cells. Each step preserves
``query_index``'s signature.

---

## 9. Future migration: native and GPU rendering

The Python prototype is a deliberate floor. Once measured profiles
demand it, the rendering path migrates as described in
`UNAV_PRO_ARCHITECTURE.md` §5 and
`POINT_CLOUD_GENERATION.md` §3:

  1. **Native AABB-vs-cone kernel.** A pybind11 / Maxon SDK module
     reads ``index.json``, runs the gate over all cells in C++ with
     SIMD, and returns the candidate set. The Python orchestration
     stays.
  2. **Native chunk loader.** Replace ``load_catalog`` with a
     mmap-backed Parquet/binary reader. Removes the JSON parse from
     the per-query critical path.
  3. **Native point-buffer assembly.** Pack survivors into a SoA
     buffer ``uid[u64], xyz[f32×3], color[u32], size[f16]`` directly
     in C++.
  4. **GPU compute for cone/frustum tests.** CUDA / Metal / Vulkan
     compute kernels run the AABB and per-point tests in parallel;
     the buffer is uploaded once per query and survives multiple
     refinements (e.g. dragging the navigator).

None of these changes the plugin's UI, its scene model, or the index
manifest format. They replace pieces of one query path.

---

## 10. Test coverage

`unav_pro/tests/test_spatial_index.py` covers:

  * Cell math — `cell_index_for`, `cell_bbox`, zero-size error.
  * AABB-vs-cone gate — inside far-clip, too far, too close,
    entirely behind, partially in front, full-sphere disable.
  * Build pipeline — chunk + metadata creation, chunk-size
    enforcement, source list collection, single-object (degenerate
    bbox) safety, bad-chunk-size error.
  * Manifest round-trip — `SpatialIndex.save` / `.load`,
    missing-file error.
  * Query — cone correctly excludes back-cluster, candidate count is
    bounded, `max_visible_objects` cap respected, far-cluster cells
    contribute zero I/O when the cone excludes them.
