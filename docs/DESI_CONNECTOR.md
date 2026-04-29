# UNAV Pro — DESI Connector

Cone-search connector for the Dark Energy Spectroscopic Instrument
public data, targeting NOIRLab's Astro Data Lab TAP service:

```
https://datalab.noirlab.edu/tap/sync
```

The DESI Early Data Release is exposed there as `desi_edr.zpix` (and
`desi_edr.zall_pix`); DR1 is `desi_dr1.zpix`.

Stub status. The function signatures, ADQL surface, column mapping,
and test surface are all production-shaped, but the live HTTP path
is exercised only against mocked responses in this MVP. The same
`fetch_fn`-injected design that powers the Gaia, Horizons, and SDSS
connectors lets `_http_fetch` go live without any caller-visible
change.

Companion to `UNAV_PRO_DATA_PIPELINE.md`, `GAIA_CONNECTOR.md`, and
`SDSS_CONNECTOR.md`.

---

## 1. Scope

  * **Cone search** around (RA, Dec) with a row cap.
  * **Redshift catalog only.** `zpix` is the per-target best-redshift
    table; this is what scenes will visualize. Full photometric
    crossmatch with Legacy/BASS/MzLS imaging is reserved for the
    production crossmatch stage.
  * **Object types covered:** galaxies, quasars, stars (the
    `SPECTYPE` column has values `GALAXY`, `QSO`, `STAR`).
  * **Server-side `--spectype` filter.** Optional and recommended;
    cuts the wire size dramatically for galaxy-only or QSO-only
    scenes.
  * **Survey metadata preserved.** `SURVEY`, `PROGRAM`,
    `DESI_TARGET`, `HEALPIX` ride in `metadata_json` so a future
    filter can gate by survey phase or target class.
  * **No credentials.** Public endpoint; UNAV identifies itself via
    User-Agent.
  * **Stdlib only.** `urllib`, `csv`, `json`, `dataclasses`. No
    `pyvo`, no `astroquery`.

Releases supported: `desi_edr` (default) and `desi_dr1`. Adding a
future release is a one-line addition to `_RELEASE_TO_TABLE`.

---

## 2. CLI

`tools/fetch_desi_region.py` is the canonical entry point.

```bash
python tools/fetch_desi_region.py \
    --ra 180.0 --dec 30.0 --radius-deg 1.0 \
    --limit 5000 \
    --output data/desi_sample.jsonl
```

| Flag                  | Default      | Notes                                                          |
|-----------------------|--------------|----------------------------------------------------------------|
| `--ra`                | required     | Cone-center RA in degrees, `[0, 360)`.                         |
| `--dec`               | required     | Cone-center Dec in degrees, `[-90, 90]`.                       |
| `--radius-deg`        | required     | Cone radius in degrees, `(0, 30]`.                             |
| `--limit`             | 5 000        | Max rows; bounded at 100 000.                                  |
| `--release`           | `desi_edr`   | One of `desi_edr`, `desi_dr1`.                                 |
| `--spectype`          | none         | Optional server-side filter: `GALAXY`, `QSO`, or `STAR`.       |
| `--output`            | required     | Output JSONL path; parents are created.                        |
| `--redshift-max-z`    | 0.1          | Above this z, `distance_parsec` stays None.                    |
| `--quiet`             | off          | Suppress the summary line.                                     |

Exit codes: 0 ok, 2 invalid args, 3 archive failure.

---

## 3. ADQL strategy

`build_adql(query)` emits a standard cone search:

```sql
SELECT TOP 5000
    targetid, target_ra, target_dec,
    z, zerr, zwarn,
    spectype, subtype,
    desi_target,
    survey, program, healpix
FROM desi_edr.zpix
WHERE 1=CONTAINS(POINT('ICRS', target_ra, target_dec),
                 CIRCLE('ICRS', 180.0, 30.0, 1.0))
ORDER BY z ASC
```

When `--spectype` is given, an extra `AND spectype = 'GALAXY'` (or
`QSO` / `STAR`) clause is appended so the filter happens server-side
and the wire payload shrinks by one or two orders of magnitude for
galaxy-only / QSO-only scenes.

`ORDER BY z ASC` puts nearby objects first, so a user-supplied
`--limit` truncates the high-z tail rather than the local
neighborhood.

---

## 4. UNAV mapping

| UNAV field            | Source                                                                  |
|-----------------------|-------------------------------------------------------------------------|
| `uid`                 | `desi_edr:<targetid>` (release-prefixed for cross-source disambiguation). |
| `catalog_source`      | The release: `desi_edr` / `desi_dr1`.                                   |
| `object_type`         | `SPECTYPE` mapped: `GALAXY` → `galaxy`, `QSO` → `quasar`, `STAR` → `star`; else `unknown`. |
| `name`                | `targetid` as a string.                                                 |
| `ra_deg` / `dec_deg`  | `target_ra` / `target_dec`.                                             |
| `redshift`            | `Z` from the catalog (the best-redshift fit).                           |
| `distance_parsec`     | Coarse Hubble-law inversion if `0 < z ≤ redshift_max_z` **and** `ZWARN == 0`; else `None`. |
| `metadata_json`       | `spectype`, `subtype`, `zerr`, `zwarn`, `desi_target`, `survey`, `program`, `healpix`. |

Both lowercase and uppercase column names from the response are
accepted (`targetid` / `TARGETID`, etc.) so the connector survives
TAP servers that normalize column case differently.

---

## 5. Redshift → distance

`safe_redshift_to_distance(z, z_err, zwarn, max_z, h0)` extends the
SDSS helper with a DESI-specific quality gate: if `ZWARN != 0` the
function returns `None` regardless of `z`. The DESI redshift
pipeline encodes fit warnings as a bitmask; any non-zero value means
the redshift is suspect.

  * `z` missing or ≤ 0 → `None`.
  * `ZWARN != 0` → `None`. The redshift is preserved on the row;
    only the distance is suppressed.
  * `z > max_z` (default 0.1) → `None`. Same Hubble-law caveat as
    the SDSS connector — proper cosmology-aware comoving distance
    is a future tightening.
  * Otherwise: `distance_pc = (c · z / H₀) × 10⁶`.

Galaxies with `ZWARN != 0` still flow through to the C4D scene; they
are just placed on the placeholder celestial sphere instead of at a
specific distance, and the `metadata_json` carries the warning code
for downstream filters and the inspector.

---

## 6. Failure modes

| Situation                          | Behavior                                            |
|------------------------------------|-----------------------------------------------------|
| Argument out of range              | `ValueError` at `DESIQuery`; CLI exits 2.           |
| Unknown `--spectype` / release     | `ValueError`; CLI exits 2.                          |
| HTTP non-200 / network error       | `DESIQueryError`; CLI exits 3.                      |
| Empty CSV body                     | Returns 0 rows; CLI prints a warning and writes an empty JSONL. |
| Individual bad row                 | Counted in the log, skipped — never aborts the run. |
| Missing `targetid` / RA / Dec      | Row silently skipped (counted).                     |
| Mixed-case column names            | Both lowercase and uppercase accepted (`targetid` / `TARGETID`). |

The connector does not retry on transient errors. Adding
exponential-backoff retries is a small change to `_http_fetch`;
deferred until rate-limit data justifies it.

---

## 7. Testing

`unav_pro/tests/test_desi_connector.py` covers the connector with
**no network access** — every test injects a `fetch_fn` that returns
a hand-crafted CSV body.

  * `DESIQuery` validation (RA / Dec / radius / limit / release,
    `spectype` normalization to uppercase, unknown spectype).
  * ADQL builder — required columns, ICRS cone geometry, optional
    `spectype` clause, release-specific table name, redshift-
    ascending ordering.
  * `safe_redshift_to_distance` — zero / negative / above-max /
    `ZWARN != 0` rejected / clean low-z accepted.
  * Row → `CatalogObject` normalization — galaxy with valid
    spectrum, high-z quasar (no distance), `ZWARN != 0` keeps the
    row but blocks the distance, star, unknown for missing
    `SPECTYPE`, skipped rows for missing identifier or position,
    uppercase column names accepted.
  * `fetch_rows` — correct URL / ADQL / params, empty body,
    fetcher exception propagation.
  * `fetch_and_normalize` end-to-end.

Integration tests against the live NOIRLab TAP service belong in a
separate `tools/qa/` script run on demand.

---

## 8. Roadmap

  * **Crossmatch with Legacy Surveys photometry.** Join on
    `desi_edr.photometry` (or the equivalent imaging table) so
    `apparent_magnitude` and `color_index` are populated for every
    DESI row. The MVP leaves both as `None` because `zpix` carries
    no broadband mags.
  * **Spectroscopic features.** Emission-line widths and equivalent
    widths from the redshift fit are useful for galaxy / AGN
    classification; reserve for the metadata inspector's
    *Spectroscopy* tab.
  * **`DESI_TARGET` bit decoding.** The bitmask encodes target
    classes (BGS, LRG, ELG, QSO, …); a future helper can expand it
    into a list of strings stored alongside the raw integer.
  * **Cosmology-aware distance.** Replace the Hubble-only helper
    with a FlatLambdaCDM integrator. Same signature; callers don't
    change.
  * **HEALPix tile alignment.** DESI rows already carry a `healpix`
    index; the future production index can fold those into the same
    HEALPix tiling used by Gaia for free.
  * **Async TAP.** Large queries should go through the TAP async
    interface. Add a `fetch_async(query) → JobHandle` once the sync
    path proves insufficient.

The connector is intentionally minimal. It exists to prove the
adapter contract holds for the cosmological-survey class of source —
where the natural distance scale is gigaparsec, the natural
identifier is a bit-encoded `TARGETID`, and the natural quality gate
is the redshift `ZWARN` bitmask.
