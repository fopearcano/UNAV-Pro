#!/usr/bin/env python3
"""Export a UNAV catalog (or pre-filtered subset) to the v0.8
visible-sector binary format the future C++ point renderer reads.

Example::

    python tools/export_visible_sector_binary.py \\
        --input data/catalogs/gaia_pleiades_sample.jsonl \\
        --output cache/binary/gaia_pleiades.unav

The CLI does not run a navigator filter; it converts whatever
JSONL / CSV the caller hands it. For a navigator-filtered cache
the typical workflow is:

  1. ``tools/fetch_*.py`` → JSONL.
  2. ``tools/build_spatial_index.py`` → chunked index.
  3. (offline) the dialog's *Sync Visible Sector* path or any
     other filter dumps the surviving subset to its own JSONL.
  4. This tool packs that subset into the binary file.

This is a preprocessing tool. It does not require Cinema 4D and
does not require credentials.
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
from data.binary_export import (  # noqa: E402
    BinaryExportError, export_objects,
)
from data.catalog_io import CatalogIOError, load_catalog  # noqa: E402
from data.schema import DEFAULT_SCALE_MODE, SCALE_MODES  # noqa: E402


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Export a UNAV catalog (JSONL/CSV) to the v0.8 binary "
            "visible-sector format the future C++ point renderer reads."
        ),
    )
    p.add_argument("--input", required=True,
                   help="Input JSONL or CSV catalog path.")
    p.add_argument("--output", required=True,
                   help="Output binary file path (parent dirs created).")
    p.add_argument("--scale-mode", default=DEFAULT_SCALE_MODE,
                   choices=sorted(SCALE_MODES.keys()),
                   help=(
                       "C4D scale mode used to compute c4d_x/y/z "
                       "from cartesian_pc (default 'pc')."
                   ))
    p.add_argument("--sidecar-path", default="",
                   help=(
                       "Optional relative metadata sidecar path embedded "
                       "in the binary header. Empty string == no sidecar."
                   ))
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    """CLI entry point. Exit codes:

      * 0 — success.
      * 2 — invalid arguments / missing input.
      * 3 — export error (corrupt input / I/O failure).
    """
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    init_logging()

    if not os.path.isfile(args.input):
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 2

    try:
        objects = load_catalog(args.input)
    except CatalogIOError as exc:
        print(f"error: could not read catalog: {exc}", file=sys.stderr)
        return 3

    try:
        bytes_written, header, sources = export_objects(
            args.output, objects,
            scale_mode=args.scale_mode,
            sidecar_path=args.sidecar_path or "",
        )
    except (OSError, BinaryExportError) as exc:
        print(f"error: export failed: {exc}", file=sys.stderr)
        return 3

    if not args.quiet:
        print(
            f"Wrote {header.point_count} points "
            f"({header.source_count} source(s)) to {args.output} "
            f"({bytes_written} bytes, scale_mode={args.scale_mode}, "
            f"scale_factor={header.coordinate_scale_factor})."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
