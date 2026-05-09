# Dataset Summary Export

The v2.3 dataset summary JSON. Tells a downstream reader
what UNAV had loaded at export time: which datasets, how
many objects, which navigation parameters, which science
layers were enabled, which missions referenced the package.

For the milestone overview see
[`V2_3_EXPORT_PIPELINES.md`](V2_3_EXPORT_PIPELINES.md). For
the package layout see
[`EXPORT_PACKAGE_FORMAT.md`](EXPORT_PACKAGE_FORMAT.md).

---

## 1. The shape

```json
{
  "schema_version": 1,
  "plugin_version": "v2.3",
  "exported_at_iso": "2026-01-01T12:34:56Z",

  "dataset_count": 3,
  "enabled_dataset_count": 2,
  "datasets": [
    {
      "name": "Gaia DR3 (Pleiades)",
      "enabled": true,
      "path": "data/gaia_pleiades.jsonl",
      "db_path": null,
      "namespace": true,
      "object_count": 4823,
      "bounding_radius_pc": 14.2
    },
    ...
  ],

  "object_count_estimate": 9512,
  "sources": {"Gaia DR3": 9012, "JPL Horizons": 8, "SDSS": 492},
  "object_types": {"star": 9012, "planet": 8, "galaxy": 492},

  "coordinate_scale": "pc",
  "max_visible_objects": 100000,
  "cone_half_angle_deg": 30.0,
  "far_clip_parsec": 1000.0,
  "near_clip_parsec": 0.1,

  "active_science_layers": ["distance_shells", "motion_vectors"],
  "mission_references": ["8f3c7a9c4b1d2e0f", "1a2b3c4d5e6f7081"],
  "notes": []
}
```

---

## 2. Field reference

### 2.1 Header

* `schema_version` — int, currently `1`.
* `plugin_version` — UNAV Pro version that produced the
  summary.
* `exported_at_iso` — UTC export timestamp.

### 2.2 Dataset registry

* `dataset_count` — total registered (enabled + disabled).
* `enabled_dataset_count` — subset that's currently in the
  visible-sector pipeline.
* `datasets` — one row per registered entry. Each row
  carries `name`, `enabled`, `path` (JSONL), `db_path`
  (SQLite, may be null), `namespace`, plus optional
  `object_count` / `bounding_radius_pc` from the registry's
  cached stats.

### 2.3 Object-level histograms

Populated when the exporter's `objects=` argument is
non-empty. The dialog supplies the merged catalog from the
active registry; tests can supply synthetic rows.

* `object_count_estimate` — count after the merge step.
* `sources` — `{catalog_source: count}`. Rows without a
  source land in `"<unspecified>"`.
* `object_types` — `{object_type: count}` with the same
  fallback.

When `objects=` is omitted, these three fields are all
empty / zero.

### 2.4 Navigator parameters

A best-effort dump of the active navigator state at export
time:

* `coordinate_scale` — the v0.x `c4d_scale` mode (e.g.
  `"pc"`, `"kpc"`).
* `max_visible_objects` — the navigator's safety cap.
* `cone_half_angle_deg` — half-angle of the visible cone.
* `far_clip_parsec` / `near_clip_parsec` — visible-sector
  range.

When the dialog can't supply navigator params (e.g. no
active document), these fields are `null`.

### 2.5 Science layers

* `active_science_layers` — list of layer ids from
  `ScienceLayerSettings.enabled_layer_ids()`. Empty list
  means no layers active at export time.

### 2.6 Mission references

* `mission_references` — list of `mission_id` strings the
  artist included in the package. Useful for cross-
  referencing the package's `missions/` directory.

### 2.7 Notes

* `notes` — list of human-readable strings. Populated
  when the exporter couldn't fully build the summary
  (missing registry, unrecognised science-layer settings
  shape, …).

---

## 3. Building the summary

```python
from export import build_dataset_summary

summary = build_dataset_summary(
    registry=dataset_registry,
    navigator_params=navigator_params,
    science_layer_settings=science_layer_settings,
    objects=catalog_objects,
    plugin_version="v2.3",
    mission_references=["abc123", "def456"],
)
```

Every keyword argument is optional — a missing piece
produces zero / empty values + a note. The dialog hands in
whatever it has at export time; tests can build the
summary from any subset.

---

## 4. Atomic write

```python
from export import write_dataset_summary

written = write_dataset_summary(summary, "/tmp/dataset_summary.json")
```

Wraps the v1.7 `safe_write_json` helper. Returns the path
on success or `None` on failure. Same contract as every
other v2.3 exporter.

---

## 5. Plain-text rendering

The dialog's log shows `render_summary_text(summary)` after
each export:

```
=== Dataset summary ===
  datasets       : 3 (2 enabled)
  objects (est.) : 9512
  sources        : Gaia DR3=9012, JPL Horizons=8, SDSS=492
  scale          : pc
  science layers : distance_shells, motion_vectors
```

Sections that don't apply (no objects, no scale, no science
layers) are omitted.

---

## 6. Determinism

* Histograms use Python's stdlib `Counter` (insertion-
  order-stable for our use case).
* Lists are sorted before render where applicable.
* Same input → byte-identical JSON.

The only non-deterministic field is `exported_at_iso`. Two
exports of the same UNAV state differ in exactly that line.

---

## 7. What the summary is *not*

* **Not a catalog.** The summary doesn't carry per-object
  rows; only counts + provenance. For row-level data, the
  caller exports the JSONL / DB itself separately.
* **Not a cosmology export.** Distances cited in the
  summary are whatever UNAV's `cartesian_x/y/z` carry;
  redshift-derived distances are the v0.5 Hubble proxy.
* **Not a complete plugin-state dump.** Navigator pose,
  bookmarks, missions, overlays — those have their own
  export paths. The summary is the dataset-level
  snapshot.
