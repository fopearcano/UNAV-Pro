# Render Backends

The v0.7 backend interface and what each shipping backend
guarantees. The interface is defined in
`unav_pro/c4d_objects/render_backend.py`; concrete backends live
alongside (`render_backend.py` for Debug Objects + Point Cloud,
`instance_builder.py` for Instances).

---

## 1. The interface

```python
class RenderBackend:
    mode: str  # token from core.render_mode

    def clear(doc) -> int:
        """Remove every backend-managed object from doc. Returns the count removed."""

    def build_visible_sector(
        doc, objects, *, encoding, scale_mode, max_visible,
    ) -> BackendUpdateResult:
        """Initial full build."""

    def update_visible_sector(
        doc, *, added, removed_uids, kept_uids, encoding, scale_mode,
    ) -> BackendUpdateResult:
        """Incremental sync; the diff is already computed by scene_sync."""

    def get_object_uid_from_selection(doc, c4d_object) -> Optional[str]:
        """Read the uid off a clicked node, or return None."""

    def supports_metadata_selection() -> bool:
        """True iff a click on a backend-owned node yields a uid."""

    def get_stats() -> BackendStats:
        """Return the most recent build stats for the dialog."""
```

`BackendUpdateResult(added, removed, kept, skipped, warnings)` and
`BackendStats(mode, last_build_seconds, visible_count,
generated_count, estimated_scene_objects)` are the two
return-shape dataclasses every backend must populate.

`scene_sync.sync_visible_sector` calls
`update_visible_sector(...)` after computing the diff; the
backend's job is to apply `(added, removed_uids, kept_uids)`
inside the caller's undo block. There is no need to recompute
the diff inside the backend.

---

## 2. Debug Objects (default)

* **What it builds.** One `c4d.Onull` per visible row, each with
  a full marker BaseContainer (uid, source, type, name, ra, dec,
  distance, schema version). The v0.1 path, preserved.
* **Selection.** Direct: clicking a null in the Object Manager
  yields its full marker. The v0.5 inspector renders Identity /
  Astrometry / Photometry / Survey-Class / Raw-JSON as before.
* **Hard cap.** 10 000.
* **Soft warning.** Above 5 000 visible objects.
* **When to use.** Small-to-mid scenes where artists want every
  object selectable individually with full marker metadata.
* **Trade-offs.** Heaviest mode; viewport responsiveness drops
  past ~10 k.

Implementation: `DebugObjectsBackend` in `render_backend.py`
delegates to the existing `point_cloud_builder` helpers
(`build_point_object`, `build_starfield`, `clear_starfield`).

---

## 3. Instances

* **What it builds.** One shared template null
  (`UNAV_InstanceTemplate`, hidden, parented under
  `UNAV_Debug`) plus one `c4d.Oinstance` per visible row.
  Each instance carries a **minimal marker** with just
  `uid` + `kind` + `is_unav` + `schema_version`. Position
  comes from `c4d.SetAbsPos`; colour from
  `ID_BASEOBJECT_COLOR`; per-instance "size" from local scale
  on the instance (the template renders at unit dot).
* **Selection.** Direct: clicking the instance yields the uid;
  the inspector resolves the rest from the active
  `MetadataLookup`. The marker is intentionally tiny so the
  `.c4d` save stays small even at 200 k instances.
* **Hard cap.** 200 000.
* **Soft warning.** Above 50 000 visible instances.
* **When to use.** Mid-to-large scenes (10 k – 200 k objects).
* **Trade-offs.** Lighter than Debug Objects but still C4D
  scene nodes — every instance occupies a slot in the Object
  Manager and contributes to the safety advisory's scene-count.
  The per-instance marker stays uid-only on purpose; richer
  metadata stays in the lookup. See
  [`INSTANCE_MODE_LIMITATIONS.md`](INSTANCE_MODE_LIMITATIONS.md).

Implementation: `InstanceBackend` in `instance_builder.py`.

---

## 4. Point Cloud (experimental placeholder)

* **What it builds.** A single
  `UNAV_PointCloudPlaceholder` null under
  `UNAV_VisibleSector` so the editor knows the cloud exists,
  plus an in-memory `uid → CatalogObject` map on the backend
  itself so the v0.6 search panel and the inspector's
  search-based fallback can still resolve clicks.
* **Selection.** Indirect — clicking the placeholder does not
  yield a uid (`get_object_uid_from_selection` returns `None`,
  `supports_metadata_selection()` is `False`). The dialog
  detects this and replaces the inspector panel text with the
  "use Search tab" hint
  (`ui.metadata_panel.point_cloud_panel_text()`).
* **Hard cap.** 1 000 000 (advisory; the real renderer will
  set its own cap based on GPU memory).
* **Soft warning.** None — the cap is the cap.
* **When to use.** Today: experiments / smoke-testing the
  search fallback path. Tomorrow: the C++/GPU implementation
  swaps out `_ensure_placeholder` for a real `BaseDraw`
  callback; the rest of the contract stays the same.
* **Trade-offs.** No per-object selection until the GPU path
  ships. The fallback search workflow is the recommended
  inspection route.

Implementation: `PointCloudBackend` in `render_backend.py`.

---

## 5. Mode-switch contract

`scene_sync.sync_visible_sector(..., render_mode=...)` builds a
fresh backend per click via `backend_for_mode(...)`. Switching
mode between syncs is therefore safe:

1. Click Sync with `mode=instances` — old debug-object children
   removed by `_current_visible_objects` + `update_visible_sector`
   semantics; instances appear under `UNAV_VisibleSector`.
2. Click Sync with `mode=point_cloud` — the existing instances
   are removed (they no longer match the desired uid set under
   the cloud backend's bookkeeping) and replaced by the
   placeholder null.

The dialog warns the artist when crossing the soft threshold for
a mode but never silently escalates. `RenderModePolicy` carries
the mode + cap + warning toggle as a single object the UI passes
through.

---

## 6. Adding a new backend

1. Subclass `RenderBackend` and set `mode` to a new token from
   `core.render_mode.RENDER_MODES`.
2. Implement the five methods (`clear`, `build_visible_sector`,
   `update_visible_sector`, `get_object_uid_from_selection`,
   `supports_metadata_selection`).
3. Populate `BackendStats` via `_record_stats(...)` so the
   dialog's stats strip works.
4. Add the mode token + cap to `core.render_mode.DEFAULT_CAPS`.
5. Add the label to `RENDER_MODE_LABELS`.
6. Register the backend in `backend_for_mode(...)`.
7. Add a unit test against the pure-Python contract; the
   c4d-bound paths can stay smoke-tested via the existing
   guarded pattern.

---

## 7. Stats and the dialog

The Render Mode strip in the dialog reads
`mock_actions.last_render_stats()` after each Sync click and
formats `BackendStats.short_summary()`:

```
mode=instances, visible=12345, generated=12345, scene≈12349, build=87ms
```

* `visible` — total objects in the visible sector after the pass
  (added + kept).
* `generated` — backend-created C4D nodes in this pass (the
  delta — a sync that only removes objects shows `generated=0`).
* `scene≈` — estimate the safety advisory should treat as the
  visible-sector contribution to C4D's scene-object count.
* `build=Nms` — wall-clock time of the last
  `update_visible_sector` call.

These four numbers are the entire surface the dialog needs to
show "the backend is doing work, and the work is fast / heavy."
