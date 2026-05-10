# UNAV Pro — v3.45 Native Cinema 4D Workflow

How v3.45 makes UNAV feel like a real Cinema 4D
plug-in rather than a tool that happens to live
inside one.

For the underlying audit see
[`V3_45_C4D_INTEGRATION_AUDIT.md`](V3_45_C4D_INTEGRATION_AUDIT.md).

---

## 1. Native vs custom: what we kept

UNAV honours Cinema 4D's conventions wherever
possible:

* **One dialog, several panels.** A `GeDialog`
  subclass with native panels — no floating helper
  windows.
* **`BaseObject` + `BaseTag` only.** No custom
  geometry primitives, no custom shaders. Visible-
  sector points, overlays, science layers, mission
  previews, and waypoint nulls are all stock
  C4D objects with UNAV marker containers
  attached.
* **Standard undo discipline.** Every scene mutation
  goes through `StartUndo` / `AddUndo` /
  `EndUndo`. v3.45 enforces this via the new
  `UndoSession` context manager (see
  [`UNDO_REDO_SUPPORT.md`](UNDO_REDO_SUPPORT.md)).
* **Standard timeline writing.** Baked tracks are
  real `c4d.CTrack` instances; markers are real
  `TimelineMarker` records. The dialog never
  rolls its own keyframe view.

## 2. Object Manager polish

* **Single canonical root.** `UNAV_Project` is the
  one top-level UNAV null in every document. Six
  child groups underneath
  (`UNAV_Navigation`, `UNAV_VisibleSector`,
  `UNAV_Overlays`, `UNAV_ScienceLayers`,
  `UNAV_Missions`, `UNAV_Debug`) match the v3.1
  canonical hierarchy.
* **Deterministic names.**
  `c4d_objects.naming.*` produces the same name
  for the same input every time. No timestamps,
  no random suffixes.
* **No duplicate roots.** v3.45's
  `find_duplicate_roots` planner detects + queues
  any duplicates; `cleanup_project_structure`
  removes them inside an undo block.
* **Discoverable prefix.** Every UNAV-owned
  object's name starts with `UNAV_`; every UNAV-
  owned timeline marker starts with `UNAV:`.
  Cinema 4D's *Find Object* dialog finds them
  with one click.

## 3. Selection handling

UNAV's selection model is "the artist owns it":

* `Inspect Selected Object` reads
  `doc.GetActiveObject()` directly. No UNAV-side
  selection state shadows the document's.
* When the inspector resolves a selected uid, it
  does **not** change the active selection — the
  panel only reads.
* When the dialog *does* set a selection (after
  Search → Focus, or Bookmarks → Jump), it calls
  `BaseDocument.SetActiveObject(obj, mode=BIT_ACTIVE)`
  exactly once + emits `EventAdd` so the OM
  refreshes.

## 4. Attribute Manager integration

* Navigator parameters (cone angle, near/far clip,
  max visible) live in C4D **user data** on the
  navigator null. The artist edits them via the
  AM exactly the same way they'd edit a stock
  null.
* Mission metadata (title, tags) lives in the
  mission JSON — the AM doesn't see it. The
  Mission panel renders it.
* Overlay settings live in the v2.0 settings
  dataclass — also outside the AM. The Overlays
  panel renders them.
* v3.45 doesn't introduce new AM-visible fields.
  The contract is "C4D-native scene data lives on
  C4D objects; UNAV-internal data lives in JSON."

## 5. UI text + status messages

v3.45 tightens a few status-line strings for
clarity:

* `"Sync Visible Sector"` (button) → unchanged.
* Status log on success:
  `"Sync: +N added, =M kept, -K removed (mode=instances)"`
  → drops the noise prefix on rebuilds where
  nothing changed (`unchanged (12,003 visible)`).
* Long-operation warnings now reference the v3.0
  task queue: `"… consider routing through the
  task queue"`.
* Reset-tools messages all start with
  `"Reset 'X':"` so the artist can scan the log
  for reset history.

## 6. Viewport interaction

The viewport-visibility planner
(`c4d_objects/viewport_visibility.py`) introduces
three workflow profiles:

* **Author** — everything visible (default).
* **Lecture** — debug nulls + waypoint helpers
  hidden; visible-sector points + overlays stay.
* **Bake** — only visible-sector points stay;
  everything else hidden so the C4D renderer sees
  only what should end up in the frame.
* **Hidden** — the whole UNAV layer is invisible.

The dialog's *Display* panel exposes the profile
picker; the c4d-bound applier walks every
UNAV-owned object and flips its
`ID_BASEOBJECT_VISIBILITY_*` slots.

The label-clutter policy (also in
`viewport_visibility.py`) returns the labels to
keep visible at the current camera distance, so a
sector with 200 waypoint labels doesn't make the
viewport unreadable.

## 7. Timeline polish

* **Baked track names.**
  `naming.baked_track_name(target="camera",
  suffix="PSR")` →
  `"UNAV:Bake:camera:PSR"`. The timeline groups
  every UNAV-owned bake under the
  `UNAV:Bake:*` namespace.
* **Marker tokens.**
  `naming.marker_token(kind, payload)` → e.g.
  `"UNAV:waypoint:saturn"`. Five kinds:
  `waypoint`, `epoch`, `sync`, `science`,
  `presentation` (new in v3.45 for the v3.3
  presentation mode).
* **Cleanup.** *Clear UNAV Keyframes* /
  *Clear Timeline Markers* dispatch via the v3.45
  `UndoSession` so a single Ctrl-Z unwinds.

## 8. Scene lifecycle

The v3.45 lifecycle planner
(`c4d_objects/lifecycle.py`) explicitly handles:

* **Document opened** — rebind state-manager,
  reload workspace if active, rediscover scene
  objects.
* **Document closed** — flush workspace, drop
  in-memory pointers, reset caches.
* **Document switched** — rebind to new doc,
  rediscover scene objects when multi-doc.
* **Plugin reloaded** — full state re-bind +
  cache reset.
* **Document saved** — refresh workspace mtime.

See [`MULTI_DOCUMENT_BEHAVIOR.md`](MULTI_DOCUMENT_BEHAVIOR.md)
for the multi-doc model.

## 9. What we kept off the table

* No custom viewport renderer. UNAV doesn't draw
  pixels in the editor; Cinema 4D's native
  viewport handles everything.
* No `c4d.threading`. The plugin is single-
  threaded; the v3.0 task queue is cooperative.
* No stand-alone helper objects we expect the
  artist to manage. Every UNAV object is born
  under `UNAV_Project`.
* No external renderer bridges. UNAV populates
  the scene; C4D's renderers (Standard / Redshift
  / Octane / Arnold) draw it.
