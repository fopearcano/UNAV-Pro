#!/usr/bin/env python3
"""Fetch a list of solar-system bodies at one epoch from JPL Horizons.

Example::

    python tools/fetch_jpl_solar_system.py \\
        --epoch "2026-01-01T00:00:00" \\
        --bodies "Mercury,Venus,Earth,Mars,Jupiter,Saturn,Uranus,Neptune,Pluto,Moon" \\
        --center "500@10" \\
        --output data/catalogs/jpl_solar_system_2026.jsonl \\
        --build-index cache/jpl_solar_system_2026

Per-body type tagging is supported via ``name=type`` syntax inside
``--bodies``::

    --bodies "Mercury,Venus,Earth,Mars,Jupiter,Moon=moon,Voyager 1=spacecraft"

Bodies without an explicit ``=type`` suffix get the
``--default-object-type`` (``planet`` by default).

This is a preprocessing tool. It does not require Cinema 4D and does
not require credentials. Per-body fetch failures are recorded in the
output summary; the rest of the batch still flows through.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List


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
    BatchBodyRequest,
    DEFAULT_CENTER,
    DEFAULT_OBJECT_TYPE,
    fetch_batch_normalize_and_write,
)


def _parse_bodies(spec: str, default_type: str) -> List[BatchBodyRequest]:
    """Parse the ``--bodies`` string into ``BatchBodyRequest``s.

    Format: comma-separated body designations, each optionally
    followed by ``=type`` to override the default object_type.
    Whitespace around tokens is stripped; empty entries are
    dropped silently.
    """
    out: List[BatchBodyRequest] = []
    for raw in (spec or "").split(","):
        token = raw.strip()
        if not token:
            continue
        if "=" in token:
            body, _, otype = token.partition("=")
            body = body.strip()
            otype = otype.strip().lower()
        else:
            body, otype = token, default_type
        if not body:
            continue
        if otype not in ALLOWED_OBJECT_TYPES:
            raise argparse.ArgumentTypeError(
                f"object_type '{otype}' (for body '{body}') not in "
                f"{ALLOWED_OBJECT_TYPES}"
            )
        out.append(BatchBodyRequest(body=body, object_type=otype))
    return out


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Fetch a list of solar-system bodies at one epoch from "
            "JPL Horizons and write a UNAV JSONL catalog. Per-body "
            "failures are recorded but do not abort the batch. "
            "Optionally build a chunked spatial index inline."
        ),
    )
    p.add_argument("--epoch", required=True,
                   help="Epoch as ISO date / time (any Horizons-accepted format).")
    p.add_argument("--bodies", required=True,
                   help=(
                       "Comma-separated body designations. Each may "
                       "carry an optional '=type' suffix "
                       f"({'/'.join(ALLOWED_OBJECT_TYPES)}). Bodies "
                       "without a suffix use --default-object-type."
                   ))
    p.add_argument("--default-object-type", default=DEFAULT_OBJECT_TYPE,
                   choices=ALLOWED_OBJECT_TYPES,
                   help=(
                       f"Default object_type for bodies without an "
                       f"explicit suffix (default {DEFAULT_OBJECT_TYPE})."
                   ))
    p.add_argument("--center", default=DEFAULT_CENTER,
                   help=(
                       f"Observer center (default {DEFAULT_CENTER} == Sun)."
                   ))
    p.add_argument("--output", required=True, help="Output JSONL path.")
    p.add_argument("--build-index", dest="build_index", default=None,
                   help=(
                       "Optional output directory for a chunked spatial "
                       "index built from the fetched rows."
                   ))
    p.add_argument("--index-chunk-size", type=int, default=1_000,
                   help="Max rows per index chunk file (default 1000).")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress the summary line.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    """CLI entry point. Exit codes:

      * 0 — success (even if some bodies failed; the rest were
        written and a per-body error list is printed on stderr).
      * 2 — invalid arguments.
      * 3 — every body failed.
    """
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        # argparse exits with code 2 on parse error; surface that.
        return int(exc.code) if exc.code is not None else 2

    init_logging()

    try:
        requests = _parse_bodies(args.bodies, args.default_object_type)
    except argparse.ArgumentTypeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not requests:
        print("error: --bodies parsed to an empty list", file=sys.stderr)
        return 2

    report = fetch_batch_normalize_and_write(
        requests, args.epoch, args.output,
        center=args.center,
        build_index_dir=args.build_index,
        index_chunk_size=args.index_chunk_size,
    )

    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for body, msg in report.errors:
        print(f"error: {body}: {msg}", file=sys.stderr)

    if report.object_count == 0:
        print(
            "error: every body failed; see per-body errors above",
            file=sys.stderr,
        )
        return 3

    if not args.quiet:
        line = (
            f"Wrote {report.object_count} bodies "
            f"(of {len(requests)} requested; {report.failed} failed) "
            f"to {report.output_path} "
            f"(epoch={args.epoch}, center={args.center})."
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
