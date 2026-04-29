# UNAV Pro — Data Pipeline

**Project:** C4D Universal Navigator Pro
**Document status:** Draft v0.1
**Companion docs:** UNAV_PRO_ARCHITECTURE.md, UNAV_PRO_C4D_PLUGIN_STRATEGY.md

---

## 1. Pipeline overview

The data pipeline is a one-way flow:

```
  External archives
        |
        v
  [1] Source adapter        per-catalog fetch + parse
        |
        v
  [2] Normalizer            map raw fields to canonical schema
        |
        v
  [3] Coordinate stage      ICRS/heliocentric -> galactic Cartesian (pc, float64)
        |
        v
  [4] Quality / cuts        astrometric quality, distance bounds, magnitude cuts
        |
        v
  [5] Crossmatch            optional positional match across sources
        |
        v
  [6] Tiler                 partition into HEALPix cells x distance shells
        |
        v
  [7] Decimator             produce LOD levels per tile
        |
        v
  [8] Writer                Parquet tiles + SQLite manifest
        |
        v
  Local cache  <----  consumed by spatial index + plugin
```

Stages 1–8 are offline, idempotent, and resumable. The plugin never runs
stages 1–7 inline with viewport interaction; it only reads stage 8 output.

---

## 2. Supported sources (initial set)

| Source        | Release  | Approx. rows     | Primary use in UNAV          |
|---------------|----------|------------------|------------------------------|
| Gaia          | DR3      | 1.8 B            | Stellar astrometry, photometry, distances within Milky Way |
| Hipparcos/Tycho-2 | re-reduction | 2.5 M     | Bright-star backbone, named stars |
| SDSS          | DR18     | ~ 1 B objects    | Extragalactic photometry, redshifts |
| DESI          | EDR / DR1| 10–40 M spectra  | Galaxy/quasar redshifts, large-scale structure |
| NASA/JPL Horizons | live | bodies, not catalog | Solar-system bodies, ephemerides |
| NASA Exoplanet Archive | live | ~ 6 k    | Exoplanet host stars, planetary metadata |
| Open Exoplanet Catalogue | mirror | ~ 4 k | Cross-reference |

Each source is implemented as an adapter behind the same interface so adding
a future catalog (e.g. Euclid, LSST/Rubin, JWST source catalog) is a new
adapter, not a pipeline change.

---

## 3. Adapter contract

Every source adapter implements:

```
class SourceAdapter:
    name: str
    release: str
    schema_version: int

    def discover(self) -> list[Partition]:
        # enumerate available tiles / files / queries
        ...

    def fetch(self, partition: Partition) -> RawBatch:
        # download or stream raw rows for one partition
        ...

    def normalize(self, raw: RawBatch) -> CanonicalBatch:
        # map to canonical schema (see section 4)
        ...

    def provenance(self, partition: Partition) -> Provenance:
        # URL, checksum, license, ingest timestamp
        ...
```

Adapters never write to the cache directly; they yield `CanonicalBatch`
objects to the pipeline driver, which is the single writer.

---

## 4. Canonical schema

Stored as Parquet, one row per object, per source. Cross-source merging
happens at query time via `match_group_id`, not by collapsing rows.

| Column                | Type      | Notes                                     |
|-----------------------|-----------|-------------------------------------------|
| `uid`                 | uint64    | Globally unique inside UNAV               |
| `source`              | dict<str> | e.g. `gaia_dr3`, `sdss_dr18`              |
| `source_id`           | string    | Native catalog ID                         |
| `match_group_id`      | uint64    | Crossmatch group, 0 if unmatched          |
| `ra_deg`              | float64   | ICRS                                      |
| `dec_deg`             | float64   | ICRS                                      |
| `parallax_mas`        | float32   | Nullable                                  |
| `parallax_error_mas`  | float32   | Nullable                                  |
| `distance_pc`         | float32   | Derived if parallax usable, else null     |
| `distance_method`     | dict<str> | `parallax`, `photometric`, `redshift`, …  |
| `redshift_z`          | float32   | Nullable                                  |
| `pm_ra_masyr`         | float32   | Proper motion, RA*cos(dec)                |
| `pm_dec_masyr`        | float32   |                                           |
| `radial_velocity_kms` | float32   | Nullable                                  |
| `epoch_jyear`         | float32   | Reference epoch                           |
| `x_pc`, `y_pc`, `z_pc`| float64   | Galactic Cartesian, barycentric           |
| `mag_g`, `mag_bp`,    | float32   | Photometric bands; null if absent         |
| `mag_rp`, `mag_u`,    |           |                                           |
| `mag_r`, `mag_i`, …   |           |                                           |
| `abs_mag_g`           | float32   | Derived if distance available             |
| `color_bp_rp`         | float32   |                                           |
| `object_type`         | dict<str> | `star`, `galaxy`, `quasar`, `planet`, …   |
| `quality_flags`       | uint32    | Bitfield, source-specific meaning         |
| `extra`               | json      | Raw source row, retained for inspector    |

`x_pc/y_pc/z_pc` are the canonical position used by the spatial index. They
are computed once at ingest using the source's own distance estimate and the
chosen `distance_method`. Objects without a usable distance are placed on a
"distant sphere" at a configurable radius and flagged so the index can
exclude them from depth-sensitive queries.

---

## 5. Coordinate transform stage

1. Start in ICRS spherical `(ra_deg, dec_deg, distance_pc)`.
2. Convert to ICRS Cartesian (parsec).
3. Rotate to galactic Cartesian using the IAU 1958 / Hipparcos rotation.
4. Origin remains barycentric; UNAV's *floating origin* is applied later, at
   query time, not at ingest.

Transforms use `astropy.coordinates` in the Python pipeline. Results are
stored in `float64` to keep precision at megaparsec scale.

For solar-system bodies (JPL Horizons), positions are time-dependent; we do
not store Cartesian columns. The adapter stores SPK / OEM kernels and the
engine evaluates positions on demand at the requested epoch.

---

## 6. Quality cuts and configuration

The pipeline does not silently drop data. Cuts are expressed as named
**profiles** in `pipeline.yaml`:

```yaml
profiles:
  gaia_default:
    require: [parallax_mas]
    parallax_over_error_min: 5.0
    distance_pc_max: 10000
    mag_g_max: 20.0
  gaia_full:
    require: []
  sdss_galaxies:
    object_type: [galaxy]
    redshift_z_min: 0.0
    redshift_z_max: 2.0
```

The plugin's preferences page lets the user pick which profile is used when
ingesting each source. Profiles are recorded in tile provenance so a scene
knows exactly which cuts produced its data.

---

## 7. Crossmatch

Stage 5 is optional and runs after all sources for a given region are
ingested.

- **Algorithm.** k-d tree positional match on galactic Cartesian, with
  source-specific tolerance (typical: 1″ for Gaia↔SDSS, 5″ for SDSS↔DESI).
- **Output.** Adds `match_group_id` to every matched row; unmatched rows
  keep `match_group_id = 0`.
- **Cost.** O(N log N); tractable per HEALPix cell, which is how we run it.
- **Re-runs.** Crossmatch is rerun whenever a new source is added in a
  region; group IDs are stable across reruns via a deterministic hash of
  the member uids.

---

## 8. Tiling and LOD

### 8.1 Spatial tiling

- Sky is partitioned by **HEALPix** at one or more `Nside` levels per
  source. Default: Gaia `Nside = 256` (~13.4′ cells), SDSS `Nside = 64`,
  DESI `Nside = 64`.
- Each sky cell is further split into **distance shells** (log-spaced):
  e.g. `[0, 10, 100, 1000, 10⁴, 10⁵, 10⁶, 10⁷, 10⁸, 10⁹] pc`.
- A *tile* is the intersection: one HEALPix cell × one distance shell ×
  one source.

### 8.2 LOD

Each tile is written at multiple decimations:

| Level | Sampling   | Used when                                   |
|-------|------------|---------------------------------------------|
| L0    | full       | tile fully inside view frustum and close    |
| L1    | 1 in 16    | mid-range                                   |
| L2    | 1 in 256   | far / off-axis                              |
| L3    | 1 in 4096  | very far / overview shots                   |

Decimation is brightness-weighted: brighter objects are kept preferentially,
so the silhouette of the Milky Way is preserved at every level. The exact
weighting is a configurable function of `mag_g` (or the relevant band).

LOD selection at query time is driven by the projected pixel density target
(see ARCHITECTURE §3.4). The index returns the coarsest level that meets
the target; the plugin can override per-tile.

---

## 9. Storage layout on disk

```
<cache_root>/
  manifest.sqlite                      # global manifest, ingestion log
  sources/
    gaia_dr3/
      profile.yaml                     # cuts used
      tiles/
        nside256/
          pix_000123/
            shell_03/
              L0.parquet
              L1.parquet
              L2.parquet
              L3.parquet
              meta.json                # row count, bbox, hashes
    sdss_dr18/
      ...
  bakes/
    <project>/<bake_id>.unavbake       # filtered baked subsets
```

Parquet is chosen for columnar compression, predicate pushdown, and zero-
copy mmap into numpy via `pyarrow`. SQLite holds the manifest because it is
transactional, single-file, and dependency-free.

---

## 10. Update and freshness policy

- **Releases.** Catalog releases are immutable from our point of view; we
  pin to a specific release (`gaia_dr3`, not `gaia_latest`). Upgrading to
  `gaia_dr4` is an explicit user action and writes to a new directory.
- **Live sources.** JPL Horizons and the NASA Exoplanet Archive are
  re-fetched on a TTL (default: 7 days). The plugin warns if a scene
  references stale live data.
- **Integrity.** Each tile records SHA-256 of its source download; the
  pipeline verifies on read and refuses to serve corrupted tiles.

---

## 11. Error handling and resumability

- The pipeline driver writes a **work log** to `manifest.sqlite` keyed by
  `(source, partition, stage)`. Every stage is idempotent.
- A failed run resumes from the last completed stage per partition.
- Network and parse errors are recorded with the partition; they don't fail
  the whole run.
- Quotas / rate limits on remote archives are respected via a per-source
  token-bucket configured in the adapter.

---

## 12. Engine query API (cache → spatial index → plugin)

The plugin doesn't talk to Parquet directly. The engine exposes:

```
query_frustum(camera, near_pc, far_pc, max_points, lod_hint) -> PointBuffer
query_cone(apex_pc, axis, half_angle_rad, length_pc, max_points) -> PointBuffer
query_ray(origin_pc, dir, tol_pc, max_results) -> list[uid]
query_id(uid) -> CanonicalRow
query_bbox_pc(min_pc, max_pc, max_points, lod_hint) -> PointBuffer
list_sources() -> list[SourceInfo]
ingest(source, profile, region) -> JobHandle
job_status(handle) -> JobStatus
```

`PointBuffer` is a struct-of-arrays:
`uid[u64], x[f32], y[f32], z[f32], color[u32 packed], size[f16], flags[u16]`,
with positions already in C4D world units relative to the current floating
origin so the plugin can blit them straight into a particle buffer.

---

## 13. Pipeline tooling

The pipeline is a standalone CLI, separate from the C4D plugin:

```
unav-ingest  --source gaia_dr3 --profile gaia_default --region all
unav-tile    --source gaia_dr3 --nside 256
unav-bake    --scene path/to/file.unavscene --out filtered.unavbake
unav-verify  --source gaia_dr3
unav-cache   --gc                    # LRU eviction
```

This tooling is what runs on a workstation overnight to produce the cache;
it is also what a studio's pipeline / asset team would call from a render
farm. The plugin shells out to the same code via the engine protocol when
the user clicks "Ingest" in the UI, but heavy ingestion is meant to be done
out of band.

---

## 14. Licensing and attribution

Every adapter records:

- the source's citation requirement,
- its license / data-policy URL,
- a flag indicating whether redistribution of the cache is permitted.

The plugin's *About / Data* dialog enumerates all data sources currently
referenced by the open scene, with citations. Bakes carry the same metadata
inside the `.unavbake` manifest so downstream users can attribute correctly.
