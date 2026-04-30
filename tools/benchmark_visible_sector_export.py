#!/usr/bin/env python3
"""Benchmark the v0.8 / v1.0 binary visible-sector exporter.

Generates a synthetic point catalog of N rows, runs each phase of
the export pipeline, and prints wall-clock + throughput numbers.
The output gives a credible upper bound on what the native GPU
renderer (v1.0+) sees on the wire — the Python side is the
generation cost, the C++ side is the load + draw cost.

Example::

    python tools/benchmark_visible_sector_export.py --points 100000 \\
        --output /tmp/bench.unav --version v2 --camera-relative

Reports:

  * synthetic-catalog generation seconds,
  * binary-export seconds,
  * sidecar-write seconds (when --sidecar-path is given),
  * round-trip parse seconds (read + CRC),
  * file size + per-point bytes.

This is a preprocessing tool. It does not require Cinema 4D and
does not require credentials. Honest-numbers benchmark: the script
deliberately does not warm the OS cache or pre-touch malloc; the
first invocation reflects the cold-start cost.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from typing import List


def _bootstrap_sys_path() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    plugin_root = os.path.join(repo_root, "unav_pro")
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)


_bootstrap_sys_path()

from core.logging_util import init_logging  # noqa: E402
from data.binary_export import (  # noqa: E402
    FORMAT_VERSION_V1,
    FORMAT_VERSION_V2,
    UnavBinaryPoint,
    compute_uid_hash,
    make_v2_extras,
    read_visible_sector,
    write_visible_sector,
)


_VERSION_TOKENS = {
    "v1": FORMAT_VERSION_V1,
    "v2": FORMAT_VERSION_V2,
}


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Benchmark the binary visible-sector exporter. Generates "
            "a synthetic catalog of N points and times the export, "
            "the optional sidecar write, and a parse round-trip."
        ),
    )
    p.add_argument("--points", type=int, default=10_000,
                   help="Synthetic point count (default 10000).")
    p.add_argument("--output", default="",
                   help=(
                       "Output file path. If empty, writes to a "
                       "tmp file and removes it after timing."
                   ))
    p.add_argument("--version", choices=tuple(_VERSION_TOKENS),
                   default="v2",
                   help="Binary format version (default v2).")
    p.add_argument("--camera-relative", action="store_true",
                   help=(
                       "v2 only: emit camera-relative point coords "
                       "(positions become offsets from the sector "
                       "origin)."
                   ))
    p.add_argument("--seed", type=int, default=0,
                   help="RNG seed for reproducible numbers.")
    p.add_argument("--no-roundtrip", action="store_true",
                   help="Skip the parse round-trip phase.")
    return p.parse_args(argv)


def _generate_points(count: int, seed: int) -> List[UnavBinaryPoint]:
    """Pseudo-random point cloud filling a 1000-pc cube."""
    rng = random.Random(seed)
    out: List[UnavBinaryPoint] = []
    half = 500.0
    for i in range(count):
        out.append(UnavBinaryPoint(
            x=rng.uniform(-half, half),
            y=rng.uniform(-half, half),
            z=rng.uniform(-half, half),
            size=rng.uniform(0.1, 4.0),
            r=rng.random(),
            g=rng.random(),
            b=rng.random(),
            uid_hash=compute_uid_hash(f"bench:{i}"),
            source_id=1,
        ))
    return out


def main(argv=None) -> int:
    args = _parse_args(argv)
    init_logging()

    if args.points <= 0:
        print("error: --points must be > 0", file=sys.stderr)
        return 2

    output = args.output
    cleanup_after = False
    if not output:
        import tempfile
        fd, output = tempfile.mkstemp(suffix=".unav", prefix="unav_bench_")
        os.close(fd)
        cleanup_after = True

    print(
        f"Benchmark: {args.points} points, version={args.version}, "
        f"camera_relative={bool(args.camera_relative)}"
    )

    # 1. Generate.
    t0 = time.monotonic()
    points = _generate_points(args.points, args.seed)
    t1 = time.monotonic()
    gen_secs = t1 - t0
    gen_rate = args.points / gen_secs if gen_secs > 0 else float("inf")
    print(
        f"  generate : {gen_secs * 1000:8.2f} ms "
        f"({gen_rate / 1e6:.3f} Mpoints/s)"
    )

    # 2. Build v2 extras (only used by v2 export).
    version = _VERSION_TOKENS[args.version]
    extras = None
    sector_origin = None
    if version == FORMAT_VERSION_V2:
        t0 = time.monotonic()
        extras = make_v2_extras(points)
        sector_origin = extras.sector_origin
        if args.camera_relative:
            from data.binary_export import (
                RENDERER_FLAG_POINTS_RELATIVE_TO_SECTOR_ORIGIN,
                make_relative_points,
            )
            extras.renderer_flags |= (
                RENDERER_FLAG_POINTS_RELATIVE_TO_SECTOR_ORIGIN
            )
            points = make_relative_points(points, sector_origin)
        t1 = time.monotonic()
        print(f"  v2 extras: {(t1 - t0) * 1000:8.2f} ms")

    # 3. Write.
    t0 = time.monotonic()
    bytes_written = write_visible_sector(
        output, points,
        sources=[(1, "bench")],
        coordinate_scale_factor=1.0,
        format_version=version,
        v2_extras=extras,
    )
    t1 = time.monotonic()
    write_secs = t1 - t0
    write_rate_mb = (bytes_written / (1024 * 1024)) / write_secs if write_secs > 0 else float("inf")
    print(
        f"  export   : {write_secs * 1000:8.2f} ms "
        f"(file {bytes_written / (1024 * 1024):.2f} MB, "
        f"{write_rate_mb:.1f} MB/s, "
        f"{bytes_written / max(args.points, 1):.1f} bytes/pt)"
    )

    # 4. Round-trip read.
    if not args.no_roundtrip:
        t0 = time.monotonic()
        parsed = read_visible_sector(output)
        t1 = time.monotonic()
        read_secs = t1 - t0
        rate = args.points / read_secs if read_secs > 0 else float("inf")
        print(
            f"  parse    : {read_secs * 1000:8.2f} ms "
            f"({rate / 1e6:.3f} Mpoints/s, "
            f"{parsed.header.point_count} points decoded)"
        )

    if cleanup_after:
        try:
            os.remove(output)
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
