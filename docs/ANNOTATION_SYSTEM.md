# Annotation System

The v1.9 ``voyage.annotations`` module gives missions three
layers of annotation: waypoint-level, scene-level, and
mission-level — plus a metadata-derived note synthesiser.

---

## 1. The three layers

| Layer | Where it lives | Purpose |
|-------|----------------|---------|
| **Waypoint** | ``MissionWaypoint.notes`` (already in v1.4) + the new ``derive_notes(wp)`` helper | Per-stop prose. Renders under each waypoint in the dialog and in the Markdown export. |
| **Scene** | ``Mission.scene_annotations`` (new in v1.9) | Free 3D labels at fixed coordinates. Don't drive the camera path. |
| **Mission** | ``Mission.description``, ``Mission.tags`` | Summary + categorisation for the whole voyage. |

All three round-trip through the existing mission JSON.
Existing v1.4 / v1.8 missions deserialise unchanged.

---

## 2. Scene annotations

```python
from voyage import (
    SceneAnnotation,
    add_scene_annotation,
    get_scene_annotations,
    remove_scene_annotation_at,
)

annotation = SceneAnnotation(
    label="Solar System Origin",
    x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
    notes="The Sun. Treat as the navigator's home anchor.",
    tags=["origin", "Star"],
)
add_scene_annotation(mission, annotation)

# Read back any time:
for a in get_scene_annotations(mission):
    print(a.label, a.notes)

# Remove by index:
remove_scene_annotation_at(mission, 0)
```

`SceneAnnotation` validates: a non-empty label is required.
Tags lower-case automatically (same convention as waypoint
tags).

The on-disk JSON stores annotations as plain dicts (not
dataclass instances), so the mission round-trip stays
backward-compatible. The ``get_scene_annotations`` helper
wraps them in ``SceneAnnotation`` instances on read.

---

## 3. Metadata-derived notes

`derive_notes(waypoint)` synthesises plain-text notes from a
waypoint's existing fields:

```python
from voyage import MissionWaypoint, derive_notes

wp = MissionWaypoint(
    kind="object", uid="gaia:42",
    catalog_source="Gaia DR3", object_type="star",
    epoch_jd=2451545.0,
)
derive_notes(wp)
# → ["from Gaia DR3", "object type: star", "uid: gaia:42",
#    "epoch: JD 2451545.000"]
```

The full rule set:

* ``catalog_source`` → ``"from <source>"``
* ``object_type`` → ``"object type: <type>"``
* ``uid`` (object / search_result / orbital kinds) → ``"uid: <uid>"``
* ``bookmark_id`` → ``"bookmark: <id>"``
* ``search_query`` → ``"found via search: <q>"``
* ``epoch_jd`` → ``"epoch: JD <X.XXX>"``
* ``has_pc_position`` → ``"position (pc): (x, y, z)"``
* ``pause_seconds > 0`` → ``"dwell: <X.XX> s"``
* ``camera_offset`` → ``"camera offset: (dx, dy, dz)"``

These are deterministic. The dialog renders them under each
waypoint; the Markdown exporter cites them as bullet points.

---

## 4. The unified annotations report

```python
from voyage import build_mission_annotations

report = build_mission_annotations(
    mission,
    scene_annotations=mission.scene_annotations,
    include_derived=True,
)
print(report.render_text())
```

`MissionAnnotations` carries:

* `title` / `description` / `mission_tags` from the mission.
* `waypoint_annotations` — one ``WaypointAnnotation`` per
  waypoint (index, label, kind, notes, derived sentences, tags).
* `scene_annotations` — list of ``SceneAnnotation`` instances.

`render_text()` produces a multi-line plain-text rendering
the dialog drops verbatim into its annotations panel.

`include_derived=False` skips the metadata synthesis — useful
when the artist only wants their own prose.

---

## 5. Markdown export integration

`mission_to_markdown(mission, include_annotations=True)` calls
the same machinery to produce a publication-style summary:

* The waypoints table is followed by per-waypoint
  ``### Waypoint N: <label>`` sub-sections containing the
  artist's notes + a bullet list of derived sentences.
* Scene annotations get their own ``## Scene Annotations``
  section.

`include_annotations=False` skips both blocks for a barebones
table-only export.

---

## 6. The dialog wiring

v1.9 doesn't yet ship a dedicated Annotations panel. The
Missions tab's existing **Route Analytics** button drops the
analytics + annotation rendering into the dialog log; the
**Export Markdown…** button writes the same data to disk in
Markdown form.

A future v1.x release may surface a dedicated panel
(per-waypoint editor, scene-annotation list with focus
buttons, etc.). v1.9's contract is "annotations *exist* and
*persist*"; the polished editor lands later.

---

## 7. Determinism

All three layers are deterministic:

* ``derive_notes`` is a pure function over the waypoint's
  fields; same input → byte-identical output.
* ``build_mission_annotations`` walks the mission in fixed
  order.
* ``render_text`` uses sorted tag lists where applicable.

Tests assert byte-equality across two consecutive renders.

---

## 8. What the annotation system is *not*

* **Not rich text.** All annotations are plain UTF-8.
  Markdown formatting is the artist's responsibility (the
  ``mission_to_markdown`` exporter passes notes through
  unchanged).
* **Not auto-generated mission descriptions.** UNAV does not
  invent a mission summary; ``mission.description`` is the
  artist's text verbatim.
* **Not a comment thread.** One ``notes`` field per
  waypoint, one ``description`` per mission. There's no
  multi-author / timestamped layer.
* **Not a translation layer.** No i18n; the derived
  sentences are English. Future v1.x can add localisation
  on top if needed.
