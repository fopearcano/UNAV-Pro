# UNAV Pro v0.4 — JPL Horizons Solar-System Epoch Workflow

The second real-data import path: fetch a list of solar-system
bodies (planets, moons, asteroids, comets, spacecraft) from the
public NASA/JPL Horizons web API at one chosen epoch, normalize
them into the UNAV schema, optionally build the chunked spatial
index, and load them alongside Gaia stars in Cinema 4D.

This document covers the recommended end-to-end workflow. For
the connector internals (request shape, response parsing, units,
failure semantics) see
[`JPL_HORIZONS_CONNECTOR.md`](JPL_HORIZONS_CONNECTOR.md). For the
coordinate / epoch contract that underlies every emitted row see
[`SOLAR_SYSTEM_COORDINATES_AND_EPOCHS.md`](SOLAR_SYSTEM_COORDINATES_AND_EPOCHS.md).
For mixing JPL and Gaia in one C4D scene see
[`MIXED_DATASET_WORKFLOW.md`](MIXED_DATASET_WORKFLOW.md).

---

## 1. Prerequisites

* Python 3.9+ (the same interpreter Cinema 4D ships with works
  fine, but the CLIs do **not** require Cinema 4D).
* A working internet connection to `ssd.jpl.nasa.gov`.
* No Horizons credentials. The web API is public.
* Stdlib only. No `astroquery`, no `astropy`, no SPICE kernels.

---

## 2. The CLIs

UNAV Pro ships two Horizons-facing tools:

* **`tools/fetch_jpl_body.py`** — single body, one epoch. Useful
  for one-off lookups (a probe, a single comet, a target asteroid).
* **`tools/fetch_jpl_solar_system.py`** — batch fetch a list of
  bodies at the same epoch. Per-body failures are recorded but do
  not abort the batch.

### 2.1 Single body

```
python tools/fetch_jpl_body.py \
    --body "Mars" \
    --epoch "2026-01-01T00:00:00" \
    --center "500@10" \
    --output data/catalogs/jpl_mars_2026.jsonl
```

| Flag                  | Default      | Notes                                                         |
|-----------------------|--------------|---------------------------------------------------------------|
| `--body`              | required     | Horizons body designation (name, NAIF ID, or `DES=...`).      |
| `--epoch`             | required     | Any time format Horizons accepts (ISO date, `JDxxxxx`, etc.). |
| `--center`            | `@10` (Sun)  | Observer center. `500@10` is an alias for the Sun.            |
| `--object-type`       | `planet`     | One of `planet/moon/asteroid/comet/spacecraft/unknown`.       |
| `--output`            | required     | Output JSONL path. Parent directories are created.            |
| `--build-index`       | none         | Optional output directory for a chunked spatial index.        |
| `--index-chunk-size`  | 1000         | Max rows per index chunk file.                                |
| `--quiet`             | off          | Suppress the summary line on stdout.                          |

Exit codes: **0** ok, **2** invalid arguments, **3** Horizons
query / parse failed.

### 2.2 Batch (planet pack)

```
python tools/fetch_jpl_solar_system.py \
    --epoch "2026-01-01T00:00:00" \
    --bodies "Mercury,Venus,Earth,Mars,Jupiter,Saturn,Uranus,Neptune,Pluto,Moon=moon" \
    --center "500@10" \
    --output data/catalogs/jpl_solar_system_2026.jsonl \
    --build-index cache/jpl_solar_system_2026
```

| Flag                    | Default      | Notes                                                                     |
|-------------------------|--------------|---------------------------------------------------------------------------|
| `--epoch`               | required     | Single epoch shared by every body in the batch.                           |
| `--bodies`              | required     | Comma-separated body designations. Each may carry `=type` to override.    |
| `--default-object-type` | `planet`     | Default `object_type` for bodies without an explicit suffix.              |
| `--center`              | `@10` (Sun)  | Observer center.                                                          |
| `--output`              | required     | Output JSONL path.                                                        |
| `--build-index`         | none         | Optional output directory for a chunked spatial index.                    |
| `--index-chunk-size`    | 1000         | Max rows per index chunk file.                                            |
| `--quiet`               | off          | Suppress the summary line on stdout.                                      |

Exit codes: **0** at least one body succeeded (per-body errors
on stderr if partial), **2** invalid arguments / unknown
`object_type`, **3** every body failed.

The `--bodies` parser accepts a per-body `=type` suffix:

```
--bodies "Mercury,Venus,Earth,Mars,Moon=moon,Voyager 1=spacecraft"
```

Bodies without an explicit suffix inherit `--default-object-type`.

---

## 3. UNAV mapping

Every emitted row conforms to the canonical `CatalogObject`
schema (`unav_pro/data/schema.py`). Per the v0.4 contract:

| UNAV field                  | Source                                                                                |
|-----------------------------|---------------------------------------------------------------------------------------|
| `uid`                       | `jpl:{body}:{epoch}` — release-agnostic, registry will namespace.                     |
| `catalog_source`            | `"JPL Horizons"` — human-readable label.                                              |
| `object_type`               | from CLI (`planet/moon/asteroid/comet/spacecraft/unknown`).                           |
| `name` / `common_name`      | the body designation as passed in.                                                    |
| `cartesian_x/y/z`           | populated **directly** from the Horizons (X, Y, Z) heliocentric vector in parsec.     |
| `c4d_x/y/z`                 | equal to `cartesian_x/y/z` at default `scale_mode="pc"`.                              |
| `ra_deg` / `dec_deg`        | derived from the same vector for inspector display.                                   |
| `distance_parsec`           | derived from the same vector.                                                         |
| `metadata_json`             | `body`, `epoch`, `center`, `ref_plane`, `out_units`, `vector_au`, `vector_pc`, `distance_au`, `distance_km`, optional velocity components, Horizons `signature`. |

The body designation, epoch, and observer center live in
`metadata_json`, **not** elsewhere on the row, so the inspector
can show them and the registry's namespace prefix
(`<dataset_name>:`) layers on top of the connector's `jpl:`
prefix without collisions.

---

## 4. The recommended end-to-end workflow

```
1. Pick an epoch (e.g. 2026-01-01T00:00:00) and a body list.

2. Fetch + index (offline; runs anywhere, no Cinema 4D required):

       python tools/fetch_jpl_solar_system.py \
           --epoch "2026-01-01T00:00:00" \
           --bodies "Mercury,Venus,Earth,Mars,Jupiter,Saturn,Uranus,Neptune,Pluto,Moon=moon" \
           --center "500@10" \
           --output data/catalogs/jpl_solar_system_2026.jsonl \
           --build-index cache/jpl_solar_system_2026

3. In Cinema 4D, open Universal Navigator Pro.

4. Open the Dataset Manager and Add Dataset for the JSONL file.
   Set the Index Path to cache/jpl_solar_system_2026.

5. (Optional) Add the Gaia regional dataset from v0.3 alongside.

6. Load Active Datasets.

7. Click Create Navigation Null, position it, then
   Sync Visible Sector. Bodies inside the cone become C4D nulls
   under UNAV_VisibleSector with the source-aware visual encoding.

8. Click any body → Inspect Selected Object. The inspector shows
   the epoch, observer center, the heliocentric vector in AU and
   parsec, and the distance in AU and km.
```

---

## 5. Failure modes

| Scenario                                | What happens                                                              |
|-----------------------------------------|---------------------------------------------------------------------------|
| Network down / DNS failure              | `JPLHorizonsError`; single-body CLI exits 3.                              |
| HTTP 4xx / 5xx (incl. rate limiting)    | `JPLHorizonsError` carrying status + first 300 chars of body; exits 3.    |
| Body designation matches multiple bodies| `JPLHorizonsError` with the candidates excerpt; exits 3.                  |
| Body not found                          | `JPLHorizonsError` with Horizons's "No matches" text; exits 3.            |
| Empty / malformed `$$SOE` block         | `JPLHorizonsError` with the offending block excerpt; exits 3.             |
| Invalid epoch                           | Horizons rejects the request; surfaced as `JPLHorizonsError`; exits 3.    |
| Invalid argument (unknown object_type)  | CLI exits 2 with a clear `error:` line.                                   |
| Soft-batch warning (> 25 bodies)        | Printed on stderr; batch proceeds.                                        |
| Partial batch failure                   | Per-body errors printed on stderr; surviving bodies are written; exits 0. |
| Every body in batch failed              | `error: every body failed`; exits 3.                                      |

The connector never embeds the full Horizons metadata blob into
generated C4D objects. The blob lives in the catalog file and
gets pulled by the inspector via the uid lookup.

---

## 6. What this v0.4 milestone explicitly does **not** add

* **No orbital animation.** Static point at the requested epoch
  only; per-frame ephemerides are deferred.
* **No SPICE kernels.** The connector talks to the public
  Horizons web API; SPK / BSP support is deferred.
* **No new survey connectors.** SDSS / DESI ingestion is not
  changed in this milestone.
* **No automatic in-plugin Horizons download.** The CLIs are the
  only Horizons-fetch surface; the plugin reads the resulting
  cache.
* **No new C4D scene primitives.** Visible-sector generation
  remains nulls under `UNAV_VisibleSector` with the v0.1
  minimal-marker policy intact.
