# UNAV Pro v0.2 — Sector Streaming Workflow

The headline change in v0.2: **C4D never loads a full catalog into
memory.** Each registered dataset is queried through its spatial
index, and only the chunks of the cells that the navigator's cone
actually touches reach the plugin. Everything else stays on disk.

This document is the v0.2 contract: what the workflow looks like
end to end, where the streaming logic lives, what guarantees the
safety system enforces, and how the pieces connect to the existing
v0.1 surfaces (navigator, scene-sync, metadata inspector, route
planner).

For the manual acceptance checklist that proves the contract
holds, see
[`V0_2_ACCEPTANCE_TESTS.md`](V0_2_ACCEPTANCE_TESTS.md).

---

## 1. The five-step workflow

| Step | Action | Surface |
|------|--------|---------|
| 1    | **Select Dataset** — register a JSONL/CSV catalog file. | Dataset Manager → Add Dataset |
| 2    | **Build / Load Index** — chunked spatial index on disk. | Dataset Manager → Build Index, or `tools/build_spatial_index.py` |
| 3    | **Create Navigator** — origin + forward + cone parameters. | Main dialog → Create Navigation Null |
| 4    | **Sync Visible Sector** — stream the cone's chunks; diff & build. | Main dialog → Sync Visible Sector |
| 5    | **Inspect Object Metadata** — full record from external lookup. | Main dialog → Inspect Selected Object |

The dialog's top **Workflow** strip surfaces the *current step's*
hint at all times — populated by `core.sector_streaming.workflow_step`,
refreshed after every action.

---

## 2. Data flow

```
remote catalogs                            (Gaia / SDSS / DESI / JPL Horizons / …)
       │
       ▼
external preprocessing tools                (tools/fetch_*.py — stdlib-only CLIs)
       │
       ▼
normalized JSONL                            (canonical CatalogObject schema)
       │
       ▼
external chunked spatial index              (tools/build_spatial_index.py)
       │  index.json + chunks/cell_<i>_<j>_<k>/chunk_NN.jsonl
       ▼
DatasetRegistry entry                       (~/.unav_pro/datasets.json — entry.index_path set)
       │
       ▼
core.sector_streaming                       (the v0.2 bridge module)
       │  - per-dataset: query_index when index_path readable;
       │                 fall back to load_catalog with a warning.
       │  - merge across enabled datasets, namespace uids, apply cap.
       ▼
core.scene_sync.sync_visible_sector         (compute_diff: add / keep / remove)
       │
       ▼
UNAV_Starfield → UNAV_VisibleSector         (one Onull per uid; minimal marker)
       │
       ▼
metadata inspector                          (full record via MetadataLookup)
```

The plugin **never** opens a network socket at scene-load time.
The CLIs are the only place catalog data crosses the public-archive
boundary; they run offline and once per region.

---

## 3. Where the streaming logic lives

* `unav_pro/core/sector_streaming.py` — the new v0.2 bridge.
  - `stream_sector_for_dataset(entry, params, origin_c4d, forward,
    *, dataset_size_warning, hard_full_load_ceiling)`
    returns a `DatasetStreamResult` with the surviving objects,
    the I/O footprint (`candidate_cells`, `total_cells`,
    `candidate_objects`), advisory warnings, and any error.
    Prefers `query_index` when `entry.index_path` is populated and
    the manifest is readable. Falls back to `load_catalog` +
    `apply_filter` with a warning when no index exists; refuses
    outright above the hard ceiling.
  - `stream_sector_for_active_datasets(registry, params,
    origin_c4d, forward)` aggregates across every enabled dataset,
    de-duplicates by namespaced uid, and applies a global
    `max_visible_objects` cap.
  - `workflow_step(...)` is the pure helper the dialog uses to
    render the current step hint.

* `unav_pro/core/mock_actions.py` — the action handlers
  (`generate_point_cloud`, `regenerate_visible_field`,
  `sync_visible_sector`) prefer the streaming path; they fall
  back to the bundled-sample full-load path only when no enabled
  registry entry exists, so a brand-new install still works on
  day zero.

* `unav_pro/core/dataset_registry.py` and
  `unav_pro/ui/dataset_manager.py` — already in v0.1; the
  `DatasetEntry.index_path` is what the streaming path consults.

* `unav_pro/core/spatial_index.py` — already in v0.1; `query_index`
  loads only the chunks the cone touches.

---

## 4. uid namespacing — guaranteed cross-dataset uniqueness

Streaming preserves the registry's namespacing rule:

```
final_uid = f"{entry.name}:{original_uid}"     # entry.namespace=True (default)
```

Two enabled datasets that happen to share an original uid land in
the merged lookup as two distinct namespaced uids. There are
no silent collisions.

`stream_sector_for_active_datasets` also de-duplicates the
namespaced uids across the merged result; the count is reported
in `StreamResult.duplicates_skipped`.

---

## 5. Metadata stays external, only uids on C4D objects

The minimal-marker policy from v0.1 carries forward unchanged.
Each generated `c4d.Onull` carries:

* `MARKER_KEY_UID` — namespaced uid (the lookup key).
* `MARKER_KEY_CATALOG_SOURCE`, `MARKER_KEY_OBJECT_TYPE`,
  `MARKER_KEY_NAME` — minimal identification.
* `MARKER_KEY_RA_DEG`, `MARKER_KEY_DEC_DEG`,
  `MARKER_KEY_DISTANCE_PC` — basic position.

The schema's full `metadata_json` blob is **not** embedded by
default. The Inspector reads it from the `MetadataLookup`,
which v0.2's streaming path populates with the streamed
(visible-sector) objects so the Inspector finds full records for
anything the user can click. Objects outside the visible sector
fall back to "marker only" rendering — the only sane choice when
the catalog is too big to load.

---

## 6. Safety integration

Three guarantees the streaming path enforces:

1. **Refuse to generate beyond `max_visible_objects`.**
   `stream_sector_for_active_datasets` truncates the merged list
   at the navigator's cap before it ever reaches `build_starfield`.
   The downstream safety check in
   `mock_actions.generate_point_cloud` blocks any leftover excess
   if the user has bumped the dialog's safety cap below the
   navigator's.
2. **Warn if a dataset is not indexed.** Falling back to
   `load_catalog` works for small catalogs (the bundled sample,
   100 rows) but emits an explicit warning when the catalog is
   above `dataset_size_warning` (1 000 000 rows by default).
   The warning text says "build the spatial index for sector-
   streaming I/O".
3. **Refuse raw huge full-catalog loads.** If the unindexed
   catalog is above `hard_full_load_ceiling` (5 000 000 rows by
   default), the streaming path returns an `error` instead of
   loading. The action surfaces the error and writes nothing to
   the scene.

All three are pure-CPython policy decisions; they do not require
Cinema 4D and are unit-tested.

---

## 7. Status-line reporting

After a streamed action, the dialog log carries:

```
+312 added, =1218 kept, -47 removed; stream: 1530 visible (of 4823 candidates); 1 warning(s)
```

* The diff summary (the v0.1 scene-sync output).
* The streaming summary
  (`StreamResult.short_summary` — visible vs candidate count,
  capped count, warning / error counts).
* Any per-dataset warning inlined as ``warn: …``.

The Diagnostics dialog shows the same warnings under Recent log
entries.

---

## 8. What hasn't changed

The streaming work is intentionally additive. v0.1 contracts
survive v0.2 unchanged:

* Hierarchy: `UNAV_Starfield → UNAV_VisibleSector → point objects`
  (plus `UNAV_Debug` peer; navigator and route hierarchies at
  scene root).
* Marker container: `BC_ID_UNAV_MARKER` with the same key
  schema. The minimal-marker default and the
  `embed_full_metadata_in_marker` opt-in are unchanged.
* Persistence: `Save UNAV State` / `Load UNAV State` still
  write the document's BaseContainer + the sidecar JSON.
* Diff-and-update: `Sync Visible Sector` runs the same
  `compute_diff` + add/keep/remove pass; only the *source* of
  the candidate list changes.
* CLI tools: `tools/fetch_*.py` and `tools/build_spatial_index.py`
  keep their argparse signatures.

For the corresponding migration plan beyond v0.2, see
[`ROADMAP_CPP_GPU_VERSION.md`](ROADMAP_CPP_GPU_VERSION.md).
