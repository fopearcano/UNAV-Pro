# UNAV Pro v3.1 — Project Workspaces & Scene Organization

Release date: 2026-05-10
Codename: *Project Workspaces & Scene Organization*

v3.1 is the **collaborative project structure** milestone.
The goal: make UNAV usable inside real production projects
with organised scenes, reusable voyage assets, and team-
friendly structure.

This is **not** rendering. **Not** new authoring surfaces.
The runtime feature surface is unchanged from v3.0; v3.1
adds the **structure** under which the existing surfaces
operate.

---

## Highlights

* **Workspace system.** New
  `unav_pro/project/workspace.py` builds a standard
  directory tree (`datasets/`, `cache/`, `missions/`,
  `routes/`, `exports/`, `overlays/`, `timelines/`,
  `notes/`) with a `project_manifest.json` at the root.
  Workspaces are local directories the artist owns;
  references inside the manifest are
  workspace-relative so a workspace stays portable
  across machines.
* **Project manifest.**
  `unav_pro/project/project_manifest.py` defines the
  full schema: `ProjectManifest` plus `DatasetReference`
  / `MissionReference` / `RouteReference` /
  `TimelineReference` plus overlay + science-layer
  settings snapshots. v3.1 ships `schema_version: 1`;
  loaders fail-closed on newer versions.
* **Standardised scene hierarchy.** New
  `unav_pro/c4d_objects/scene_structure.py` declares
  the canonical Cinema 4D layout:
  `UNAV_Project / UNAV_Navigation / UNAV_VisibleSector
  / UNAV_Overlays / UNAV_ScienceLayers / UNAV_Missions
  / UNAV_Debug`. Pre-v3.1 roots (`UNAV_Starfield`, etc.)
  are migrated automatically when
  `ensure_project_structure(doc)` runs against a
  legacy scene.
* **Mission packs.** New
  `unav_pro/project/mission_packs.py` bundles missions
  for sharing across projects. `import_pack` is
  duplicate-safe with three collision strategies:
  `"skip"`, `"replace"`, `"rename"`.
* **Notes system.** New `unav_pro/project/notes.py`
  with three kinds of notes: project / mission /
  dataset, all stored as plain markdown for
  diff-friendliness. Atomic writes; idempotent
  deletes.
* **Project panel facade.** New
  `unav_pro/project/panel_actions.py` provides
  pure-Python wrappers the dialog's *Project* panel
  calls (Create / Open / Save / Summary / Open
  Folder / Notes). The facade is fully unit-tested
  without any UI primitives.

## What's new in detail

### Modules

* `unav_pro/project/__init__.py` — package entry; re-
  exports the public API.
* `unav_pro/project/project_manifest.py` —
  `ProjectManifest` + reference dataclasses + atomic
  JSON I/O.
* `unav_pro/project/workspace.py` — `Workspace` facade,
  `create_workspace`, `open_workspace`,
  `WorkspaceSummary`.
* `unav_pro/project/notes.py` — `NotesStore`,
  `NoteEntry`, `relative_path_for_note`.
* `unav_pro/project/mission_packs.py` — `MissionPack`,
  `build_pack_from_missions`, `read_pack`,
  `write_pack`, `import_pack` with collision
  strategies + `ImportReport`.
* `unav_pro/project/panel_actions.py` — pure facade for
  the dialog's Project panel.
* `unav_pro/c4d_objects/scene_structure.py` — pure
  planning helpers (`plan_hierarchy`, `diff_hierarchy`,
  `plan_cleanup`) + c4d-bound builders
  (`ensure_project_structure`,
  `cleanup_project_structure`).

### Documentation

* `docs/V3_1_PROJECT_WORKSPACES.md` — milestone
  overview.
* `docs/SCENE_ORGANIZATION.md` — canonical Cinema 4D
  hierarchy + migration.
* `docs/MISSION_ASSET_MANAGEMENT.md` — mission packs
  + reusable mission assets.
* `docs/PROJECT_NOTES_SYSTEM.md` — the notes layer.

### Release engineering

* `PLUGIN_VERSION` 3.0.0 → 3.1.0; codename *Project
  Workspaces & Scene Organization*.
* `RELEASE_NOTES_v3.1.md` (this file).
* CHANGELOG entry.
* Packaging script ships the four new docs +
  RELEASE_NOTES_v3.1.md; `REQUIRED_FILES` updated.

## What didn't change

* No new on-disk schemas for v0.x → v3.0 surfaces.
  Mission JSON, Route JSON, Camera Path JSON, Export
  Manifest, DB schema, binary format are all
  byte-identical to v3.0. The new `ProjectManifest`
  schema is additive.
* No new runtime dependencies. Stdlib-only at runtime.
* No rendering, no IPC, no RelativityRender bridge.
* No threading. The v3.0 task queue is still
  cooperative single-threaded.
* No replacement of core architecture. v0.1 → v3.0
  authoring surfaces continue to work unmodified.

## Migration

* **Drop-in v3.0 upgrade.** v3.0 saves load cleanly in
  v3.1. No format change.
* Workspaces are **opt-in**. Existing flat-on-disk
  workflows (per-user `~/.unav_pro/`) continue to work;
  the `Workspace` layer is a project-scoped container
  that lives next to the v0.x storage.
* Legacy scene roots (`UNAV_Starfield`,
  `UNAV_Overlays`, `UNAV_ScienceLayers`) auto-migrate
  to the canonical hierarchy when
  `ensure_project_structure(doc)` runs against them.

## Acceptance

* [x] User can create / open / save UNAV workspaces.
* [x] Scenes remain organised — canonical
  `UNAV_Project` hierarchy materialised by
  `ensure_project_structure`.
* [x] Mission assets are reusable — packs ship
  with `read_pack` / `write_pack` /
  `import_pack` (duplicate-safe).
* [x] Project structure is deterministic — manifests
  serialise to byte-stable JSON; references are
  workspace-relative.
* [x] Notes persist safely — atomic
  temp+rename writes, idempotent deletes.
* [x] Exports integrate with project structure —
  `workspace_export_subdir` + `export_path_for_action`
  land exports inside `<workspace>/exports/`.
* [x] No renderer assumptions, no IPC.

## Testing

* Full suite passes: **2032 tests** (1895 v3.0
  baseline + 137 new v3.1 tests).
* New v3.1 test files:
  * `test_v31_project_manifest.py` — schema, references,
    validation, round-trip, I/O.
  * `test_v31_workspace.py` — create / open / save,
    subdir helpers, references, summary.
  * `test_v31_scene_structure.py` — pure planning
    helpers (the c4d-bound builders raise outside the
    host).
  * `test_v31_mission_packs.py` — pack format,
    importer collision strategies, error containment.
  * `test_v31_notes.py` — safe-filename mapping, write
    / read / delete, summaries, atomic writes.
  * `test_v31_panel_actions.py` — pure UI facade
    lifecycle + export-path helpers.

## Boundary, restated

UNAV Pro v3.1 is an **astronomical navigation + voyage /
camera-animation tool for Cinema 4D**, scaled for very
large catalogs (v3.0) and organised for production
projects (v3.1). Rendering, IPC, real-time scientific
simulation, online services, and render-engine bridges
remain explicitly out of scope.

For the long-form view of the boundary see
[`docs/ROADMAP.md`](docs/ROADMAP.md) §4–§5.
