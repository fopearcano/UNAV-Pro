#!/usr/bin/env python3
"""Fetch a Gaia DR3 sky region and write a UNAV JSONL catalog.

Example::

    python tools/fetch_gaia_region.py \\
        --ra 56.75 --dec 24.12 --radius-deg 1.0 \\
        --limit 5000 \\
        --output data/catalogs/gaia_pleiades_sample.jsonl \\
        --build-index cache/gaia_pleiades

This is a preprocessing tool. It does not require Cinema 4D to run
and never imports the C4D-bound parts of the plugin. The output is a
plain JSONL file readable by ``data.catalog_io.load_catalog``; with
``--build-index``, a chunked spatial index is also written next to
it.
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
from data.connectors.gaia_connector import (  # noqa: E402
    DEFAULT_GAIA_RELEASE,
    DEFAULT_PARALLAX_SNR_MIN,
    GaiaQuery,
    GaiaQueryError,
    fetch_normalize_and_write,
)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Fetch a Gaia DR3 sky region and write a UNAV-format "
            "JSONL catalog. Optionally build a chunked spatial index "
            "for sector-streaming."
        ),
    )
    p.add_argument("--ra", type=float, required=True,
                   help="Cone center, RA in degrees [0, 360).")
    p.add_argument("--dec", type=float, required=True,
                   help="Cone center, Dec in degrees [-90, 90].")
    p.add_argument("--radius-deg", type=float, required=True,
                   help="Cone radius in degrees (max 30).")
    p.add_argument("--limit", type=int, default=5_000,
                   help="Max rows to return (default 5000).")
    p.add_argument("--release", default=DEFAULT_GAIA_RELEASE,
                   choices=("gaia_dr3", "gaia_dr2"),
                   help="Gaia data release to query (default gaia_dr3).")
    p.add_argument("--output", required=True,
                   help="Output JSONL path. Parent directories are created.")
    p.add_argument("--build-index", dest="build_index", default=None,
                   help=(
                       "Optional output directory for a chunked spatial "
                       "index built from the fetched rows. When set, "
                       "the directory is created and ``index.json`` + "
                       "per-cell JSONL chunks are written there."
                   ))
    p.add_argument("--index-chunk-size", type=int, default=5_000,
                   help=(
                       "Max rows per index chunk file when --build-index "
                       "is used (default 5000)."
                   ))
    p.add_argument("--parallax-snr-min", type=float,
                   default=DEFAULT_PARALLAX_SNR_MIN,
                   help=(
                       "Minimum parallax/parallax_error required to "
                       "compute distance_parsec (default 5.0). Below "
                       "this, rows still flow through but distance "
                       "stays None."
                   ))
    p.add_argument("--no-parallax-cut", action="store_true",
                   help=(
                       "Disable the parallax SNR cut (compute distance "
                       "for any positive parallax)."
                   ))
    p.add_argument("--quiet", action="store_true",
                   help="Suppress the summary line on stdout.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    """CLI entry point. Exit codes:

      * 0 — success.
      * 2 — invalid arguments (out-of-range coordinates / radius /
        limit / unknown release).
      * 3 — Gaia archive query failed (network, HTTP, malformed
        response).
    """
    args = _parse_args(argv)
    init_logging()

    snr = 0.0 if args.no_parallax_cut else args.parallax_snr_min

    try:
        query = GaiaQuery(
            ra_deg=args.ra,
            dec_deg=args.dec,
            radius_deg=args.radius_deg,
            limit=args.limit,
            release=args.release,
        )
    except ValueError as exc:
        print(f"error: invalid query: {exc}", file=sys.stderr)
        return 2

    try:
        report = fetch_normalize_and_write(
            query, args.output,
            parallax_snr_min=snr,
            build_index_dir=args.build_index,
            index_chunk_size=args.index_chunk_size,
        )
    except GaiaQueryError as exc:
        print(f"error: Gaia archive query failed: {exc}", file=sys.stderr)
        return 3

    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if report.object_count == 0:
        print("warning: query returned 0 usable rows", file=sys.stderr)

    if not args.quiet:
        line = (
            f"Wrote {report.object_count} Gaia objects to "
            f"{report.output_path} (release={query.release}, "
            f"radius={query.radius_deg}°, limit={query.limit}; "
            f"{report.with_distance} with parallax-derived distance)."
        )
        if report.index_path is not None:
            line += (
                f" Built index at {report.index_path} — "
                f"{report.index_total_objects} objects in "
                f"{report.index_cell_count} cells."
            )
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
