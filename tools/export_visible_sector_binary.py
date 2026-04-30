#!/usr/bin/env python3
"""Export a UNAV catalog (or a navigator-filtered visible sector)
to the v0.8 binary visible-sector format the v0.9 native plugin
reads.

Two modes:

1. **Whole-catalog mode** (v0.8 default). Hand the CLI a JSONL or
   CSV catalog; every row is exported.

       python tools/export_visible_sector_binary.py \\
           --input data/catalogs/gaia_pleiades_sample.jsonl \\
           --output cache/binary/gaia_pleiades.unav

2. **Navigator-filtered mode** (v0.9). Hand the CLI an indexed
   dataset directory plus a navigator-state JSON (the same shape
   ``NavigationParams.to_dict()`` produces, plus a ``pose``
   block carrying the navigator's C4D world-space origin and
   forward vector). Only objects that pass the navigator's cone
   are exported.

       python tools/export_visible_sector_binary.py \\
           --dataset cache/gaia_pleiades \\
           --navigator-state navigator.json \\
           --output cache/visible_sector.bin

   The navigator-state JSON is::

       {
         "pose": {
           "origin_c4d": [0.0, 0.0, 0.0],
           "forward":    [0.0, 0.0, -1.0]
         },
         "params": { ...NavigationParams.to_dict()... }
       }

This is a preprocessing tool. It does not require Cinema 4D and
does not require credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional, Tuple


def _bootstrap_sys_path() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    plugin_root = os.path.join(repo_root, "unav_pro")
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)


_bootstrap_sys_path()

from core.logging_util import init_logging  # noqa: E402
from core.navigation_state import NavigationParams  # noqa: E402
from core.spatial_filter import c4d_units_to_pc  # noqa: E402
from core.spatial_index import query_index  # noqa: E402
from data.binary_export import (  # noqa: E402
    BinaryExportError, export_objects,
)
from data.catalog_io import CatalogIOError, load_catalog  # noqa: E402
from data.schema import (  # noqa: E402
    DEFAULT_SCALE_MODE, SCALE_MODES, CatalogObject,
    compute_derived_fields,
)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Export a UNAV catalog or navigator-filtered visible "
            "sector to the v0.8 binary format the v0.9 native "
            "plugin reads."
        ),
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--input",
                     help="Whole-catalog JSONL/CSV input.")
    src.add_argument("--dataset",
                     help=(
                         "Indexed dataset directory (output of "
                         "tools/build_spatial_index.py). Requires "
                         "--navigator-state."
                     ))
    p.add_argument("--navigator-state", default=None,
                   help=(
                       "Navigator state JSON (with 'pose' + 'params' "
                       "blocks). Required when --dataset is used."
                   ))
    p.add_argument("--output", required=True,
                   help="Output binary file path.")
    p.add_argument("--scale-mode", default=DEFAULT_SCALE_MODE,
                   choices=sorted(SCALE_MODES.keys()),
                   help=(
                       "C4D scale mode used to compute c4d_x/y/z "
                       "from cartesian_pc (default 'pc')."
                   ))
    p.add_argument("--sidecar-path", default="",
                   help=(
                       "Optional relative metadata sidecar path "
                       "embedded in the binary header. Empty == none."
                   ))
    p.add_argument("--max-points", type=int, default=0,
                   help=(
                       "Hard cap on points written. 0 = no cap; "
                       "non-zero clips after the navigator filter."
                   ))
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


def _load_navigator_state(path: str) -> Tuple[
    Tuple[float, float, float],
    Tuple[float, float, float],
    NavigationParams,
]:
    with open(path, "r", encoding="utf-8") as fh:
        d = json.load(fh)
    pose = d.get("pose") or {}
    origin = pose.get("origin_c4d") or [0.0, 0.0, 0.0]
    forward = pose.get("forward") or [0.0, 0.0, -1.0]
    if len(origin) != 3 or len(forward) != 3:
        raise ValueError(
            "navigator-state pose must carry 3-element origin_c4d "
            "and forward vectors"
        )
    params_dict = d.get("params") or {}
    params = NavigationParams.from_dict(params_dict).clamped()
    return (
        (float(origin[0]), float(origin[1]), float(origin[2])),
        (float(forward[0]), float(forward[1]), float(forward[2])),
        params,
    )


def _objects_for_dataset(
    dataset_dir: str,
    origin_c4d: Tuple[float, float, float],
    forward: Tuple[float, float, float],
    params: NavigationParams,
):
    """Stream a navigator-filtered subset out of an indexed dataset.

    Uses ``core.spatial_index.query_index`` (which already loads
    only the cells the cone touches and runs the exact-rejection
    filter) so the CLI behaves like the in-plugin Sync click.
    Returns the surviving ``CatalogObject`` list.
    """
    origin_pc = c4d_units_to_pc(origin_c4d, scale_mode=params.c4d_scale)
    sources = params.selected_catalog_sources or None
    if sources is not None and len(sources) == 0:
        sources = None
    result, _meta = query_index(
        dataset_dir,
        origin_pc=origin_pc,
        forward=forward,
        cone_half_angle_deg=float(params.cone_angle_deg),
        near_pc=float(params.near_clip_parsec),
        far_pc=float(params.far_clip_parsec),
        max_visible_objects=int(params.max_visible_objects) or None,
        selected_sources=sources,
    )
    objects = list(result.objects)
    for obj in objects:
        if obj.c4d_x is None or obj.c4d_y is None or obj.c4d_z is None:
            compute_derived_fields(obj, scale_mode=params.c4d_scale)
    return objects


def main(argv=None) -> int:
    """CLI entry point. Exit codes:

      * 0 — success.
      * 2 — invalid arguments / missing input.
      * 3 — export error.
    """
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    init_logging()

    if args.dataset and not args.navigator_state:
        print(
            "error: --dataset requires --navigator-state",
            file=sys.stderr,
        )
        return 2

    objects: list

    try:
        if args.input is not None:
            if not os.path.isfile(args.input):
                print(
                    f"error: input not found: {args.input}",
                    file=sys.stderr,
                )
                return 2
            objects = load_catalog(args.input)
        else:
            if not os.path.isdir(args.dataset):
                print(
                    f"error: dataset directory not found: {args.dataset}",
                    file=sys.stderr,
                )
                return 2
            if not os.path.isfile(args.navigator_state):
                print(
                    f"error: navigator-state not found: {args.navigator_state}",
                    file=sys.stderr,
                )
                return 2
            origin_c4d, forward, params = _load_navigator_state(
                args.navigator_state,
            )
            objects = _objects_for_dataset(
                args.dataset, origin_c4d, forward, params,
            )
    except (CatalogIOError, OSError, ValueError) as exc:
        print(f"error: could not assemble objects: {exc}", file=sys.stderr)
        return 3

    if args.max_points and len(objects) > args.max_points:
        objects = list(objects)[: int(args.max_points)]

    try:
        bytes_written, header, sources = export_objects(
            args.output, objects,
            scale_mode=args.scale_mode,
            sidecar_path=args.sidecar_path or "",
        )
    except (OSError, BinaryExportError) as exc:
        print(f"error: export failed: {exc}", file=sys.stderr)
        return 3

    if not args.quiet:
        src_label = (
            f"input={args.input}"
            if args.input is not None
            else f"dataset={args.dataset}"
        )
        print(
            f"Wrote {header.point_count} points "
            f"({header.source_count} source(s)) to {args.output} "
            f"({bytes_written} bytes, scale_mode={args.scale_mode}, "
            f"scale_factor={header.coordinate_scale_factor}); "
            f"{src_label}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
