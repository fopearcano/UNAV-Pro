# UNAV Pro — Plugin Lifecycle

The end-to-end picture of how UNAV runs inside Cinema 4D:
which singletons exist, when they get loaded, when they get
saved, and what happens when you reopen the dialog or close
the host. Read this if you're wondering "why did my state
disappear?" or "is it safe to click Sync twice?"

For the audit-level view of the same surfaces see
[`V1_7_ARCHITECTURE_AUDIT.md`](V1_7_ARCHITECTURE_AUDIT.md);
for the explicit non-goals see
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

---

## 1. The startup path

When the artist clicks **Extensions → Universal Navigator
Pro** for the first time in a host session:

1. The dialog's `CreateLayout` fires (laid out by
   `ui/main_dialog.py`).
2. `InitValues` runs once. It:
   * loads `~/.unav_pro/config.json` (or default if missing),
   * loads `~/.unav_pro/bookmarks.json` (or empty),
   * lazily resolves the metadata lookup the first time a
     panel asks for it,
   * lazily creates the `TimeNavigatorState` singleton at
     J2016.0 the first time the Time Navigator panel reads
     the epoch,
   * calls `state_manager.health_summary()` and writes the
     one-liner to the dialog log.
3. The dialog stays open. Every subsequent click runs
   through `Command(mid, msg)`; nothing in `CreateLayout`
   or `InitValues` re-fires.

Closing the dialog window does *not* destroy the
singletons — they live in the host's Python interpreter
until C4D itself shuts down or the plugin is reloaded.
Re-opening the dialog re-uses the same `MetadataLookup`,
the same `TimeNavigatorState`, the same `MissionManager`.

This is intentional: it keeps the artist's epoch / loaded
catalogs / playback cursor stable across "I closed the
dialog by accident" / "I want to dock the panel."

---

## 2. The persistence surfaces

Five on-disk surfaces, each independently fail-closed.

| File | Module | Written when | Loaded when |
|------|--------|--------------|-------------|
| `~/.unav_pro/config.json` | `core/config.py` | "Save Config" / "Reset Config" / explicit dialog actions | `InitValues` |
| `~/.unav_pro/bookmarks.json` | `core/bookmarks.py` | every Add / Remove / Move | `InitValues` |
| `~/.unav_pro/datasets.json` | `core/dataset_registry.py` | Dataset Manager save | `InitValues` (lazy) |
| `~/.unav_pro/projects/<scene>.json` | `core/project_state.py` | "Save UNAV State" | "Load UNAV State" |
| `~/.unav_pro/missions/*.json` | `voyage/mission_manager.py` | every mission CRUD | first Mission tab open |

All five are written via `core.config.safe_write_json` (v1.7+),
which writes to a `.tmp` sibling and atomically renames into
place. A crash during a write leaves the previous valid file
intact.

All five fail-closed on read: missing or corrupt → return
defaults / empty list, never raise. Corrupt files are
logged at warning level so the artist can grep for them
in the diagnostics panel.

---

## 3. The visible-sector lifecycle

Click "Sync Visible Sector". The pipeline:

1. **Read** the navigator pose + current `NavigationParams`.
2. **Stream** candidates via `core/sector_streaming` — one
   call per active dataset, threaded through
   `db.spatial_query.query_cone` (DB-backed) or the JSONL
   chunked index reader.
3. **Diff** the candidate UIDs against the currently-
   materialised UIDs (`compute_diff`).
4. **Update** the C4D scene via the active render backend
   (`debug_objects` / `instances` / `point_cloud` /
   `native_point_viewer`). Each backend removes the diff's
   `removed_uids` and adds `added_uids`.
5. **Commit** the C4D undo block; fire `EventAdd`.

What v1.7 made safer:

* The OM-walking helper (`_current_visible_objects`) is
  defensive: half-deleted children are logged and
  skipped rather than crashing the iteration.
* The DB cone query auto-derives a SQL `LIMIT` from
  `max_visible_objects`, so working memory stays bounded
  on million-row catalogs.

What v1.7 still does *not* prevent:

* Two clicks in rapid succession on Sync. The second click
  reads the OM state mid-update of the first. Today this
  is harmless because backend writes are idempotent
  (re-adding an existing UID is a no-op), but it's not
  guaranteed; the dialog should add a re-entrancy guard
  in v1.x.

---

## 4. The render-mode switch

The Render Mode dropdown picks one of:
`debug_objects` / `instances` / `point_cloud` /
`native_point_viewer`. Switching modes:

1. The new backend is instantiated.
2. The next "Sync Visible Sector" click runs the diff
   against the OM. The diff treats the entire current
   visible-sector contents as `removed_uids` plus the new
   candidates as `added_uids` — i.e. it correctly cleans
   up whatever the previous backend produced.
3. v1.7 adds an integration test
   (`test_v17_stability::test_mode_switch_diff_chain`)
   that flips through three modes and asserts no orphan
   UIDs remain.

The contract every backend must honour: every
materialised C4D node carries the UNAV marker
(`KIND_POINT` + `MARKER_KEY_UID`), so the next backend's
remove pass picks it up regardless of who created it.

---

## 5. The time-navigator lifecycle

`TimeNavigatorState` is a process-wide singleton at
`core.time_navigator._default_state`. It carries:

* `current_epoch_jd` (JD float),
* `step_days` (artist's preferred increment),
* `is_playing` (placeholder until SceneHook lands),
* `last_label` (for the dialog's status line).

Per-scene persistence: the scene's `project_state` sidecar
carries `current_epoch_jd` so reopening the `.c4d` restores
the artist's preferred epoch via the dialog's "Load UNAV
State" path. The singleton is *not* automatically synced —
the artist clicks "Load UNAV State" explicitly. (There is
no automatic per-document state in v1.7 — see
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) §6.)

`default_state(reload=True)` resets the singleton to the
default epoch (J2016.0). Used by the diagnostics panel's
"Reload State" button and by tests.

---

## 6. The dialog ↔ host boundary

The dialog never:

* runs Cinema 4D scripts,
* spawns threads,
* uses `time.sleep` or `asyncio`,
* schedules its own timers.

Everything is event-driven via `Command(mid, msg)`. A
future v1.x will add a `SceneHook` that fires once per
viewport redraw; that hook will drive
`Playback.advance()` and the visible-sector Auto-Sync.
v1.7 leaves the SceneHook unimplemented; mission playback
advances one tick per artist click.

Closing the C4D host runs each singleton's normal
finalisation: in-flight DB connections close in their
`__del__` / context-manager paths; the registry / config /
bookmarks are persisted only on explicit clicks (so a
crash before save loses unsaved changes — same as v1.6).

---

## 7. Reset / reload

Two distinct semantics, both exposed by the diagnostics
panel:

* **Reload State** — calls
  `core.state_manager.reload_all()`. Drops every singleton;
  the next access re-loads from disk. Useful when the
  artist has hand-edited a config file.
* **Reset Config** — calls `core.config.reset_config()`.
  Replaces `~/.unav_pro/config.json` with a fresh default
  and re-installs it as the active config.

Neither resets the C4D scene contents. Rebuilding the
visible sector is a separate "Sync Visible Sector" click.

---

## 8. Health checks

The diagnostics panel runs
`core.state_manager.health_summary()` on demand. Each
subsystem reports `(name, ok, detail)`:

```
=== UNAV State Health ===
UNAV health: OK (6 subsystems)

  [OK] config             v1 at /home/.../.unav_pro/config.json
  [OK] bookmarks          5 bookmark(s) at /home/.../.unav_pro/bookmarks.json
  [OK] datasets           3 entries (2 enabled)
  [OK] time_navigator     epoch JD 2457389.000, step 1d
  [OK] metadata_lookup    1234 object(s) cached
  [OK] missions           2 mission(s)
```

When one subsystem is broken, the line flips to `[!!]` and
the summary line lists the failing names so the artist can
file an issue with concrete information.
