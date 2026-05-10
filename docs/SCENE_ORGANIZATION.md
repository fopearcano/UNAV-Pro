# UNAV Pro — Scene Organization

The v3.1 standardised Cinema 4D hierarchy. Every UNAV
project scene looks the same, regardless of which artist
authored it.

For the workspace overview see
[`V3_1_PROJECT_WORKSPACES.md`](V3_1_PROJECT_WORKSPACES.md).

---

## 1. The canonical hierarchy

```
UNAV_Project                   (single project root)
├── UNAV_Navigation             (the navigator + its targets)
├── UNAV_VisibleSector          (materialised point set)
├── UNAV_Overlays               (procedural overlays)
├── UNAV_ScienceLayers          (science layers)
├── UNAV_Missions               (mission previews + voyages)
└── UNAV_Debug                  (debug helpers; cone, etc.)
```

The root is a single `UNAV_Project` null. Six canonical
child groups live underneath. Builders create them on
demand; the artist never has to.

## 2. Why this layout?

Scene structure should reflect **artist intent**:

* **Navigation** is the input — where the camera /
  navigator lives and what it points at.
* **VisibleSector** is the output — the materialised
  point set the navigator culled.
* **Overlays / ScienceLayers** are *informational
  geometry* that helps the artist understand what's in
  the scene (planes, distance rings, shells, motion
  vectors).
* **Missions** is the authoring surface — mission
  preview splines + waypoint nulls.
* **Debug** is opt-in scaffolding (the navigator cone,
  bookkeeping helpers) that should never end up in a
  final render.

Every category has its own root, so an artist can
hide / lock / colour-code one without affecting the
others.

## 3. Migrating from v3.0 and earlier

Pre-v3.1 scenes used three top-level UNAV nulls:

* `UNAV_Starfield` (v0.1) — point cloud + visible sector
* `UNAV_Overlays` (v2.0)
* `UNAV_ScienceLayers` (v2.1)

v3.1 absorbs them under `UNAV_Project`:

* `UNAV_Starfield` → `UNAV_Project / UNAV_VisibleSector`
* `UNAV_Overlays` → `UNAV_Project / UNAV_Overlays`
* `UNAV_ScienceLayers` → `UNAV_Project / UNAV_ScienceLayers`

The migration is automatic when
`ensure_project_structure(doc)` runs against a legacy
scene. Children of the legacy roots come along
unchanged.

## 4. Pure planning helpers

`unav_pro.c4d_objects.scene_structure` exposes a pure-
Python layer for tests and for any host that doesn't
have Cinema 4D loaded:

* `plan_hierarchy()` returns the `HierarchyPlan`
  describing the canonical tree.
* `diff_hierarchy(existing_root_names=...,
  existing_project_children=...)` returns a
  `HierarchyDiff` with three lists:
  * `missing_children` — canonical children to create.
  * `legacy_to_migrate` — legacy → canonical name
    pairs.
  * `extra_unav_groups` — UNAV-prefixed nulls the
    builder leaves alone (logged for the artist).
* `plan_cleanup(project_children=...,
  enabled_dataset_uids=..., materialised_uids=...)`
  returns a `CleanupPlan` listing groups to remove and
  uids that are now orphans (their driver dataset was
  disabled).

## 5. C4D-bound builders

* `ensure_project_structure(doc)` — idempotent;
  creates the project root + six canonical children;
  migrates legacy roots in place. Returns the project
  root `BaseObject`.
* `get_project_child(doc, name)` — read-only lookup
  of a canonical child.
* `cleanup_project_structure(doc, plan=...)` — apply
  a `CleanupPlan`; returns the count of nodes
  removed.

All c4d-bound calls run inside a `doc.StartUndo()` /
`doc.EndUndo()` window owned by the caller (the
dialog), so a single Ctrl-Z reverts everything.

## 6. Naming consistency

Scene-walk code in v0.x → v3.0 reads object names to
recognise UNAV groups. v3.1 keeps every legacy reader
working: the canonical names are exactly the legacy
names where they overlap (`UNAV_Overlays`,
`UNAV_ScienceLayers`). Only `UNAV_Starfield` becomes
`UNAV_VisibleSector` — and the migration is automatic.

If the artist renames a canonical group manually, the
plugin treats it as user content and leaves it alone.
The next `ensure_project_structure` call recreates the
canonical group; both end up in the project root.

## 7. Acceptance + tests

* `test_v31_scene_structure` covers `plan_hierarchy`,
  `diff_hierarchy`, and `plan_cleanup` against
  a variety of starting-state scenarios.
* The c4d-bound builders raise `RuntimeError` outside
  Cinema 4D — no host is required for the test
  suite.
