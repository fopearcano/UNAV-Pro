# UNAV Pro v2.1 — Astrophysical Overlays & Science Layers

UNAV's v2.1 milestone adds **science-aware overlays** on top
of v2.0's procedural navigation overlays. Where v2.0 supplied
neutral navigation aids (grids, planes, distance rings),
v2.1 lets the artist drop layers that interpret the dataset:
distance / redshift / magnitude shells, per-row motion
vectors, per-source bounding regions, solar-system orbital
placeholders.

This is **not a render engine**. v2.1 is navigation,
annotation, and spatial interpretation — every layer
materialises as plain Cinema 4D scene objects under a
dedicated ``UNAV_ScienceLayers`` root null. None of the
layers participate in the visible-sector pipeline; the v2.0
overlays system is unchanged; the v1.4 mission system, the
v1.7 stability layer, the v1.8 timeline baker, and the v1.9
voyage tools are all unchanged.

For the deep dives:

* [`SCIENCE_LAYER_SYSTEM.md`](SCIENCE_LAYER_SYSTEM.md) — the
  eight layer kinds, their math, and the C4D builder
  contract.
* [`SCIENCE_LAYER_LIMITATIONS.md`](SCIENCE_LAYER_LIMITATIONS.md)
  — what each layer is *not*. v2.1 is conservative about
  scientific claims; this doc spells out every proxy /
  cosmetic mapping the layers use.

---

## 1. What v2.1 actually delivers

| Surface | Change |
|---------|--------|
| `astro/overlay_layers.py` | New module: per-layer ``*Settings`` dataclasses + per-layer pure-Python builders. Eight kinds — three real, three dataset-driven, two placeholders. |
| `astro/science_layers.py` | Orchestrator: ``ScienceLayerSettings`` aggregator + ``build_science_bundle`` aggregate builder + ``ScienceBundle`` output. |
| `c4d_objects/overlays_builder.py` | Extended with `apply_science_bundle` / `clear_science_layers`. Materialises bundles under ``UNAV_ScienceLayers`` (sibling of the v2.0 ``UNAV_Overlays``). Idempotent. |
| `core/project_state.py` | New `science_layers` dict on ``ProjectState``. Round-trips through the per-scene sidecar. |
| `ui/main_dialog.py` | Overlays tab gains a Science Layers section: eight enable checkboxes + Build / Clear buttons + status line. |
| Tests | Two new test files (``test_v21_*``) covering layer settings, geometry, dataset-awareness, idempotency, persistence. |
| Docs | This file + the two deep-dives. |

**No new features beyond science-aware overlays.** No
rendering, no IPC, no external renderer bridge. Every v1.x
+ v2.0 surface is unchanged.

---

## 2. The eight layer kinds

```
distance_shells           — three orthogonal great circles per radius
redshift_shells           — same, with radii from Hubble-law proxy
magnitude_shells          — same, with radii from a cosmetic mag→r map
motion_vectors            — short tangent-plane / line-of-sight segments per row
catalog_source_regions    — bounding sphere per distinct catalog_source
solar_system_orbits       — heliocentric placeholder rings per JPL body
constellation_boundaries  — placeholder (IAU boundary data is v2.x)
object_density_volume     — placeholder (estimator is v2.x)
```

Three are real, three are dataset-driven (need rows from the
active registry), two are placeholders. The placeholders
emit no polylines + a single warning so the dialog can wire
the toggle today and the v2.x implementation drops in
without changing any signatures.

---

## 3. Dataset awareness

Each dataset-driven layer declares which catalog sources it
benefits from:

| Layer | Sources | Behaviour when source absent |
|-------|---------|-------------------------------|
| `motion_vectors` | Gaia DR3 | Empty + a warning ("no rows carry pmra/pmdec"). |
| `catalog_source_regions` | Gaia / SDSS / DESI / JPL | One sphere per source actually present; missing sources skipped silently. |
| `solar_system_orbits` | JPL Horizons | Empty + a warning ("no JPL Horizons rows"). |

Layers that don't consume rows (`distance_shells`,
`redshift_shells`, `magnitude_shells`,
`constellation_boundaries`, `object_density_volume`)
build regardless of dataset state.

The `LAYER_SUPPORTED_SOURCES` map in
``astro/science_layers.py`` documents the mapping for the
diagnostics renderer.

---

## 4. The build flow

```python
from astro import (
    ScienceLayerSettings, DistanceShellSettings,
    MotionVectorSettings, build_science_bundle,
)
from c4d_objects.overlays_builder import apply_science_bundle

settings = ScienceLayerSettings(
    distance_shells=DistanceShellSettings(enabled=True),
    motion_vectors=MotionVectorSettings(enabled=True),
)
bundle = build_science_bundle(settings, objects=catalog_rows)
apply_science_bundle(bundle)   # c4d-bound; no-op outside C4D
```

The bundle has one ``LayerBuildResult`` per kind (always
eight). Each result carries:

* `layer_id` — stable string the C4D builder keys off.
* `polylines` / `labels` — the geometry payload.
* `warnings` — human-readable strings the dialog appends to
  the log.
* `item_count` — number of "things" the layer drew (radii,
  rows, sources, bodies).

`build_science_bundle` is deterministic: same input →
byte-identical output (counts + polylines + warnings).

---

## 5. C4D scene tree

```
UNAV_ScienceLayers/
  UNAV_ScienceLayer_distance_shells/
    10 pc (XY) (distance_shells#0)
    10 pc (XZ) (distance_shells#1)
    10 pc (YZ) (distance_shells#2)
    100 pc (XY) (distance_shells#3)
    ...
  UNAV_ScienceLayer_motion_vectors/
    pm:gaia:1 (motion_vectors#0)
    rv:gaia:5 (motion_vectors#1)
    ...
  UNAV_ScienceLayer_catalog_source_regions/
    Gaia DR3 (n=412) (XY) (catalog_source_regions#0)
    ...
    [labels]
    Gaia DR3 (n=412)
    ...
```

**Idempotency.** Each rebuild removes every per-layer
container (``UNAV_ScienceLayer_*``) before re-inserting; the
root null itself persists. Re-running the build with the
same bundle produces the same scene tree — no duplicates,
no orphans.

**Decoupling.** The science-layers root is a sibling of the
v2.0 ``UNAV_Overlays`` root and the v0.1 ``UNAV_Starfield``
root. None of the three walks under another. Each builder
only touches its own subtree.

**Empty-bundle path.** Calling ``apply_science_bundle`` with
an all-empty bundle removes the entire ``UNAV_ScienceLayers``
subtree — same convention as v2.0's ``apply_overlay_bundle``.

---

## 6. Persistence

`ScienceLayerSettings.to_dict()` emits a nested dict that
``ProjectState.science_layers`` carries through the per-
scene sidecar:

```
~/.unav_pro/projects/<scene>.json
```

The dialog's **Save UNAV State** writes the current science-
layer enable flags + per-layer knobs alongside the v0.x
navigator + route + datasets, the v2.0 overlays, and the
v1.4 / v1.9 mission references. **Load UNAV State** restores
them.

A v2.0 project state without the new ``science_layers`` key
loads cleanly — the field defaults to an empty dict, the
``ScienceLayerSettings`` constructed from it is the
all-defaults instance.

---

## 7. The dialog flow

The Overlays tab gains a "Science Layers (v2.1)" section
below the v2.0 navigation overlays:

```
--- Science Layers (v2.1) ---
[ ] Distance shells          [ ] Redshift shells (proxy)
[ ] Magnitude shells (cosmetic) [ ] Motion vectors (Gaia)
[ ] Catalog source regions    [ ] Solar System orbits (placeholder)
[ ] Constellation boundaries (placeholder)  [ ] Object density volume (placeholder)
[Build / Refresh Science Layers]  [Clear Science Layers]
(science layers idle)
```

Click a checkbox → settings update. Click **Build / Refresh**
→ bundle is built, warnings logged, scene populated. Click
**Clear** → ``UNAV_ScienceLayers`` removed.

Every warning produced by the layer builders gets logged so
the artist sees *why* a layer is empty (e.g. "no rows carry
proper-motion fields").

---

## 8. Acceptance criteria

* [x] User can enable / disable each science layer.
* [x] Layers are dataset-aware: they emit warnings when the
  active dataset doesn't carry the right fields.
* [x] Repeated rebuilds do not duplicate scene objects
  (idempotency contract).
* [x] Unsupported / placeholder layers show clear warnings.
* [x] Science layers are decoupled from
  ``UNAV_Starfield`` and ``UNAV_Overlays``.
* [x] Settings persist via the project state sidecar.
* [x] No render-engine assumptions; no external renderer
  bridge; no IPC.
* [x] No scientific claims beyond the data — every proxy /
  cosmetic mapping is documented in
  ``SCIENCE_LAYER_LIMITATIONS.md``.

---

## 9. What v2.1 explicitly does **not** do

| Out of scope                              | Why                                     |
|-------------------------------------------|------------------------------------------|
| Photorealistic rendering                  | The v2.1 contract is geometry only.      |
| Real cosmology engine                     | Redshift shells use the v0.5 Hubble proxy; v2.x can plug a real cosmology engine behind the same builder. |
| Real luminosity-distance for magnitudes   | The mag→radius map is cosmetic.           |
| Real density estimator                    | ``object_density_volume`` is a v2.x placeholder. |
| Real orbital propagation                  | ``solar_system_orbits`` is a v2.x placeholder ring at the row's instantaneous heliocentric distance. |
| IAU constellation boundaries              | Data lands in v2.x; the toggle is wired today. |
| RelativityRender / external integration   | Explicitly excluded.                     |
| IPC / sockets                             | Explicitly excluded.                     |
