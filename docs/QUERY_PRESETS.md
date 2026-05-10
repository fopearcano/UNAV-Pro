# UNAV Pro — Query Presets

Reference for `unav_pro/query/query_presets.py`.

For the milestone overview see
[`V3_7_ADVANCED_ASTRONOMICAL_QUERIES.md`](V3_7_ADVANCED_ASTRONOMICAL_QUERIES.md).

---

## 1. The eight presets

| Name | What it builds |
| --- | --- |
| `nearest_stars` | `NEAREST` query, `object_types=("star",)`, configurable reference point + max. |
| `brightest_stars` | `BRIGHTEST` query, `object_types=("star",)`. |
| `nearby_gaia_objects` | `NEAREST` query against Gaia rows; configurable distance cap. |
| `high_redshift_galaxies` | `HIGHEST_REDSHIFT`, `object_types=("galaxy",)`, default `redshift_min=1.0`. |
| `high_redshift_quasars` | Same as galaxies; `object_types=("quasar",)`. |
| `solar_system_at_epoch` | `BY_TYPE` against JPL bodies; sets `epoch_jd` + `interpolate_ephemeris=True` when an epoch is supplied. |
| `around_navigator` | `NEAREST` capped at `far_clip_pc`. |
| `along_route` | `NEAR_ROUTE` sentinel; the route-query module handles the corridor math. |
| `selected_dataset_summary` | `BY_SOURCE` against one named source. |

## 2. Calling a preset

```python
from query import (
    nearest_stars, list_presets, get_preset, run_query,
)

q = nearest_stars(
    reference_point_pc=(0.0, 0.0, 0.0),
    max_results=10,
)
report = run_query(q, my_catalog_rows)
print(report.short_summary())
```

The dialog's *Advanced Query* panel offers a
*Preset* dropdown populated by `list_presets()`;
pick a row and the panel calls
`select_preset_action(name, ...)` which returns
the same `AdvancedQuery` you'd build by hand.

## 3. Required vs. optional context

Three presets advertise context they need:

* `solar_system_at_epoch` — sets
  `requires_epoch=True`. The dialog disables the
  preset until a time-navigator epoch is active.
* `along_route` — sets `requires_route=True`. The
  dialog disables it until a route or mission is
  loaded.
* The other six work in any state.

The descriptors carry these flags so the dialog
can grey out the right rows without hard-coding
the relationships.

## 4. Determinism

Every preset's builder is **pure** — same kwargs
produce the same `AdvancedQuery` byte-for-byte.
The engine is deterministic (no PRNG); chaining
preset → run → export gives reproducible
artefacts.

## 5. Adding a new preset

1. Add a builder function returning an
   `AdvancedQuery`.
2. Append a `QueryPresetDescriptor` to
   `PRESET_REGISTRY`.
3. Add a unit test asserting the builder's
   output shape.

The dialog picks the new preset up automatically.

## 6. Tests

* `test_v37_query_presets` — registry size,
  per-preset builder shape, parameter forwarding,
  unknown-name resolution.
