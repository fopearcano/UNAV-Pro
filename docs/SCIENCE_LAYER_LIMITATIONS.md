# Science Layer Limitations

What the v2.1 science layers will and will not say. The v2.1
acceptance criteria explicitly require "do not make
scientific claims beyond available data" — this document is
the audit of every approximation, proxy, and cosmetic mapping
the layers use.

If a layer surfaces a number on screen, the rule it followed
to compute it is here. If you find a number you can't
account for, file a bug — silent claims are the failure mode
this doc exists to prevent.

For the system overview see
[`SCIENCE_LAYER_SYSTEM.md`](SCIENCE_LAYER_SYSTEM.md).

---

## 1. Distance shells — accurate

The distance-shells layer simply draws spheres at the
parsec radii the artist supplies. There's no estimation, no
proxy, no caveat. The radii in the label match the radii of
the polylines.

**What this layer is *not*:** a measurement. The layer doesn't
inspect the dataset to derive a "good" set of radii — the
artist supplies them and is responsible for picking values
that make sense for the active dataset.

---

## 2. Redshift shells — Hubble proxy

The radii come from:

```
r_pc ≈ (c · z / H₀) × 1e6
```

with `c = 299_792.458 km/s` and `H₀ = 67.4 km/s/Mpc` (Planck
2018).

This formula is the **linear-regime Hubble proxy** and is a
coarse approximation **only**:

* Valid (~10% accurate) at `z ≲ 0.1`.
* Off by a factor of ~2 at `z = 1`.
* Off by an order of magnitude at `z ≳ 3`.
* Ignores cosmological deceleration / dark-energy effects.
* Returns a single distance interpretation (proper distance);
  real cosmology distinguishes luminosity / angular-diameter
  / comoving / proper distance.

The layer always logs the warning "redshift_shells use the
v0.5 Hubble-law proxy (coarse; not for cosmology)" so the
artist sees the caveat before the shells render. The
polyline labels also embed `(approximate)` so screenshots
carry the disclaimer.

**Use only as a visual ladder, not as a cosmology
reference.** For real cosmological distances use a real
cosmology engine (e.g. `astropy.cosmology`).

---

## 3. Magnitude shells — cosmetic mapping

The radii come from:

```
r_pc(mag) = 50 × 5^((mag - 5) / 3)
```

So `5 mag → 50 pc`, `8 mag → 250 pc`, `11 mag → 1250 pc`,
`14 mag → 6250 pc`. The mapping is **arbitrary** — picked so
the radii grow visibly with magnitude across the typical
catalog range. It is not derived from any flux-distance
relation.

The layer always logs "magnitude_shells use a cosmetic mag→
radius mapping (visual aid only; not a flux-distance
converter)" and the polyline labels embed `(cosmetic)`.

**What the layer is for:** giving the artist a visual sense
of "things this dim are typically this far away" *for the
active dataset*. The artist can confirm this by eyeballing
the catalog density against the shells.

**What the layer is *not* for:** measuring anything. Real
astrometry uses absolute magnitude + parallax; the v2.1
layer uses neither.

---

## 4. Motion vectors — visible-but-coarse scaling

The proper-motion vector length is

```
displacement_pc = scale_pc_per_masyr × √(pmra² + pmdec²)
```

with the default `scale_pc_per_masyr = 0.05`.

The *physical* tangential velocity is

```
v_tan ≈ pmra · distance · 4.74 km/s per (mas/yr × kpc)
```

— a real Gaia star with `pm = 5 mas/yr` at 100 pc moves
~2.4 km/s tangentially. The v2.1 vector length is **not**
this physical velocity; it is a viewport-scale proxy chosen
so the vector is visible. A faster-moving star produces a
visibly longer arrow than a slower one (the *direction* and
*relative magnitude* are correct), but the absolute length
is cosmetic.

Similarly, the radial-velocity arrow length is:

```
displacement_pc = sign(rv) × |rv| × rv_scale_pc_per_kms
```

with the default `rv_scale_pc_per_kms = 0.001`. Same
caveat: direction (receding vs approaching) is correct;
absolute length is for visibility.

**Caps.** The motion-vector layer respects
`MAX_MOTION_VECTORS = 5000` per build. Larger Gaia subsets
are silently truncated + a warning is logged. The artist can
narrow the dataset (e.g. "Gaia within 50 pc") before
building.

**Skipped rows.** Rows without a parsec position are
skipped silently. Rows below `min_pm_masyr` are filtered out.

---

## 5. Catalog source regions — bounding-sphere math

Per distinct `catalog_source` in the dataset, the layer
emits a bounding sphere using the v2.0
``compute_bounding_sphere`` formula:

* **Centre.** Arithmetic mean of every contributing row's
  parsec position.
* **Radius.** L2 distance from the centroid to the farthest
  contributing row.

This is a centroid sphere — a worst-case bound, not the
minimum-enclosing sphere. It's closed-form and deterministic;
that's enough for the v2.1 visualisation use case.

**What this layer is *not*:** a clustering analysis. It
doesn't separate sub-populations within a single catalog
(e.g. Gaia stars by spectral type). One sphere per source,
period.

---

## 6. Solar System orbits — placeholder

The layer emits one ring per JPL body, in the XY plane, at
the row's *instantaneous* heliocentric distance.

This is **not** the body's actual orbit. Mars's orbit is an
ellipse; the v2.1 ring is a circle whose radius matches
Mars's distance at the moment of the JPL fetch. Two rows
of "Mars at different epochs" are deduplicated (the layer
keys off the body name in the uid prefix), so the output is
"one ring per body at one snapshot's distance."

The layer always logs "solar_system_orbits is a placeholder
— rings sit at the row's instantaneous heliocentric
distance, not the true orbital ellipse."

The v2.x replacement will compute the actual osculating
ellipse from the body's velocity vector + heliocentric
position; the placeholder is in place so the dialog toggle
+ the C4D scene-tree slot exist today.

---

## 7. Constellation boundaries — empty placeholder

The layer emits no polylines. Enabling it logs
"constellation_boundaries: v2.1 placeholder — IAU boundary
data lands in v2.x."

The IAU 1930 constellation boundaries are 89 closed polygons
in B1875 equatorial coordinates. UNAV does not yet ship the
boundary data. When v2.x ingests the dataset, the layer will
emit one closed polyline per boundary; the C4D builder
contract is unchanged.

---

## 8. Object density volume — empty placeholder

Same shape as §7: enabling the layer logs
"object_density_volume: v2.1 placeholder — density estimator
lands in v2.x."

The v2.0 ``compute_density_heatmap_placeholder`` is the
backing store; v2.x will plug a real estimator + a marching-
cubes-style isosurface renderer behind the same layer.

---

## 9. Things v2.1 deliberately does not provide

Beyond the per-layer caveats above:

* **No constellation labels.** Even if v2.x ships boundaries,
  the labels would need a separate IAU dataset.
* **No HR diagram positioning.** Magnitude shells do not
  express absolute magnitude; the layer cannot tell a giant
  from a dwarf.
* **No proper-motion propagation.** The layer draws an
  *instantaneous* tangent vector; it does not advance the
  star's position over time. The v1.2 Time Navigator does
  that.
* **No spectral classification overlays.** The layer set is
  positional / kinematic only.
* **No age / metallicity overlays.** UNAV's data layer does
  not carry these fields.
* **No photometric distance estimates.** The mag→r mapping
  is cosmetic, period.

Each of these would need additional dataset / cosmology
infrastructure that v2.1 doesn't ship. They are explicitly
v2.x or later.

---

## 10. How to read a science-layer scene

When the artist looks at a v2.1 scene, the rule is:

* **Geometry is real** — the polylines really are circles
  / lines / spheres at the labelled coordinates.
* **Labels carry caveats** — `(approximate)`, `(cosmetic)`,
  `(placeholder)` are loud signals.
* **Warnings carry the rules** — every per-layer warning the
  builder emits ends up in the dialog log. If it isn't in
  the log, the layer made no proxy / no claim.

If you find yourself trusting a science-layer number for a
real measurement, the rule is: don't. The layers exist to
help the artist *plan* a cinematic; for real measurements,
go back to the underlying catalog data.
