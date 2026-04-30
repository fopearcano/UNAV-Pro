#!/usr/bin/env python3
"""Fetch a small SDSS sky region and write a UNAV JSONL catalog.

Example::

    python tools/fetch_sdss_region.py \\
        --ra 180.0 --dec 0.0 --radius-deg 0.5 \\
        --limit 5000 \\
        --output data/catalogs/sdss_region_sample.jsonl \\
        --build-index cache/sdss_region_sample

This is a preprocessing tool. It does not require Cinema 4D and does
not require credentials. The chunked spatial index is built inline
when ``--build-index`` is supplied.
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
from data.connectors.sdss_connector import (  # noqa: E402
    DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
    DEFAULT_SDSS_RELEASE,
    SDSSQuery,
    SDSSQueryError,
    fetch_normalize_and_write,
)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Fetch a small SDSS sky region (PhotoObj + optional "
            "SpecObj redshift join) and write a UNAV JSONL catalog. "
            "Optionally build a chunked spatial index inline."
        ),
    )
    p.add_argument("--ra", type=float, required=True,
                   help="Cone center, RA in degrees [0, 360).")
    p.add_argument("--dec", type=float, required=True,
                   help="Cone center, Dec in degrees [-90, 90].")
    p.add_argument("--radius-deg", type=float, required=True,
                   help="Cone radius in degrees (max 30).")
    p.add_argument("--limit", type=int, default=5_000,
                   help="Max rows (default 5000).")
    p.add_argument("--release", default=DEFAULT_SDSS_RELEASE,
                   choices=("sdss_dr18", "sdss_dr17"),
                   help="SDSS data release.")
    p.add_argument("--output", required=True,
                   help="Output JSONL path.")
    p.add_argument("--no-spectro", action="store_true",
                   help="Skip the SpecObj join (photometry only).")
    p.add_argument("--build-index", dest="build_index", default=None,
                   help=(
                       "Optional output directory for a chunked spatial "
                       "index built from the fetched rows."
                   ))
    p.add_argument("--index-chunk-size", type=int, default=5_000,
                   help="Max rows per index chunk file (default 5000).")
    p.add_argument("--redshift-max-z", type=float,
                   default=DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
                   help=(
                       "Max redshift for the linear Hubble proxy "
                       "(default 0.1). Above this, distance_parsec "
                       "stays None and metadata_json is not stamped."
                   ))
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    """CLI entry point. Exit codes:

      * 0 — success (rows may be 0; a warning prints on stderr).
      * 2 — invalid arguments.
      * 3 — archive query failed.
    """
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    init_logging()

    try:
        query = SDSSQuery(
            ra_deg=args.ra,
            dec_deg=args.dec,
            radius_deg=args.radius_deg,
            limit=args.limit,
            release=args.release,
            include_spectro=not args.no_spectro,
        )
    except ValueError as exc:
        print(f"error: invalid query: {exc}", file=sys.stderr)
        return 2

    try:
        report = fetch_normalize_and_write(
            query, args.output,
            redshift_max_z=args.redshift_max_z,
            build_index_dir=args.build_index,
            index_chunk_size=args.index_chunk_size,
        )
    except SDSSQueryError as exc:
        print(f"error: SDSS archive query failed: {exc}", file=sys.stderr)
        return 3

    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if not args.quiet:
        line = (
            f"Wrote {report.object_count} SDSS rows to "
            f"{report.output_path} (release={query.release}, "
            f"radius={query.radius_deg}°, limit={query.limit}; "
            f"{report.with_redshift} with redshift, "
            f"{report.with_proxy_distance} with Hubble-proxy distance)."
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
