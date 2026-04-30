# JPL Time-Series Workflow

How to fetch a multi-epoch JPL Horizons time series, ingest it
into the v1.2 SQLite DB, and watch the planets move in the C4D
scene as the Time Navigator advances.

For the v0.4 single-epoch baseline see
[`SOLAR_SYSTEM_COORDINATES_AND_EPOCHS.md`](SOLAR_SYSTEM_COORDINATES_AND_EPOCHS.md).
For the time model itself see
[`EPOCHS_AND_JULIAN_DATES.md`](EPOCHS_AND_JULIAN_DATES.md).

---

## 1. The CLI

`tools/fetch_jpl_solar_system.py` has two modes selected by
mutually-exclusive arguments:

| Mode             | Trigger                                | Output                                     |
|------------------|----------------------------------------|--------------------------------------------|
| Single-epoch     | ``--epoch ISO``                        | One row per body in JSONL.                 |
| Time-series      | ``--start ISO --end ISO --step-days N``| One row per (body, epoch) in JSONL + (optionally) DB. |

The single-epoch path is the v0.4 status quo — fast (one
Horizons batch + one JSONL write) and bit-for-bit identical
to v1.1 output.

The time-series path is the v1.2 addition. It walks the
``[start, end]`` range in ``step-days`` increments, fetches
each epoch's batch from Horizons, and accumulates one row per
``(body, epoch)`` pair. Each row's ``uid`` already encodes the
epoch (``jpl:body:iso_epoch``) so duplicates across epochs are
impossible.

---

## 2. Quick start

```bash
python tools/fetch_jpl_solar_system.py \
    --start "2026-01-01T00:00:00" \
    --end   "2026-12-31T00:00:00" \
    --step-days 7 \
    --bodies "Mercury,Venus,Earth,Mars,Jupiter,Saturn,Uranus,Neptune" \
    --output data/catalogs/jpl_2026_weekly.jsonl \
    --db     data/unav.db
```

This builds a 53-epoch sweep (one snapshot per week through
2026), 8 bodies per epoch — 424 ``(body, epoch)`` rows total.
The JSONL is the canonical artefact (artists archive it like
any other catalog); the ``--db`` sink imports the same data
into the v1.2 SQLite ``object_states`` table so the in-plugin
Time Navigator can scrub through it.

Watch the ``--max-epochs`` cap (default 400). For dense sweeps
or long-term studies raise it explicitly:

```bash
--max-epochs 4000
```

The cap exists to prevent a typo (e.g. ``--step-days 0.001``)
from launching a multi-thousand-call Horizons sweep.

---

## 3. What lands in the DB

When ``--db`` is set, the CLI calls
``DBManager.insert_objects`` (with ``replace=True``) and then
``DBManager.insert_states`` for the same batch:

| Table             | Row contents                                                      |
|-------------------|-------------------------------------------------------------------|
| ``objects``       | One row per (body, epoch). UID is ``jpl:Body:ISO``.               |
| ``object_states`` | One ``state_type='ephemeris'`` row per (body, epoch). Carries ``x/y/z`` parsec, the ``epoch_jd``, and the FK back to ``objects.uid``. |

This is the same ``object_states`` shape the Gaia
proper-motion path uses (with ``state_type='proper_motion'``);
the resolver in ``core/temporal_resolver.py`` dispatches on the
``state_type`` field.

---

## 4. The artist-side workflow

1. **Fetch.** Run the CLI above for the campaign's date range.
2. **Open the DB in UNAV.** Dataset Manager → "Add catalog" →
   point at ``data/unav.db``. The dataset shows up like any
   other catalog source.
3. **Sync the visible sector.** The first sync uses whatever
   epoch the Time Navigator is on (default J2016 if the user
   hasn't changed it).
4. **Step the epoch.** The Time Navigator panel's ``<`` / ``>``
   buttons advance / rewind by ``step_days``. Each step the
   panel calls ``sync_visible_sector_at_epoch``, which re-runs
   ``query_cone_for_navigator`` with the new epoch — so the
   visible-sector positions reflect the requested time.
5. **Watch them move.** Mars / Jupiter etc. translate by the
   correct distance per step; nearby Gaia stars with high
   pmra/pmdec also drift.

---

## 5. Interpolation between snapshots

The temporal resolver
(``core/temporal_resolver.EphemerisStore``) supports two modes
for picking an ``ephemeris`` position when the requested epoch
falls between two snapshots:

* ``interpolate=True`` (default) — linear interpolation of
  ``x/y/z`` between the two bracketing snapshots.
* ``interpolate=False`` — pick the nearest snapshot.

For dense time-series (daily / weekly cadence over a year), the
linear interpolation is visually indistinguishable from the
exact orbit. For sparse series (annual snapshots over a
century) the planet will "drift in a straight line" between
snapshots — which is wrong; switch to the nearest-only mode or
re-fetch with finer cadence.

If the requested epoch is **outside** the bracket
``[earliest_snapshot, latest_snapshot]``, the resolver does a
nearest-snapshot fallback regardless of the ``interpolate``
flag. This avoids extrapolating the orbit linearly off into
empty space.

---

## 6. Sizing

A back-of-the-envelope for the on-disk overhead:

| Configuration                          | Rows added | DB-size delta (approx) |
|---------------------------------------|------------|------------------------|
| 8 planets × 365 days (daily, 1 year)  | 2920       | ~600 KB                |
| 8 planets × 53 weeks                  | 424        | ~100 KB                |
| 8 planets × 12 months × 100 years     | 9600       | ~2 MB                  |

Each ``object_states`` row is small (~200 bytes incl. index
overhead). The ``cartesian_x/y/z`` columns on the ``objects``
table dominate — and those exist whether or not the
time-series path is used.

For the v1.2 acceptance criteria (a few campaigns, weekly to
monthly cadence, decade-scale ranges) the DB stays well under a
megabyte.

---

## 7. Failure modes

The Horizons API has rate limits and per-target quirks. The
CLI handles these as follows:

* **Per-body fetch failure.** Logged on stderr; the rest of
  the batch still flows through. The summary line at the end
  reports ``X failed`` so the artist sees the count.
* **Whole-epoch failure.** All bodies failed for a given epoch.
  Logged on stderr; the next epoch is attempted. Counted in
  ``failed_epochs`` in the final summary.
* **Every epoch failed.** Exit code 3. JSONL is *not* written.
* **Out-of-range bodies / unknown designations.** Horizons'
  error message is propagated verbatim.

The ``--db`` sink is best-effort. If the DB write fails after a
successful Horizons fetch, a ``warning: db persist failed``
line goes to stderr but the JSONL still writes — the artist
can re-run with ``--db data/unav.db`` only (no ``--output``)
in a future v1.x update once that flag exists, or import the
JSONL via the Dataset Manager's standard import path.

---

## 8. Test coverage

The (body, epoch) → DB path is exercised by
``unav_pro/tests/test_db_object_states.py`` end-to-end via the
``test_query_cone_with_epoch_uses_proper_motion_state`` and
``test_fetch_states_at_epoch_uses_tolerance`` tests; the CLI
glue in ``tools/fetch_jpl_solar_system.py`` is exercised by the
existing connector tests under
``unav_pro/tests/test_jpl_horizons_connector.py``.
