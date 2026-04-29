# UNAV Pro — Gaia Connector

The first real catalog adapter shipped with UNAV Pro. Fetches a small
sky region from the public Gaia ESA archive over HTTP/TAP and writes
a UNAV-format JSONL catalog ready for the rest of the pipeline.

Companion to:

  * `UNAV_PRO_DATA_PIPELINE.md` (canonical schema + adapter contract)
  * `SPATIAL_INDEXING_AND_CHUNKING.md` (where the JSONL output goes
    next)
  * `INSTALL_C4D_2023_PLUS.md` (the plugin that consumes the index)

---

## 1. Scope

  * **Read-only.** Cone search around (RA, Dec) with a hard row cap.
  * **Small regions.** The CLI's `--radius-deg` is bounded at 30°; the
    `--limit` is bounded at 100 000. Anything bigger should go through
    the production tiling pipeline (HEALPix + distance shells), not
    this single-region tool.
  * **No credentials.** The Gaia archive is public; UNAV identifies
    itself with a User-Agent string and otherwise issues a vanilla
    HTTPS request.
  * **No heavy dependencies.** Stdlib only — `urllib`, `csv`, `json`,
    `dataclasses`. No `astroquery`, no `astropy`. Runs on a clean
    Python install.

Releases supported: `gaia_dr3` (default) and `gaia_dr2`. Adding a
future release is a one-line addition to
`_RELEASE_TO_TABLE` in
`unav_pro/data/connectors/gaia_connector.py`.

---

## 2. CLI

`tools/fetch_gaia_region.py` is the canonical entry point. It
bootstraps the plugin's `unav_pro/` directory onto `sys.path` so it
runs without Cinema 4D installed.

```bash
python tools/fetch_gaia_region.py \
    --ra 56.75 --dec 24.12 --radius-deg 1.0 \
    --limit 5000 \
    --output data/gaia_sample.jsonl
```

| Flag                  | Default     | Notes                                                                 |
|-----------------------|-------------|-----------------------------------------------------------------------|
| `--ra`                | required    | Cone-center RA in degrees, `[0, 360)`.                                |
| `--dec`               | required    | Cone-center Dec in degrees, `[-90, 90]`.                              |
| `--radius-deg`        | required    | Cone radius in degrees, `(0, 30]`.                                    |
| `--limit`             | 5 000       | Max rows; bounded at 100 000.                                         |
| `--release`           | `gaia_dr3`  | One of `gaia_dr3`, `gaia_dr2`.                                        |
| `--output`            | required    | Output JSONL path; parents are created.                               |
| `--parallax-snr-min`  | 5.0         | Min `parallax / parallax_error` to derive `distance_parsec`.          |
| `--no-parallax-cut`   | off         | Compute distance for any positive parallax (still ignores ≤ 0).       |
| `--quiet`             | off         | Suppress the summary line.                                            |

Exit codes:

  * **0** — success (including zero-row results, with a warning).
  * **2** — invalid arguments (out-of-range RA/Dec/radius/limit, …).
  * **3** — Gaia archive query failed (network error, HTTP non-200,
    rate-limiting). The MVP does not retry — let the operator wait
    and rerun.

Pipe the output through `tools/build_spatial_index.py` to produce a
chunked cache the plugin can query:

```bash
python tools/build_spatial_index.py \
    --input data/gaia_sample.jsonl \
    --output cache/gaia_pleiades \
    --chunk-size 5000
```

---

## 3. Column mapping (Gaia DR3 → UNAV)

Implemented in `_row_to_object` in
`unav_pro/data/connectors/gaia_connector.py`.

| Gaia column             | UNAV field             | Notes                                                |
|-------------------------|------------------------|------------------------------------------------------|
| `source_id`             | `uid`, `name`          | `uid` is prefixed: `gaia_dr3:<source_id>`.           |
| (constant)              | `catalog_source`       | `"gaia_dr3"` / `"gaia_dr2"` per release.             |
| (constant)              | `object_type`          | `"star"` — Gaia's source table is overwhelmingly stellar; refinement happens at crossmatch time. |
| `ra`                    | `ra_deg`               | ICRS, validated to `[0, 360)`.                       |
| `dec`                   | `dec_deg`              | ICRS, validated to `[-90, 90]`.                      |
| `parallax`              | `parallax_mas`         | Raw value preserved, including non-positive ones.    |
| `parallax_error`        | `metadata_json.parallax_error_mas` | Used for the SNR cut, retained for inspection. |
| `parallax`+error → derived | `distance_parsec`   | See §4 — only set when safe.                         |
| `pmra`                  | `proper_motion_ra`     | mas/yr.                                              |
| `pmdec`                 | `proper_motion_dec`    | mas/yr.                                              |
| `radial_velocity`       | `radial_velocity_kms`  | km/s.                                                |
| `phot_g_mean_mag`       | `apparent_magnitude`   | Drives the render-radius mapping in the schema.      |
| `bp_rp`                 | `color_index`          | Reserved for a future spectral-class derivation.     |

Anything Gaia returns that UNAV does not surface is dropped, by
design. Adding a new field is a small change to the column tuple plus
the row mapper plus a test row.

---

## 4. Parallax → distance

`safe_parallax_to_distance(parallax_mas, parallax_error_mas, snr_min,
distance_pc_max)` returns `None` if any of these hold:

  * parallax is missing or `≤ 0` (negative-parallax noise);
  * parallax error is provided and `parallax / error < snr_min`
    (default 5.0);
  * implied distance > `distance_pc_max` (default 100 kpc — beyond
    this, Bayesian distance priors dominate the naive `1000/π`
    inversion).

Otherwise returns `1000.0 / parallax_mas` in pc.

When the helper returns `None`, the row still flows through to UNAV
with `distance_parsec = None`. The schema then places the object on
the placeholder celestial sphere at compute-derived time, tagged
via `metadata_json.distance_method = "placeholder_sphere"`. Downstream
filtering can trivially exclude these via that tag if a scene wants
parallax-confirmed stars only.

The CLI exposes both knobs:

  * `--parallax-snr-min 0` accepts every positive parallax (dangerous
    for distance interpretation but useful for surveys).
  * `--no-parallax-cut` is shorthand for the same.

---

## 5. Failure modes

| Class                    | Behavior                                           |
|--------------------------|----------------------------------------------------|
| Argument out of range    | CLI exits with code 2 and an `error:` line on stderr. |
| HTTP non-200             | `GaiaQueryError`; CLI exits with code 3.           |
| Network down / DNS fail  | `GaiaQueryError`; CLI exits with code 3.           |
| Empty CSV body           | Returns 0 rows; CLI prints a `warning:` and writes an empty JSONL. |
| Individual bad row       | Counted in the log, skipped — never aborts the run. |

The connector does **not** retry on rate-limit (HTTP 429) or service
unavailable (HTTP 503). Adding retries with exponential backoff is a
local change to `_http_fetch`; deferred until we have rate-limit
data from real-world use.

---

## 6. Testing

`unav_pro/tests/test_gaia_connector.py` covers the connector with
**no network access** — every test injects a `fetch_fn` that returns
a hand-crafted CSV body.

  * `GaiaQuery` validation — RA/Dec/radius/limit ranges, unknown
    release.
  * ADQL builder — required columns present, ICRS cone geometry,
    brightest-first ordering, release-specific table name.
  * `safe_parallax_to_distance` — negative / missing / low-SNR /
    high-SNR / disabled cut / implausibly far.
  * Row → CatalogObject normalization — full row, missing identifier,
    missing position, out-of-range position, missing optional fields,
    null-string handling, low-SNR parallax keeps `parallax_mas` raw
    while leaving `distance_parsec` as None.
  * `fetch_rows` with injected fetcher — verifies URL, FORMAT, LANG,
    QUERY params; empty body; propagates fetcher errors.
  * `fetch_and_normalize` end-to-end — keeps good rows, skips bad
    ones, threads the release name through.

These tests are deliberately offline. Integration tests against the
live Gaia archive are out of scope for the unit-test suite — they
belong in a separate `tools/qa/` script run on demand.

---

## 7. Roadmap

  * **Resumable streaming.** TAP also exposes an async endpoint for
    queries that exceed the sync timeout. The connector will gain
    `fetch_async(query) -> JobHandle` once the sync path proves
    insufficient.
  * **Quality flags.** Gaia DR3 carries `astrometric_excess_noise`,
    `ruwe`, etc. The MVP does not surface these; extending the
    column tuple + the `extra` blob is a one-commit change once
    callers ask for them.
  * **Crossmatch IDs.** Hipparcos / Tycho-2 / 2MASS cross-IDs ride in
    side tables (e.g. `gaiadr3.tycho2tdsc_merge_best_neighbour`).
    They are reserved for the production crossmatch stage described
    in `UNAV_PRO_DATA_PIPELINE.md` §7, not this MVP.
  * **Other releases.** The connector is parameterized on release
    and table name; adding a future Gaia DR4 is one entry in
    `_RELEASE_TO_TABLE`.

The connector is intentionally one of the smallest things in the
repo. It exists to prove the adapter contract from
`UNAV_PRO_DATA_PIPELINE.md` §3 holds end-to-end before we add
SDSS, DESI, JPL Horizons, and the rest.
