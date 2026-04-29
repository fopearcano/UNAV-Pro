# UNAV Pro — Visual Encoding

How catalog rows turn into colours and sizes for the C4D viewport.
The encoding layer sits between the schema's per-object defaults and
the point-cloud builder so artists can switch *what data the
visualization shows* without re-ingesting anything.

Companion to:

  * `POINT_CLOUD_GENERATION.md` (consumer of the encoded values).
  * `data/schema.py` (`display_color_for`,
    `render_radius_from_magnitude` — the natural-mode floor).

---

## 1. Modes the user can pick

Implemented in `unav_pro/core/visual_encoding.py`. Six colour modes
and three size modes; the dialog dropdown surfaces all six colour
modes by name, plus the size modes via API.

### Colour modes

| Label                  | Token             | Drives                                                     |
|------------------------|-------------------|------------------------------------------------------------|
| Natural Star Color     | `natural`         | Schema's spectral-class palette for stars; type default elsewhere. |
| Catalog Source         | `catalog_source`  | Per-source palette (`gaia_*` blue, `sdss_*` orange, `desi_*` green, `jpl_horizons` yellow, …). |
| Object Type            | `object_type`     | Schema's `_TYPE_COLORS` ignoring spectral type.            |
| Redshift               | `redshift`        | Cool-warm gradient over `[redshift_min, redshift_max]`.    |
| Magnitude              | `magnitude`       | Bright-to-dim gradient over `[magnitude_min, magnitude_max]`. |
| BP-RP Color Index      | `bp_rp`           | Cool-warm gradient over `[bp_rp_min, bp_rp_max]`.          |

### Size modes

| Label                  | Token         | Drives                                                  |
|------------------------|---------------|---------------------------------------------------------|
| Magnitude (default)    | `magnitude`   | Schema's magnitude curve; warpable via `brightness_exaggeration`. |
| Object Type            | `object_type` | Per-type fixed radius (galaxies > stars > asteroids).   |
| Uniform                | `uniform`     | Constant 1.0 before `size_scale`.                       |

### Scalars

| Field                       | Default | Effect                                                                  |
|-----------------------------|---------|-------------------------------------------------------------------------|
| `size_scale`                | 1.0     | Multiplies the final radius. UI knob.                                   |
| `brightness_scale`          | 1.0     | Multiplies the final radius after `size_scale`. UI knob.                |
| `brightness_exaggeration`   | 1.0     | Exponent on the magnitude curve in the `magnitude` size mode. > 1 widens the gap between bright and dim, < 1 flattens it. |

---

## 2. Encoding pipeline

```
CatalogObject + VisualEncodingParams
        |
        +-- encode_color(obj, params)  -> sRGB int triple (0..255 each)
        |       mode-specific helper, falling back to color_natural
        |       when the required field (redshift / magnitude /
        |       bp_rp) is missing.
        |
        +-- encode_size(obj, params)   -> base radius (float)
        |       mode-specific helper.
        |
        +-- multiply by size_scale * brightness_scale
        |
        v
encode(obj, params) -> ((r, g, b), radius)
```

`apply_to_object(obj, params)` writes the result back into
`obj.display_color_rgb` and `obj.render_radius` so cached values
stay consistent with the schema's expectation.

---

## 3. Self-healing fallbacks

Every mode whose required field can be missing falls through to
`color_natural` instead of producing a degenerate colour:

  * `redshift` mode on a star with no `redshift` → spectral-class
    colour.
  * `magnitude` mode on a row with no `apparent_magnitude` →
    spectral / type colour.
  * `bp_rp` mode on a row with no `color_index` → spectral / type
    colour.

This keeps a single mode usable across mixed catalogs (stars + DESI
galaxies + JPL planets) without forcing the user to pre-filter.

The `catalog_source` and `object_type` modes always succeed because
their inputs are required schema fields.

---

## 4. Gradient definitions

Two named gradients are defined in `visual_encoding.py`:

  * **Cool-warm** (`_COOL_WARM_STOPS`) — five-stop linear: deep blue
    → cyan → green → yellow → red. Used by both `redshift` and
    `bp_rp` modes; both encodings put physically *redder* values at
    the warm end, matching astronomy convention.
  * **Bright-dim** (`_BRIGHT_DIM_STOPS`) — three-stop linear: warm
    white (bright) → mid grey → dim. Used by the `magnitude` colour
    mode.

`_sample_gradient(stops, t)` is the piecewise-linear sampler. It
clamps `t` to `[0, 1]`; out-of-range values match the endpoint
colour rather than extrapolate.

---

## 5. Per-source and per-type palettes

`_SOURCE_COLORS` covers the connectors that ship today:

| Source                        | Palette role                |
|-------------------------------|-----------------------------|
| `gaia_dr3`, `gaia_dr2`        | Cool blue (stellar surveys) |
| `sdss_dr18`, `sdss_dr17`      | Warm orange (extragalactic) |
| `desi_edr`, `desi_dr1`        | Green (DESI redshifts)      |
| `jpl_horizons`                | Yellow (solar system)       |
| `unav_sample`                 | Neutral grey                |
| any other / unknown           | Falls back to grey          |

`_TYPE_SIZES` provides fixed radii for the `object_type` size mode
across all schema categories (`star`, `galaxy`, `quasar`, `nebula`,
`cluster`, `planet`, `exoplanet`, `moon`, `asteroid`, `comet`,
`spacecraft`, `unknown`). The values are tuned so the artist sees
expected hierarchy at a glance: galaxies > nebulae > stars >
asteroids.

---

## 6. UI integration

The main dialog gains a "Display" group above the action buttons:

| Control            | Widget                  | Bound to                              |
|--------------------|-------------------------|---------------------------------------|
| Color mode         | `AddComboBox` (six items) | `params.color_mode` (token)         |
| Size scale         | `AddEditNumberArrows`   | `params.size_scale`                   |
| Brightness scale   | `AddEditNumberArrows`   | `params.brightness_scale`             |

`UnavMainDialog._read_encoding()` snapshots the three controls into
a `VisualEncodingParams` whenever the user clicks **Generate Point
Cloud** or **Regenerate Visible Field**. Out-of-range inputs (zero
size scale, etc.) silently fall back to defaults rather than refuse
the build.

The `encoding` argument now flows through:

  * `mock_actions.generate_point_cloud(encoding=...)`
  * `mock_actions.regenerate_visible_field(encoding=...)`
  * `point_cloud_builder.build_starfield(..., encoding=...)`
  * `point_cloud_builder.build_point_object(..., encoding=...)`

`encoding=None` at any layer means "use the schema's natural
rendering" — exactly what the plugin produced before this layer
existed. The change is additive and backwards compatible.

---

## 7. Robustness rules

The encoding layer follows the standing plugin invariants
(`PLUGIN_STRUCTURE.md` §9):

  1. **Pure CPython, no c4d, no numpy.** Every helper is unit-testable
     without a host.
  2. **`VisualEncodingParams` validates at construction.** Unknown
     mode tokens, non-positive scalars, and inverted ranges raise
     `ValueError` with a clear message; the dialog catches and
     ignores so a typo in a number field cannot break the build.
  3. **Fallback to natural.** Missing-field paths in `encode_color`
     never produce a sentinel colour like pure black; they go
     through `color_natural`.
  4. **Idempotent output.** `apply_to_object` is safe to call
     multiple times; it overwrites the cached fields with the
     current params.

---

## 8. Test coverage

`unav_pro/tests/test_visual_encoding.py` covers (42 tests):

  * **Constants and labels.** Mode tokens cover the user-spec list,
    label↔token round trip, unknown-label fallbacks.
  * **Param validation.** Defaults, unknown modes, non-positive
    scalars, inverted ranges.
  * **Per-mode colour functions.** `natural` distinguishes spectral
    classes; `catalog_source` palette is per-source with a grey
    fallback; `object_type` distinguishes galaxy/quasar; `redshift`
    is monotone in red and inverse-monotone in blue, clamped at
    range edges, returns `None` for missing input; `magnitude` is
    bright-luminance-dominant; `bp_rp` is monotone in red and
    inverse-monotone in blue.
  * **Per-mode size functions.** Magnitude curve is monotone,
    clamped, exaggeration widens contrast; object-type sizes are
    per-category and cover every category required by the spec.
  * **`encode_color` dispatch.** Each mode delegates correctly;
    `redshift` / `magnitude` / `bp_rp` fall back to `natural` when
    their input field is missing.
  * **`encode` top-level.** Defaults reproduce the natural+magnitude
    path; `size_scale` and `brightness_scale` multiply correctly
    and stack.
  * **`apply_to_object(s)`.** Cached fields are written back;
    sequence helper mutates and returns the same list.

---

## 9. Future extensions

  * **Animated gradients.** Per-frame parameter tweens for the
    redshift / magnitude ramps so the visualization can pulse or
    sweep at render time. Trivial extension once the navigator's
    time axis lands.
  * **Custom palettes.** Let the artist load a `.lut` or paste
    sRGB stops; today the gradients are hard-coded constants.
  * **Photometric-band selection.** When the schema gains
    `mag_g/mag_r/mag_i/...` columns, the magnitude colour mode will
    surface a band picker instead of using the single
    `apparent_magnitude` field.
  * **Per-source overrides.** A scene with both Gaia and DESI rows
    might want spectral colour for stars *and* redshift colour for
    galaxies in one pass. Reachable today by running the encoding
    twice with a per-object filter; the API is shaped to take a
    callable that picks the params per object once we build that
    UX.

The encoding is intentionally narrow and orthogonal: it touches
*only* the cached colour and radius. Adding a future mode is one
function, one entry in `COLOR_MODES` / `SIZE_MODES`, one entry in
`COLOR_MODE_LABELS` / `SIZE_MODE_LABELS`, and the corresponding
tests.
