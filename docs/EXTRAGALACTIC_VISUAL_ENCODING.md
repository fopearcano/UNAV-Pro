# Extragalactic Visual Encoding

How UNAV Pro's visual encoder renders SDSS / DESI galaxies and
quasars, and the redshift-aware colour and size modes that make
them visually distinct from Gaia stars and JPL solar-system bodies
in a mixed scene. This is the artist-facing companion to
[`VISUAL_ENCODING.md`](VISUAL_ENCODING.md), focused on the
extragalactic catalogs added in v0.5.

The implementation lives in `unav_pro/core/visual_encoding.py`. All
the decisions below are pure-Python and round-trip into
`display_color_rgb` / `render_radius` on each `CatalogObject`.

---

## 1. The colour modes that matter for extragalactic data

| Mode               | What it does                                                        | Best for                                                                |
|--------------------|---------------------------------------------------------------------|-------------------------------------------------------------------------|
| `redshift`         | Cool-warm gradient: `z = redshift_min` → blue, `z = redshift_max` → red.| Showing depth / "redshift = distance proxy" colour at sight.            |
| `catalog_source`   | One colour per survey label.                                        | Mixed-catalog scenes; tells Gaia / JPL / SDSS / DESI apart immediately. |
| `object_type`      | One colour per `object_type`.                                       | Showing star/galaxy/quasar/planet differentiation regardless of survey. |
| `natural`          | Spectral palette for stars; type defaults for everything else.      | Star-dominated scenes.                                                  |
| `magnitude`        | Bright-dim ramp on `apparent_magnitude`.                            | Photometric tracers.                                                    |
| `bp_rp`            | Cool-warm ramp on Gaia `BP-RP` colour index.                        | Gaia-only stellar populations.                                          |

For mixed Gaia + JPL + SDSS + DESI scenes, the recommended
default is **`catalog_source`** (separates the four sources at
sight) or **`redshift`** (colours extragalactic objects by depth
and lets the natural fallback handle stars and planets).

---

## 2. The `redshift` colour mode

The redshift ramp is a cool-warm gradient with five stops:

```
0.00 → (40,  60, 200)   deep blue
0.25 → (40, 200, 200)   cyan
0.50 → (80, 200,  80)   green
0.75 → (255, 220, 80)   amber
1.00 → (220,  60,  60)  red
```

The ramp is parameterised by `redshift_min` / `redshift_max` on
`VisualEncodingParams`. Defaults are `0.0` / `3.0`, which spans
DESI EDR's typical galaxy + quasar range with reasonable headroom.

* **Lower `redshift_max`** (e.g. `0.5`) — useful when the scene
  is dominated by nearby galaxies and you want to spread the
  ramp across a tighter depth band.
* **Higher `redshift_max`** (e.g. `5.0`) — useful for
  high-redshift quasar work so the warmest colours hit only the
  truly distant rows.

Behaviour outside the ramp:

* `z < redshift_min` clamps to the cold end (no wrap-around).
* `z > redshift_max` clamps to the warm end.
* `z is None` falls through to **`natural`** mode for that row,
  so a Gaia star or a JPL body in the same scene still gets a
  sensible colour rather than a silent grey.

Physical motivation: positive redshift means a redder spectrum
(observationally), so the high end of the ramp being red is the
common artist intuition. The ramp is `cool_warm` rather than a
rainbow because cool-warm carries low perceptual ambiguity for
audiences with red-green colour vision differences.

---

## 3. `catalog_source` palette

The encoder ships with the following per-source defaults, designed
so a mixed-catalog scene reads as four disjoint populations at
sight:

| Source label    | RGB             | Notes                                           |
|-----------------|-----------------|-------------------------------------------------|
| `Gaia DR3` / `gaia_dr3` | `(170, 191, 255)` | Cool blue-white — natural Gaia palette.   |
| `Gaia DR2` / `gaia_dr2` | `(170, 191, 255)` | Same as DR3 (artist-relevant grouping).   |
| `SDSS` / `sdss_dr18` / `sdss_dr17` | `(255, 200, 130)` | Warm amber — photometric + spectro. |
| `DESI` / `desi_edr` / `desi_dr1`   | `(130, 220, 180)` | Green-teal — spectroscopic.         |
| `JPL Horizons` / `jpl_horizons`    | `(240, 220, 100)` | Yellow-gold — solar-system bodies.  |
| `unav_sample`   | `(220, 220, 220)` | Neutral grey — bundled sample.                  |

Both the v0.4+ human-readable labels (`"SDSS"`, `"DESI"`,
`"Gaia DR3"`, `"JPL Horizons"`) and the legacy v0.3 release
tokens (`"sdss_dr18"`, `"desi_edr"`, …) resolve to the same
colour, so a mixed scene of catalogs emitted by different
versions still reads consistently.

Unknown sources fall through to the `unav_sample` neutral grey.

---

## 4. The `object_type` size mode for extragalactic data

Galaxies and quasars are visually larger than Gaia stars under
the `object_type` size mode, which is the artist-expected
relative scale:

| `object_type` | Default radius (C4D units before `size_scale`) |
|---------------|------------------------------------------------|
| `star`        | `1.0`                                          |
| `quasar`      | `2.0`                                          |
| `galaxy`      | `3.0`                                          |
| `nebula`      | `4.0`                                          |
| `cluster`     | `3.5`                                          |
| `planet`      | `1.5`                                          |
| `moon`        | `0.8`                                          |
| `comet`       | `1.2`                                          |
| `asteroid`    | `0.3`                                          |
| `spacecraft`  | `0.6`                                          |
| `unknown`     | `1.0`                                          |

For Gaia + extragalactic mixed scenes, this size mode plus the
`catalog_source` colour mode gives the cleanest visual separation:
each source is one colour, each type is one size.

---

## 5. Self-healing fallbacks

Every mode falls through to **`natural`** when its required field
is missing on a row. Specifically:

| Mode           | Required field      | Fallback behaviour                              |
|----------------|---------------------|-------------------------------------------------|
| `redshift`     | `redshift`          | Falls back to `natural` for that row.            |
| `magnitude`    | `apparent_magnitude` | Falls back to `natural` for that row.           |
| `bp_rp`        | `color_index`       | Falls back to `natural` for that row.            |
| `catalog_source` | `catalog_source`  | Returns the `unav_sample` neutral grey.          |
| `object_type`  | `object_type`       | Returns the `unknown` neutral grey.              |
| `natural`      | (none)              | Spectral palette for stars; type default else.   |

This is why a scene of "Gaia + DESI quasars" can be coloured by
**`redshift`** safely: every Gaia star gets its natural-spectral
colour, every DESI row gets its redshift-ramp colour. The
encoder never raises and never silently turns the scene grey.

---

## 6. Configuration surface

`VisualEncodingParams` carries the artist-facing knobs:

```python
@dataclass
class VisualEncodingParams:
    color_mode: str = "natural"
    size_mode: str = "magnitude"
    size_scale: float = 1.0
    brightness_scale: float = 1.0
    brightness_exaggeration: float = 1.0

    redshift_min: float = 0.0
    redshift_max: float = 3.0

    magnitude_min: float = -1.5
    magnitude_max: float = 22.0

    bp_rp_min: float = -0.5
    bp_rp_max: float = 3.0
```

The dialog wires every knob through to the `VisualEncoding`
panel; advanced workflows can call `apply_to_objects(objs,
params)` directly at preprocessing time and pin the encoded
colours and radii into the JSONL on disk.

---

## 7. What this contract intentionally leaves out

* **No surface-brightness modulation.** Galaxies are point-rendered
  as nulls under the v0.1+ minimal-marker policy; per-object
  apparent size is governed by `object_type` / `magnitude` modes,
  not by physical extent.
* **No type-conditional ramps.** A scene with both galaxies and
  quasars under the redshift mode shares one colour ramp; future
  work can split the ramp by `object_type` if artists need
  quasars distinguishable from galaxies at the same `z`.
* **No log-redshift mode.** The current ramp is linear in `z`.
  For a quasar-dominated scene with `0 < z < 5`, a future
  `log_redshift` mode would compress the high end visually.
