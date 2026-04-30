#!/usr/bin/env python3
"""Fetch solar-system bodies from JPL Horizons.

Two modes:

1. **Single epoch** (v0.4): one snapshot per body.

   ``python tools/fetch_jpl_solar_system.py \\
       --epoch "2026-01-01T00:00:00" \\
       --bodies "Mercury,Venus,Earth,Mars,Jupiter,Saturn,Uranus,Neptune,Pluto,Moon" \\
       --center "500@10" \\
       --output data/catalogs/jpl_solar_system_2026.jsonl``

2. **Time series** (v1.2): multi-epoch sweep, one row per (body,
   epoch). Useful for the time-navigator workflow — every JPL
   body lands as a series of ``ephemeris`` rows in the v1.2
   ``object_states`` table.

   ``python tools/fetch_jpl_solar_system.py \\
       --start "2026-01-01T00:00:00" \\
       --end "2026-12-31T00:00:00" \\
       --step-days 7 \\
       --bodies "Mercury,Venus,Earth,Mars" \\
       --output data/catalogs/jpl_solar_system_2026_timeseries.jsonl \\
       --db data/unav.db``

The ``--db`` sink (v1.2) imports each (body, epoch) row into the
SQLite DB's ``objects`` + ``object_states`` (``state_type =
'ephemeris'``) tables alongside the JSONL output. It is in
addition to ``--output``; both are independent.

Per-body type tagging via the ``name=type`` syntax inside
``--bodies`` continues to work::

    --bodies "Mercury,Venus,Earth,Mars,Jupiter,Moon=moon,Voyager 1=spacecraft"

Bodies without an explicit ``=type`` suffix get the
``--default-object-type`` (``planet`` by default).

This is a preprocessing tool. It does not require Cinema 4D and
does not require credentials. Per-body fetch failures are
recorded in the output summary; the rest of the batch still
flows through.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional


def _bootstrap_sys_path() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    plugin_root = os.path.join(repo_root, "unav_pro")
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)


_bootstrap_sys_path()

from core.logging_util import init_logging  # noqa: E402
from core.time_model import (  # noqa: E402
    DAYS_PER_JULIAN_YEAR, Epoch, iso_to_julian_date, julian_date_to_iso,
)
from data.catalog_io import write_catalog  # noqa: E402
from data.connectors.jpl_horizons_connector import (  # noqa: E402
    ALLOWED_OBJECT_TYPES,
    BatchBodyRequest,
    DEFAULT_CENTER,
    DEFAULT_OBJECT_TYPE,
    fetch_batch_and_normalize,
    fetch_batch_normalize_and_write,
)


def _parse_bodies(spec: str, default_type: str) -> List[BatchBodyRequest]:
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
            "Fetch a list of solar-system bodies from JPL Horizons. "
            "Single-epoch (--epoch) or time-series "
            "(--start / --end / --step-days)."
        ),
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--epoch", default=None,
                      help="Single epoch (ISO datetime). Mutually exclusive with --start/--end.")
    mode.add_argument("--start", default=None,
                      help="Time-series start epoch (ISO datetime). Requires --end and --step-days.")
    p.add_argument("--end", default=None,
                   help="Time-series end epoch (ISO datetime).")
    p.add_argument("--step-days", type=float, default=None,
                   help="Time-series step in days (e.g. 1, 7, 30).")
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
                   help=f"Observer center (default {DEFAULT_CENTER} == Sun).")
    p.add_argument("--output", required=True, help="Output JSONL path.")
    p.add_argument("--build-index", dest="build_index", default=None,
                   help="Optional output directory for a chunked spatial index.")
    p.add_argument("--index-chunk-size", type=int, default=1_000,
                   help="Max rows per index chunk file (default 1000).")
    p.add_argument("--db", dest="db_path", default=None,
                   help=(
                       "v1.2: SQLite DB to populate with object_states "
                       "rows (state_type='ephemeris'). The DB is "
                       "created with the v1.2 schema if missing."
                   ))
    p.add_argument("--max-epochs", type=int, default=400,
                   help=(
                       "Hard cap on time-series epoch count. Above "
                       "this the CLI refuses (avoids accidental "
                       "many-thousand-call sweeps)."
                   ))
    p.add_argument("--quiet", action="store_true", help="Suppress the summary line.")
    return p.parse_args(argv)


def _validate_time_series(args) -> Optional[str]:
    if args.epoch is not None:
        if args.end is not None or args.step_days is not None:
            return "use --epoch alone or --start/--end/--step-days; not both"
        return None
    if args.end is None or args.step_days is None:
        return "--start requires --end and --step-days"
    if args.step_days <= 0:
        return "--step-days must be > 0"
    return None


def _build_epoch_list(args) -> List[Epoch]:
    if args.epoch is not None:
        return [Epoch.from_iso(args.epoch)]
    start = Epoch.from_iso(args.start)
    end = Epoch.from_iso(args.end)
    if end.jd < start.jd:
        raise ValueError("--end is before --start")
    step = float(args.step_days)
    out: List[Epoch] = []
    current = start.jd
    while current <= end.jd + 1e-9:
        out.append(Epoch.from_jd(current))
        current += step
        if len(out) > args.max_epochs:
            raise ValueError(
                f"refused to build more than {args.max_epochs} epochs; "
                "lower the range or raise --max-epochs"
            )
    return out


def _persist_to_db(
    db_path: str,
    objects: list,
    epochs_jd: list,
) -> None:
    """Insert a (body, epoch) batch into the DB. Each object gets an
    ``object_states`` row of ``state_type='ephemeris'`` keyed by the
    body's uid + epoch."""
    from db.db_manager import (
        DBManager, ObjectState, STATE_TYPE_EPHEMERIS,
    )
    with DBManager(db_path) as db:
        db.apply_schema()
        # Upsert the objects rows. The uid is already epoch-aware
        # (jpl:body:iso_epoch) so duplicates are impossible across
        # epochs.
        db.insert_objects(objects, replace=True)
        states = []
        for obj, epoch_jd in zip(objects, epochs_jd):
            states.append(ObjectState(
                uid=obj.uid,
                epoch_jd=float(epoch_jd),
                state_type=STATE_TYPE_EPHEMERIS,
                x=obj.cartesian_x,
                y=obj.cartesian_y,
                z=obj.cartesian_z,
            ))
        db.insert_states(states)


def main(argv=None) -> int:
    """CLI entry point. Exit codes:

      * 0 — success (per-body errors print on stderr).
      * 2 — invalid arguments.
      * 3 — every body failed (single-epoch) or every epoch failed
        (time-series).
    """
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    init_logging()

    err = _validate_time_series(args)
    if err is not None:
        print(f"error: {err}", file=sys.stderr)
        return 2

    try:
        requests = _parse_bodies(args.bodies, args.default_object_type)
    except argparse.ArgumentTypeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not requests:
        print("error: --bodies parsed to an empty list", file=sys.stderr)
        return 2

    try:
        epochs = _build_epoch_list(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # ----------------------------------------------------------------
    # Single-epoch path keeps the v0.4 fast path (one Horizons
    # batch + one JSONL write + optional inline index build).
    # ----------------------------------------------------------------
    if len(epochs) == 1 and args.db_path is None:
        report = fetch_batch_normalize_and_write(
            requests, epochs[0].iso, args.output,
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
                f"(epoch={epochs[0].iso}, center={args.center})."
            )
            if report.index_path is not None:
                line += (
                    f" Built index at {report.index_path} — "
                    f"{report.index_total_objects} object(s) in "
                    f"{report.index_cell_count} cell(s)."
                )
            print(line)
        return 0

    # ----------------------------------------------------------------
    # Time-series path (v1.2): one batch per epoch, append to JSONL,
    # populate object_states in the DB.
    # ----------------------------------------------------------------
    parent = os.path.dirname(os.path.abspath(args.output))
    if parent:
        os.makedirs(parent, exist_ok=True)

    accumulated: list = []
    accumulated_epoch_jds: list = []
    failed_epochs = 0
    total_failed = 0

    for epoch in epochs:
        result = fetch_batch_and_normalize(
            requests, epoch.iso, center=args.center,
        )
        if result.failed:
            total_failed += result.failed
            for body, msg in result.errors:
                print(
                    f"warning: {epoch.iso} / {body}: {msg}",
                    file=sys.stderr,
                )
        if not result.objects:
            failed_epochs += 1
            continue
        # Each row's uid already encodes the epoch (jpl:body:epoch).
        accumulated.extend(result.objects)
        accumulated_epoch_jds.extend([epoch.jd] * len(result.objects))
        if not args.quiet:
            print(
                f"  {epoch.iso}: kept {len(result.objects)} body(ies)"
            )

    if not accumulated:
        print(
            "error: every epoch failed; see per-body errors above",
            file=sys.stderr,
        )
        return 3

    # Single JSONL write — append every (body, epoch) row.
    write_catalog(accumulated, args.output)

    if args.db_path is not None:
        try:
            _persist_to_db(args.db_path, accumulated, accumulated_epoch_jds)
        except Exception as exc:  # noqa: BLE001
            print(f"warning: db persist failed: {exc}", file=sys.stderr)

    if not args.quiet:
        print(
            f"Wrote {len(accumulated)} (body, epoch) row(s) over "
            f"{len(epochs)} epoch(s) to {args.output} "
            f"({failed_epochs} epoch(s) wholly failed; "
            f"{total_failed} per-body failures)."
        )
        if args.db_path is not None:
            print(
                f"  + ephemeris states inserted into {args.db_path}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
