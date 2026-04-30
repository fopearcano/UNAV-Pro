#!/usr/bin/env python3
"""Import a UNAV JSONL / CSV catalog into the v1.1 SQLite database.

Example::

    python tools/import_catalog_to_db.py \\
        --input data/catalogs/gaia_pleiades_sample.jsonl \\
        --db data/unav.db

The importer:

* Streams ``--input`` row-by-row (no full-file load), so a 10 M-row
  JSONL never sits in RAM.
* Applies the bundled ``unav_pro/db/schema.sql`` to the target DB
  before inserting (idempotent — re-running is safe).
* Uses ``INSERT OR IGNORE`` by default so duplicate uids are
  skipped; ``--replace`` opts into ``INSERT OR REPLACE`` for
  positions-only re-imports.
* Builds B-tree indexes alongside the inserts (the schema's
  ``CREATE INDEX IF NOT EXISTS`` lines).

Multiple ``--input`` paths can be passed; each is streamed in
turn and the same DB accumulates them.

This is a preprocessing tool. It does not require Cinema 4D and
does not require credentials.
"""

from __future__ import annotations

import argparse
import os
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
from data.catalog_io import CatalogIOError, load_catalog  # noqa: E402
from db.db_manager import DBError, DBManager, iter_jsonl  # noqa: E402


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Import a UNAV JSONL/CSV catalog into the v1.1 SQLite DB. "
            "Multiple --input paths accumulate into one DB."
        ),
    )
    p.add_argument("--input", required=True, action="append",
                   help=(
                       "Catalog file (JSONL or CSV). May be repeated to "
                       "import several catalogs into the same DB."
                   ))
    p.add_argument("--db", required=True,
                   help="Output SQLite path. Created if missing.")
    p.add_argument("--replace", action="store_true",
                   help=(
                       "Use INSERT OR REPLACE so existing uids are "
                       "overwritten. Default INSERT OR IGNORE skips "
                       "duplicates."
                   ))
    p.add_argument("--skip-metadata", action="store_true",
                   help=(
                       "Don't write the per-row metadata_json blob. "
                       "Useful for positions-only re-imports."
                   ))
    p.add_argument("--batch-size", type=int, default=5_000,
                   help="Rows per executemany() call (default 5000).")
    p.add_argument("--vacuum", action="store_true",
                   help="Run VACUUM after import (slow; reclaims disk).")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    """Exit codes:

      * 0 — success.
      * 2 — invalid arguments / missing input.
      * 3 — DB / I/O error.
    """
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    init_logging()

    inputs: List[str] = list(args.input)
    for path in inputs:
        if not os.path.isfile(path):
            print(f"error: input not found: {path}", file=sys.stderr)
            return 2

    try:
        with DBManager(args.db) as db:
            db.apply_schema()
            grand_inserted = 0
            grand_meta = 0
            t0 = time.monotonic()
            for path in inputs:
                if not args.quiet:
                    print(f"Importing {path} → {args.db} ...")
                t_path = time.monotonic()
                if path.lower().endswith(".jsonl") or path.lower().endswith(".json"):
                    iterable = iter_jsonl(path)
                else:
                    # CSV / fallback — load_catalog into memory; warn for
                    # large files via the existing safety advisory.
                    iterable = iter(load_catalog(path))
                inserted, meta = db.import_iter(
                    iterable,
                    replace=args.replace,
                    metadata=not args.skip_metadata,
                    batch_size=int(args.batch_size),
                )
                grand_inserted += inserted
                grand_meta += meta
                elapsed = time.monotonic() - t_path
                if not args.quiet:
                    print(
                        f"  inserted {inserted} object(s) "
                        f"+ {meta} metadata row(s) in {elapsed:.2f}s"
                    )
            if args.vacuum:
                if not args.quiet:
                    print("VACUUM ...")
                db.vacuum()

            stats = db.stats()
    except (DBError, CatalogIOError, OSError) as exc:
        print(f"error: import failed: {exc}", file=sys.stderr)
        return 3

    if not args.quiet:
        total_elapsed = time.monotonic() - t0
        print(
            f"Done. {grand_inserted} object(s) + "
            f"{grand_meta} metadata row(s) in {total_elapsed:.2f}s. "
            f"DB: {stats.short_summary()}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
