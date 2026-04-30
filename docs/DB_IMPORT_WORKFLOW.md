# DB Import Workflow

How to turn a UNAV JSONL / CSV catalog into the v1.1 SQLite DB
the dialog queries. The CLI is
``tools/import_catalog_to_db.py``; this doc walks through the
typical workflow plus the edge cases.

For the schema the importer writes into see
[`SQL_SCHEMA.md`](SQL_SCHEMA.md). For the broader v1.1
milestone see [`V1_1_QUERY_ENGINE.md`](V1_1_QUERY_ENGINE.md).

---

## 1. Quick start

```bash
# 1. Fetch a catalog (any v0.3+ connector emits JSONL).
python tools/fetch_gaia_region.py \
    --ra 56.75 --dec 24.12 --radius-deg 1.0 \
    --limit 5000 \
    --output data/catalogs/gaia_pleiades.jsonl

# 2. Import into the v1.1 DB.
python tools/import_catalog_to_db.py \
    --input data/catalogs/gaia_pleiades.jsonl \
    --db data/unav.db
```

The DB file is created on first call and applied with the
schema in ``unav_pro/db/schema.sql``. Re-running with the same
``--input`` is idempotent: ``INSERT OR IGNORE`` skips uids that
are already in the DB.

---

## 2. CLI surface

```
usage: import_catalog_to_db.py [-h] --input INPUT --db DB
                                [--replace] [--skip-metadata]
                                [--batch-size BATCH_SIZE] [--vacuum]
                                [--quiet]
```

| Flag                  | Default | What it does                                                            |
|-----------------------|--------:|--------------------------------------------------------------------------|
| ``--input``           | required | Catalog file (JSONL / CSV). Repeatable: each path streams into the same DB. |
| ``--db``              | required | Output SQLite path. Created if missing.                                  |
| ``--replace``         | off     | ``INSERT OR REPLACE`` — overwrites existing uids. Default skips them.    |
| ``--skip-metadata``   | off     | Don't write the parallel ``metadata`` table. Useful for positions-only updates. |
| ``--batch-size``      | 5000    | Rows per ``executemany()``. Higher = fewer round-trips, more RAM.        |
| ``--vacuum``          | off     | Run ``VACUUM`` after import. Slow; reclaims disk space + rebuilds B-trees. |
| ``--quiet``           | off     | Suppress per-file progress lines.                                        |

Exit codes:

* **0** — success.
* **2** — invalid arguments / missing input.
* **3** — DB / I/O error.

---

## 3. Multi-catalog DBs

The most common workflow: build one DB per project that
combines several connectors.

```bash
python tools/import_catalog_to_db.py \
    --input data/catalogs/gaia_pleiades.jsonl \
    --input data/catalogs/sdss_region_sample.jsonl \
    --input data/catalogs/desi_region_sample.jsonl \
    --input data/catalogs/jpl_solar_system_2026.jsonl \
    --db data/multi_source.db
```

Each ``--input`` is streamed and inserted in turn. uids stay
disjoint by construction (the v0.4+ connectors use distinct
``gaia:``, ``sdss:``, ``desi:``, ``jpl:`` prefixes). The
search panel can then filter by ``source = "Gaia DR3"`` to
slice the combined DB.

---

## 4. Updating existing rows

The default behaviour is to **skip** existing uids. To
overwrite, pass ``--replace``:

```bash
python tools/import_catalog_to_db.py \
    --input data/catalogs/gaia_pleiades.jsonl \
    --db data/unav.db \
    --replace
```

``--replace`` matters for two scenarios:

* **Re-fetch with updated values.** v0.5 fixed the SDSS
  ``catalog_source`` from ``sdss_dr18`` to ``"SDSS"``. The DB
  importer caught up on the next ``--replace`` re-import.
* **Position fixes.** A future ``compute_derived_fields``
  improvement that lands different cartesian values; the
  importer's ``--replace`` updates the positions in place.

The ``metadata_json`` blob always uses ``INSERT OR REPLACE``
on the metadata table because the JSON is unconditionally
re-derived from the source row. ``--skip-metadata`` opts out.

---

## 5. Streaming behaviour

The importer never materialises the full input list. ``iter_jsonl``
streams the JSONL line-by-line; the CSV path uses
``data.catalog_io.load_catalog`` (which walks the file
similarly). Memory footprint is ``batch_size`` rows worth of
``CatalogObject`` instances at a time — a few MB even at the
default 5000 batch.

For multi-million-row catalogs you can raise ``--batch-size``
to 50 000 or 100 000 if you have RAM to spare; the
``executemany()`` round-trip cost amortises over more rows.

---

## 6. After the import

* **Stats.** The CLI prints a summary line on success:
  ``Done. 5000 object(s) + 0 metadata row(s) in 0.34s. DB:
  5,000 objects (1 source(s), 1 type(s), 0.5 MB)``.
* **Verify.** Use any SQLite client:
  ```bash
  sqlite3 data/unav.db "SELECT source, COUNT(*) FROM objects GROUP BY source"
  ```
* **Register.** Inside Cinema 4D, **Dataset Manager… → Add
  DB-backed Dataset → pick `data/unav.db`**. The registry
  records ``db_path`` + the stats from ``scan_db_stats``;
  the entry shows ``db`` instead of ``idx``.

---

## 7. Failure modes

| Scenario                                | What happens                                                |
|-----------------------------------------|-------------------------------------------------------------|
| Input file missing                      | CLI exits 2 with ``error: input not found: …``.             |
| DB exists with mismatched schema        | CLI exits 3 with ``error: import failed: schema version mismatch``. |
| Bad JSONL row mid-stream                | Logged at WARNING, skipped, rest of file proceeds.          |
| Disk full mid-batch                     | CLI exits 3 with the OS error string.                       |
| Already-imported uid                    | Default: skipped silently. ``--replace`` overwrites.        |
| ``metadata_json`` is invalid JSON       | Stored verbatim; ``DBManager.fetch_metadata`` returns None. |

---

## 8. v1.2+ enhancements (out of scope today)

* **Update mode.** A ``--update`` flag that surgically updates
  only the columns the input row sets (vs the all-or-nothing
  ``--replace``).
* **Dry run.** ``--dry-run`` to print the row count + sources
  without writing.
* **Parquet input.** A direct Parquet → DB stream so the
  next-generation pipeline can skip JSONL.
* **Sharding.** Emit per-source DBs by default for very large
  imports; the registry handles multi-DB merge already.

Until then, the v1.1 importer stays narrow: stream JSONL /
CSV, write SQLite, surface stats.
