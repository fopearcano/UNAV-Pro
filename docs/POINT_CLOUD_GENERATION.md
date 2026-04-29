# UNAV Pro — Point Cloud Generation

How the plugin turns a UNAV catalog into a Cinema 4D scene, what it
does at MVP scale, and how the strategy must change as catalog size
grows. Companion to ``UNAV_PRO_ARCHITECTURE.md`` §3.5 and
``PLUGIN_STRUCTURE.md`` §6.

---

## 1. MVP strategy (≤ 10 k objects)

Implementation: ``unav_pro/c4d_objects/point_cloud_builder.py``.

For every catalog row:

  * one ``c4d.BaseObject(c4d.Onull)`` is created;
  * its display style is set to ``NULLOBJECT_DISPLAY_DOT`` so it
    appears as a small viewport marker;
  * its ``NULLOBJECT_RADIUS`` comes from ``radius_for_object`` (a
    magnitude-driven, clamped, scale-aware size);
  * ``ID_BASEOBJECT_USECOLOR`` + ``ID_BASEOBJECT_COLOR`` carry the sRGB
    colour from ``color_for_object`` (spectral-class lookup for stars,
    type-default otherwise);
  * a sub-``BaseContainer`` at ``BC_ID_UNAV_MARKER`` carries the UNAV
    marker payload: ``uid``, ``catalog_source``, ``object_type``,
    ``name``, ``metadata_json``, plus core astrometry.

Every UNAV object is parented under one ``UNAV_Starfield`` null. The
parent itself carries a marker with ``kind="starfield"`` so:

  * ``find_starfield(doc)`` can locate it after a save/load round trip,
  * ``clear_starfield(doc)`` can identify and remove only UNAV-tagged
    objects, leaving the rest of the user's scene untouched.

The whole build runs inside ``doc.StartUndo() / doc.EndUndo()`` so a
single Ctrl-Z reverts it. ``c4d.EventAdd()`` refreshes the viewport at
the end.

### Why nulls and not spheres / planes / instances at this scale

| Primitive          | Pros                              | Cons                                       |
|--------------------|-----------------------------------|--------------------------------------------|
| ``Onull`` (chosen) | Cheapest object, no geometry, taggable, viewport dot | Not directly renderable — fine for editor; render needs TP / instance pass |
| ``Osphere``        | Renders out of the box            | Polygons cost real memory; parameter changes recook geometry |
| ``Oplane``         | Cheap, billboard-able             | Needs orientation logic per-frame to face camera |
| ``Oinstance``      | Renderable, light                 | Still one ``BaseObject`` per row — no win at this scale |
| ``MatrixObject``   | Single object holds N matrices    | Per-instance metadata is harder; selection is coarser |

At ≤ 10 k the per-object cost of a null is negligible (hundreds of
microseconds per insert in C4D 2023). Nulls give us scene-graph
selection, the Object Manager UI, and proper undo for free. We pay
that for now and migrate later.

---

## 2. Performance envelope

| Catalog size | Expected build time (Python) | Viewport at 30 fps?         | Strategy                       |
|--------------|------------------------------|-----------------------------|--------------------------------|
| 100          | ≪ 100 ms                     | yes                         | Per-object null (current)      |
| 1 k          | ~ 100–400 ms                 | yes                         | Per-object null (current)      |
| 10 k         | ~ 2–6 s                      | yes, may stutter on select  | Per-object null (current)      |
| 100 k        | minutes                      | no                          | ``MatrixObject`` instance grid |
| 1 M          | hours / runs out of memory   | no                          | ``BaseDraw`` + packed buffer; native code preferred |

These are order-of-magnitude estimates on a 2024-era workstation. The
sample catalog of 100 objects builds in well under one frame and is
the only size guaranteed by the MVP.

---

## 3. Migration paths beyond 10 k

### 3.1 ``MatrixObject`` (10 k → ~ 200 k)

A single ``c4d.MatrixObject`` (object type ``Omgmatrix``) owns an
array of ``c4d.Matrix`` instances and a parallel array of colours. One
``BaseObject``, N matrices — the per-row C4D overhead disappears.

Trade-offs:

  * Per-instance metadata cannot live on a per-instance
    ``BaseContainer`` — we move it to a side-car: a parallel UNAV
    array stored on the parent's marker container, indexed by the
    matrix slot.
  * Selection becomes "select an index", not "select a BaseObject" —
    the metadata inspector grows a hit-test path that maps a clicked
    matrix back to a uid.
  * Render-time visibility depends on the renderer: Standard /
    Physical see matrix instances natively; some third-party
    renderers need a ``c4d.Oinstance`` per slot in TP fallback.

### 3.2 ``BaseDraw`` callback + packed buffer (200 k → ~ 2 M)

``BaseDraw`` lets a generator object draw OpenGL/Metal directly. We
keep a packed point buffer (uid[u64], xyz[f32×3], colour[u32],
size[f16], flags[u16]) in CPU memory and submit it once per redraw.

Trade-offs:

  * No scene-graph entry per point — selection requires custom
    ray-vs-buffer hit testing inside the inspector.
  * Not visible to renderers without a fallback path. The plugin will
    let the user toggle *Editor draw* (BaseDraw) vs *Render-ready*
    (TP / matrix) per ``UnavDataset`` — see PLUGIN_STRATEGY §4.4.
  * Still bounded by Python: the buffer pack itself is O(N) Python
    code and dominates above ~ 1 M points.

### 3.3 Native code (≥ 2 M)

The path described in ARCHITECTURE §5: pybind11 / Maxon SDK module
for spatial index core, buffer assembly, and cone/frustum kernels.
The Python plugin keeps the same ``build_starfield`` entry point; it
just calls a native ``unav_buffer_pack`` instead of a Python loop.

GPU compute (CUDA / Metal / Vulkan) lives behind the same boundary.
The plugin never knows — it sees a packed buffer ready to draw.

---

## 4. Why this can't all be done in Python

The Python prototype is bounded by three things:

  1. **GIL.** Buffer assembly cannot use C4D's main thread without
     stalling the viewport; offloading to a worker thread still
     serializes through the GIL on every Python-side allocation.
  2. **Allocation cost.** Each ``c4d.BaseObject`` is an allocated
     handle plus a ``BaseContainer``; even with hand-tuned code,
     creating a million of them is a multi-minute operation.
  3. **Float32 viewport.** Even with a perfect builder, the C4D
     viewport stack is float32. At kpc / Mpc scales this loses
     precision on individual point positions until we apply the
     floating-origin rebase from ARCHITECTURE §3.6 — a separate
     workstream, but a hard prerequisite for big fields.

These limits motivate the C++ migration plan. They are not a
discovery; they are the predicted shape of the problem and the reason
the Python plugin is intentionally an MVP.

---

## 5. UI integration

The dialog buttons, defined in ``unav_pro/ui/main_dialog.py``, route
through ``unav_pro/core/mock_actions.py``:

  * **Load Dataset** → ``mock_actions.load_dataset()`` reads the
    bundled sample catalog and reports ``loaded N objects``. No scene
    side effects.
  * **Generate Point Cloud** → ``mock_actions.generate_point_cloud()``
    loads the bundled sample, calls
    ``c4d_objects.point_cloud_builder.build_starfield`` against the
    active document, reports ``generated N point objects under
    'UNAV_Starfield'``.
  * **Clear Scene** → ``mock_actions.clear_scene()`` calls
    ``clear_starfield`` and reports the count removed. **Only
    UNAV-tagged objects are removed**; user content is untouched.
  * **Create Navigation Null** → still a stub; navigation lands later.

Every handler returns a status string and never raises out of the
dialog event loop.

---

## 6. Data flow at runtime

```
User clicks "Generate Point Cloud"
        |
        v
mock_actions.generate_point_cloud()
        |
        +-- data.catalog_io.load_catalog( default_sample_catalog_path() )
        |       |
        |       +-- data/samples/sample_catalog_100.jsonl
        |
        +-- documents.GetActiveDocument()
        |
        +-- c4d_objects.point_cloud_builder.build_starfield(doc, objects)
                |
                +-- clear_starfield(doc)   # idempotent rebuild
                +-- _create_starfield_null(doc, scale_mode)
                +-- for obj in objects:
                |       build_point_object(obj, scale_mode)
                |          |-- position_for_object  (from cached c4d_x/y/z)
                |          |-- radius_for_object    (magnitude-driven)
                |          |-- color_for_object     (spectral / type)
                |          \-- _write_marker        (BC_ID_UNAV_MARKER)
                +-- doc.AddUndo(NEWOBJ, child)  # full undo support
                +-- c4d.EventAdd()              # viewport refresh
```

---

## 7. Save/load round-trip

The marker container is part of the object's ``BaseContainer`` and
therefore survives ``.c4d`` save/load. After reopening:

  * ``find_starfield`` re-locates the parent by marker.
  * ``is_unav_object`` correctly identifies all children.
  * ``clear_scene`` works without re-running ``build_starfield``.

The pipeline-level cache (Parquet tiles, ``.unavscene`` references) is
**not** required to reopen a generated ``.c4d`` — the per-object
metadata is sufficient to render and to drive the metadata inspector
once that lands. Re-generation does require the catalog file.
