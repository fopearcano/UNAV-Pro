#!/usr/bin/env python3
"""Build a UNAV spatial index from a local catalog.

Usage::

    python tools/build_spatial_index.py \\
        --input  unav_pro/data/samples/sample_catalog_100.jsonl \\
        --output cache \\
        --chunk-size 5000

The script bootstraps the plugin's ``unav_pro/`` directory onto
``sys.path`` so it runs without the plugin being installed into
Cinema 4D — preprocessing tools must work on a render farm or a
plain Python venv.
"""

from __future__ import annotations

import argparse
import os
import sys


def _bootstrap_sys_path() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    plugin_root = os.path.join(repo_root, "unav_pro")
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)


_bootstrap_sys_path()

from core.logging_util import init_logging  # noqa: E402
from core.spatial_index import (  # noqa: E402
    DEFAULT_CHUNK_SIZE,
    build_index,
)
from data.catalog_io import CatalogIOError, load_catalog  # noqa: E402


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build a chunked spatial index from a UNAV catalog.",
    )
    p.add_argument(
        "--input", required=True,
        help="Path to a JSONL or CSV UNAV catalog file.",
    )
    p.add_argument(
        "--output", required=True,
        help="Output directory; ``index.json`` and ``chunks/`` are written here.",
    )
    p.add_argument(
        "--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
        help=f"Max rows per JSONL chunk file (default: {DEFAULT_CHUNK_SIZE}).",
    )
    p.add_argument(
        "--cell-size-pc", type=float, default=None,
        help="Override the auto-chosen grid cell size, in parsec.",
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="Suppress the build summary line.",
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    init_logging()

    if not os.path.isfile(args.input):
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 2

    try:
        objects = load_catalog(args.input)
    except CatalogIOError as exc:
        print(f"error: could not load catalog: {exc}", file=sys.stderr)
        return 2

    if not objects:
        print("error: catalog is empty", file=sys.stderr)
        return 2

    index = build_index(
        objects,
        output_dir=args.output,
        chunk_size=args.chunk_size,
        cell_size_pc=args.cell_size_pc,
    )

    if not args.quiet:
        print(
            f"Indexed {index.total_objects} objects into "
            f"{len(index.cells)} cells "
            f"(cell size {index.cell_size_pc:.3g} pc, "
            f"chunk size {index.chunk_size}). "
            f"Wrote {os.path.join(args.output, 'index.json')}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
