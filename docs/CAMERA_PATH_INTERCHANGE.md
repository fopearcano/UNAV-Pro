# Camera-Path Interchange JSON

A DCC-agnostic JSON format for the per-frame camera state
UNAV bakes from a mission. Designed so a Houdini / Maya /
Blender import script can read it without any UNAV runtime
dependency.

For the package layout that contains it see
[`EXPORT_PACKAGE_FORMAT.md`](EXPORT_PACKAGE_FORMAT.md). For
the v2.2 evaluator that produces the underlying samples see
[`ANIMATED_UNAV_STATE.md`](ANIMATED_UNAV_STATE.md).

---

## 1. Top-level shape

```json
{
  "schema_version": 1,
  "plugin_version": "v2.3",
  "exported_at_iso": "2026-01-01T12:34:56Z",
  "fps": 30,
  "start_frame": 0,
  "end_frame": 240,
  "frame_count": 241,
  "coordinate_convention": "C4D world units, Y-up",
  "units": {
    "position": "C4D_world_units",
    "rotation": "radians_HPB",
    "fov": "radians_horizontal",
    "epoch": "julian_date",
    "time": "seconds"
  },
  "mission_title": "Inner System Tour",
  "mission_id": "8f3c7a9c4b1d2e0f",
  "records": [
    {
      "frame": 0,
      "seconds": 0.0,
      "position": [0.0, 0.0, 0.0],
      "rotation_hpb": [0.0, 0.0, 0.0],
      "fov_rad": null,
      "epoch_jd": 2451545.0,
      "waypoint_index": 0
    },
    ...
  ]
}
```

---

## 2. Field reference

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | int | Currently `1`. Bumped on incompatible layout changes. |
| `plugin_version` | string | UNAV Pro version that produced the file. |
| `exported_at_iso` | string | UTC export timestamp. |
| `fps` | int | Frames per second the records are spaced at. |
| `start_frame` | int | First frame in the bake range. |
| `end_frame` | int | Last frame (inclusive). |
| `frame_count` | int | `end_frame - start_frame + 1`. |
| `coordinate_convention` | string | Free-form description; default `"C4D world units, Y-up"`. |
| `units` | object | Per-channel unit map; see §3. |
| `mission_title` | string \| null | Source mission title (informational). |
| `mission_id` | string \| null | Source mission id (informational). |
| `records` | list[object] | One record per frame. |

Each record:

| Field | Type | Notes |
|-------|------|-------|
| `frame` | int | C4D frame number. |
| `seconds` | float | Wall-clock seconds relative to `start_frame`. |
| `position` | list[3 floats] | Camera position. |
| `rotation_hpb` | list[3 floats] | Heading / Pitch / Bank in radians, C4D convention. |
| `fov_rad` | float \| null | Optional horizontal FOV. v2.2 carries one constant value across the path. |
| `epoch_jd` | float \| null | Optional Julian Date when the path is time-aware. |
| `waypoint_index` | int | Source segment index in the camera path. |

---

## 3. The `units` block

The block tells the importer how to interpret each channel:

* `position` — the unit of the per-frame xyz.
  * `"C4D_world_units"` — UNAV's default: parsec scaled by
    the active dataset's C4D scale factor (the dialog's
    `c4d_scale` setting).
  * Importers can multiply back by the inverse scale factor
    if they want parsec.
* `rotation` — the rotation channel encoding.
  * `"radians_HPB"` — Cinema 4D's Heading-Pitch-Bank order
    in radians. The HPB triple is what
    `c4d.BaseObject.SetRelRot` consumes directly.
* `fov` — `"radians_horizontal"` — horizontal FOV in
  radians.
* `epoch` — `"julian_date"`.
* `time` — `"seconds"`.

A future v2.x can add new units (`"parsec"`, `"degrees_HPB"`
etc.) without bumping the schema version, as long as the
field is documented here. The importer should treat unknown
units as opaque.

---

## 4. The HPB convention

UNAV converts its internal `(w, x, y, z)` quaternion to
HPB via `c4d_objects.timeline_keys.quaternion_to_hpb`:

* `H` (heading) — rotation about Y.
* `P` (pitch) — rotation about X.
* `B` (bank) — rotation about Z.
* Order: `H × P × B` applied right-to-left in the body frame
  (Cinema 4D's stock convention).

At the gimbal lock pole (`|pitch| ≈ 90°`), heading + bank
fold into a single rotation; the converter handles this
without producing NaN.

A Maya / Houdini importer can convert HPB to its own Euler
order via the standard rotation-matrix decomposition; the
v2.3 export uses radians so the conversion is unitless.

---

## 5. Determinism

The exchange document is deterministic by construction:

* The v2.2 evaluator produces byte-identical samples for
  identical input.
* The exporter walks `samples` in frame order.
* `to_json(sort_keys=True, indent=2)` produces stable
  output.

The only non-deterministic field is `exported_at_iso`. A
diff tool comparing two exports of the same mission shows
exactly one line of difference.

---

## 6. Reading the document

A minimal Python reader (no UNAV dependency):

```python
import json

def load_camera_path(path):
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    if doc.get("schema_version") != 1:
        raise ValueError(f"unsupported schema version: {doc.get('schema_version')}")
    return doc

doc = load_camera_path("camera_paths/Inner_System_Tour.json")
for record in doc["records"]:
    print(record["frame"], record["position"], record["rotation_hpb"])
```

A Houdini importer can hand the records to a
``CameraNode``'s position / rotation channels frame-by-
frame. A Blender importer can use the same per-record
interface against `bpy.context.scene.camera`. The format
intentionally avoids any binding to a specific DCC.

---

## 7. Three builder entry points

`export/camera_exchange.py` exposes three builders:

* `build_camera_exchange_from_mission(mission, path,
  frame_range, ...)` — the most common path. Evaluates the
  v2.2 animated state and flattens it.
* `build_camera_exchange_from_timeline(timeline,
  frame_range, ...)` — when the caller already has an
  ``AnimatedTimeline``.
* `build_camera_exchange_from_keyframes(keyframes,
  frame_range, ...)` — when the caller has v1.8
  ``KeyframeRecord`` rows from a hand-built bake.

All three produce a `CameraExchangeDocument` with the same
schema; pick whichever matches the caller's existing data.

---

## 8. What the format does *not* carry

* **No splines.** The export is per-frame samples; the
  underlying Catmull-Rom curve (v1.4) is not emitted. A
  downstream tool that wants the curve can refit one
  through the frame samples.
* **No camera target.** UNAV's "look-at" is encoded in the
  HPB triple at each frame; if the importer wants a target,
  it must convert direction → target itself.
* **No animated FOV.** v2.3 carries one constant FOV (or
  none). A future v2.x can vary FOV across the path
  without changing the document shape.
* **No tangent vectors.** Speeds / acceleration can be
  approximated by finite differences over the per-frame
  records.
* **No constraints / parents.** The exporter assumes the
  importer parents the camera to whatever rig it wants.

These are deliberate. The document is a shareable record
of "where the camera is at each frame," not a
reconstruction of UNAV's voyage internals.
