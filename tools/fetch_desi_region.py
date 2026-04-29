#!/usr/bin/env python3
"""Fetch a small DESI sky region and write a UNAV JSONL catalog.

Example::

    python tools/fetch_desi_region.py \\
        --ra 180.0 --dec 30.0 --radius-deg 1.0 \\
        --limit 5000 --output data/desi_sample.jsonl

Stub status: hits the live NOIRLab Astro Data Lab TAP endpoint when
the network is available; tests cover the offline path with a
mocked fetcher.
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
from data.connectors.desi_connector import (  # noqa: E402
    DEFAULT_DESI_RELEASE,
    DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
    DESIQuery,
    DESIQueryError,
    fetch_and_normalize,
)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Fetch a small DESI EDR / DR1 sky region and write a "
            "UNAV JSONL catalog."
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
    p.add_argument("--release", default=DEFAULT_DESI_RELEASE,
                   choices=("desi_edr", "desi_dr1"),
                   help="DESI data release.")
    p.add_argument("--spectype", default=None,
                   choices=("GALAXY", "QSO", "STAR"),
                   help="Optional server-side filter on SPECTYPE.")
    p.add_argument("--output", required=True,
                   help="Output JSONL path.")
    p.add_argument("--redshift-max-z", type=float,
                   default=DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
                   help=(
                       "Max redshift for Hubble-law distance "
                       "(default 0.1). Above this, distance_parsec "
                       "stays None."
                   ))
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    init_logging()

    try:
        query = DESIQuery(
            ra_deg=args.ra,
            dec_deg=args.dec,
            radius_deg=args.radius_deg,
            limit=args.limit,
            release=args.release,
            spectype=args.spectype,
        )
    except ValueError as exc:
        print(f"error: invalid query: {exc}", file=sys.stderr)
        return 2

    try:
        objects = fetch_and_normalize(query, redshift_max_z=args.redshift_max_z)
    except DESIQueryError as exc:
        print(f"error: DESI archive query failed: {exc}", file=sys.stderr)
        return 3

    if not objects:
        print("warning: query returned 0 usable rows", file=sys.stderr)

    write_catalog(objects, args.output, fmt="jsonl")

    if not args.quiet:
        with_d = sum(1 for o in objects if o.distance_parsec is not None)
        print(
            f"Wrote {len(objects)} DESI rows to {args.output} "
            f"(release={query.release}, radius={query.radius_deg}°, "
            f"limit={query.limit}, spectype={query.spectype or '*'}; "
            f"{with_d} with Hubble-law distance)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
