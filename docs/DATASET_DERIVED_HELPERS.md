# Dataset-Derived Helpers

The v2.0 ``procedural/dataset_helpers`` module turns the
loaded catalog into structured summaries the dialog can
render and the overlay system can consume.

Four helpers:

| Helper | Status | Used for |
|--------|--------|----------|
| ``compute_bounding_sphere`` | Real (centroid + farthest-point radius). | "Active dataset bounding sphere" overlay; safe-zone framing in the route analytics. |
| ``compute_source_distribution`` | Real (per-source / per-type histogram). | Diagnostics panel summary; route-analytics provenance. |
| ``compute_density_heatmap_placeholder`` | Placeholder (zero-filled grid). | Reserved API for the v2.x density-heatmap overlay. |
| ``compute_redshift_shells_placeholder`` | Placeholder (v0.5 Hubble proxy). | Reserved API for the v2.x redshift-shell overlay. |

All four are pure stdlib. All four are tested without
Cinema 4D.

---

## 1. Bounding sphere

```python
from procedural import compute_bounding_sphere

sphere = compute_bounding_sphere(catalog_objects)
print(sphere.count, sphere.centre_pc, sphere.radius_pc)
```

* **Centre.** Arithmetic mean of every contributing
  object's ``cartesian_x/y/z``.
* **Radius.** L2 distance from the centroid to the *farthest*
  contributing point. This is a worst-case bound, not the
  minimum-enclosing sphere (Welzl's algorithm) — the
  centroid sphere is closed-form, deterministic, and good
  enough for the v2.0 overlay use case.

Objects without a parsec position (``cartesian_x is None``)
are silently skipped. Empty input returns a zero-radius
sphere at the origin.

The dialog can draw the sphere as a v2.0 ``distance_rings``
overlay with the centroid as the parent transform and the
radius as the only ring.

---

## 2. Source distribution

```python
from procedural import compute_source_distribution

dist = compute_source_distribution(catalog_objects)
print(dist.render_text())
```

Output:

```
=== Dataset summary (1234 objects) ===
--- Catalog sources ---
  Gaia DR3          : 1180
  JPL Horizons      :    8
  SDSS              :   46
--- Object types ---
  star              : 1180
  planet            :    8
  galaxy            :   30
  quasar            :   16
```

* `total` — overall row count.
* `by_catalog_source` — histogram keyed by
  ``CatalogObject.catalog_source`` (rows without a source
  bucket under ``"<unspecified>"``).
* `by_object_type` — histogram keyed by
  ``CatalogObject.object_type`` (same fallback).

The v1.9 route analytics layer renders the same data via its
own histogram code; the v2.0 helper is the dataset-wide
companion (route analytics is per-mission).

---

## 3. Density heatmap (placeholder)

```python
from procedural import compute_density_heatmap_placeholder

heatmap = compute_density_heatmap_placeholder(
    catalog_objects, bins=8, extent_pc=100.0,
)
assert heatmap.is_placeholder is True
assert len(heatmap.cells) == 8 * 8 * 8
```

v2.0 returns a zero-filled grid sized for the requested bin
count. The signature accepts an iterable of objects so the
v2.x density estimator can drop in without changing the
call-sites.

* `bins` — per-axis bin count, clamped to ``[1, 64]``.
* `extent_pc` — half-width of the cubic region the heatmap
  spans.
* `cells` — flat list of ``bins**3`` floats, indexed via
  ``heatmap.cell_index(ix, iy, iz)``.
* `is_placeholder=True` is the loud signal the dialog uses
  to surface "(awaiting v2.x density estimator)".

---

## 4. Redshift shells (placeholder)

```python
from procedural import compute_redshift_shells_placeholder

shells = compute_redshift_shells_placeholder([0.01, 0.1, 1.0])
print(shells.render_text())
```

Output:

```
(redshift shells use the v0.5 Hubble proxy)
  z = 0.010  →  4.45e+07 pc
  z = 0.100  →  4.45e+08 pc
  z = 1.000  →  4.45e+09 pc
```

Distances use the v0.5 Hubble-law proxy:
```
d_pc ≈ (c · z / H₀) × 1e6
```

with `H₀ = 67.4 km/s/Mpc` (Planck 2018) and
`c = 299_792.458 km/s`. **Not suitable for cosmology** —
the proxy collapses at z ≳ 0.1.

* Default redshift ladder:
  ``DEFAULT_SHELL_REDSHIFTS = (0.01, 0.05, 0.1, 0.5, 1.0)``.
* Negative or zero z values are dropped silently.
* `is_placeholder=True` until v2.x ships a real cosmology
  engine behind the same API.

The dialog can draw the shells as a ``distance_rings``
overlay using the proxy radii.

---

## 5. Determinism

All four helpers are pure functions:

* No randomness.
* No external state.
* Histograms use Python's stdlib ``Counter``.
* Same input → byte-identical output.

Tests in ``test_v20_dataset_helpers.py`` cover every helper
end-to-end.

---

## 6. What the helpers are *not*

* **Not a cosmology engine.** The redshift-shell helper is
  a coarse proxy.
* **Not a clustering / density estimator.** The density
  heatmap is an empty grid.
* **Not a real-time streaming system.** Every helper takes
  an iterable and walks it once. Million-row catalogs are
  fine; ten-million-row catalogs need the v2.x streaming
  variants.
* **Not C4D-bound.** The helpers produce data; the C4D
  overlay builder consumes it. The two layers are
  intentionally separated so the helpers stay testable
  outside the host.
