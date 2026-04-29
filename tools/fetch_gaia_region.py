#!/usr/bin/env python3
"""Fetch a small Gaia sky region and write a UNAV JSONL catalog.

Example::

    python tools/fetch_gaia_region.py \\
        --ra 56.75 --dec 24.12 --radius-deg 1.0 \\
        --limit 5000 --output data/gaia_sample.jsonl

This is a preprocessing tool. It does not require Cinema 4D to run
and never imports the C4D-bound parts of the plugin. The output is a
plain JSONL file readable by ``data.catalog_io.load_catalog``.
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
from data.catalog_io import write_catalog  # noqa: E402
from data.connectors.gaia_connector import (  # noqa: E402
    DEFAULT_GAIA_RELEASE,
    DEFAULT_PARALLAX_SNR_MIN,
    GaiaQuery,
    GaiaQueryError,
    fetch_and_normalize,
)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Fetch a small Gaia sky region and write a UNAV-format "
            "JSONL catalog."
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
                   help="Gaia data release to query.")
    p.add_argument("--output", required=True,
                   help="Output JSONL path.")
    p.add_argument("--parallax-snr-min", type=float,
                   default=DEFAULT_PARALLAX_SNR_MIN,
                   help=(
                       "Minimum parallax/parallax_error required to "
                       "compute distance (default 5.0). Below this, "
                       "rows still flow through but distance_parsec "
                       "stays None."
                   ))
    p.add_argument("--no-parallax-cut", action="store_true",
                   help=(
                       "Disable the parallax SNR cut (compute "
                       "distance for any positive parallax)."
                   ))
    p.add_argument("--quiet", action="store_true",
                   help="Suppress the summary line on stdout.")
    return p.parse_args(argv)


def main(argv=None) -> int:
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
        objects = fetch_and_normalize(query, parallax_snr_min=snr)
    except GaiaQueryError as exc:
        print(f"error: Gaia archive query failed: {exc}", file=sys.stderr)
        return 3

    if not objects:
        print("warning: query returned 0 usable rows", file=sys.stderr)

    write_catalog(objects, args.output, fmt="jsonl")

    if not args.quiet:
        with_distance = sum(1 for o in objects if o.distance_parsec is not None)
        print(
            f"Wrote {len(objects)} Gaia objects to {args.output} "
            f"(release={query.release}, "
            f"radius={query.radius_deg}°, limit={query.limit}; "
            f"{with_distance} with parallax-derived distance)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
