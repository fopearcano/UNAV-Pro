# UNAV Pro — Object Manager Structure

How v3.45 keeps the Cinema 4D Object Manager organised.

For the canonical hierarchy see
[`SCENE_ORGANIZATION.md`](SCENE_ORGANIZATION.md). This
document is the **operational** companion: how the
plug-in detects + repairs OM drift, and what the
diagnostics panel surfaces.

---

## 1. The canonical layout

Every UNAV project document looks the same:

```
UNAV_Project                         ← single root, always present
├── UNAV_Navigation                   ← navigator + targets
│   └── UNAV_Navigator                  (one)
├── UNAV_VisibleSector                ← materialised point set
│   └── UNAV_Object_<uid> × N           (per visible-sector child)
├── UNAV_Overlays                     ← procedural overlays
│   └── UNAV_Overlay_<kind> × M         (per enabled overlay)
├── UNAV_ScienceLayers                ← science layers
│   └── UNAV_Science_<kind> × K         (per enabled science layer)
├── UNAV_Missions                     ← mission previews + voyages
│   └── UNAV_Mission_<id>_Preview       (per loaded mission)
└── UNAV_Debug                        ← debug helpers (cone, scratch)
```

Every name follows
`unav_pro/c4d_objects/naming.py`. Same input → same
name; the OM tree is **deterministic** across
re-syncs.

## 2. Categories the diagnostics panel reports

`unav_pro/c4d_objects/object_manager_view.py::count_unav_objects`
walks the document and produces a per-category
count:

| Category | What's counted |
| --- | --- |
| `navigation` | `UNAV_Navigation` + descendants |
| `visible_sector` | `UNAV_VisibleSector` + descendants |
| `overlays` | `UNAV_Overlays` + descendants |
| `science_layers` | `UNAV_ScienceLayers` + descendants |
| `missions` | `UNAV_Missions` + descendants |
| `debug` | `UNAV_Debug` + descendants |

Anything UNAV-prefixed that doesn't sit under one
of these six is an **orphan** (see §4).

## 3. Detecting duplicate roots

`find_duplicate_roots(roots)` returns a
`DuplicateRootReport`:

```python
roots = [ObjectNode("UNAV_Project"), ObjectNode("UNAV_Project")]
rep = find_duplicate_roots(roots)
rep.duplicates  # ["UNAV_Project"]
```

The c4d-bound cleanup pass removes all but the
first occurrence of each duplicate inside an undo
block.

`DuplicateRootReport` also surfaces **legacy
roots** (`UNAV_Starfield`, `UNAV_Overlays`,
`UNAV_ScienceLayers`) that should be migrated under
`UNAV_Project`. The v3.1
`scene_structure.ensure_project_structure` does
the migration.

## 4. Detecting orphans

`find_orphans(roots)` walks every UNAV-prefixed
child of `UNAV_Project` whose name **isn't** one
of the six canonical names and reports it:

```python
orphan_node = ObjectNode("UNAV_Experimental")
project = ObjectNode("UNAV_Project", children=[orphan_node])
rep = find_orphans([project])
rep.orphans  # [("UNAV_Experimental", "UNAV_Project")]
```

The dispatcher offers to re-parent or drop these.
v3.45's policy is **never silently delete artist
content** — orphans are reported, not removed.

## 5. Flattened tree view

`flatten_unav_tree(roots)` produces a depth-first
list of every UNAV-prefixed node + its category.
The diagnostics panel renders this verbatim:

```
UNAV_Project
  UNAV_Navigation              [navigation]
    UNAV_Navigator             [navigation]
  UNAV_VisibleSector           [visible_sector]
    UNAV_Object_demo_1         [visible_sector]
    UNAV_Object_demo_2         [visible_sector]
  UNAV_Overlays                [overlays]
    UNAV_Overlay_grid          [overlays]
  UNAV_Missions                [missions]
    UNAV_Mission_tour_Preview  [missions]
```

Use the *Diagnostics → Show Object Manager View*
button (or `render_object_manager_view(roots)`
programmatically) to dump this.

## 6. Cleanup workflow

The recommended cleanup loop is:

1. **Run health check.** v3.4 surfaces the OM
   status as part of the `workspace` /
   `visible_sector` probes.
2. **Run *Object Manager Diagnostics*.** v3.45
   reports counts + duplicates + orphans.
3. **Apply *Clear Generated UNAV Objects*.** v3.4
   removes legacy / scratch nulls.
4. **Apply *Rebuild Scene Hierarchy*.** v3.4
   recreates the canonical six children.
5. **Resync.** `Sync Visible Sector` repopulates
   `UNAV_VisibleSector`.

Each step is idempotent — running them in any order
converges to the canonical state.

## 7. Acceptance

* [x] Single canonical root (`UNAV_Project`).
* [x] Six fixed child groups.
* [x] Deterministic names via
  `c4d_objects.naming`.
* [x] Duplicate detection + cleanup planner.
* [x] Orphan detection (artist content untouched).
* [x] Diagnostics panel surfaces counts +
  flattened view.
* [x] No rendering, no IPC.

## 8. Tests

* `test_v345_object_manager_view` covers
  `count_unav_objects`, `flatten_unav_tree`,
  `find_duplicate_roots`, `find_orphans`,
  `render_object_manager_view`.
