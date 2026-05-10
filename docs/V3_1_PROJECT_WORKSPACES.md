# UNAV Pro — v3.1 Project Workspaces

The v3.1 milestone is about **production-ready project
organisation**. Real productions have many missions, many
artists, and a need for the same project to look the same
when reopened weeks later. v3.1 adds the
**workspace-based project layer** that makes that work.

This is **not** rendering. **Not** a new authoring
surface. The runtime feature set is unchanged from v3.0;
v3.1 adds the *structure* under which the existing
authoring surfaces operate.

For deep dives see:

* [`SCENE_ORGANIZATION.md`](SCENE_ORGANIZATION.md) — the
  canonical Cinema 4D hierarchy.
* [`MISSION_ASSET_MANAGEMENT.md`](MISSION_ASSET_MANAGEMENT.md)
  — mission packs and reusable mission assets.
* [`PROJECT_NOTES_SYSTEM.md`](PROJECT_NOTES_SYSTEM.md) —
  the project / mission / dataset notes layer.

---

## 1. The workspace

A workspace is a directory tree the artist owns:

```
UNAV_Project/
├── project_manifest.json
├── datasets/
├── cache/
├── missions/
├── routes/
├── exports/
├── overlays/
├── timelines/
└── notes/
```

Every UNAV operation that produces a file (catalogs,
mission JSONs, route JSONs, baked timelines, exports) can
land inside the relevant subdirectory. The manifest at
the root tracks what's there and references everything by
**workspace-relative path** so the workspace stays
portable across machines.

## 2. The manifest

`project_manifest.json` is a JSON document with eight
top-level fields:

* `schema_version` — bump-on-incompatible-change;
  v3.1 ships `1`.
* `project_name` / `project_description` — free-form
  artist-owned strings.
* `plugin_version` — the version that wrote it.
  Forensic; the loader doesn't reject mismatches.
* `created_at_iso` / `updated_at_iso` — UTC stamps.
* `scale_mode` — the navigator's scale (e.g.
  `"parsec_to_cm"`).
* `datasets` — list of `DatasetReference` entries.
* `missions` — list of `MissionReference` entries.
* `routes` — list of `RouteReference` entries.
* `timelines` — list of `TimelineReference` entries.
* `overlays` / `science_layers` — settings snapshots.
* `metadata` — free-form dict.

Every reference inside the manifest is a
**workspace-relative** path. The loader rejects absolute
paths and `..` traversal so a malicious manifest cannot
escape the workspace.

## 3. Lifecycle

```python
from project import create_workspace, open_workspace

# Create.
ws = create_workspace(
    "/path/to/UNAV_Project",
    project_name="Voyager Cinematic",
    plugin_version="3.1.0",
)

# Open.
ws = open_workspace("/path/to/UNAV_Project")

# Inspect.
print(ws.summary().render())

# Mutate references.
ws.add_mission(MissionReference(
    mission_id="my-mission",
    path="missions/my-mission.json",
))
ws.save()
```

`create_workspace` refuses to overwrite an existing
manifest unless `overwrite=True` — the artist must
explicitly opt in. `open_workspace` raises
`WorkspaceError` on a missing or malformed manifest.

## 4. The dialog's Project panel

The v3.1 dialog gains a *Project* panel with six buttons:

* **Create Workspace…**
* **Open Workspace…**
* **Save Workspace**
* **Project Summary**
* **Open Project Folder**
* **Notes**

Each button calls a thin facade in
`unav_pro/project/panel_actions.py`. The facade is pure
Python — tests exercise the lifecycle without faking any
UI primitives.

## 5. Export integration

When a workspace is active, exports default to landing
inside `<workspace>/exports/<subdir>/`. The
`workspace_export_subdir(...)` helper computes the
absolute target path and creates the directory.

When no workspace is active, the existing v2.3 export
defaults (next to the scene file) remain in effect.

## 6. Acceptance

* [x] User can create / open / save UNAV workspaces.
  `create_workspace` / `open_workspace` /
  `Workspace.save()`.
* [x] Scenes remain organised. The v3.1 hierarchy
  (`UNAV_Project` + six canonical children) is
  documented in
  [`SCENE_ORGANIZATION.md`](SCENE_ORGANIZATION.md) and
  materialised by `ensure_project_structure(...)`.
* [x] Mission assets are reusable. Mission packs
  (`unav_pro.project.mission_packs`) bundle one or
  more missions for sharing; `import_pack` is
  duplicate-safe (skip / replace / rename).
* [x] Project structure is deterministic. Manifests
  serialise to byte-stable JSON; references are
  workspace-relative; the eight subdirs are always
  the same.
* [x] Notes persist safely. Atomic temp+rename writes;
  delete is idempotent.
* [x] Exports integrate with project structure.
  `workspace_export_subdir` + `export_path_for_action`
  land exports inside `exports/`.
* [x] No renderer assumptions, no IPC, no
  RelativityRender bridge.

## 7. What's not in v3.1

* No project-version migration framework. v3.1 ships
  schema_version 1; the loader rejects newer
  versions fail-closed.
* No multi-workspace support. One workspace per
  Cinema 4D document.
* No remote storage / git integration. Workspaces
  are local directories the artist version-controls
  externally if they want to.
* No automatic asset relocation. Moving a workspace
  preserves relative references; absolute paths are
  refused at save time.
