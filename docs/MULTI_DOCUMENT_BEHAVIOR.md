# UNAV Pro — Multi-Document Behaviour

How v3.45 handles Cinema 4D's multi-document model:
the user has more than one document open at once,
flips between them, opens a new one, closes one,
saves one, reloads the plug-in, etc.

For the underlying audit see
[`V3_45_C4D_INTEGRATION_AUDIT.md`](V3_45_C4D_INTEGRATION_AUDIT.md).

---

## 1. The model

Cinema 4D maintains a list of open
`BaseDocument` instances; one is "active" at any
moment (the document the user is editing). The
plug-in's job is to:

* Always operate on the **active** document.
* Track per-document UNAV state without leaking
  one document's edits into another's.
* React cleanly when the active document switches,
  closes, or opens.

v3.45 captures the policy as a **pure planner** in
`unav_pro/c4d_objects/lifecycle.py`. The c4d-bound
hook in `unav_plugin.pyp` calls the planner on
each lifecycle event and runs the returned action
plan.

## 2. Lifecycle events

Five events, each producing a `LifecycleActionPlan`:

| Event | Action plan |
| --- | --- |
| `OPENED` | rebind state-manager, reload workspace if any, rediscover scene objects, reset caches |
| `CLOSED` | flush workspace if any, rebind state-manager, reset caches |
| `SWITCHED` | rebind state-manager, rediscover scene objects (when multi-doc), reset caches |
| `RELOADED` | rebind, reload workspace, rediscover, reset caches |
| `SAVED` | refresh workspace mtime |

Each plan exposes booleans (`rebind_state_manager`,
`reload_workspace`, `flush_workspace`,
`rediscover_scene_objects`, `reset_caches`) the
dispatcher reads and applies.

## 3. Per-document state isolation

The plug-in tracks two pieces of per-document state:

* The active **workspace** pointer
  (`core/state_manager.current_workspace`).
* The active **mission** pointer
  (`core/state_manager.current_mission`).

These are process-wide singletons. When the active
document switches, the dispatcher:

1. Reads the new active document's UNAV sidecar
   (if any).
2. Replaces the workspace + mission pointers via
   `set_current_workspace` /
   `set_current_mission`.
3. Resets the v3.0 chunk-reuse cache (the cached
   query results were keyed against the old
   document's dataset).
4. Calls `c4d.EventAdd()` so the dialog re-renders
   with the new document's state.

## 4. Document scope tracking

`MultiDocumentReport` (in `lifecycle.py`) gives
the diagnostics panel a snapshot of every document
the plug-in knows about:

```python
DocumentScope(doc_id="ws/voyager", title="Voyager",
              is_active=True, has_unav_state=True)
DocumentScope(doc_id="ws/saturn", title="Saturn Cinematic",
              is_active=False, has_unav_state=True)
```

`build_multi_document_report(...)` validates the
list (rejects duplicate doc_ids; marks the active
document) and renders one line per document.

## 5. Plugin reload

During development the artist may use the
*Extensions → Reload Python Plugins* command. The
v3.45 `RELOADED` plan handles this:

* Rebinds the state-manager from scratch.
* Reloads the workspace (if any).
* Rediscovers scene objects (the in-memory
  scene_structure helpers don't carry pointers
  across reloads).
* Resets every cache.

The artist's on-disk artefacts (workspace,
catalogs, missions) are sacred — never touched by
a reload.

## 6. Save behaviour

When the document saves, the plug-in:

* Bumps the workspace's `updated_at_iso` if a
  workspace is bound (so an external editor
  noticing the file change knows the plugin
  authored the write).
* Does **not** auto-save the dataset registry,
  mission catalog, or any cache. Those have their
  own atomic save paths.

## 7. Multi-document with active workspace

When two documents are open and one of them owns a
workspace:

* Switching to the workspace document binds the
  state-manager to that workspace.
* Switching away unbinds (resets the pointer to
  None). The OS-level file tree continues to live;
  only the in-memory pointer is dropped.
* Switching back rebinds via reload.

This means edits in document A's workspace can't
leak into document B's because the state-manager
pointer follows the active document.

## 8. Acceptance

* [x] Five lifecycle events have explicit plans.
* [x] State-manager pointers follow the active
  document.
* [x] Caches reset on document switch.
* [x] Plugin reload restores state cleanly.
* [x] No leaked references after close.
* [x] No on-disk artefact mutation outside the
  artist's explicit actions.

## 9. Tests

* `test_v345_lifecycle` covers `plan_for_event`
  for every event + every workspace state
  combination, plus `MultiDocumentReport`
  validation.
