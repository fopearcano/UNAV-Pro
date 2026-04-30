# Redshift → Distance: Limitations

UNAV Pro's SDSS and DESI connectors fill `distance_parsec` from a
**linear Hubble proxy** when, and only when, a row's redshift is in
the safe regime. This is **not** a cosmology-grade comoving
distance. This document is the contract: what the proxy is, when it
fires, when it refuses, what the inspector shows the artist, and
what the upgrade path is.

The implementation lives in
`unav_pro/data/connectors/redshift_distance.py`; both the SDSS and
DESI connectors call into it, so the contract is enforced in one
place.

---

## 1. What the proxy actually computes

The mapping is the textbook linear Hubble's law:

```
d_Mpc = (c [km/s] · z) / H₀ [km/s/Mpc]
d_pc  = d_Mpc · 1e6
```

with these defaults:

| Constant                | Value                | Notes                                          |
|-------------------------|----------------------|------------------------------------------------|
| `SPEED_OF_LIGHT_KM_S`   | `299792.458`         | Exact, IAU 2018.                                |
| `HUBBLE_KM_S_MPC` (`H₀`) | `70.0`              | Round value — easily overridden by the caller. |
| `DEFAULT_REDSHIFT_DISTANCE_MAX_Z` | `0.1`     | Cutoff above which the proxy refuses.          |

It is intentionally:

* **Not cosmology-aware.** No matter / Lambda content; no
  integration; no light-time correction; no peculiar-velocity
  correction.
* **Linear in z.** Real comoving distance is concave in `z`; this
  proxy diverges from a Planck-cosmology comoving distance at
  the percent level around `z ≈ 0.05` and at the tens-of-percent
  level around `z ≈ 0.5`.

That divergence is exactly why it refuses above `z = 0.1`.

---

## 2. When the proxy fires

`safe_redshift_to_distance_pc` returns a parsec value **only**
when **all** of these are true:

* `z` is provided and `z > 0`.
* `z ≤ max_z` (default `0.1`; both connector CLIs expose
  `--redshift-max-z` to widen at the artist's risk).
* If the caller passes `zwarn` (DESI provides it), `zwarn == 0`.
  Any non-zero DESI quality flag means the redshift fit is
  suspect and the proxy must not fire.

Whenever the proxy returns a value, the connector also stamps
`metadata_json` with:

```json
{
  "distance_method": "redshift_hubble_proxy",
  "distance_proxy_warning": "Distance derived from naive Hubble's law (d = c·z / H0) at z <= 0.1; approximate, not cosmology-grade.",
  "distance_proxy_z": <z>,
  "distance_proxy_h0_km_s_mpc": <H0>,
  "distance_proxy_max_z": <max_z>
}
```

The metadata inspector keys off `distance_method` to surface the
**APPROXIMATE — Distance derived from naive Hubble's law…** line
in the Astrometry section, so the artist can never confuse a
proxy distance with a parallax-based Gaia distance or an explicit
Horizons vector.

---

## 3. When it refuses

| Condition                                | Result                                                            |
|------------------------------------------|-------------------------------------------------------------------|
| `z` missing                              | `distance_parsec = None`                                          |
| `z ≤ 0` (negative or zero redshift)      | `distance_parsec = None`                                          |
| `z > max_z` (default `0.1`)              | `distance_parsec = None`                                          |
| `zwarn != 0` (DESI quality flag)         | `distance_parsec = None`                                          |
| Helper raises (impossible, but)          | `distance_parsec = None`                                          |

In every refusal path, the row still flows through normalization;
the redshift itself is preserved on the object so the redshift
visual-encoding mode and the inspector still work. The schema's
placeholder-sphere fallback then places the object at
`distance = PLACEHOLDER_SPHERE_PC` (1 Mpc) for visualization
only — that placement is independent of the proxy and is also
flagged via `metadata_json["distance_method"] = "placeholder_sphere"`.

---

## 4. The two distinct "approximate distance" tags

UNAV uses **two** non-overlapping tags in `metadata_json`:

| `distance_method`         | Source                                            | Inspector message                                         |
|---------------------------|---------------------------------------------------|-----------------------------------------------------------|
| `redshift_hubble_proxy`   | this helper, when the proxy fired                 | "APPROXIMATE — Distance derived from naive Hubble's law…" |
| `placeholder_sphere`      | `compute_derived_fields` when no distance is known| (no astrometry warning; the row is on a 1 Mpc sphere)     |

Both indicate "do not trust this as a precise physical distance."
Only the redshift proxy carries the warning text in the
inspector's Astrometry section, because the placeholder sphere is
already a deliberate visual placeholder.

---

## 5. Configurability and override

* The CLIs expose `--redshift-max-z` so an artist can widen the
  cutoff at their own risk. Above `z = 0.1` the linear inversion
  is wrong even at first order; the option is there for
  experiments, not for production.
* The helper's `h0_km_s_mpc` argument is keyword-only so
  alternate values (e.g. Planck 2018's `67.4`) can be substituted
  by code, but the CLIs do not currently expose a flag for it.
  If a project demands a specific cosmology, the cleanest path
  is to call `fetch_normalize_and_write` directly with the
  desired `H₀`.

The proxy values for `H₀`, `max_z`, and the resulting `z` are all
recorded in `metadata_json`, so a later analysis can recompute the
distance under a different cosmology without re-fetching.

---

## 6. Upgrade path

The proxy is intentionally a stand-in for a real
cosmology-aware comoving distance integrator. The eventual
upgrade is a small `cosmology` module wrapping
`scipy.integrate.quad` over the FlatΛCDM `E(z)` integrand, with:

* `H₀`, `Ω_m`, `Ω_Λ` configurable via project state;
* `comoving_distance_pc(z)` and `luminosity_distance_pc(z)`
  helpers callable from the connectors;
* a new `distance_method = "comoving_flat_lambda_cdm"` tag so the
  inspector surfaces a different (more confident) banner.

Until then: the linear proxy with a hard `z ≤ 0.1` cutoff, the
APPROXIMATE banner in the inspector, and the explicit metadata
stamp are the safety net.

---

## 7. What artists should do

* **Trust** Gaia distances (parallax inversion at high SNR) and
  JPL Horizons positions (heliocentric ICRF vectors).
* **Trust** the redshift value itself on SDSS/DESI rows for
  sorting, colouring, and grouping. The redshift colour mode is
  meaningful regardless of whether the distance was derived.
* **Do not trust** `distance_parsec` on a SDSS/DESI row that
  carries `distance_method = "redshift_hubble_proxy"` for any
  measurement. Use it for relative depth ordering only.
* **Do not extrapolate** the redshift→distance relation past
  `z = 0.1`. The connector enforces that automatically.
