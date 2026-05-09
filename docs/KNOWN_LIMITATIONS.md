# UNAV Pro — Known Limitations

Companion to [`LIMITATIONS.md`](LIMITATIONS.md). Where the
older doc summarises the full backlog ("things v1.x will
fix"), this doc enumerates the **acknowledged shortcomings
the v1.7 stabilization pass deliberately chose not to fix**,
each with its reasoning. The list is short on purpose: every
item here is "we know, and the cost outweighs the value
right now."

If you hit one of these and need it fixed, file an issue
referencing the section number; v1.x or v1.y can promote it
to the active backlog.

---

## 1. Untitled scene sidecar collisions

`core.project_state.sidecar_path_for(None)` uses the literal
filename `_untitled.json`. Two unsaved Cinema 4D documents
opened simultaneously will overwrite each other's UNAV
sidecar.

* **Why not fixed.** The artist's normal flow is to save the
  C4D scene before persisting UNAV state; the per-scene
  sidecar is keyed off the scene path. Untitled-scene
  persistence is a corner case.
* **Mitigation.** If you keep two unsaved scenes open, save
  one before clicking "Save UNAV State" in either.

---

## 2. `compute_diff` sorts the kept set

`core.scene_sync.compute_diff` sorts the `kept` UID list. If
the upstream filter returns objects in a meaningful order
(e.g. distance-sorted), the kept set loses that order during
re-sync.

* **Why not fixed.** The Python C4D backends iterate the OM
  in scene-tree order anyway; the sort doesn't observably
  reorder the viewport. The future C++ point renderer is
  the consumer that cares about insertion order, and the
  binary export keeps its own ordering.
* **Mitigation.** None needed today. Revisit when the
  native renderer ships with order-sensitive draw paths.

---

## 3. Dataset merge mutates input objects

`DatasetRegistry.merge_active` rewrites every
`CatalogObject.uid` in place during merge (prepending the
dataset's namespace). Callers that re-use the input list
afterwards will see the namespaced UIDs.

* **Why not fixed.** The registry is the only caller of the
  internal merge path; existing tests assert the in-place
  rewrite. Changing the contract risks subtle bugs in the
  visible-sector pipeline.
* **Mitigation.** Treat `merge_active`'s input as consumed.

---

## 4. Sample registry seeded only on first run

When `~/.unav_pro/datasets.json` is missing, the
`get_dataset_registry()` facade seeds with the bundled
sample. If the artist deletes every dataset and saves an
empty registry, the next launch keeps the empty registry —
they need to manually re-add the sample (or delete the file
to re-trigger seeding).

* **Why not fixed.** Once the artist has explicitly cleared
  the registry, silently re-seeding contradicts their
  choice.
* **Mitigation.** Dialog has an "Add Sample Catalog" button
  in the Dataset Manager.

---

## 5. Bookmark id collision is detected, not auto-resolved

`state_manager.validate_bookmarks` reports duplicate ids in
the diagnostics panel; nothing rewrites them. Duplicates
arise only when the user hand-edits `bookmarks.json`.

* **Why not fixed.** Auto-rewriting feels presumptuous;
  the artist may have done the duplication on purpose.
* **Mitigation.** Surface "duplicate bookmark id" as a red
  health line in the diagnostics panel.

---

## 6. Time Navigator state is process-wide

`time_navigator.default_state()` is a single
`TimeNavigatorState` shared by every C4D document open in
the host. Two documents can't carry independent epochs.

* **Why not fixed.** The dialog itself is a singleton at
  the host level; two-doc support would need a
  per-document state map keyed off the doc's
  `BaseDocument` identity. Out of scope for v1.7.
* **Mitigation.** Save UNAV State per scene (the project
  state sidecar already carries the epoch).

---

## 7. Metadata lookup is global, not per-dataset

`core.metadata_lookup.MetadataLookup` is a flat uid → object
table. When two datasets carry overlapping uids (rare, but
possible across surveys), the later-loaded one wins
silently.

* **Why not fixed.** The dataset registry already
  namespaces uids on merge (`<dataset>:<uid>`), so the
  collision only occurs if a caller bypasses the merge
  path.
* **Mitigation.** Always go through `merge_active`.

---

## 8. Native viewer reload is not transactional

`Reload Native Viewer` overwrites the on-disk binary file
and asks the C++ side to re-read. If the C++ side is mid-
read while the Python side overwrites, the binary's CRC
check on the C++ side fires and the re-read fails (the
artist sees a "binary file invalid" log and re-clicks). No
data loss.

* **Why not fixed.** A two-file (`.bin` + `.tmp` →
  rename) protocol is already in the v1.x roadmap.
* **Mitigation.** Don't click Reload twice in a row.

---

## 9. Visible-sector cap is a soft hint past the prefilter

`navigation_state.NavigationParams.max_visible_objects` is
honoured by the spatial query (LIMIT) and by the render
backend (cap on materialised C4D nodes). It is *not*
honoured per intermediate stage — e.g. the temporal
resolver applied during epoch-aware queries fans out per-
candidate state rows and could briefly exceed the cap in
working memory.

* **Why not fixed.** Working-memory excess is short-lived
  and bounded by `4 × cap` thanks to the v1.7
  bbox-cap derivation.
* **Mitigation.** Set `max_visible_objects` conservatively
  on million-row datasets.

---

## 10. Mission "Play" is dialog-driven

`voyage.playback.Playback.advance()` must be called by an
external loop (the dialog's idle handler in v1.4; a future
SceneHook in v1.x). v1.7 does not ship the SceneHook, so
"Play" advances one tick per dialog click rather than
running in real time.

* **Why not fixed.** The SceneHook lands with the v1.x
  Auto-Sync pipeline; building it as a separate v1.7
  task would duplicate effort.
* **Mitigation.** Use Step Forward / Next Waypoint for now.

---

## How to read this document

* If your concern is here → it's known, deferred for the
  reasons documented.
* If your concern is *not* here → file an issue.
* If you fix one of these → delete the section, update
  `V1_7_ARCHITECTURE_AUDIT.md`, and add a focused test.
