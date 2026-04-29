# UNAV Pro — Ray / Cone Filtering

How UNAV Pro reduces the working set of catalog objects before
materializing anything in Cinema 4D. This is the central pro feature
that keeps scenes small and viewports responsive: the plugin must
never load or generate the full universe.

Companion to:

  * `UNAV_PRO_ARCHITECTURE.md` §3.7 (filter system)
  * `NAVIGATION_NULL_SYSTEM.md` (parameter source)
  * `POINT_CLOUD_GENERATION.md` (consumer of filter output)

---

## 1. Pipeline

```
Catalog (JSONL on disk)
        |
        v
load_catalog()                 -> [CatalogObject, ...]      pure data
        |
        v
filter_for_navigator()         -> FilterResult              pure pc math
        |   reads NavigationParams from the navigator
        |   reads navigator origin + forward vector
        |
        v
build_starfield()              -> UNAV_Starfield + N nulls   c4d-bound
```

The whole pre-build pipeline is **pure-CPython, parsec-coordinate
math**. The C4D-bound code is a thin wrapper that converts the
navigator's C4D-units pose into parsec, calls the filter, and hands
the surviving list to the existing point-cloud builder.

Implementation: `unav_pro/core/spatial_filter.py`.

---

## 2. Filter passes (in order)

For each input object the filter applies these gates, in this order,
and counts each rejection by reason:

| # | Gate                         | Reject reason            | Cheap? |
|---|------------------------------|--------------------------|--------|
| 1 | `selected_sources` set?      | `rejected_source`        | yes    |
| 2 | `selected_types` set?        | `rejected_type`          | yes    |
| 3 | Cartesian position usable?   | `rejected_no_position`   | yes    |
| 4 | `dist >= near_clip_pc`       | `rejected_near_clip`     | cheap  |
| 5 | `dist <= far_clip_pc`        | `rejected_far_clip`      | cheap  |
| 6 | Forward hemisphere (dot > 0) | `rejected_behind`        | cheap  |
| 7 | Cone half-angle (cos test)   | `rejected_outside_cone`  | cheap  |
| 8 | `max_visible_objects` cap    | `rejected_over_cap`      | sort   |

The cheap gates run before any vector math so the filter is essentially
free for objects that don't survive #1–#3.

`FilterStats.short_summary()` produces the one-line dialog status:

```
kept 312/100000; 84312 outside cone; 14998 far; 378 behind
```

`FilterStats.total == kept + sum(rejected_*)` is enforced by tests.

---

## 3. Cone math

Forward is the navigator's local **−Z** axis transformed to world
space (see `NAVIGATION_NULL_SYSTEM.md` §2). For each candidate point:

```
displacement   = point_pc - origin_pc
distance       = |displacement|
cos_angle      = (displacement · forward_unit) / distance
cos_threshold  = cos(half_angle_deg)
inside_cone    = cos_angle > 0 and cos_angle >= cos_threshold
```

Edge cases:

  * `cone_half_angle_deg <= 0` → pure ray (only points exactly on the
    axis pass).
  * `cone_half_angle_deg >= 180` → cone test disabled; only distance
    gates apply.
  * `forward == (0, 0, 0)` → cone test disabled (zero-direction is
    treated as "no orientation").
  * `distance == 0` → object at navigator's origin; passes the cone
    test (and may still fail `near_clip_pc`).

The geometry kernel `cone_contains(...)` is a separate public function
so the future filter-cone tag and the metadata inspector's hit-test
share one implementation.

---

## 4. The max-object cap

`max_visible_objects` is a hard ceiling on the surviving list,
defaulting to whatever the navigator's user data says (100 000). When
the cap kicks in:

  * Default (`rank_by="distance"`): keep the **closest** N. Tie-break
    on brightness when known.
  * `rank_by="brightness"`: keep the visually **brightest** N
    (lowest apparent magnitude). Tie-break on distance.

The cap is applied **after** the spatial gates so the user always sees
"the most relevant N of what would otherwise have been kept", not
"the first N off disk."

---

## 5. Coordinate frame

The filter is purely parsec-coordinate. The caller is responsible for
converting:

  * **Navigator origin.** `core.spatial_filter.c4d_units_to_pc(xyz,
    scale_mode)` is the inverse of `schema.pc_to_c4d_units` and uses
    the same `SCALE_MODES` table. The high-level
    `filter_for_navigator(objects, origin_c4d, forward, params)`
    helper does this for you.
  * **Forward vector.** Direction-only and unitless — pass it through
    unchanged.
  * **Object positions.** Already in pc on the schema's
    `cartesian_x/y/z`. Cached during ingest by
    `compute_derived_fields`; recomputed lazily on first read.

Keeping the kernel pure-pc means it can be replaced wholesale with a
pybind11/SIMD/CUDA implementation without touching call sites — the
target of `UNAV_PRO_ARCHITECTURE.md` §5.

---

## 6. Why this is the headline feature

Loading 1.8 B Gaia rows into a `.c4d` scene is not a feature, it is a
crash. Every UNAV scene must:

  1. **Reference** a cache (Parquet tiles or local JSONL) by path or
     manifest hash.
  2. **Filter** that cache down to a working set bounded by the
     navigator's pose and `max_visible_objects`.
  3. **Materialize** only the working set as nulls / matrices /
     packed buffers.

This module is step 2. It is the gate that makes steps 1 and 3
tractable. Anything that wants to render a real catalog goes through
it.

---

## 7. UI integration

Three buttons in the main dialog touch this code:

| Button                       | Action                                                                                       |
|------------------------------|----------------------------------------------------------------------------------------------|
| **Generate Point Cloud**     | If a navigator exists, filter then build. If not, build first 5 000 with a warning.          |
| **Apply View Filter**        | Run the filter and report the rejection breakdown only — does not touch the scene.           |
| **Regenerate Visible Field** | Clear the existing `UNAV_Starfield`, re-filter, and rebuild. The iterate-and-tweak workflow. |

`Generate Point Cloud` is intentionally protective: if no
`UNAV_Navigator` exists in the scene, it caps the build at
`_NAVIGATOR_LESS_FALLBACK_CAP = 5 000` and warns the user that they
should create a navigator to filter the full catalog. This matches
the principle of refusing to materialize the universe when no
filtering criterion has been provided.

---

## 8. Performance envelope and migration path

| Catalog size | Filter time (Python, MVP) | Strategy                                                           |
|--------------|---------------------------|--------------------------------------------------------------------|
| 100          | < 1 ms                    | Pure Python loop (current).                                        |
| 10 k         | ~ 5–20 ms                 | Pure Python loop (current).                                        |
| 100 k        | ~ 50–200 ms               | Still acceptable as a manual click; not per-frame.                 |
| 1 M          | ~ 0.5–2 s                 | Vectorize with numpy: `dx, dy, dz = positions - origin`.           |
| 10 M+        | seconds → tens            | Native pybind11 kernel; HEALPix prefilter at tile granularity.     |
| any size, per-frame | n/a in Python      | C++ + GPU compute (`UNAV_PRO_ARCHITECTURE.md` §5).                 |

Order of attack when Python becomes a bottleneck:

  1. **HEALPix prefilter.** The cone covers only a small set of sky
     pixels; load only those tiles. This is a 100×–1000× win before
     the per-object math even runs.
  2. **Numpy vectorization.** Replace the Python loop with array
     arithmetic in the same function; no API change.
  3. **Native kernel.** Drop in a C++/SIMD implementation behind the
     same `apply_filter` signature.

Each step preserves the call site. The MVP loop is intentionally
clear so each migration is a local rewrite, not a redesign.

---

## 9. Test coverage

`unav_pro/tests/test_spatial_filter.py` covers:

  * Cone geometry kernel — inside / outside / behind / distance-shell /
    pure ray (zero half-angle) / disabled cone (180° half-angle).
  * Distance gates — near / far / inside-shell.
  * Direction gates — inside cone / outside cone / behind / zero
    forward disables direction.
  * Source filter — exclusion by `catalog_source`.
  * Type filter — exclusion by `object_type`.
  * Max-object cap — distance ranking, brightness ranking, cap-of-zero.
  * No-position handling — placeholder sphere distance, exception
    safety in `compute_derived_fields`.
  * Stats — per-reason counts sum to total; `short_summary()` lists
    only non-zero reasons.
  * Coordinate conversion — `c4d_units_to_pc` per scale mode.
  * `filter_for_navigator` — wires `NavigationParams` through.
