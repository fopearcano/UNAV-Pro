#!/usr/bin/env python3
"""Fetch one solar-system body's position at one epoch from JPL Horizons.

Example::

    python tools/fetch_jpl_body.py \\
        --body "Mars" --epoch "2026-01-01" \\
        --output data/jpl_mars.jsonl

This is a preprocessing tool. It does not require Cinema 4D and does
not require credentials. The output is a UNAV-format JSONL file with
exactly one ``CatalogObject`` row.
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
from data.connectors.jpl_horizons_connector import (  # noqa: E402
    ALLOWED_OBJECT_TYPES,
    DEFAULT_CENTER,
    DEFAULT_OBJECT_TYPE,
    JPLBodyQuery,
    JPLHorizonsError,
    fetch_and_normalize,
)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Fetch one solar-system body's static position at one "
            "epoch from JPL Horizons and write a UNAV JSONL catalog."
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
                       "Use '@0' for Solar System Barycenter, '500@399' for "
                       "Earth geocentric."
                   ))
    p.add_argument("--object-type", default=DEFAULT_OBJECT_TYPE,
                   choices=ALLOWED_OBJECT_TYPES,
                   help=(
                       "UNAV object type tag for this body "
                       f"(default {DEFAULT_OBJECT_TYPE})."
                   ))
    p.add_argument("--quiet", action="store_true",
                   help="Suppress the summary line.")
    return p.parse_args(argv)


def main(argv=None) -> int:
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
        obj = fetch_and_normalize(query)
    except JPLHorizonsError as exc:
        print(f"error: Horizons query failed: {exc}", file=sys.stderr)
        return 3

    write_catalog([obj], args.output, fmt="jsonl")

    if not args.quiet:
        d = obj.distance_parsec or 0.0
        print(
            f"Wrote {args.body} @ {args.epoch} to {args.output} "
            f"(type={args.object_type}, ra={obj.ra_deg:.4f} deg, "
            f"dec={obj.dec_deg:.4f} deg, distance={d:.6g} pc)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
