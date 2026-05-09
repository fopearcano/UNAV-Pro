# Science Layer System

The eight v2.1 layer kinds, their math, and the Cinema 4D
builder's idempotency contract.

For the milestone summary see
[`V2_1_ASTROPHYSICAL_OVERLAYS.md`](V2_1_ASTROPHYSICAL_OVERLAYS.md).
For what the layers will and will not say see
[`SCIENCE_LAYER_LIMITATIONS.md`](SCIENCE_LAYER_LIMITATIONS.md).

---

## 1. Layer identifiers

Each kind has a stable string identifier the C4D builder
keys off. These are the on-disk values; renaming them would
break every saved scene state.

```
LAYER_DISTANCE_SHELLS         = "distance_shells"
LAYER_REDSHIFT_SHELLS         = "redshift_shells"
LAYER_MAGNITUDE_SHELLS        = "magnitude_shells"
LAYER_MOTION_VECTORS          = "motion_vectors"
LAYER_CATALOG_SOURCE_REGIONS  = "catalog_source_regions"
LAYER_SOLAR_SYSTEM_ORBITS     = "solar_system_orbits"
LAYER_CONSTELLATION_BOUNDARIES = "constellation_boundaries"
LAYER_OBJECT_DENSITY_VOLUME   = "object_density_volume"
```

---

## 2. Distance shells

Concentric spherical shells at user-specified parsec radii.
Each radius produces three orthogonal great circles (XY / XZ /
YZ planes) so the shell visually reads as a sphere rather
than a single ring.

* `radii_pc` — list of radii. Default ladder
  `[10, 50, 100, 1000]`.
* `segment_count` — points per circle (default 64).

Settings validation drops non-positive / non-numeric entries
and caps the count at 32.

The output is `3 × len(radii_pc)` polylines.

---

## 3. Redshift shells (Hubble proxy)

Concentric shells whose radii come from the v0.5 Hubble-law
proxy:

```
r_pc ≈ (c · z / H₀) × 1e6
```

with `c = 299_792.458 km/s` and `H₀ = 67.4 km/s/Mpc`
(Planck 2018). The layer always emits the warning "redshift_
shells use the v0.5 Hubble-law proxy (coarse; not for
cosmology)" so the artist sees the caveat in the log.

* `redshifts` — list of z values. Default ladder
  `[0.01, 0.05, 0.1, 0.5, 1.0]`.

Negative or zero z values are dropped silently. The output
is `3 × len(redshifts)` polylines.

See [`SCIENCE_LAYER_LIMITATIONS.md`](SCIENCE_LAYER_LIMITATIONS.md)
§2 for why this layer is *only* useful at z ≲ 0.1 and how
the artist should interpret the radii at higher z.

---

## 4. Magnitude shells (cosmetic)

Concentric shells whose radii come from a closed-form
**cosmetic** mag → radius mapping:

```
r_pc(mag) = 50 × 5^((mag - 5) / 3)
```

So `5 mag → 50 pc`, `8 mag → 250 pc`, `11 mag → 1250 pc`,
`14 mag → 6250 pc`. The mapping is **not** a flux-distance
converter — the v2.1 layer is a *visual aid* for the
dataset's brightness distribution, not an astrometric
calculation.

The layer always emits the warning "magnitude_shells use a
cosmetic mag→radius mapping (visual aid only; not a flux-
distance converter)" so the artist sees the caveat.

---

## 5. Motion vectors

Per-row line segments visualising motion direction. Two
flavours:

### 5.1 Proper motion (Gaia)

Drawn in the **tangent plane** at the row's position. The
tangent-plane basis at position p is:

* `outward = p / |p|`
* `east = (-sin(ra), cos(ra), 0)`
* `north = outward × east`

The motion vector is

```
displacement = scale_pc_per_masyr × (pmra · east + pmdec · north)
```

`scale_pc_per_masyr` defaults to 0.05 — much coarser than
the physical conversion (which would make typical Gaia
motions invisible at scene scale) so the artist actually
sees the vector in the viewport.

### 5.2 Radial velocity

Drawn along the **line-of-sight** (the outward direction).
Sign indicates receding (positive = arrow points away from
origin) or approaching.

```
displacement = sign(rv) × |rv| × rv_scale_pc_per_kms × outward
```

`rv_scale_pc_per_kms` defaults to 0.001.

### 5.3 Caps + filters

* `min_pm_masyr` — drop rows whose total proper motion is
  below this threshold (default 0; surfaces "fast movers"
  when set).
* `max_vectors` — hard cap (default `MAX_MOTION_VECTORS = 5000`).
  Rows past the cap are silently dropped + a warning is
  logged.

Rows without a parsec position are silently skipped.

---

## 6. Catalog source regions

Bounding sphere per distinct ``catalog_source`` in the
active dataset. Each sphere is rendered as three orthogonal
great circles (XY / XZ / YZ planes), centred on the
source's centroid, with radius equal to the distance from
the centroid to the farthest row.

A label anchor is inserted at each centroid carrying the
source name + count (``"Gaia DR3 (n=412)"``).

Useful for "show me how the Gaia and SDSS catalogs occupy
space" cinematics.

---

## 7. Solar System orbits (placeholder)

For each row whose ``catalog_source`` starts with `JPL` or
`Horizons`, the layer emits a heliocentric ring in the XY
plane at the row's instantaneous distance from the origin.

Bodies are deduplicated by uid prefix (so `jpl:Mars:2026`
and `jpl:Mars:2027` produce one ring, not two).

**This is a placeholder.** The ring is at the row's
*instantaneous* distance, not the true orbital ellipse. The
layer always logs "solar_system_orbits is a placeholder —
rings sit at the row's instantaneous heliocentric distance,
not the true orbital ellipse." A v2.x release will swap in
an osculating-elements propagator behind the same builder.

---

## 8. Constellation boundaries (placeholder)

The IAU constellation boundaries are 89 closed polygons in
B1875 equatorial coordinates. UNAV does not yet ship the
boundary data. The layer is declared so the dialog toggle
exists today; the v2.x boundary data drops in without an
API change.

When enabled, the layer emits no polylines + a single
informational warning.

---

## 9. Object density volume (placeholder)

Reserved API for the v2.x density-heatmap overlay. The v2.0
``compute_density_heatmap_placeholder`` returns the empty
grid the v2.x estimator will populate; the v2.1 layer is
the rendering surface above it.

When enabled, the layer emits no polylines + a single
informational warning.

---

## 10. The C4D builder contract

`apply_science_bundle(bundle)` materialises a science bundle
under ``UNAV_ScienceLayers``. The contract:

1. Find or create the root ``UNAV_ScienceLayers`` null.
2. Remove every existing per-layer container
   (``UNAV_ScienceLayer_*``) under the root.
3. For each non-empty layer in the bundle:
   * Create a fresh ``UNAV_ScienceLayer_<layer_id>``
     container.
   * Insert one ``c4d.SplineObject`` per polyline.
   * Insert one ``c4d.Onull`` per label.
4. Fire ``c4d.EventAdd``.

An empty bundle (no flag enabled, no inputs) drops the
entire subtree.

The builder is c4d-only — importing the module from a non-C4D
process is safe; every helper no-ops + returns 0 / False.

### 10.1 Idempotency

Re-running the build with the same bundle produces the same
scene tree — no duplicates, no orphans. The root null itself
is preserved across rebuilds so the artist's parent
transformations on the root survive.

### 10.2 Decoupling

The science-layers root is a sibling of:

* the v2.0 ``UNAV_Overlays`` root (procedural overlays);
* the v0.1 ``UNAV_Starfield`` root (visible-sector pipeline).

None of the three walks under another. Each builder only
touches its own subtree, so:

* Rebuilding science layers never touches v2.0 overlays.
* Rebuilding v2.0 overlays never touches science layers.
* Rebuilding the visible sector touches neither.

The `UNAV_ScienceLayer_` container prefix is distinct from
v2.0's `UNAV_Overlay_` prefix, so even a stray name
collision can't confuse the two builders.

---

## 11. Determinism

Every layer builder is a pure function:

* Closed-form trigonometry (no random sampling).
* Settings + (optionally) a row sequence as inputs.
* No external state.

Same inputs → byte-identical output. Tests in
``test_v21_science_layers.py::test_distance_shells_deterministic``
+ ``test_build_science_bundle_is_idempotent`` assert this
end-to-end.

---

## 12. Adding a new layer kind

1. Add a `LAYER_<NAME>` string constant in
   ``astro/overlay_layers.py``. Append it to
   ``SCIENCE_LAYER_IDS``.
2. Add the corresponding `*Settings` dataclass.
3. Implement the builder function: takes settings + (if
   needed) an iterable of rows; returns a
   ``LayerBuildResult``.
4. Wire it into ``ScienceLayerSettings`` and
   ``build_science_bundle``.
5. Add an entry to ``LAYER_SUPPORTED_SOURCES`` in
   ``astro/science_layers.py`` documenting which catalog
   sources the layer benefits from.
6. Add tests in ``test_v21_science_layers.py``.
7. Document the layer in this file under §2.

The C4D builder picks up the new kind automatically — the
container-name helper (``container_name_for_layer``) keys
off the layer id string.
