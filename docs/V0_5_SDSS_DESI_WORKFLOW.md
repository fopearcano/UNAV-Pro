# UNAV Pro v0.5 — SDSS / DESI Extragalactic Workflow

The third real-data import path: fetch a small sky region from SDSS
DR18 (photometry + spectro redshifts) or DESI EDR / DR1
(spectroscopic redshifts), normalize to the UNAV schema, optionally
build the chunked spatial index, and load alongside Gaia stars and
JPL solar-system bodies in Cinema 4D — with redshift-aware visual
encoding and an inspector that flags approximate distances.

This document covers the recommended end-to-end workflow. For the
underlying caveats see
[`REDSHIFT_DISTANCE_LIMITATIONS.md`](REDSHIFT_DISTANCE_LIMITATIONS.md).
For the redshift colour mode see
[`EXTRAGALACTIC_VISUAL_ENCODING.md`](EXTRAGALACTIC_VISUAL_ENCODING.md).
For mixed-catalog scenes see
[`MIXED_DATASET_WORKFLOW.md`](MIXED_DATASET_WORKFLOW.md).

---

## 1. Prerequisites

* Python 3.9+ (the same interpreter Cinema 4D ships with works
  fine, but the CLIs do **not** require Cinema 4D).
* A working internet connection to:
  * `skyserver.sdss.org` (SDSS), or
  * `datalab.noirlab.edu` (DESI via NOIRLab Astro Data Lab).
* No SDSS / DESI credentials. Both endpoints are public.
* Stdlib only. No `astroquery`, no `astropy`, no `pandas`.

---

## 2. The CLIs

### 2.1 SDSS region

```
python tools/fetch_sdss_region.py \
    --ra 180.0 \
    --dec 0.0 \
    --radius-deg 0.5 \
    --limit 5000 \
    --output data/catalogs/sdss_region_sample.jsonl \
    --build-index cache/sdss_region_sample
```

| Flag                  | Default      | Notes                                                                |
|-----------------------|--------------|----------------------------------------------------------------------|
| `--ra`                | required     | Cone-center RA in degrees `[0, 360)`.                                |
| `--dec`               | required     | Cone-center Dec in degrees `[-90, 90]`.                              |
| `--radius-deg`        | required     | Cone radius in degrees `(0, 30]`.                                    |
| `--limit`             | 5000         | Max rows; bounded at 100 000 (hard).                                 |
| `--release`           | `sdss_dr18`  | `sdss_dr18` / `sdss_dr17`.                                           |
| `--output`            | required     | Output JSONL path. Parent directories are created.                   |
| `--no-spectro`        | off          | Skip the SpecObj redshift join (photometry only).                    |
| `--build-index`       | none         | Optional output directory for a chunked spatial index.               |
| `--index-chunk-size`  | 5000         | Max rows per index chunk file.                                       |
| `--redshift-max-z`    | 0.1          | Max redshift for the linear Hubble proxy.                            |
| `--quiet`             | off          | Suppress the summary line on stdout.                                 |

Exit codes: **0** ok, **2** invalid arguments, **3** archive query
failed.

### 2.2 DESI region

```
python tools/fetch_desi_region.py \
    --ra 180.0 \
    --dec 0.0 \
    --radius-deg 0.5 \
    --limit 5000 \
    --output data/catalogs/desi_region_sample.jsonl \
    --build-index cache/desi_region_sample
```

| Flag                  | Default      | Notes                                                                |
|-----------------------|--------------|----------------------------------------------------------------------|
| `--ra` / `--dec` / `--radius-deg` | required | same as SDSS.                                                |
| `--limit`             | 5000         | Max rows; bounded at 100 000 (hard).                                 |
| `--release`           | `desi_edr`   | `desi_edr` / `desi_dr1`.                                             |
| `--spectype`          | none         | Optional server-side filter: `GALAXY` / `QSO` / `STAR`.              |
| `--output`            | required     | Output JSONL path.                                                   |
| `--build-index`       | none         | Optional output directory for a chunked spatial index.               |
| `--index-chunk-size`  | 5000         | Max rows per index chunk file.                                       |
| `--redshift-max-z`    | 0.1          | Max redshift for the linear Hubble proxy.                            |
| `--quiet`             | off          | Suppress the summary line on stdout.                                 |

Same exit codes as SDSS.

---

## 3. UNAV mapping

Every emitted row conforms to the canonical `CatalogObject` schema
(`unav_pro/data/schema.py`). Per the v0.5 contract:

### 3.1 SDSS

| UNAV field                | Source                                                                                    |
|---------------------------|-------------------------------------------------------------------------------------------|
| `uid`                     | `sdss:{specObjID or objID}` — release-agnostic; spectro id preferred when present.        |
| `catalog_source`          | `"SDSS"` — human-readable label.                                                          |
| `object_type`             | `star` / `galaxy` / `quasar` / `unknown`. Spec class beats photometric type when present. |
| `ra_deg` / `dec_deg`      | ICRS, validated.                                                                          |
| `redshift`                | SpecObj `z` when joined; else `None`.                                                     |
| `distance_parsec`         | Linear Hubble proxy at `0 < z ≤ 0.1`; otherwise `None`.                                   |
| `apparent_magnitude`      | `modelMag_r`.                                                                             |
| `color_index`             | `modelMag_g − modelMag_r`.                                                                |
| `metadata_json`           | `objid`, `specobjid`, `release` (`sdss_dr18` / `sdss_dr17`), `spec_class`, `spec_subclass`, all five `modelMag_*`, `photo_type`, optional `distance_method` / `distance_proxy_*` fields when a proxy distance was returned. |

### 3.2 DESI

| UNAV field                | Source                                                                                    |
|---------------------------|-------------------------------------------------------------------------------------------|
| `uid`                     | `desi:{targetid}` — release-agnostic.                                                     |
| `catalog_source`          | `"DESI"` — human-readable label.                                                          |
| `object_type`             | from `SPECTYPE`: `galaxy` / `quasar` / `star` / `unknown`.                                |
| `ra_deg` / `dec_deg`      | from `target_ra`/`target_dec`; ICRS, validated.                                           |
| `redshift`                | `z`.                                                                                      |
| `distance_parsec`         | Linear Hubble proxy at `0 < z ≤ 0.1` **and** `zwarn == 0`; otherwise `None`.              |
| `metadata_json`           | `targetid`, `release` (`desi_edr` / `desi_dr1`), `spectype`, `subtype`, `zerr`, `zwarn`, `desi_target`, `survey`, `program`, `healpix`, optional `distance_method` / `distance_proxy_*` fields when a proxy distance was returned. |

The release token (`sdss_dr18` / `desi_edr` / etc.) lives in
`metadata_json`, not in the uid, so two releases of the same
source land on the same uid and the inspector can show both
records side-by-side via the lookup.

---

## 4. The recommended end-to-end workflow

```
1. Pick a sky region.

2. Fetch + index (offline; runs anywhere, no Cinema 4D required):

       python tools/fetch_sdss_region.py \
           --ra 180.0 --dec 0.0 --radius-deg 0.5 \
           --limit 5000 \
           --output data/catalogs/sdss_region_sample.jsonl \
           --build-index cache/sdss_region_sample

       python tools/fetch_desi_region.py \
           --ra 180.0 --dec 0.0 --radius-deg 0.5 \
           --limit 5000 \
           --output data/catalogs/desi_region_sample.jsonl \
           --build-index cache/desi_region_sample

3. In Cinema 4D, open Universal Navigator Pro.

4. Open the Dataset Manager and Add Dataset for each JSONL,
   pointing each entry's Index Path at its matching cache
   directory.

5. (Optional) Add the Gaia and JPL datasets from v0.3 / v0.4
   alongside.

6. Disable the bundled sample. Click Load Active Datasets.

7. Click Create Navigation Null. Position and rotate it.

8. Click Sync Visible Sector. The streaming layer queries
   each dataset's index independently; only the cells the
   navigator's cone touches are loaded.

9. In the Visual Encoding panel:
     - Color Mode → Redshift (extragalactic colour ramp), or
                    Catalog Source (one colour per survey).
     - Size  Mode → Object Type (galaxies/quasars larger than
                    Gaia stars), or Magnitude.

10. Click any object → Inspect Selected Object:
      - Redshift z and the survey/program/object-class fields
        appear under "Survey / Class".
      - Approximate-distance objects are flagged with
        "APPROXIMATE — Distance derived from naive Hubble's
        law…" in the Astrometry section.
```

---

## 5. Failure modes

| Scenario                                 | What happens                                                              |
|------------------------------------------|---------------------------------------------------------------------------|
| Network down / DNS failure               | `SDSSQueryError` / `DESIQueryError`; CLI exits 3.                         |
| HTTP 4xx / 5xx (incl. rate limiting)     | error carries status + first 300 chars of body; CLI exits 3.              |
| Empty result set                         | CLI prints `warning: query returned 0 usable rows` on stderr; exits 0.    |
| Invalid argument (out-of-range coords)   | CLI exits 2 with a clear `error:` line.                                   |
| Unknown release / spectype               | CLI exits 2.                                                              |
| Malformed CSV row                        | Counted in the log, dropped from the output. The rest succeeds.           |
| Negative / zero / missing redshift       | Row flows through; `distance_parsec` stays `None`; raw value preserved.   |
| `zwarn != 0` on a DESI row               | Row flows through; `distance_parsec` stays `None`; `zwarn` preserved.     |
| Redshift above `--redshift-max-z`        | Row flows through; `distance_parsec` stays `None`; no proxy stamp.        |

The connector never embeds the full archive metadata blob into
generated C4D objects. The blob lives in the catalog file and
gets pulled by the inspector via the uid lookup.

---

## 6. What this v0.5 milestone explicitly does **not** add

* **No cosmology-grade comoving distance.** All
  redshift-derived distances are linear Hubble proxies gated at
  `z ≤ 0.1`. See
  [`REDSHIFT_DISTANCE_LIMITATIONS.md`](REDSHIFT_DISTANCE_LIMITATIONS.md).
* **No huge catalog fetch.** The 100 000-row hard cap remains.
* **No automatic in-plugin SDSS / DESI download.** The CLIs are
  the only fetch surface; the plugin reads the resulting cache.
* **No new C4D scene primitives.** Visible-sector generation
  remains nulls under `UNAV_VisibleSector` with the v0.1
  minimal-marker policy intact.
* **No crossmatch.** A Gaia source and a SDSS or DESI counterpart
  for the same physical object are two separate inspector
  entries.
