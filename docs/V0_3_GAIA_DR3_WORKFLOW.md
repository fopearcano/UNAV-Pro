# UNAV Pro v0.3 — Gaia DR3 Regional Workflow

The first real-data import path: fetch a small Gaia DR3 sky region
from the public ESA archive, normalize it into the UNAV schema,
optionally build the chunked spatial index, and use it inside the
sector-streaming visible-sector pipeline established in v0.2.

This document covers the recommended end-to-end workflow. For the
hard limits and safety policies the connector enforces, see
[`GAIA_QUERY_LIMITS_AND_SAFETY.md`](GAIA_QUERY_LIMITS_AND_SAFETY.md).
For the streaming layer that consumes the resulting cache, see
[`V0_2_SECTOR_STREAMING_WORKFLOW.md`](V0_2_SECTOR_STREAMING_WORKFLOW.md).

---

## 1. Prerequisites

* Python 3.9+ (the same interpreter Cinema 4D ships with works
  fine, but the CLIs do **not** require Cinema 4D).
* A working internet connection to `gea.esac.esa.int`.
* No Gaia credentials. The TAP endpoint is public.
* Stdlib only. No `astroquery`, no `astropy`, no `pandas`.

---

## 2. The CLI

```
python tools/fetch_gaia_region.py \
    --ra 56.75 \
    --dec 24.12 \
    --radius-deg 1.0 \
    --limit 5000 \
    --output data/catalogs/gaia_pleiades_sample.jsonl
```

| Flag                  | Default          | Notes                                                                |
|-----------------------|------------------|----------------------------------------------------------------------|
| `--ra`                | required         | Cone-center RA in degrees `[0, 360)`.                                |
| `--dec`               | required         | Cone-center Dec in degrees `[-90, 90]`.                              |
| `--radius-deg`        | required         | Cone radius in degrees `(0, 30]`.                                    |
| `--limit`             | 5000             | Max rows; bounded at 100 000 (hard) with a soft warning above 50 000. |
| `--release`           | `gaia_dr3`       | One of `gaia_dr3` / `gaia_dr2`.                                      |
| `--output`            | required         | Output JSONL path. Parent directories are created.                   |
| `--build-index`       | none             | Optional output directory for a chunked spatial index.               |
| `--index-chunk-size`  | 5000             | Max rows per index chunk file.                                       |
| `--parallax-snr-min`  | 5.0              | Min `parallax / parallax_error` to derive `distance_parsec`.         |
| `--no-parallax-cut`   | off              | Skip the SNR cut entirely.                                           |
| `--quiet`             | off              | Suppress the summary line on stdout.                                 |

Exit codes: **0** ok, **2** invalid arguments (out-of-range
coordinates / radius / limit / unknown release), **3** archive
query failed.

---

## 3. Fetch + index in one command

For a sector-streaming-ready cache, ask the CLI to build the index
inline:

```
python tools/fetch_gaia_region.py \
    --ra 56.75 --dec 24.12 --radius-deg 1.0 \
    --limit 5000 \
    --output data/catalogs/gaia_pleiades_sample.jsonl \
    --build-index cache/gaia_pleiades
```

That writes:

* `data/catalogs/gaia_pleiades_sample.jsonl` — the normalized
  catalog.
* `cache/gaia_pleiades/index.json` — manifest.
* `cache/gaia_pleiades/chunks/cell_<i>_<j>_<k>/chunk_NN.jsonl` —
  per-cell chunks.

When the artist registers the JSONL in the **Dataset Manager** and
sets the `index_path` to `cache/gaia_pleiades`, the C4D plugin
streams only the cells the navigator's cone touches.

---

## 4. UNAV mapping

Every emitted row conforms to the canonical `CatalogObject` schema
(`unav_pro/data/schema.py`). Per the v0.3 contract:

| UNAV field                | Source                                                               |
|---------------------------|----------------------------------------------------------------------|
| `uid`                     | `gaia:{source_id}` — release-agnostic, registry will namespace.      |
| `catalog_source`          | `"Gaia DR3"` (or `"Gaia DR2"`) — human-readable label.               |
| `object_type`             | `"star"`.                                                            |
| `name`                    | The Gaia `source_id` as a string.                                    |
| `ra_deg` / `dec_deg`      | ICRS, validated.                                                     |
| `parallax_mas`            | Raw Gaia parallax, including non-positive values.                    |
| `distance_parsec`         | `1000 / parallax_mas` only when safe; otherwise `None` (placeholder sphere). |
| `proper_motion_ra` / `_dec` | Gaia `pmra` / `pmdec` (mas/yr).                                    |
| `radial_velocity_kms`     | Gaia `radial_velocity` when present (km/s).                          |
| `apparent_magnitude`      | Gaia `phot_g_mean_mag`.                                              |
| `color_index`             | Gaia `bp_rp`.                                                        |
| `metadata_json`           | All raw Gaia fields preserved verbatim (`source_id`, `release`, RA, Dec, parallax + error, pmra, pmdec, RV, G-mag, BP-RP). |

The `release` token (`gaia_dr3` / `gaia_dr2`) lives in
`metadata_json`, not in the uid, so two releases of the same
source land on the same uid and the inspector can show both
records side-by-side via the lookup.

---

## 5. The recommended end-to-end workflow

```
1. Pick a sky region.

2. Fetch + index (offline; runs anywhere, no Cinema 4D required):

       python tools/fetch_gaia_region.py \
           --ra 56.75 --dec 24.12 --radius-deg 1.0 \
           --limit 5000 \
           --output data/catalogs/gaia_pleiades_sample.jsonl \
           --build-index cache/gaia_pleiades

3. In Cinema 4D, open Universal Navigator Pro.

4. Open the Dataset Manager and Add Dataset for the JSONL file.
   Set the Index Path to cache/gaia_pleiades (or rebuild via
   Build Index inside the dialog).

5. Disable the bundled sample. Load Active Datasets.

6. Click Create Navigation Null. Position and rotate it.

7. Click Sync Visible Sector. The status log shows the streaming
   summary:

       +N added, =0 kept, -0 removed; stream: M visible (of K candidates)

   K is the number of rows the cone-vs-cell prefilter loaded from
   disk; M is what survived the exact filter; N is what landed in
   the C4D scene. The full Gaia subset never enters memory.

8. Click any UNAV object → Inspect Selected Object. The full Gaia
   record is read from the metadata lookup.
```

The same JSONL file works without `--build-index` for small
catalogs (≤ a few thousand rows): the streaming path falls back
to a full load with no warning. Above the size threshold the
fallback is loud — see
[`GAIA_QUERY_LIMITS_AND_SAFETY.md`](GAIA_QUERY_LIMITS_AND_SAFETY.md).

---

## 6. Failure modes

| Scenario                                | What happens                                                            |
|-----------------------------------------|-------------------------------------------------------------------------|
| Network down / DNS failure              | `GaiaQueryError`; CLI exits 3.                                          |
| HTTP 4xx / 5xx (incl. rate limiting)    | `GaiaQueryError` carrying status + first 300 chars of body; CLI exits 3.|
| Empty result set                        | CLI prints `warning: query returned 0 usable rows` on stderr; exits 0.  |
| Invalid argument (out-of-range coords)  | CLI exits 2 with a clear `error:` line.                                 |
| Soft-limit warning (limit > 50 000)     | Printed on stderr; query proceeds.                                      |
| Soft-radius warning (radius > 5°)       | Printed on stderr; query proceeds.                                      |
| Negative parallax                       | Row flows through; `distance_parsec` stays `None`; raw value preserved. |
| Low SNR parallax (below `--parallax-snr-min`) | Same as negative — row keeps `parallax_mas`, drops `distance_parsec`. |
| Missing optional column in CSV          | Skipped silently in normalization; raw row retains what it had.         |
| Malformed CSV row                       | Counted in the log, dropped from the output. The rest of the import succeeds. |

The connector never embeds the full Gaia metadata blob into
generated C4D objects. The blob lives in the catalog file and
gets pulled by the inspector via the uid lookup.

---

## 7. What this v0.3 milestone explicitly does **not** add

* **No SDSS / DESI work.** Those connector docs already exist
  (`SDSS_CONNECTOR.md` / `DESI_CONNECTOR.md`); they were not
  changed in this milestone.
* **No huge catalog fetch.** The 100 000-row hard cap remains.
* **No automatic in-plugin Gaia download.** The CLI is the only
  Gaia-fetch surface; the plugin reads the resulting cache.
* **No new C4D scene primitives.** Visible-sector generation
  remains nulls under `UNAV_VisibleSector` with the v0.1
  minimal-marker policy intact.
