# UNAV Pro — Data Source Overview

The four real-catalog connectors UNAV Pro ships, at a glance.
For per-source detail, follow the link in each row.

| Source        | Connector / CLI                                                      | Endpoint                                                          | Object types it surfaces                | Object-type tag UNAV applies | Distance source                       |
|---------------|-----------------------------------------------------------------------|-------------------------------------------------------------------|------------------------------------------|------------------------------|----------------------------------------|
| Gaia DR3 / DR2 | [`tools/fetch_gaia_region.py`](../tools/fetch_gaia_region.py) · [doc](GAIA_CONNECTOR.md) | `gea.esac.esa.int/tap-server/tap/sync` (TAP / ADQL)              | Stars                                    | `star`                       | Parallax (Gaia); SNR-gated (default 5σ). |
| SDSS DR18 / DR17 | [`tools/fetch_sdss_region.py`](../tools/fetch_sdss_region.py) · [doc](SDSS_CONNECTOR.md) | `skyserver.sdss.org/dr18/SkyServerWS/SearchTools/SqlSearch` (SQL) | Galaxies, quasars, stars                 | from `SpecObj.class` → `galaxy`/`quasar`/`star` (else `unknown`) | Hubble-law from `SpecObj.z` when `0 < z ≤ 0.1`; else `None`. |
| DESI EDR / DR1 | [`tools/fetch_desi_region.py`](../tools/fetch_desi_region.py) · [doc](DESI_CONNECTOR.md) | `datalab.noirlab.edu/tap/sync` (TAP / ADQL)                       | Galaxies, quasars, stars                 | from `SPECTYPE` → `galaxy`/`quasar`/`star` | Hubble-law from `Z` when `0 < z ≤ 0.1` and `ZWARN == 0`. |
| NASA / JPL Horizons | [`tools/fetch_jpl_body.py`](../tools/fetch_jpl_body.py) · [doc](JPL_HORIZONS_CONNECTOR.md) | `ssd.jpl.nasa.gov/api/horizons.api` (web)                         | Planets, moons, asteroids, comets, spacecraft | caller picks via `--object-type` (`planet` / `moon` / `asteroid` / `comet` / `spacecraft`) | Cartesian `(X, Y, Z)` in heliocentric ICRF (J2000), AU-D, converted to parsec. |

All connectors:

* Stdlib only (`urllib`, `csv`, `json`). No `astroquery`, no
  `astropy`, no `pandas`, no credentials.
* Hard cap on cone radius (30°) and row count (100 000) to
  prevent typo'd queries from overrunning the public archives.
* `fetch_fn` injection so tests run **offline** against hand-
  crafted mocked responses; full test coverage of every parsing
  and edge case path.
* Failure modes surface as `<Connector>QueryError` and the CLI
  exits with status `3` (network/archive failure) or `2`
  (invalid argument).

---

## Common UNAV mapping

Every connector emits rows that conform to the canonical
[`unav_pro/data/schema.py`](../unav_pro/data/schema.py)
`CatalogObject` shape:

| UNAV field            | Set by every connector? |
|-----------------------|--------------------------|
| `uid`                 | Yes — release-prefixed (`gaia_dr3:<id>`, `sdss_dr18:<id>`, `desi_edr:<id>`, `jpl_horizons:<slug>@<epoch>`). |
| `catalog_source`      | Yes — the release name.   |
| `object_type`         | Yes — see table above.    |
| `ra_deg` / `dec_deg`  | Yes — ICRS, validated.    |
| `name`                | Yes — original ID or body name. |
| `metadata_json`       | Yes — release-specific extras (parallax error, photometry, ZWARN, vector components, signature). |

Optional fields filled when the source provides them:

* `parallax_mas`, `distance_parsec`, `radial_velocity_kms`,
  `proper_motion_ra/dec` — Gaia.
* `redshift`, `apparent_magnitude`, `color_index` — SDSS, DESI.
* `distance_parsec` from heliocentric Cartesian magnitude — JPL
  Horizons.

---

## Pipeline shape: connector → cache → plugin

```
remote archive         (Gaia ESA / SkyServer / NOIRLab TAP / Horizons)
       │
       ▼
fetch_<source>_*.py    one cone, one HTTPS request, no creds
       │
       ▼
*.jsonl                UNAV-format catalog rows on disk
       │  (optional)
       ▼
build_spatial_index    chunked grid + index.json
       │
       ▼
DatasetRegistry        in-plugin entry; per-user persistence
       │
       ▼
MetadataLookup         merged uid → CatalogObject (namespaced)
       │
       ▼
spatial_filter +       cone gate against the navigator
spatial_index queries
       │
       ▼
point_cloud_builder    one C4D Onull per surviving uid
```

The plugin never opens an HTTPS socket. Data fetch is offline,
batch, repeatable; the live workflow is "filter the local cache."

---

## Choosing a source

* **"Stars near the Sun, with proper motion."** → Gaia DR3, with
  the default 5σ parallax cut. Tight cone (≤ 0.5°) at a known
  position, brightest first.
* **"Galaxies in a sky region with redshifts."** → SDSS DR18
  with the spectro join, or DESI EDR with `--spectype GALAXY`.
  DESI has cleaner redshift quality flags via `ZWARN` and a more
  uniform survey footprint; SDSS has broader photometry.
* **"Quasars at high redshift."** → DESI EDR with
  `--spectype QSO`. Distances stay `None` past z = 0.1 by
  default; the rows still flow through and the inspector shows
  the redshift.
* **"Solar-system body for foreground."** → JPL Horizons. One
  body per CLI call; pick the appropriate `--object-type`.

For multi-source scenes (the typical pro workflow — see
[`PRO_WORKFLOW.md`](PRO_WORKFLOW.md)), register every source in
the dataset manager and let *Load Active Datasets* merge them
with namespaced uids.

---

## Per-source caveats

* **Gaia.** Negative parallaxes are noise; the connector keeps
  them in `parallax_mas` but sets `distance_parsec = None`. Below
  the SNR floor (default 5), same behaviour.
* **SDSS.** The CLI's default joins `PhotoObj` with `SpecObj`,
  which can be slow on the public archive for big regions. Use
  `--no-spectro` for photometry-only queries; the resulting rows
  carry `redshift = None`.
* **DESI.** `ZWARN != 0` is the catalog's "this redshift fit is
  suspect" flag; the connector preserves the redshift on the row
  but suppresses the Hubble-distance derivation. The inspector
  shows both.
* **JPL Horizons.** Disambiguation: a name like "Mars" matches
  both the planet and the Mars system barycenter. The connector
  raises `JPLHorizonsError` with the candidate excerpt; pass a
  NAIF ID (`499` for Mars) or a more specific name to resolve.

---

## Adding a new source

The connector contract is documented in
[`UNAV_PRO_DATA_PIPELINE.md`](UNAV_PRO_DATA_PIPELINE.md) §3 and
the four shipping connectors are the reference implementation.
The minimum a new connector needs:

1. A request builder (ADQL / SQL / form-encoded params, whatever
   the archive accepts).
2. A `fetch_rows(query, fetch_fn=None)` returning raw row dicts;
   the `fetch_fn` injection point is what makes tests run
   offline.
3. A `normalize_rows(rows)` mapping the source columns onto
   `CatalogObject`.
4. A CLI in `tools/` that bootstraps `unav_pro/` onto
   `sys.path` and calls the connector.

Add a per-source doc following the pattern of the four shipping
connector docs. Update this overview table.
