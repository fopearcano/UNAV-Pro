# UNAV Pro v2.3 — Export Pipelines & Interchange

UNAV's v2.3 milestone makes the plugin's data
*shareable*. Voyages, routes, camera paths, timeline
keyframes, and science-layer / dataset summaries can be
exported into self-describing files other DCCs, archival
workflows, or human readers can consume — without UNAV
running.

This is **not a render engine**. v2.3 is data interchange
and production workflow support. The visible-sector
pipeline, the v2.0 overlays, the v2.1 science layers, the
v2.2 timeline baker, and the v1.x voyage tools are all
unchanged.

For the deep dives:

* [`EXPORT_PACKAGE_FORMAT.md`](EXPORT_PACKAGE_FORMAT.md) —
  the on-disk layout: directory tree, manifest schema,
  versioning.
* [`CAMERA_PATH_INTERCHANGE.md`](CAMERA_PATH_INTERCHANGE.md)
  — DCC-agnostic camera JSON: position / rotation / FOV /
  frame-time mapping, units block.
* [`DATASET_SUMMARY_EXPORT.md`](DATASET_SUMMARY_EXPORT.md)
  — what the dataset summary carries + how to read it
  outside UNAV.

---

## 1. What v2.3 actually delivers

| Surface | Change |
|---------|--------|
| `export/export_manager.py` | New module: format registry + ``export_one(format, path, ...)`` single-format dispatcher + ``export_package(...)`` high-level package builder. Validation + atomic writes baked in. |
| `export/export_package.py` | New: `PackageManifest`, `PackagePayload`, `build_export_package`, `read_export_package`. Stable directory layout (`missions/`, `routes/`, `timelines/`, `camera_paths/`, `datasets/`, `summaries/`, `docs/`). |
| `export/camera_exchange.py` | New: DCC-agnostic camera-path JSON (`CameraExchangeDocument`, builders from mission / timeline / keyframes, atomic writer). |
| `export/dataset_summary.py` | New: `DatasetSummary` dataclass + `build_dataset_summary` + atomic writer. |
| `export/export_validation.py` | New: pre-flight validators (writable path / directory, mission, camera path, registry, manifest, duplicate filenames). Used by every exporter. |
| `ui/main_dialog.py` | Missions tab gains six **Export** buttons: Mission, Route, Camera Path, Timeline Data, Dataset Summary, Full Package. |
| Tests | Two new test files (`test_v23_*`) covering validation, single-format export, package builder, manifest round-trip, camera exchange, dataset summary. 57 new tests; **1649 Python tests pass.** |
| Docs | This file + three deep-dives. |

**No new features beyond exports.** No rendering, no IPC,
no external renderer bridge. Every v1.x + v2.x surface is
unchanged.

---

## 2. Eight supported formats

| Format constant | Default extension | Writer |
|-----------------|-------------------|--------|
| `FORMAT_MISSION_JSON` | `.json` | v1.4 ``Mission.to_json`` (atomic) |
| `FORMAT_ROUTE_JSON` | `.json` | v0.6 ``Route.to_json`` (atomic) |
| `FORMAT_WAYPOINT_CSV` | `.csv` | v1.9 ``mission_to_csv`` (atomic) |
| `FORMAT_ROUTE_MARKDOWN` | `.md` | v1.9 ``mission_to_markdown`` (atomic) |
| `FORMAT_CAMERA_PATH_JSON` | `.json` | v2.3 camera exchange JSON |
| `FORMAT_TIMELINE_KEYFRAMES_JSON` | `.json` | v1.8 keyframes flattened to JSON |
| `FORMAT_SCIENCE_LAYER_JSON` | `.json` | v2.1 ``ScienceLayerSettings.to_dict`` |
| `FORMAT_DATASET_SUMMARY_JSON` | `.json` | v2.3 dataset summary |

The dialog enumerates `list_export_formats()` to render the
picker; tests assert every entry has a stable `name`,
`label`, and `extension`.

---

## 3. The single-format API

```python
from export import (
    ExportSettings, FORMAT_MISSION_JSON, export_one,
)

result = export_one(
    FORMAT_MISSION_JSON, "/tmp/mission.json",
    mission=mission,
    settings=ExportSettings(allow_overwrite=False),
)
print(result.render_text())
```

`export_one`:

1. Resolves the writer for `format_name`. Unknown formats
   produce a validation error.
2. Runs `validate_writable_path(path, allow_overwrite=...)`.
3. Runs per-format pre-flight checks (mission for the
   mission-shaped formats; camera path for the camera-path
   format).
4. Dispatches to the writer. Writer exceptions are caught
   and surface as a `writer_exception` validation error.
5. Returns an ``ExportResult`` with `success`, `path`,
   `validation`, and a one-line `detail`.

Every exporter is *fail-closed*: any error-severity
validation issue aborts the export with no file written.
Warnings are logged but don't block the export.

---

## 4. The package API

```python
from export import (
    PackageBuildSettings, build_dataset_summary, export_package,
)

report = export_package(
    "/tmp/UNAV_Export",
    missions=[mission_a, mission_b],
    camera_paths_by_label={
        "alpha_path": (mission_a, camera_path_a, frame_range),
        "beta_path":  (mission_b, camera_path_b, frame_range),
    },
    timeline_keyframes_by_label={
        "alpha_path": (timeline_a.keyframes, frame_range),
    },
    science_layer_settings=science_layer_settings,
    dataset_summary_data=build_dataset_summary(registry=registry),
    active_dataset_names=["Gaia DR3", "SDSS"],
    settings=PackageBuildSettings(plugin_version="v2.3"),
)
print(report.render_text())
```

The package builder:

1. Pre-flights the directory.
2. Pre-flights duplicate filenames across all subdirs.
3. Materialises the directory tree
   (`missions/`, `routes/`, `timelines/`, `camera_paths/`,
   `datasets/`, `summaries/`, `docs/`).
4. Writes each asset atomically.
5. Builds + validates the manifest.
6. Writes `manifest.json` atomically.

Every input is optional. Empty inputs simply produce no
files in the corresponding subdirectory; the manifest's
``included_assets`` map reflects only what was written.

The dialog's **Export Full Package…** button uses this
high-level API. See
[`EXPORT_PACKAGE_FORMAT.md`](EXPORT_PACKAGE_FORMAT.md) for
the manifest schema + on-disk layout.

---

## 5. Validation pre-flight

Every exporter runs the v2.3 pre-flight validators before
materialising any file. The validator returns a
``ValidationReport`` with three severity levels:

* `error` — abort the export.
* `warning` — log it, proceed.
* `info` — log it, proceed.

Built-in validators:

* `validate_writable_path` — empty path, parent missing,
  overwrite refused, target-is-a-directory.
* `validate_writable_directory` — same shape, for the
  package builder.
* `validate_mission_for_export` — no mission, missing
  title, empty waypoints, unresolved waypoint count.
* `validate_camera_path_for_export` — empty path, single-
  waypoint path warning.
* `validate_dataset_registry` — missing / empty / no
  enabled entries.
* `validate_manifest` — required fields + soft type checks.
* `validate_no_duplicate_filenames` — within-package
  uniqueness.

The dialog logs every validation report; tests drive each
validator directly without touching the host.

---

## 6. Atomic writes everywhere

Every exporter ultimately calls
``core.config.safe_write_json`` (the v1.7 helper). A crash
mid-write cannot truncate a previously valid file: the
helper writes to a sibling `.tmp` file and atomically
renames into place.

This guarantees that:

* a partial export is never visible on disk,
* re-running an export with `allow_overwrite=True`
  preserves the previous file until the new one is fully
  written,
* the manifest write happens last in the package builder, so
  a partial package always has a present-or-absent (never
  half-written) manifest.

---

## 7. Filename hygiene

The package builder sanitises mission / route / camera-path
labels into safe filenames. Path separators (`/`, `\\`),
Windows-illegal characters (`:*?\"<>|`), and whitespace are
replaced with underscores. The resulting filename is capped
at 96 characters and gets the format's default extension if
absent.

Tests
(`test_v23_export_pipeline::test_package_safe_filename_replaces_invalid_chars`)
assert that a mission titled `"Bad/Name:Here"` becomes
something safe like `"Bad_Name_Here.json"` in the package.

---

## 8. The dialog flow

```
[Export Mission]      [Export Route]            [Export Camera Path]
[Export Timeline Data] [Export Dataset Summary] [Export Full Package…]
```

Each button:

1. Asks for a save path / directory via Cinema 4D's file
   dialog.
2. Calls the appropriate `export_one` / `export_package`.
3. Logs the `ExportResult` / `PackageBuildReport`.

The dialog's previous Markdown / CSV exports (from v1.9)
still live on the v1.9 row alongside `Filter`; v2.3 adds
the parallel buttons that flow through the unified export
manager. Both paths produce equivalent files.

---

## 9. Acceptance criteria

* [x] Artist can export complete voyage packages from one
  click.
* [x] Exported data is organised under a stable directory
  layout (`missions/`, `routes/`, `timelines/`,
  `camera_paths/`, `datasets/`, `summaries/`, `docs/`).
* [x] Every export is self-describing: schema versions on
  every JSON, units block on the camera-path JSON, manifest
  version on the package.
* [x] Exports are deterministic and versioned — same input
  → byte-identical output (within a fixed timestamp).
* [x] Camera-path exports are reusable in other DCCs (flat
  per-frame array, units block, no UNAV-specific runtime
  references).
* [x] Dataset summaries are understandable on their own:
  source counts, object counts, active filters, coordinate
  scale, active science layers, mission references.
* [x] Export failures are safe and clear — fail-closed
  validation, atomic writes, no partial state on disk.
* [x] No render-engine assumptions; no external renderer
  bridge; no IPC.

---

## 10. What v2.3 explicitly does **not** do

| Out of scope                                  | Why                                              |
|-----------------------------------------------|--------------------------------------------------|
| Cinema 4D scene export (.c4d / .fbx)          | The v0.x C4D-rendering surface is unchanged; ``.c4d`` save is the host's native path. |
| FBX / Alembic / USD camera writers            | DCC-specific writers can wrap the v2.3 camera-path JSON; v2.3 ships only the canonical JSON. |
| Database export (Gaia / SDSS dumps)           | The v0.5 / v1.1 catalog tools (JSONL + SQLite + binary v3) cover this. |
| Full visible-sector binary export             | The v0.8+ ``data/binary_export`` already ships v3. |
| Image renders / video                         | No render engine.                                 |
| RelativityRender / external integration       | Explicitly excluded.                              |
| IPC / sockets                                 | Explicitly excluded.                              |
