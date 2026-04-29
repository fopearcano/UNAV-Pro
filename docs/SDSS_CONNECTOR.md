# UNAV Pro — SDSS Connector

Cone-search connector for the Sloan Digital Sky Survey, targeting the
public DR18 SkyServer SQL endpoint:

```
https://skyserver.sdss.org/dr18/SkyServerWS/SearchTools/SqlSearch
```

Stub status. The function signatures, the SQL surface, the column
mapping, and the test surface are all production-shaped, but the
live HTTP path is exercised only against mocked responses in this
MVP. The same `fetch_fn`-injected design that powers the Gaia and
Horizons connectors lets `_http_fetch` go live without any caller-
visible change.

Companion to `UNAV_PRO_DATA_PIPELINE.md`, `GAIA_CONNECTOR.md`, and
`JPL_HORIZONS_CONNECTOR.md` — same adapter pattern, different
source.

---

## 1. Scope

  * **Cone search** around (RA, Dec) with a row cap.
  * **Photometric backbone with optional spectro join.** The default
    SQL hits `PhotoObj` and left-joins `SpecObj` so rows that
    happen to have a spectrum carry redshift; rows that do not still
    flow through with photometry only.
  * **Object types covered:** stars, galaxies, quasars (via the
    spectroscopic `class` field; photometric `type` provides a
    coarser fallback).
  * **No credentials.** SkyServer is public; UNAV identifies itself
    with a User-Agent string and otherwise issues a vanilla HTTPS
    GET.
  * **Stdlib only.** `urllib`, `csv`, `json`, `dataclasses`. No
    `sciserver`, no `astroquery`, no `pandas`.

Releases supported: `sdss_dr18` (default) and `sdss_dr17`. Adding a
future release is a one-line addition to `_RELEASE_TO_ENDPOINT`.

---

## 2. CLI

`tools/fetch_sdss_region.py` is the canonical entry point.

```bash
python tools/fetch_sdss_region.py \
    --ra 180.0 --dec 30.0 --radius-deg 0.2 \
    --limit 5000 \
    --output data/sdss_sample.jsonl
```

| Flag                  | Default       | Notes                                                      |
|-----------------------|---------------|------------------------------------------------------------|
| `--ra`                | required      | Cone-center RA in degrees, `[0, 360)`.                     |
| `--dec`               | required      | Cone-center Dec in degrees, `[-90, 90]`.                   |
| `--radius-deg`        | required      | Cone radius in degrees, `(0, 30]`.                         |
| `--limit`             | 5 000         | Max rows; bounded at 100 000.                              |
| `--release`           | `sdss_dr18`   | One of `sdss_dr18`, `sdss_dr17`.                           |
| `--output`            | required      | Output JSONL path; parents are created.                    |
| `--no-spectro`        | off           | Skip the SpecObj join (photometry only — faster query).    |
| `--redshift-max-z`    | 0.1           | Above this z, `distance_parsec` stays None.                |
| `--quiet`             | off           | Suppress the summary line.                                 |

Exit codes: 0 ok, 2 invalid args, 3 archive failure.

---

## 3. SQL strategy

`build_sql(query)` emits SkyServer-flavoured SQL using the canonical
`dbo.fGetNearbyObjEq(ra_deg, dec_deg, radius_arcmin)` table-valued
function. SkyServer's cone-search function accepts arcminutes, so the
connector multiplies `radius_deg * 60` before splicing the value into
the SQL string.

Default query (with `include_spectro=True`):

```sql
SELECT TOP 5000
    p.objID, p.ra, p.dec, p.type,
    p.modelMag_u, p.modelMag_g, p.modelMag_r,
    p.modelMag_i, p.modelMag_z,
    s.specObjID,
    s.z AS spec_z, s.zErr AS spec_zerr,
    s.class AS spec_class, s.subClass AS spec_subclass
FROM PhotoObj p
LEFT JOIN SpecObj s ON s.bestObjID = p.objID
JOIN dbo.fGetNearbyObjEq(180.0, 30.0, 12.0) n
    ON p.objID = n.objID
ORDER BY p.modelMag_r ASC
```

`ORDER BY p.modelMag_r ASC` puts brighter (lower-magnitude) objects
first so a user-supplied `--limit` truncates the noise floor rather
than the signal.

`--no-spectro` drops the `LEFT JOIN SpecObj` and the spectro columns;
photometry-only queries are noticeably faster on the SkyServer side
and useful when the caller does not care about redshifts.

---

## 4. UNAV mapping

| UNAV field           | Source                                                                  |
|----------------------|-------------------------------------------------------------------------|
| `uid`                | `sdss_dr18:<objID>` (release-prefixed for cross-source disambiguation). |
| `catalog_source`     | The release: `sdss_dr18` / `sdss_dr17`.                                 |
| `object_type`        | `SpecObj.class` (`GALAXY`/`QSO`/`STAR`) when present; otherwise `PhotoObj.type` (3 → galaxy, 6 → star); else `unknown`. |
| `name`               | `objID` as a string.                                                    |
| `ra_deg` / `dec_deg` | `p.ra` / `p.dec`, validated to ICRS ranges.                             |
| `redshift`           | `SpecObj.z` if present.                                                 |
| `distance_parsec`    | Coarse Hubble-law inversion if `0 < z ≤ redshift_max_z`; else `None`.   |
| `apparent_magnitude` | `modelMag_r` (the most stable single-band magnitude across the survey). |
| `color_index`        | `modelMag_g - modelMag_r` when both present.                            |
| `metadata_json`      | All five `modelMag_*` magnitudes, `spec_class`, `spec_subclass`, `specobjid`, `spec_zerr`, `photo_type`, `release`. |

Spectroscopic class always wins over photometric type. A galaxy that
turns out to be a QSO via SpecObj is correctly tagged `quasar` even
though its `PhotoObj.type` is 3.

---

## 5. Redshift → distance

`safe_redshift_to_distance(z, z_err, max_z, h0)` performs the same
"only when safe" pattern as the Gaia parallax helper:

  * `z` missing or ≤ 0 → `None`.
  * `z > max_z` (default 0.1) → `None`. Above that the naive Hubble
    inversion `c·z / H₀` diverges from cosmology-aware comoving
    distance and is misleading. The schema's placeholder-sphere
    fallback then takes over.
  * Otherwise: `distance_pc = (c · z / H₀) × 10⁶`.

Constants: `c = 299 792.458 km/s`, `H₀ = 70 km/s/Mpc`. Both are
overridable per-call.

The proper cosmology-aware integrator (FlatLambdaCDM with Ω_m, Ω_Λ
parameters) is a future tightening — see `UNAV_PRO_DATA_PIPELINE.md`
§5 for the framing. Until then the connector is honest: high-z
quasars stay on the placeholder sphere with their redshift recorded
in `metadata_json` for downstream tools to consume.

---

## 6. Failure modes

| Situation                          | Behavior                                            |
|------------------------------------|-----------------------------------------------------|
| Argument out of range              | `ValueError` at `SDSSQuery`; CLI exits 2.           |
| HTTP non-200 / network error       | `SDSSQueryError`; CLI exits 3.                      |
| SkyServer comment header line      | `_parse_csv` strips leading `#`-prefixed lines before `csv.DictReader` so the response is parsed cleanly. |
| Individual bad row                 | Counted in the log, skipped — never aborts the run. |
| Missing `objID` / `ra` / `dec`     | Row silently skipped (counted).                     |
| Out-of-range coordinates           | Row silently skipped (counted).                     |

The connector does not retry on transient errors. Adding
exponential-backoff retries is a small change to `_http_fetch`;
deferred until rate-limit data justifies it.

---

## 7. Testing

`unav_pro/tests/test_sdss_connector.py` covers the connector with
**no network access** — every test injects a `fetch_fn` that returns
a hand-crafted CSV body.

  * `SDSSQuery` validation (RA / Dec / radius / limit / release).
  * SQL builder — cone function with arcminute conversion, photo +
    spectro columns, optional spectro join.
  * `safe_redshift_to_distance` — zero / negative / above-max /
    custom max-z / Hubble-law correctness.
  * Row → `CatalogObject` normalization — galaxy with spectro,
    quasar overrides photo type, star via photo type, unknown when
    neither matches, missing/invalid id and position skipped, null
    strings handled.
  * `fetch_rows` — strips SkyServer's `#`-prefixed comment header,
    correct URL/SQL/params, empty body, fetcher exception
    propagation.
  * `fetch_and_normalize` end-to-end.

Integration tests against the live SkyServer belong in a separate
`tools/qa/` script run on demand.

---

## 8. Roadmap

  * **Photometric SDSS imaging metadata.** `petroR50_r`, `expRad_r`,
    morphology classifiers (`fracDeV_r`, etc.) — useful for galaxy
    type filtering. One commit's worth of additions to the column
    tuple plus `metadata_json`.
  * **Quality flags.** `clean`, `flags`, `calibStatus_r` — gate
    by photometric quality the same way Gaia gates by parallax SNR.
  * **Spectroscopic line measurements.** `emLineKin`, `lineSigma_*`
    — useful for nebular galaxies / AGN. Reserve for the metadata
    inspector's *Spectroscopy* tab.
  * **Cosmology-aware distance.** Replace the Hubble-only helper
    with a FlatLambdaCDM integrator. The function signature stays
    the same; callers don't change.
  * **Async TAP.** Large queries should go through SciServer's async
    job interface. Add a `fetch_async(query) → JobHandle` once the
    sync path proves insufficient.

The connector is intentionally minimal. It exists to prove the
adapter contract from `UNAV_PRO_DATA_PIPELINE.md` §3 holds for
spectroscopic / extragalactic surveys, the same way the Gaia
connector proves it for stellar astrometry.
