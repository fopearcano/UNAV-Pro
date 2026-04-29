# UNAV Pro — Dataset Manager

A persistent registry of locally available catalog files plus a
dialog for inspecting, enabling/disabling, indexing, and merge-
loading them. Lets the user assemble scenes from multiple catalogs
(Gaia near-stars + SDSS galaxies + a bundled sample) without ever
touching JSON by hand.

Companion to:

  * `GAIA_CONNECTOR.md`, `JPL_HORIZONS_CONNECTOR.md`,
    `SDSS_CONNECTOR.md`, `DESI_CONNECTOR.md` (the producers of the
    JSONL files this manager registers).
  * `SPATIAL_INDEXING_AND_CHUNKING.md` (the spatial index the
    **Build Index** button creates).
  * `METADATA_INSPECTOR.md` (the ``MetadataLookup`` the
    **Load Active Datasets** button populates).

---

## 1. Pieces

| Module                                             | Responsibility                                                     |
|----------------------------------------------------|--------------------------------------------------------------------|
| `unav_pro/core/dataset_registry.py`                | Pure data + I/O. ``DatasetEntry``, ``DatasetStats``, ``DatasetRegistry``, scan, save/load, merge. |
| `unav_pro/ui/dataset_manager.py`                   | C4D-bound dialog (``UnavDatasetDialog``) and a controller (``DatasetManagerController``). |
| `unav_pro/ui/main_dialog.py`                       | Adds a "Dataset Manager…" button that opens the manager dialog.    |

The split mirrors the rest of the plugin: the data layer is c4d-
free and unit-tested at full depth; the c4d-bound code is a thin
glue over that data layer.

---

## 2. Data model

```
DatasetRegistry
  ├── entries: List[DatasetEntry]
  └── (de)ser as JSON

DatasetEntry
  ├── name: str            (display name, also the uid namespace)
  ├── path: str            (absolute or relative path to a JSONL/CSV)
  ├── enabled: bool
  ├── namespace: bool      (default True; see §6)
  ├── index_path: str?     (set after Build Index)
  ├── stats: DatasetStats? (set after scanning)
  └── notes: str           (errors stored here; never raise)

DatasetStats
  ├── object_count: int
  ├── bounding_radius_pc: float
  ├── available_fields: List[str]
  ├── sources: List[str]
  └── last_scanned_iso: str?
```

Stats are computed by `scan_dataset_stats(path)`, which loads the
catalog and walks every row to:

  * count objects;
  * compute the largest cartesian-pc distance from origin
    (`bounding_radius_pc`);
  * collect the schema fields that have at least one populated
    value (cosmetic fields like `display_color_rgb` are skipped);
  * collect the unique `catalog_source` values present in the file;
  * stamp `last_scanned_iso` with the current time.

Failures (missing file, parse error) are caught at the registry's
boundary and stored in `entry.notes` rather than raised.

---

## 3. Persistence

The registry persists to `~/.unav_pro/datasets.json` by default
(per-user, survives plugin reload). The file is JSON, indented for
human inspection:

```json
{
  "schema_version": 1,
  "datasets": [
    {
      "name": "UNAV Sample (bundled)",
      "path": "/.../unav_pro/data/samples/sample_catalog_100.jsonl",
      "enabled": true,
      "namespace": true,
      "index_path": null,
      "stats": {
        "object_count": 100,
        "bounding_radius_pc": 1.79e8,
        "available_fields": ["uid", "ra_deg", ...],
        "sources": ["unav_sample"],
        "last_scanned_iso": "2026-01-01T12:00:00"
      },
      "notes": ""
    }
  ]
}
```

`DatasetRegistry.load(path)` is forgiving: missing file → empty
registry; corrupt JSON → empty registry; individual malformed
entries are skipped with a warning so one bad row doesn't drop the
others.

`default_registry_path()` returns `~/.unav_pro/datasets.json`; the
manager dialog uses it unless an explicit `registry_path` is passed
(tests do this).

---

## 4. Dialog

`UnavDatasetDialog` is a stand-alone C4D `GeDialog` opened from the
main dialog's **Dataset Manager…** button. It has its own plugin
ID (`PLUGIN_ID_DATASET_DIALOG = 1000009`) so re-clicking the menu
re-opens the same window rather than spawning duplicates.

Layout:

| Section          | Widget                                                          |
|------------------|-----------------------------------------------------------------|
| Registered datasets | Multi-line read-only text panel rendered from `render_registry`. |
| Selection        | Combo box listing every registered name.                        |
| Actions          | Six buttons (see §5).                                           |
| Status           | Per-action status log.                                          |

The combo is the *picker*: every per-entry button (Remove, Toggle,
Build Index, Refresh Stats) acts on the currently selected entry.
**Add Dataset** and **Load Active Datasets** ignore the combo —
they don't need it.

`DatasetManagerController` owns the registry instance and the
on-disk path; the dialog forwards every button click to a method on
the controller and re-renders the panel after the change.

---

## 5. Buttons

| Button                  | Behaviour                                                                                  |
|-------------------------|--------------------------------------------------------------------------------------------|
| **Add Dataset**         | `c4d.storage.LoadDialog` to pick a JSONL/CSV; calls `DatasetRegistry.add_path` (auto-uniques the display name); scans on add and stores stats; persists the registry. |
| **Remove Dataset**      | Drops the selected entry from the registry; persists.                                      |
| **Enable/Disable**      | Toggles `entry.enabled`; persists.                                                         |
| **Build Index**         | Calls `core.spatial_index.build_index` against the entry's catalog; output dir is `<catalog_path>.index`; updates `entry.index_path`; persists. |
| **Load Active Datasets**| Calls `DatasetRegistry.merge_active`, builds a fresh `MetadataLookup`, and installs it via `core.metadata_lookup.set_default_lookup`. The metadata inspector and the route resolver pick it up immediately. |
| **Refresh Stats**       | Re-runs `scan_dataset_stats` on the selected entry; useful after the user replaced the file on disk; persists. |

Every action returns a status string; nothing raises out of the
dialog event loop. Failures (missing file, corrupt JSON, build
errors) land in the per-action status with enough context to fix.

---

## 6. UID namespacing — the headline feature

When two registered datasets share original uids (e.g. two Gaia
DR3 partitions of the same sky region, or a connector-generated
JSONL plus a hand-edited copy), merging them into one
`MetadataLookup` would produce silent collisions. The registry
prevents this with **opt-out** namespacing:

  * `entry.namespace = True` (the default): every uid emitted by
    that entry is prefixed with `<entry.name>:`. So an object whose
    on-disk uid is `gaia_dr3:1234567890` becomes
    `Gaia Pleiades:gaia_dr3:1234567890` in the merged lookup.
  * `entry.namespace = False`: uids pass through unchanged.

If two entries with `namespace=False` collide on a uid, the merge
keeps the first occurrence and counts the duplicate in
`MergeResult.duplicates_skipped`. The first-wins rule is
deterministic and matches the registry's insertion order, which is
what the dialog displays.

`MergeResult.short_summary()` surfaces the counts in a single
line:

> `100 objects from 2 dataset(s); 3 duplicate uid(s) skipped`

so the artist immediately sees that something collided.

The cost of the default namespacing is uglier uids in the
inspector; the benefit is **guaranteed correctness** when an artist
loads multiple datasets together. Tests verify both the namespaced
case (no collisions) and the explicit non-namespaced case
(collisions counted).

---

## 7. Lookup integration

**Load Active Datasets** is the bridge between the registry and
the rest of the plugin:

```
DatasetRegistry.merge_active() → MergeResult
        |
        v
MetadataLookup(merge.objects)
        |
        v
core.metadata_lookup.set_default_lookup(...)
```

After this, every consumer that calls `default_lookup()` — the
metadata inspector, the route panel resolver, the route panel's
"Add Selected Object" — sees the merged lookup. The inspector
panel's "marker only" fallback automatically becomes "full record"
once the catalog is loaded, even for objects in the scene that
were created before the registry existed (the marker carries the
uid; the lookup carries the row).

---

## 8. Bootstrap behaviour

The first time the manager dialog opens on a machine without a
registry file, `DatasetManagerController.__init__` runs
`bootstrap_with_sample()` which registers the bundled
`sample_catalog_100.jsonl`. The user immediately sees a working
dataset and can experiment without picking a file. The bootstrap
output is persisted on the first action so subsequent opens find
the same entry.

---

## 9. Robustness rules

The dataset manager follows the standing plugin invariants
(`PLUGIN_STRUCTURE.md` §9):

  1. **No exception escapes the C4D boundary.** Every dialog
     command is wrapped; controller methods always return a
     status string.
  2. **Missing data produces messages, not crashes.** Missing
     file, corrupt JSON, build failure, "nothing selected", and
     "no enabled datasets" all surface as status lines.
  3. **No top-level c4d import in testable modules.**
     `core/dataset_registry.py` is c4d-free and fully unit-tested;
     `ui/dataset_manager.py` guards the import.
  4. **Persistence is forgiving.** Load failures degrade to an
     empty registry; save failures log a warning and continue.
  5. **Idempotent.** Adding the same path with the same name
     fails loudly (so duplicates are visible), but adding the same
     path twice without a name auto-suffixes.
  6. **First-wins on collisions.** Merge keeps the earlier entry's
     row and counts the duplicate; the order matches the registry.

---

## 10. Test coverage

`unav_pro/tests/test_dataset_registry.py` covers (39 tests):

  * **Entry.** Validation of required fields; round-trip via dict;
    `is_indexed` reflects an existing directory; `file_exists`
    predicate.
  * **Stats scan.** Counts, bounding radius matches max distance,
    cosmetic fields excluded, raises for missing file.
  * **Registry CRUD.** Empty start; add scans and appends; auto-
    name uniquification; missing file lands in `notes` without
    crashing; remove / set_enabled / set_index_path / rescan.
  * **Persistence.** Save/load round trip with multiple entries,
    `schema_version` recorded, missing file → empty, corrupt JSON
    → empty, malformed entry skipped.
  * **Merge.** Enabled-only filtering, namespacing avoids
    collisions across overlapping uids, disabling namespace
    exposes collisions and counts duplicates, per-entry errors
    recorded, `on_error="raise"` propagates, summary includes
    dupes and errors.
  * **Pretty rendering.** Empty-route friendly text; ON / off /
    idx flags; `[missing file]` marker on absent paths.
  * **Bootstrap.** Bundled-sample seeding picks up the 100-row
    catalog with full stats.
  * **Default path.** Per-user, ends in `datasets.json`.
  * **Controller (non-c4d code).** add → persist round trip;
    remove + toggle pair; load active wires through to
    `set_default_lookup`; no-enabled-datasets short-circuit;
    build_index creates a real index dir; missing-file build
    refuses cleanly; refresh stats; controller remembers state
    across instantiations.

The c4d-bound paths in `UnavDatasetDialog` (the file picker,
combo box, and `Open(...)` lifecycle) are exercised by loading the
plugin in Cinema 4D 2023+; they are not part of the automated
suite.

---

## 11. Future extensions

Tracked as design intent, not promises:

  * **Catalog source as the namespace.** Today the namespace is
    the user-facing entry name. A future toggle can prefix uids
    with `entry.stats.sources[0]:` instead, matching the connector
    convention more strictly.
  * **Bulk Build Index.** "Build Index for all unindexed datasets"
    button.
  * **Cache reaper.** "Remove built indexes" button that lists the
    on-disk index dirs and prunes the orphaned ones.
  * **Catalog signing.** Record SHA-256 of the source file in
    stats so the dialog warns when the file content changed since
    the last scan.
  * **Per-dataset visual encoding.** Each entry gets its own
    `VisualEncodingParams` so a multi-source merge can show Gaia
    in spectral colour and DESI in redshift colour simultaneously.
  * **Remote registry sync.** A studio can host a shared
    `datasets.json` and the manager pulls + reconciles it. Useful
    once teams want a single source of truth across machines.

The MVP shipped here is intentionally narrow: register, persist,
merge, lookup. Every future feature slots in behind the same
`DatasetRegistry` / `MergeResult` / `MetadataLookup` interface.
