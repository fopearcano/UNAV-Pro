# UNAV Pro — Scene Sync Workflow

The pro workflow for keeping the C4D scene aligned with the
navigator's filtered set: **diff and update in place** instead of
clear-and-rebuild. Iteration becomes cheap, the artist's selection
and per-object tags survive every nudge of the navigator, and large
visible sectors stay performant when only a few uids changed.

Companion to:

  * `RAY_CONE_FILTERING.md` (where the visible set comes from).
  * `POINT_CLOUD_GENERATION.md` (the materializer this workflow
    drives).
  * `NAVIGATION_NULL_SYSTEM.md` (the parameter source).

---

## 1. Hierarchy

```
UNAV_Starfield                 (root null, owns the scale-mode scope)
├── UNAV_VisibleSector         (null, holds the materialized point set)
│   ├── point object (uid=...)
│   ├── point object (uid=...)
│   └── ...
└── UNAV_Debug                 (null, holds debug visualizations)
    └── UNAV_DebugCone         (apex at navigator origin, optional)
```

Implementation: ``unav_pro/c4d_objects/point_cloud_builder.py`` now
exposes ``ensure_starfield_hierarchy(doc, scale_mode)`` which is
idempotent — every action (Generate, Regenerate, Sync) calls it and
gets back the three nulls regardless of whether the scene already
contained any of them.

Each null carries the standard ``BC_ID_UNAV_MARKER`` container so
``clear_starfield`` can remove the whole subtree by marker even
after the user renames a node.

Marker ``kind`` values used by this layer:

| Kind                | Object                                       |
|---------------------|----------------------------------------------|
| ``starfield``       | ``UNAV_Starfield`` (root).                   |
| ``visible_sector``  | ``UNAV_VisibleSector`` (point host).         |
| ``debug_root``      | ``UNAV_Debug``.                              |
| ``debug_cone``      | The cone wireframe (and its pose holder).    |
| ``point``           | One catalog object — unchanged from before.  |

---

## 2. The diff

Implementation: ``unav_pro/core/scene_sync.py``.

```
compute_diff(current_uids, wanted_uids, max_visible) -> SyncDiff
```

`SyncDiff` carries four lists / counts:

  * ``added_uids`` — uids present in ``wanted`` and not in
    ``current``. Ordering is the input ``wanted`` ordering, so a
    "closest first" or "brightest first" sort upstream is preserved.
  * ``kept_uids`` — intersection. These objects stay in the scene
    untouched.
  * ``removed_uids`` — uids present in ``current`` but not in
    ``wanted``. The corresponding C4D objects are deleted.
  * ``capped_uids`` — count of ``wanted`` entries dropped past the
    ``max_visible`` cap.

`SyncDiff.short_summary()` renders a one-line status:

```
+312 added, =1218 kept, -47 removed, 84 capped
```

`SyncDiff.total_visible == len(added) + len(kept)` — the count
that ends up in the C4D scene.

---

## 3. The pass

`sync_visible_sector(doc, objects, encoding=None, scale_mode=...,
max_visible=None, show_debug_cone=False)` runs:

  1. ``ensure_starfield_hierarchy(doc, scale_mode)`` — find or
     create the three nulls.
  2. Walk the children of ``UNAV_VisibleSector``, read each marker,
     and build ``current = {uid → c4d_obj}``.
  3. ``compute_diff(current.keys(), [o.uid for o in objects],
     max_visible)``.
  4. Inside ``doc.StartUndo() / doc.EndUndo()``:
     * For each removed uid: ``AddUndo(DELETE)`` then ``Remove()``.
     * For each added uid: ``build_point_object(obj, scale_mode,
       encoding)`` then ``InsertUnder(visible_sector)`` and
       ``AddUndo(NEWOBJ)``.
     * If ``show_debug_cone``: build / refresh the debug cone under
       ``UNAV_Debug``. Otherwise: remove the cone if present.
  5. ``c4d.EventAdd()``.

`build_point_object` is reused so each newly-added object ends up
with the same marker, colour, and radius it would get on a
clear-and-rebuild — only the *uids that did not change* avoid the
allocation cost.

The whole pass is one undo step: a single Ctrl-Z reverses every
add, every remove, and any debug-cone change.

---

## 4. Performance properties

| Sub-pass                   | Cost                                      |
|----------------------------|-------------------------------------------|
| Walk current visible set   | O(N_current). One marker read per child.  |
| Compute diff               | O(N_current + N_wanted) hash-set work.    |
| Remove pass                | O(N_removed) C4D allocator hits.          |
| Add pass                   | O(N_added) ``build_point_object`` calls.  |
| Debug cone update          | O(1).                                     |

Crucially: **N_kept doesn't pay any per-object cost.** A navigator
nudge that only loses 5 stars at the back and gains 5 stars at the
front does 10 allocations + 10 deletions, regardless of how big the
visible sector is.

`max_visible` enforces the same upper bound as the filter — it is
the navigator's `max_visible_objects` user-data field, so the user
edits it in the Attribute Manager. ``compute_diff`` never returns
more than that many uids in `added + kept`.

`UNAV_VisibleSector` is *the only place* `sync_visible_sector`
mutates. The navigator hierarchy (`UNAV_Navigator`/`UNAV_Camera`/
`UNAV_ViewRay`), the user's own scene content, and even the debug
cone (which lives on its own peer null) are untouched by the
add/remove passes.

---

## 5. Debug cone

`update_debug_cone(doc, show=True)` and the per-sync
`show_debug_cone` argument both end up in the same place: a
`c4d.Ocone` placed under `UNAV_Debug`, oriented by the navigator's
global matrix.

Geometry:

  * Apex at the navigator origin.
  * Axis along navigator local **−Z** (the schema-wide forward
    convention; see `NAVIGATION_NULL_SYSTEM.md` §2).
  * Height = ``far_clip_parsec * SCALE_MODES[c4d_scale]``.
  * Bottom radius = ``height * tan(cone_angle_deg)``, clamped to a
    safe range so a near-zero or near-180° cone does not produce a
    degenerate primitive.

Display:

  * `ID_BASEOBJECT_VISIBILITY_RENDER = MODE_OFF` so the cone never
    leaks into final output.
  * `ID_BASEOBJECT_VISIBILITY_EDITOR = MODE_ON` (default).
  * Distinctive orange `ID_BASEOBJECT_COLOR` so the cone is
    obviously "UNAV scaffolding".

Toggling **Show Debug Cone** in the dialog calls
`update_debug_cone(doc, show)` immediately and reports a status
line; toggling does **not** trigger a sync of the visible sector,
and a sync respects the current checkbox state without forcing
the user to re-toggle.

---

## 6. UI

The main dialog gains a "Visible Sector" group above the action
grid:

| Control               | Widget                | Behavior                                                          |
|-----------------------|-----------------------|-------------------------------------------------------------------|
| Sync Visible Sector   | `AddButton`           | Loads catalog, filters against navigator, calls `sync_visible_sector`. Reports the diff summary in the log. |
| Auto Sync             | `AddCheckbox`         | Placeholder — toggling appends "Auto Sync: not yet implemented; click Sync Visible Sector manually" to the log. |
| Show Debug Cone       | `AddCheckbox`         | Toggling immediately runs `update_debug_cone`. Sync passes also respect the checkbox state. |

`mock_actions.sync_visible_sector(encoding=None, show_debug_cone=False)`
is the wiring layer:

  1. Loads the catalog (sample by default).
  2. Filters against the active navigator via
     ``_filter_for_active_navigator``.
  3. Reads the navigator's ``c4d_scale`` and
     ``max_visible_objects`` so the sync uses the same scale mode
     and cap as the rest of the plugin.
  4. Calls ``scene_sync.sync_visible_sector(...)`` and returns the
     diff summary plus the filter rejection breakdown.

`mock_actions.toggle_debug_cone(show)` is the standalone toggle the
checkbox uses.

---

## 7. Auto Sync (placeholder)

True auto-sync is intentionally deferred: it requires a hook into
C4D's per-frame messaging (e.g. `MessageData` listening for
`MSG_DRAW`) plus a debouncer so dragging the navigator doesn't
flood the engine. The architecture for that is described in
`UNAV_PRO_ARCHITECTURE.md` §3.5 (streaming + debouncing).

The current checkbox is a UI placeholder. When the user toggles it
on, the dialog logs:

> Auto Sync: not yet implemented; click Sync Visible Sector
> manually.

The dialog state survives across sessions because checkbox state is
part of the `GeDialog`'s persisted layout — when Auto Sync ships,
the same checkbox can drive it without a UI redesign.

---

## 8. Robustness rules

The sync layer follows the standing plugin invariants
(`PLUGIN_STRUCTURE.md` §9):

  1. **No exception escapes the C4D boundary.** The dialog wraps
     every command in a try/except logging-handler, and each item
     in the add pass is wrapped so one bad row does not abort the
     remaining adds.
  2. **Idempotent.** Clicking Sync twice with no other changes is a
     no-op (zero adds, zero removes, full keep).
  3. **Respects user content.** Only objects directly under
     `UNAV_VisibleSector` are touched. Anything elsewhere in the
     scene survives.
  4. **Single undo step.** `doc.StartUndo()/EndUndo()` wraps the
     whole pass.
  5. **Hard cap honored.** `max_visible` truncates the wanted list
     before the diff is computed, so the materialized count never
     exceeds the navigator's `max_visible_objects` field.

---

## 9. Test coverage

`unav_pro/tests/test_scene_sync.py` covers (21 tests):

  * **Diff basics.** Overlap, disjoint, full overlap, empty current,
    empty wanted, both empty.
  * **Ordering and dedup.** Added preserves input order; duplicate
    wanted uids deduped; falsy uids skipped.
  * **Cap.** Truncates after dedup, cap of zero keeps nothing, cap
    above size is a no-op, capped uids drop kept entries that fall
    past the cut, negative cap treated as no cap (with documented
    behaviour).
  * **`SyncDiff` helpers.** `short_summary` includes / omits the
    capped count; `total_visible` excludes removed.
  * **C4D guard.** `sync_visible_sector` and `update_debug_cone`
    raise `RuntimeError` outside the host.

`mock_actions.sync_visible_sector` and `toggle_debug_cone` add two
"reports cleanly outside C4D" tests to the existing
`test_mock_actions.py`.

The c4d-bound paths (`_current_visible_objects`,
`_build_debug_cone`, the actual diff-and-update inside
`sync_visible_sector`) are exercised by loading the plugin in
Cinema 4D 2023+; they are not part of the automated suite.

---

## 10. Future extensions

Tracked as design intent, not promises:

  * **Auto Sync.** A `MessageData` hook on the navigator that
    re-runs sync on a debounce (50 ms default) when the user drags
    the navigator. Uses the engine-protocol queue described in
    `UNAV_PRO_ARCHITECTURE.md` §3.10 to avoid GIL contention.
  * **Reuse on uid match.** Today, when the same uid leaves and
    re-enters the visible set across two sync calls, we delete and
    rebuild. A future optimisation can keep a small uid-keyed pool
    of detached C4D objects so the rebuild becomes a re-parent.
    Worth measuring before implementing.
  * **Per-source debug.** A second debug helper that draws the
    cells the spatial index loaded (see
    `SPATIAL_INDEXING_AND_CHUNKING.md`) so artists can see what the
    navigator is actually fetching from disk. Reaches the same
    `UNAV_Debug` null with a different marker kind.
  * **Animated sync.** Per-frame sync sampled along a navigator
    animation track for previz of a fly-through. Same primitive,
    different driver.

The MVP shipped here is intentionally narrow: one diff, three
nulls, one debug cone, and no implicit triggers. Every future
feature in this list slots in behind the same `compute_diff` /
`sync_visible_sector` interface.
