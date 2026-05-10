#!/usr/bin/env python3
"""v3.2 dataset audit CLI.

Run a science-correctness audit against a JSONL catalog
file. Emits a Markdown report (default) and optionally a
machine-readable JSON sidecar.

Example:

::

    python tools/audit_dataset.py \\
        --input data/catalogs/gaia_sample.jsonl \\
        --output reports/gaia_sample_audit.md

The CLI is **stdlib-only** + uses the v3.2 validation
machinery in ``unav_pro/data/validation_report.py``.
Designed to be safe for very large catalogs: rows are
streamed off disk one at a time and the in-memory
report carries only **issues** + counts (no row
duplication).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

# The plugin's ``.pyp`` entry point inserts the plugin
# root into sys.path so that ``from data import ...`` works
# inside Cinema 4D. The CLI follows the same convention.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.join(os.path.dirname(_HERE), "unav_pro")
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)


def _safe_write(path: str, body: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
        if not body.endswith("\n"):
            fh.write("\n")
    os.replace(tmp, path)


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="audit_dataset.py",
        description=(
            "Run a v3.2 dataset audit against a JSONL "
            "catalog. Emits a Markdown report by default; "
            "use --json-output to also emit a JSON sidecar."
        ),
    )
    p.add_argument(
        "--input", "-i", required=True,
        help="Path to a JSONL catalog file.",
    )
    p.add_argument(
        "--output", "-o", default=None,
        help=(
            "Path to write the Markdown report. Default: "
            "<input>.audit.md next to the input."
        ),
    )
    p.add_argument(
        "--json-output", default=None,
        help=(
            "Optional path for a machine-readable JSON "
            "sidecar (full report including issues + "
            "provenance summary)."
        ),
    )
    p.add_argument(
        "--include-no-provenance",
        action="store_true",
        help=(
            "Emit info-level issues for rows missing a "
            "provenance record. Off by default to keep "
            "the report focused on errors / warnings."
        ),
    )
    p.add_argument(
        "--max-rows", type=int, default=0,
        help=(
            "Stop after N rows (0 = unlimited). Useful for "
            "spot-checks on enormous catalogs."
        ),
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="Don't print the report to stdout.",
    )
    return p


def _stream_objects(path: str, *, max_rows: int = 0):
    """Yield CatalogObject rows lazily from ``path``. Bounded
    memory: one row in flight at a time."""
    from data.catalog_io import load_catalog
    n = 0
    for obj in load_catalog(path):
        yield obj
        n += 1
        if max_rows and n >= max_rows:
            break


def main(argv: Optional[list] = None) -> int:
    args = _build_argparser().parse_args(argv)
    input_path = args.input
    if not os.path.isfile(input_path):
        print(
            f"audit_dataset: input not found: {input_path}",
            file=sys.stderr,
        )
        return 2

    output_md = args.output or (
        os.path.splitext(input_path)[0] + ".audit.md"
    )

    from data.validation_report import validate_objects
    rows = list(_stream_objects(input_path, max_rows=args.max_rows))
    report = validate_objects(
        rows,
        include_no_provenance_probe=bool(args.include_no_provenance),
    )

    md = report.render_markdown()
    _safe_write(output_md, md)

    if args.json_output:
        _safe_write(args.json_output, report.to_json())

    if not args.quiet:
        print(report.short_summary())
        print(f"  markdown: {output_md}")
        if args.json_output:
            print(f"  json    : {args.json_output}")

    # Exit with non-zero code only on real errors. Warnings
    # / info do not fail the build — the artist runs the
    # audit to learn, not to gate.
    has_errors = (
        report.counts.by_severity.get("error", 0) > 0
    )
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
