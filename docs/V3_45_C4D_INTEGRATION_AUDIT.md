# UNAV Pro — v3.45 Cinema 4D Integration Audit

The exhaustive list of every place UNAV touches Cinema
4D, what it does there, and what v3.45 changes about
it.

---

## 1. Plugin registration

* `unav_pro/unav_plugin.pyp` — `RegisterCommandPlugin`
  for the dialog launcher; `RegisterMessageData` hook
  for the v3.45 lifecycle planner.
* No new plugin types in v3.45 (no Tag, no Object, no
  Renderer plug-in).
* The dialog `id` is fixed in `core/plugin_ids.py`;
  v3.45 does not introduce new ids.

## 2. Dialogs / panels

* Single `c4d.gui.GeDialog` subclass in
  `ui/main_dialog.py`. Eight tab-style panels
  (Workflow / Display / Sync / Time Navigator /
  Actions / Status Log / Route Planner / Metadata
  Inspector / Search / Bookmarks / Navigation /
  Missions / Overlays / Project / Presentation).
* No floating sub-dialogs; every panel lives inside
  the single dialog.
* v3.45 leaves panel layouts untouched but tightens
  status-message wording (see
  [`docs/V3_45_NATIVE_C4D_WORKFLOW.md`](V3_45_NATIVE_C4D_WORKFLOW.md)
  §5).

## 3. BaseObject creation

Builders that create scene objects:

| Builder | Object kind | UNDO type recorded |
| --- | --- | --- |
| `point_cloud_builder.build_point_object` | `c4d.Onull` | `UNDOTYPE_NEWOBJ` |
| `point_cloud_builder.ensure_starfield_hierarchy` | `c4d.Onull` | `UNDOTYPE_NEWOBJ` |
| `instance_builder.build_instance_pool` | `c4d.Oinstance` | `UNDOTYPE_NEWOBJ` |
| `navigation_null.create_navigator` | `c4d.Onull` | `UNDOTYPE_NEWOBJ` |
| `path_preview.build_preview_spline` | `c4d.Ospline` | `UNDOTYPE_NEWOBJ` |
| `overlays_builder` (every overlay kind) | `c4d.Onull` + `c4d.Ospline` | `UNDOTYPE_NEWOBJ` |
| `scene_structure.ensure_project_structure` | `c4d.Onull` × 6 | `UNDOTYPE_NEWOBJ` + `UNDOTYPE_BITS` |
| `render_backend` (v0.7 dispatch) | varies per backend | `UNDOTYPE_NEWOBJ` |

v3.45 captures this table as
`unav_pro/c4d_objects/undo_policy.py::UNDO_POLICY` so
tests can assert no operation is missing from the
list.

## 4. Scene sync

* `core/scene_sync.compute_diff` — pure planner.
* `core/scene_sync.sync_visible_sector` — c4d-bound.
  Wraps every add / remove in
  `doc.AddUndo(...)` and runs everything inside one
  `StartUndo` / `EndUndo` window.
* v3.45 adds `SyncDiff.is_unchanged` short-circuit
  (already in v3.0); the v3.45 patch is just the
  consistent UNDOTYPE coverage.

## 5. Overlays + science layers

* `c4d_objects/overlays_builder.build_overlays` /
  `clear_overlays` — c4d-bound; both wrap their
  mutations in undo blocks.
* Science-layer materialisation rides on the same
  builder via `to_overlay_bundle`.
* v3.45's `viewport_visibility` planner provides the
  per-profile visibility decisions for these.

## 6. Timeline baking

* `c4d_objects/timeline_keys` — writes
  `c4d.CTrack` instances on the camera + navigator
  nulls. v3.45 standardises track names via
  `naming.baked_track_name`.
* `c4d_objects/timeline_markers` — writes
  `c4d.gui.TimelineMarker` records prefixed with
  `UNAV:` (v2.2). v3.45's `naming.marker_token`
  centralises the prefix.

## 7. Navigator objects

* `c4d_objects/navigation_null.create_navigator` —
  creates the navigator null + assigns user data.
* `c4d_objects/navigation_null.find_navigator` —
  scene walk that finds the active navigator.
* v3.45 doesn't change the navigator's user-data
  layout; it does add the navigator's name to the
  `naming.SCENE_OBJECT_PREFIX` family
  (`UNAV_Navigator`).

## 8. Mission helpers

* `c4d_objects/path_preview.build_preview_spline` —
  builds the `UNAV_Mission_<id>_Preview` spline.
  v3.45 standardises the name via
  `naming.mission_preview_name`.
* `voyage/playback.Playback` — pure-Python; never
  touches Cinema 4D directly.

## 9. Selection handling

* `core/mock_actions.do_inspect_selected_object` —
  reads `doc.GetActiveObject()`, looks up the UNAV
  marker container, resolves the uid via
  `MetadataLookup`.
* The dialog's *Set Selection* path uses
  `BaseDocument.SetActiveObject` with `BIT_ACTIVE`.
* v3.45 doesn't change the selection logic — it
  documents it (see
  [`docs/V3_45_NATIVE_C4D_WORKFLOW.md`](V3_45_NATIVE_C4D_WORKFLOW.md)
  §3).

## 10. Diagnostics

* `core/health_check` — 14 probes (v3.4).
* `core/diagnostics.build_diagnostics_report` —
  pure renderer (v3.0).
* `core/state_manager.dataset_summary` /
  `visible_sector_summary` — short text helpers.
* v3.45 adds `core/diagnostics.build_document_summary`
  + `c4d_objects/object_manager_view` for the OM-
  level introspection.

## 11. New v3.45 modules

* `unav_pro/c4d_objects/undo_policy.py` — declarative
  UNDOTYPE policy + `UndoSession` context manager.
* `unav_pro/c4d_objects/naming.py` — central
  deterministic naming helpers.
* `unav_pro/c4d_objects/lifecycle.py` — pure
  scene-lifecycle planner.
* `unav_pro/c4d_objects/object_manager_view.py` —
  pure scene-hierarchy summariser + duplicate /
  orphan detectors.
* `unav_pro/c4d_objects/viewport_visibility.py` —
  per-profile visibility planner + label-clutter
  policy.

## 12. Out of scope (still)

* No new plugin types (no Tag, no Renderer, no
  Material).
* No render-engine bridges.
* No per-frame visible-sector regeneration.
* No selection-driven viewport overlays (Cinema
  4D's native viewport can't render UNAV-side gizmos
  without a custom DrawHelper, which v3.45 doesn't
  introduce).
* No `c4d.threading` use. UNAV stays main-thread.

## 13. Acceptance

* [x] Every UNDO-needing operation is in
  `UNDO_POLICY`; tests catch missing entries.
* [x] Every UNAV-owned scene object name follows
  `naming.*`; tests assert determinism.
* [x] Lifecycle events have explicit action plans;
  tests cover open / close / switch / reload /
  saved.
* [x] OM hierarchy is summarisable + dedupable;
  tests cover counts + duplicate / orphan detection.
* [x] Visibility profiles are documented; tests
  cover the per-profile decisions.
* [x] No rendering. No IPC. No threading.
