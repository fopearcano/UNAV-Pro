#!/usr/bin/env python3
"""Fetch one solar-system body's position at one epoch from JPL Horizons.

Example::

    python tools/fetch_jpl_body.py \\
        --body "Mars" \\
        --epoch "2026-01-01T00:00:00" \\
        --center "500@10" \\
        --output data/catalogs/jpl_mars_2026.jsonl \\
        --build-index cache/jpl_mars_2026

This is a preprocessing tool. It does not require Cinema 4D and does
not require credentials. The output is a UNAV-format JSONL file with
exactly one ``CatalogObject`` row; with ``--build-index``, a chunked
spatial index is written next to it.
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
from data.connectors.jpl_horizons_connector import (  # noqa: E402
    ALLOWED_OBJECT_TYPES,
    DEFAULT_CENTER,
    DEFAULT_OBJECT_TYPE,
    JPLBodyQuery,
    JPLHorizonsError,
    fetch_single_normalize_and_write,
)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Fetch one solar-system body's static position at one "
            "epoch from JPL Horizons and write a UNAV JSONL catalog. "
            "Optionally build a chunked spatial index inline."
        ),
    )
    p.add_argument("--body", required=True,
                   help=(
                       "Body designation (e.g. 'Mars', 'Europa', "
                       "'Ceres', 'Voyager 1', or a NAIF ID like 499)."
                   ))
    p.add_argument("--epoch", required=True,
                   help="Epoch as ISO date or any Horizons-accepted format.")
    p.add_argument("--output", required=True,
                   help="Output JSONL path.")
    p.add_argument("--center", default=DEFAULT_CENTER,
                   help=(
                       f"Observer center (default {DEFAULT_CENTER} == Sun). "
                       "Use '@0' for Solar System Barycenter, '500@399' "
                       "for Earth geocentric, '500@10' for Sun."
                   ))
    p.add_argument("--object-type", default=DEFAULT_OBJECT_TYPE,
                   choices=ALLOWED_OBJECT_TYPES,
                   help=(
                       "UNAV object type tag for this body "
                       f"(default {DEFAULT_OBJECT_TYPE})."
                   ))
    p.add_argument("--build-index", dest="build_index", default=None,
                   help=(
                       "Optional output directory for a chunked spatial "
                       "index built from the fetched row(s)."
                   ))
    p.add_argument("--index-chunk-size", type=int, default=1_000,
                   help="Max rows per index chunk file (default 1000).")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress the summary line.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    """CLI entry point. Exit codes:

      * 0 — success.
      * 2 — invalid arguments.
      * 3 — Horizons archive query failed.
    """
    args = _parse_args(argv)
    init_logging()

    try:
        query = JPLBodyQuery(
            body=args.body,
            epoch=args.epoch,
            center=args.center,
            object_type=args.object_type,
        )
    except ValueError as exc:
        print(f"error: invalid query: {exc}", file=sys.stderr)
        return 2

    try:
        report = fetch_single_normalize_and_write(
            query, args.output,
            build_index_dir=args.build_index,
            index_chunk_size=args.index_chunk_size,
        )
    except JPLHorizonsError as exc:
        print(f"error: Horizons query failed: {exc}", file=sys.stderr)
        return 3

    if not args.quiet:
        line = (
            f"Wrote {args.body} @ {args.epoch} to {report.output_path} "
            f"(type={args.object_type}, center={args.center})."
        )
        if report.index_path is not None:
            line += (
                f" Built index at {report.index_path} — "
                f"{report.index_total_objects} object(s) in "
                f"{report.index_cell_count} cell(s)."
            )
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
