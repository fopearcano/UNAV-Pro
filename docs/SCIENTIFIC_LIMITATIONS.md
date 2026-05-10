# UNAV Pro — Scientific Limitations

The honest list of what UNAV is **not**, and where the
science is intentionally coarse. Read this before you
make claims based on UNAV output.

This document is part of the v3.2 self-describing
contract: every export package embeds a `known_limitations`
field; the entries below are the canonical superset.

For the milestone overview see
[`V3_2_DATA_INTEGRITY.md`](V3_2_DATA_INTEGRITY.md).

---

## 1. UNAV is a visualisation tool

UNAV produces **scenes**, not science. The plugin
populates Cinema 4D with real catalog data and helps an
artist plan camera movement through it. Real astrometric
work uses astropy / SOFA / SPICE outside UNAV.

Concretely: do not cite UNAV measurements in a paper.
Do cite the upstream catalog (Gaia DR3, JPL Horizons,
SDSS, DESI) and use UNAV to communicate the results
visually.

## 2. Coordinate system

* UNAV's canonical frame is **ICRS Cartesian parsec**.
  Stars from Gaia, galaxies from SDSS / DESI, and JPL
  bodies all land in this frame after the connectors'
  normalisation pass.
* C4D world units are 1 parsec by default
  (`scale_mode="parsec_to_cm"`). A custom scale only
  affects the C4D-side display; the underlying
  coordinates remain ICRS pc.
* No precession, nutation, aberration, or relativistic
  corrections are applied. For cinematic camera work
  these effects are below the visible threshold.

## 3. Distance proxies

* **Parallax → distance** (Gaia): `d = 1000 / parallax_mas`,
  applied only when parallax is positive and signal-to-
  noise is above the connector's floor (default 5.0).
  Negative-parallax rows are kept but get no distance.
* **Redshift → distance** (SDSS / DESI): a coarse
  Hubble-law proxy `d = c·z / H₀` with `H₀ = 70 km/s/Mpc`.
  Tagged `approximate` in the v0.5 connector and in
  every science-layer rendering. **Not cosmology-grade.**
  See [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) for
  the historical context.
* **Magnitude shells** (v2.1) are illustrative spheres
  derived from the apparent-magnitude → distance rule
  of thumb; they are **cosmetic**.

## 4. Time + epochs

* Default epoch is **J2000.0** (JD 2451545.0).
* Gaia proper-motion catalogs are **J2016 reference**;
  the v1.2 time navigator propagates to other epochs
  but does not apply secular acceleration.
* JPL Horizons ephemeris rows are **time-series** keyed
  by JD. The v1.2 resolver picks the nearest snapshot;
  there is no spline interpolation between rows.
* Heliocentric vs barycentric: UNAV does not distinguish
  them in the visible-sector pipeline. For solar-system
  cinematics the difference is below the visible
  threshold.

## 5. Photometry

* Magnitudes ride straight through from the source
  catalog. Vega vs AB mag is a per-source convention;
  the v3.2 unit validator accepts both but does not
  convert.
* Color index (`B-V`) is used by the visual-encoding
  layer (v0.6) for star colour. The mapping is
  cosmetic; not a temperature-calibrated colour.
* **Extinction** (interstellar reddening) is **not
  applied**. Gaia distances and magnitudes are reported
  raw. For accurate colours the artist must apply
  extinction outside UNAV.

## 6. Coordinate-system corner cases

* The DB schema's `cartesian_x/y/z` columns are
  pre-computed from `(ra, dec, distance)` at ingest
  time. If the artist edits a row's RA/Dec/distance in
  the inspector, the Cartesian columns are **not**
  recomputed automatically. (Re-import to refresh.)
* Solar-system bodies use the JPL Horizons body's own
  reference plane, not the ecliptic. For cinematic
  work the difference is invisible.

## 7. Validation probes are sanity checks, not science

The v3.2 validation probes catch **placeholder bugs**
and **ingestion mismatches**:

* `parallax > 10 000 mas` (no real star is this close)
* `redshift > 15` (no real source is this far)
* `distance > 14.5 Gpc` (past the observable universe)
* `redshift < 0` (only blueshifted local-group members)

These are **sanity bounds**, not cosmological models.
A row that passes the probes is not "verified
correct"; it just isn't obviously wrong.

## 8. Out of scope

* No relativistic effects (light travel time, beaming,
  redshift-from-velocity).
* No detector noise / completeness modelling.
* No survey selection-function correction.
* No spectral classification beyond what the upstream
  catalog provides.
* No light-curve / time-series interpolation.
* No interstellar / intergalactic extinction.

## 9. Embedded in every export

Every v3.2 export package's `manifest.json` carries:

* `provenance_summary` — the aggregate of distinct
  sources / connectors / coordinate systems /
  fetched-at stamps for the active datasets.
* `audit_summary` — counts of issues from the most
  recent dataset audit (rows total / issues / by
  severity / by code).
* `coordinate_conventions` — free-form description of
  the science-side coordinate system (ICRS Cartesian
  parsec by default).
* `known_limitations` — the caveats from this document
  most relevant to the export.

A consumer reading the manifest can tell, from the
package alone, what UNAV is and isn't. That's the v3.2
contract.
