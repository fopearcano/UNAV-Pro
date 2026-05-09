# Export Package Format

The on-disk layout of a v2.3 UNAV Pro export package. This
is the format a third-party reader / archival tool / other
DCC needs to know to consume an exported voyage package
without UNAV running.

For the milestone overview see
[`V2_3_EXPORT_PIPELINES.md`](V2_3_EXPORT_PIPELINES.md). For
the camera-path JSON used inside `camera_paths/` see
[`CAMERA_PATH_INTERCHANGE.md`](CAMERA_PATH_INTERCHANGE.md).

---

## 1. Directory layout

A package is a directory on disk. The default top-level name
is `UNAV_Export/`; the artist can pick any directory.

```
UNAV_Export/
  manifest.json
  missions/
    <mission_title>.json
    ...
  routes/
    <route_name>.json
    ...
  timelines/
    <label>.json
    ...
  camera_paths/
    <label>.json
    ...
  datasets/
    science_layers.json
    ...
  summaries/
    dataset_summary.json
    ...
  docs/
    *.md
```

Every package has all seven sub-directories
(`PACKAGE_SUBDIRS`); empty ones are present but contain no
files. The manifest's ``included_assets`` map lists only
what was actually written.

---

## 2. The manifest

`manifest.json` is the package's table of contents. Required
fields (the v2.3 validator enforces them):

| Field | Type | Meaning |
|-------|------|---------|
| `manifest_version` | int | Schema version. Currently `1`. |
| `exported_at_iso` | string | UTC timestamp at export time, e.g. `"2026-01-01T00:00:00Z"`. |
| `plugin_version` | string | UNAV Pro version that produced the package. |
| `coordinate_convention` | string | Free-form description of the coordinate frame (default: `"C4D world units, Y-up"`). |
| `units` | object | Per-channel unit map (`position`, `rotation`, `fov`, `epoch`, `time`). |

Optional fields:

| Field | Type | Meaning |
|-------|------|---------|
| `package_name` | string | Human-readable package label. |
| `notes` | string | Free-form artist notes. |
| `active_datasets` | list[string] | Names of the datasets enabled at export time. |
| `included_assets` | object | `{subdir: [filename, ...]}` — what was written, by class. |

A complete manifest example:

```json
{
  "manifest_version": 1,
  "exported_at_iso": "2026-01-01T12:34:56Z",
  "plugin_version": "v2.3",
  "coordinate_convention": "C4D world units, Y-up",
  "units": {
    "position": "C4D_world_units",
    "rotation": "radians_HPB",
    "fov": "radians_horizontal",
    "epoch": "julian_date",
    "time": "seconds"
  },
  "package_name": "UNAV_Export",
  "notes": "",
  "active_datasets": ["Gaia DR3", "JPL Horizons"],
  "included_assets": {
    "missions": ["Inner_System_Tour.json"],
    "camera_paths": ["Inner_System_Tour.json"],
    "summaries": ["dataset_summary.json"]
  }
}
```

The manifest is written **last** in the package build flow,
so a partial export always has either a complete manifest or
no manifest at all.

---

## 3. Per-asset files

Each subdirectory carries one file per asset; the filename
is sanitised from the artist-supplied label.

### 3.1 `missions/<title>.json`

The v1.4 mission JSON, unchanged. Round-trips through
``Mission.from_json`` /  ``Mission.to_json``.

### 3.2 `routes/<name>.json`

The v0.6 route JSON, unchanged. Round-trips through
``Route.from_json`` / ``Route.to_json``.

### 3.3 `camera_paths/<label>.json`

The v2.3 DCC-agnostic camera exchange document. See
[`CAMERA_PATH_INTERCHANGE.md`](CAMERA_PATH_INTERCHANGE.md)
for the full schema.

### 3.4 `timelines/<label>.json`

A flat keyframe dump:

```json
{
  "schema_version": 1,
  "exported_at_iso": "...",
  "fps": 30,
  "start_frame": 0,
  "end_frame": 240,
  "keyframes": [
    {"frame": 0, "position": [0,0,0], "rotation_hpb": [0,0,0], "fov_rad": null},
    ...
  ]
}
```

This is the v1.8 ``KeyframeRecord`` list flattened to JSON.
A future v2.x can produce alternative formats (FBX, USD)
that consume this canonical JSON as input.

### 3.5 `datasets/science_layers.json`

The v2.1 ``ScienceLayerSettings.to_dict`` payload + an
``enabled_layers`` convenience list:

```json
{
  "schema_version": 1,
  "exported_at_iso": "...",
  "settings": { ... full ScienceLayerSettings dict ... },
  "enabled_layers": ["distance_shells", "motion_vectors"]
}
```

### 3.6 `summaries/dataset_summary.json`

The v2.3 dataset summary. See
[`DATASET_SUMMARY_EXPORT.md`](DATASET_SUMMARY_EXPORT.md).

### 3.7 `docs/*.md`

Free-form Markdown docs the artist passes via
``extra_docs={…}``. The package builder sanitises filenames
+ appends `.md` if absent.

---

## 4. Filename hygiene

Mission titles / route names / camera-path labels are
passed through ``_safe_filename`` in
`export/export_manager.py`:

* Path separators (`/`, `\\`) → `_`.
* Windows-illegal characters (`:*?"<>|`) → `_`.
* Whitespace → `_`.
* Leading / trailing underscores stripped.
* Length capped at 96 characters.
* Default extension appended if missing.

Empty / all-whitespace input falls back to `"unnamed"`.

A mission titled `"Bad/Name:Here"` becomes
`"Bad_Name_Here.json"` on disk.

---

## 5. Reading a package

```python
from export import read_export_package

manifest = read_export_package("/path/to/UNAV_Export")
if manifest is None:
    print("not a valid UNAV package")
else:
    print(manifest.plugin_version, manifest.included_assets)
```

`read_export_package` returns ``None`` when the directory
or ``manifest.json`` is missing / corrupt — same fail-closed
contract as the rest of UNAV's persistence layer.

For the asset files themselves, point a JSON loader at the
absolute path; the schema versions inside each file let a
downstream reader refuse newer versions it doesn't
understand.

---

## 6. Versioning

The manifest's `manifest_version` will be bumped only when
the on-disk layout changes incompatibly. v2.x readers can
refuse newer versions; older readers should refuse newer
versions too (the v2.3 reader logs a warning + still loads
best-effort).

Each per-asset format carries its own `schema_version`:

* Mission JSON: v1.4 schema (currently `1`).
* Route JSON: v0.6 schema (currently `1`).
* Camera path JSON: v2.3 schema (currently `1`).
* Timeline keyframe JSON: v2.3 schema (currently `1`).
* Science-layer JSON: v2.3 schema (currently `1`).
* Dataset summary JSON: v2.3 schema (currently `1`).

A package can bump one asset's version without bumping
others; the manifest's version is independent.

---

## 7. Atomicity

Every file in a package is written via
``core.config.safe_write_json`` — atomic temp-file +
rename. The manifest is written last, so a partial export
on a crashed machine looks like:

* manifest.json present + every listed file present
  (success), or
* manifest.json absent + some files present (the artist
  knows the export was partial and re-runs).

The package builder never deletes existing files outside the
sub-directories it owns. The artist can place hand-edited
files alongside the manifest without UNAV touching them on
re-export — the validator's duplicate-filename check is
within-package only.

---

## 8. The build report

`build_export_package` returns a `PackageBuildReport`:

```python
@dataclass
class PackageBuildReport:
    package_root: str
    files_written: List[str]
    warnings: List[str]
    manifest_path: str
    success: bool
```

The dialog renders `report.render_text()`:

```
Package: /tmp/UNAV_Export (3 file(s) written).
Manifest: /tmp/UNAV_Export/manifest.json
```

`success=False` indicates the build hit at least one
error-severity validation issue; the warnings list carries
the details.
