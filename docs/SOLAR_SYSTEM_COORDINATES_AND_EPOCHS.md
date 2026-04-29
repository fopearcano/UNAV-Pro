# Solar-System Coordinates and Epochs

How UNAV Pro represents JPL Horizons solar-system bodies in the
canonical schema, and what it means to ask Horizons for an
"epoch". This is the contract every row emitted by the v0.4 JPL
connector follows; the
[`V0_4_JPL_HORIZONS_WORKFLOW.md`](V0_4_JPL_HORIZONS_WORKFLOW.md)
walkthrough builds on it.

---

## 1. The reference frame

UNAV Pro asks Horizons for **heliocentric ICRF Cartesian state
vectors** at the requested epoch:

| Horizons option | Value          | Meaning                                                      |
|-----------------|----------------|--------------------------------------------------------------|
| `EPHEM_TYPE`    | `VECTORS`      | Position + velocity components, not RA/Dec angles.           |
| `CENTER`        | `@10` (Sun)    | Heliocentric. Other valid values: `@0` (SSB), `500@399` (Earth-geo), etc. |
| `REF_PLANE`     | `FRAME`        | ICRF / J2000 equatorial, **not** ecliptic.                   |
| `OUT_UNITS`     | `AU-D`         | Distances in AU, time in days.                               |
| `VEC_TABLE`     | `2`            | State vector + light-time + range.                           |

Why heliocentric ICRF, not geocentric ecliptic:

* **Heliocentric** keeps distances physically meaningful for a
  static interstellar / interplanetary scene. A geocentric frame
  would force every body to "orbit Earth" in the C4D scene,
  which is not what the navigator workflow wants.
* **ICRF (J2000) equatorial** is the same frame Gaia uses. That
  alignment is what lets v0.4 mix Gaia stars and JPL bodies in
  one C4D scene without a frame transform.
* **AU-D** is what Horizons natively emits; UNAV converts to
  parsec for storage so the schema stays in one canonical unit.

The connector lives in
`unav_pro/data/connectors/jpl_horizons_connector.py`; the
constants above are visible at the top of `build_request_params`.

---

## 2. From Horizons (X, Y, Z) to UNAV columns

A successful Horizons response embeds a free-form text block
between `$$SOE` and `$$EOE` markers. The connector pulls
`X = ...`, `Y = ...`, `Z = ...` (and the optional `VX/VY/VZ`,
`LT`, `RG`, `RR`) out of that block.

The (X, Y, Z) triple is in **AU**. UNAV converts to parsec:

```
1 pc = 648000 / π  AU
1 AU = π / 648000  pc  ≈ 4.84813681e-6 pc
```

and writes the body's position into the schema like this:

| UNAV field          | Source                                                                 |
|---------------------|------------------------------------------------------------------------|
| `cartesian_x/y/z`   | `(X_au, Y_au, Z_au) * AU_TO_PC` — written **directly**.                |
| `c4d_x/y/z`         | At default `scale_mode="pc"`, equal to `cartesian_x/y/z`.              |
| `ra_deg`            | `atan2(Y_pc, X_pc)`, normalized to `[0, 360)`.                         |
| `dec_deg`           | `asin(Z_pc / |r|)`.                                                    |
| `distance_parsec`   | `sqrt(X_pc² + Y_pc² + Z_pc²)`.                                         |

The `cartesian_*` and `c4d_*` columns are populated **directly**
by the connector — UNAV does **not** round-trip through
RA/Dec/distance for solar-system bodies. The spherical fields are
present for the inspector and for the visible-sector cone test,
but the source of truth is the cartesian vector.

That direct-write matters because solar-system distances in
parsec are tiny (Mars is ~1e-5 pc from the Sun): a
spherical→Cartesian round-trip at low distance amplifies floating
point error.

---

## 3. The epoch contract

"Epoch" in v0.4 is **a single instant**:

* Every emitted row is a snapshot. There is no animation, no
  per-frame ephemeris, no light-time correction across frames.
* The single-body CLI takes one `--epoch`. The batch CLI takes
  one `--epoch` shared by every body so the entire snapshot is
  consistent.
* Horizons accepts a wide range of formats: ISO date
  (`2026-01-01`), ISO datetime (`2026-01-01T00:00:00`),
  Julian-Day (`JD 2461041.5`), `MJD`, named time (`now`), etc.
  UNAV passes the string through verbatim — anything Horizons
  accepts works.
* Internally the connector requests a 24-hour window with a
  one-day step (`STEP_SIZE='1d'`) so Horizons returns exactly one
  ephemeris row. The `effective_stop()` helper appends `+1d` to
  the start time so callers do not have to manage this.

The epoch lives in two places on each emitted row:

* In the **uid** as `jpl:{body}:{epoch}`. Two different epochs
  for the same body get distinct uids and never collide.
* In **`metadata_json`** as `epoch`, alongside `center`,
  `vector_au`, `vector_pc`, `distance_au`, `distance_km`, and
  the optional velocity components and Horizons signature.

---

## 4. The uid contract

```
uid = "jpl:{body}:{epoch}"
```

* Body and epoch segments are lightly slugged: whitespace and
  slashes become underscores. Colons, dots, dashes, and
  underscores survive — so an ISO timestamp like
  `2026-01-01T00:00:00` keeps its colons.
* The release token (`jpl_horizons`) is **not** in the uid; it
  lives in `metadata_json`. Two Horizons releases of the same
  body at the same epoch land on the same uid and the inspector
  can show both records side-by-side via the lookup.
* The `jpl:` prefix is **disjoint** from the Gaia connector's
  `gaia:` prefix, so Gaia stars and JPL bodies coexist on the
  metadata lookup with zero collision risk. The dataset registry
  layers its own `<dataset_name>:` namespace on top.

---

## 5. Coordinate handling round-trip

For sector streaming and the visible-sector cone test, UNAV's
spatial filter walks `cartesian_x/y/z` directly. When the
visible-sector builder uses a non-`pc` `scale_mode`,
`compute_derived_fields` re-derives `c4d_x/y/z` from the
spherical fields. Because the connector writes consistent
spherical and Cartesian fields (both derived from the same AU
vector), the round-trip is idempotent at any `scale_mode`.

Concretely:

```
Horizons (X, Y, Z) AU
        │
        │   * AU_TO_PC
        ▼
cartesian_x/y/z (pc)              ← written directly
        │
        │   spherical
        ▼
ra_deg, dec_deg, distance_parsec  ← derived
        │
        │   compute_derived_fields, scale_mode in {pc, au, ly, …}
        ▼
c4d_x/y/z                          ← consumed by point cloud builder
```

For the default `scale_mode="pc"`, the third arrow is the
identity: `c4d_x/y/z == cartesian_x/y/z`.

---

## 6. Distance units in `metadata_json`

Solar-system distances in parsec are uncomfortably small for the
inspector (Mars at ~7e-6 pc reads as zero at three significant
figures). The connector therefore embeds **three** units in
`metadata_json` so the inspector and any downstream tools have a
sensible choice:

* `vector_au` — `{"X": …, "Y": …, "Z": …}` in AU, the natural
  unit for inner-system bodies.
* `vector_pc` — same triple converted to parsec, useful when
  comparing to a Gaia neighbor.
* `distance_au` and `distance_km` — scalar magnitudes for the
  inspector. `1 AU = 1.49597870700e8 km` (IAU 2012 definition).

The `out_units` field records `"AU-D"` so a future per-frame
sampler knows what time unit the velocities (`vx/vy/vz`) carry.

---

## 7. What this contract intentionally leaves out

* **No SPICE kernels.** Light-time correction, planetary
  occultation tests, and per-frame ephemerides need SPK / BSP
  data; v0.4 stays on the public web API.
* **No frame transforms.** Heliocentric ICRF in, heliocentric
  ICRF out. Geocentric or ecliptic projections are deferred.
* **No moving objects.** A row is a snapshot; the navigator
  workflow re-fetches at a new epoch via the CLI when the artist
  wants a different time.
* **No barycentric option in the CLI.** The connector accepts
  `--center "@0"` (SSB) but the recommended workflow stays at
  `@10` (Sun) for stability across body types.
