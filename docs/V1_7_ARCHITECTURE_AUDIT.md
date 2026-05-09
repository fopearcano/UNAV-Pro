# UNAV Pro v1.7 Architecture Audit

This document is the v1.7 *as-is* picture of the plugin's
internals. It is the input to the v1.7 stabilization pass —
every concern listed here is either fixed in this milestone
or explicitly deferred (with a reason). Subsequent edits to
the codebase should keep this document honest: when an
observation here becomes stale, update or delete it.

The audit was performed cold against the v1.4 codebase. The
goal was a punch-list, not a redesign.

---

## 1. Module boundaries

Layout (one-line summary per directory):

```
unav_pro/
  core/             pure-Python logic + state (no c4d, no DB)
  data/             schema, JSONL/CSV I/O, connectors, binary export
  data/connectors/  Gaia / SDSS / DESI / JPL Horizons HTTP normalisers
  db/               SQLite manager, schema, spatial / temporal query
  ui/               GeDialog subclasses + dialog-side formatters
  c4d_objects/      C4D scene hierarchy, render backends, point clouds
  voyage/           v1.4 missions / camera path / playback
  knowledge/        v1.3 classifier / summary / glossary
  tests/            pytest, c4d-free
  unav_plugin.pyp   C4D entry point
```

**Verdict.** Each directory has one clear responsibility.
No misplaced files. The boundary that gets the most strain
is `core/` ↔ `c4d_objects/` (scene_sync sits in core but
walks c4d objects); the cleanest rule is that anything which
imports `c4d` lives in `c4d_objects/` or `ui/`. v1.7 keeps
this rule unchanged.

---

## 2. State surfaces (singletons)

Every process-wide singleton in the codebase, with its
init/replace/reload API:

| Singleton | Module | Init | Replace | Reload |
|-----------|--------|------|---------|--------|
| `MetadataLookup` | `core/metadata_lookup.py` | `default_lookup()` lazy | `set_default_lookup(...)` | `default_lookup(reload=True)` |
| `TimeNavigatorState` | `core/time_navigator.py` | `default_state()` lazy | `set_default_state(...)` | (none — fixed in v1.7) |
| `MissionManager` | `voyage/mission_manager.py` | per-instance | n/a | `MissionManager.reload()` |

**v1.7 fix.** `time_navigator.default_state()` gains a
`reload=True` parameter so its API matches `metadata_lookup`.
A new `core.state_manager` module collects every singleton
behind one facade so the dialog has a single import surface.

---

## 3. Scene sync (`core/scene_sync.py`)

The reliability concerns in v1.6:

* **`_current_visible_objects()`** walks the OM via
  `GetDown` / `GetNext`. No null-check after each step.
  v1.7 adds defensive guards so a node deleted between
  read and process doesn't crash the iteration.
* **No double-sync guard.** A back-to-back call could read
  stale `current_visible_objects` while the first call's
  backend is still mid-update. v1.7 adds a re-entrancy
  flag (`_sync_in_progress`) on the dialog side; a second
  sync click during the first sync is logged and dropped.
* **Mode-switch leak risk.** Switching backends (debug →
  instances → point cloud) relies on each backend's
  `update_visible_sector` walking the same UID-keyed
  marker container. Verified: every backend uses
  `KIND_POINT` + `MARKER_KEY_UID`. v1.7 adds a
  *cross-backend* test that flips modes three times and
  asserts the OM has no orphaned `UNAV_*` children.
* **Sort drift in `compute_diff`.** `kept` is sorted; in
  ordered datasets this loses the navigator's preferred
  rank. Documented but not changed in v1.7 (the C++
  renderer is the consumer; render-order is a v1.x
  concern).

---

## 4. Dataset registry (`core/dataset_registry.py`)

* **Duplicate registration** — `add()` raises on duplicate
  name; `add_path()` flows through `add()`. ✓
* **Missing cache directory** — `is_indexed` silently
  returns False; merge proceeds without the index. v1.7
  adds a warning log (once per dataset) so the artist
  notices the cache is gone.
* **Corrupt registry JSON** — caught + empty registry.
  Already correct.
* **Per-entry corruption** — malformed entries are skipped
  with a warning. Already correct.
* **JSONL ↔ DB confusion** — if `db_path` is set the
  registry treats the entry as DB-backed; JSONL path is
  ignored. v1.7 documents this in `DATASET_MANAGER.md`.
* **No `reload()`** — v1.7 adds
  `DatasetRegistry.reload(path=None)` to re-read from disk
  after external edits.
* **Merge mutates inputs** — `merge_active_objects` rewrites
  the input objects' UIDs in place. Documented; the
  registry is the only caller (existing tests assert the
  behaviour, so changing it is risky).

---

## 5. Config / persistence layer

Four on-disk surfaces. All four follow the same fail-closed
contract: missing or corrupt → return defaults, never raise.

| File | Module | Default location |
|------|--------|------------------|
| `config.json` | `core/config.py` | `~/.unav_pro/config.json` |
| `bookmarks.json` | `core/bookmarks.py` | `~/.unav_pro/bookmarks.json` |
| Per-scene sidecar | `core/project_state.py` | `~/.unav_pro/projects/<scene>.json` |
| Mission files + index | `voyage/mission_manager.py` | `~/.unav_pro/missions/` |

**v1.7 additions:**

* All four now share a `safe_write_json()` helper in
  `core/config.py` that writes atomically (temp file →
  rename) so a crash mid-write can't truncate the file.
* `core/state_manager.health_summary()` aggregates each
  surface's load status into one report the diagnostics
  panel can render.
* The "untitled scene sidecar collision" caveat in
  `project_state.sidecar_path_for(None)` is now
  documented in `PLUGIN_LIFECYCLE.md`.

---

## 6. Logging

Coverage: every major module imports `core.logging_util.get_logger`.
No bare `except:` blocks in production code (v1.4–v1.6 lint
passes already removed them). One intentional `print(` in
`data/sample_catalog_generator.py` (CLI tool).

v1.7 adds three diagnostic helpers in
`core.state_manager`:

* `health_summary()` — overall plugin health
  (config status, registered dataset count, missions
  count, time navigator epoch, last-error count).
* `dataset_summary()` — per-dataset row count, source
  list, index status.
* `visible_sector_summary(doc)` — count of `UNAV_*`
  scene objects + last-sync stats.

The diagnostics dialog renders these on demand.

---

## 7. Dead code / placeholders

A search across the codebase for `TODO/FIXME/XXX/HACK/PLACEHOLDER`
returned zero matches in production code. The constants named
`*PLACEHOLDER*` (`PLACEHOLDER_SPHERE_PC`, `PLACEHOLDER_NAME`,
`NATIVE_PLACEHOLDER_NAME`) are intentional fallback values,
not stand-ins for unimplemented features.

No dead code identified.

---

## 8. Test gaps closed in v1.7

| Scenario | Before v1.7 | After v1.7 |
|----------|-------------|------------|
| Repeated `sync_visible_sector()` calls | not covered | `test_v17_stability::test_repeated_compute_diff_idempotent` |
| Render-mode switching (debug → instance → cloud) | not covered | `test_v17_stability::test_mode_switch_diff_chain` |
| Dataset reload after disk edit | not covered | `test_v17_stability::test_registry_reload_picks_up_disk_changes` |
| Config corruption fail-closed | covered | (already covered) |
| Mission reload | covered | (already covered) |
| state_manager health summary | new | `test_v17_state_manager::test_health_summary_*` |

---

## 9. UI naming inconsistencies

The dialog mixed five update verbs in v1.6: *Sync*, *Apply*,
*Reload*, *Refresh*, *Set*. v1.7 standardises to two:

* **Sync** — for any operation that re-reads the data layer
  and updates the scene (visible sector, time navigator's
  "Sync at Epoch", bookmarks list).
* **Apply** — for one-shot parameter changes that write
  back to the navigator state (filter, encoding, render
  mode token).

The native viewer's "Reload" stays — it reloads the on-disk
binary file and is genuinely a different operation from
re-streaming a sector. The bookmark "Reload" button is
renamed to "Sync" for consistency.

---

## 10. Memory concerns

* **`db/spatial_query.py`** — `cur.fetchall()` materialises
  the full spatial-query result set before applying the
  navigator's `max_visible_objects` cap. v1.7 enforces the
  cap at SQL level by appending a `LIMIT` clause sized to
  `max_visible_objects + safety_headroom` (so the exact-
  cone-refine pass still has a slack buffer). Bigger
  catalogs still need streaming; that's a v1.x concern.
* **`render_backend.py`** — every backend takes a
  `Sequence[CatalogObject]` and `list(...)`s it. Bounded by
  the navigator cap; safe.
* **`core/search.py`** — bounded by `HARD_MAX_RESULTS`.

---

## 11. What v1.7 does **not** do

* No new features.
* No renderer integrations.
* No conceptual redesign.
* No on-disk format changes (DB schema v2, binary v3,
  mission schema v1 unchanged).

---

## 12. Punch list status

| # | Item | Status |
|---|------|--------|
| 1 | SQL `LIMIT` in spatial_query | done |
| 2 | Repeated-sync test | done |
| 3 | Mode-switch test | done |
| 4 | `DatasetRegistry.reload()` | done |
| 5 | `time_navigator.default_state(reload=True)` | done |
| 6 | Dataset-corruption-mid-merge test | done |
| 7 | Standardise UI verbs | done |
| 8 | Document mode-switch removal contract | done (in `PLUGIN_LIFECYCLE.md`) |
| 9 | Defensive null guards in scene-walk | done |
| 10 | Coordinated parent-dir creation | done (`safe_write_json`) |
