# UNAV Pro — Persistence and Config

How UNAV Pro remembers things across plugin reloads, scene reopens,
and machine restarts. Two cleanly-separated layers:

  * **`UnavConfig`** — long-lived per-user preferences (cache root,
    default scale mode, log verbosity, last-used paths).
  * **`ProjectState`** — per-scene snapshot of everything the artist
    touched (active datasets, navigator parameters, route waypoints,
    visual encoding choices, optional config snapshot).

Companion to:

  * `DATASET_MANAGER.md` (the registry whose enabled flags
    project state restores).
  * `NAVIGATION_NULL_SYSTEM.md` (the navigator user data project
    state captures).
  * `ROUTE_PLANNER.md` (the live route project state round-trips).
  * `VISUAL_ENCODING.md` (the encoding params project state
    persists).

---

## 1. The two layers

| Layer            | Lifetime      | Storage                                                             |
|------------------|---------------|---------------------------------------------------------------------|
| `UnavConfig`     | per-user      | `~/.unav_pro/config.json`                                           |
| `ProjectState`   | per-scene     | (1) `BaseDocument` BaseContainer (saved with the .c4d) + (2) sidecar JSON at `~/.unav_pro/projects/<scene-stem>.json` |

The split is deliberate. Preferences (cache root, log level) follow
the *user*: open three different scenes, all should respect the
same cache. Project state follows the *scene*: every saved-out
.c4d should remember the navigator pose, the route, and the active
datasets it was assembled with.

---

## 2. `UnavConfig`

Implementation: `unav_pro/core/config.py`.

```python
@dataclass
class UnavConfig:
    schema_version: int       = 1
    cache_root: str           = "~/.unav_pro/cache"
    default_scale_mode: str   = "pc"
    log_level: str            = "INFO"
    auto_load_state: bool     = False
    last_state_path: str?     = None
    last_catalog_path: str?   = None
```

Validation rules:

  * Unknown `default_scale_mode` (anything outside `SCALE_MODES`) is
    silently reverted to `pc` on load with a warning.
  * Unknown `log_level` falls back to `INFO`.
  * Unknown JSON keys are dropped (forward-compat: a future config
    can be opened in this version without errors).

### API

```python
load_config(path=None) -> UnavConfig    # missing/corrupt -> defaults; never raises
save_config(cfg, path=None) -> str?     # returns the path on success, None on failure
reset_config(path=None, delete_file=False) -> UnavConfig
default_config_path() -> str            # ~/.unav_pro/config.json
```

`load_config` is the public entry point and **never raises**:

  * Missing file → defaults.
  * Corrupt JSON → defaults (warning logged).
  * Hand-edited invalid enums → snapped back to defaults
    (warning logged).

`save_config` makes parent directories on demand and silently
returns `None` if the filesystem refuses (read-only mounts,
sandboxed hosts). Preferences are not worth crashing the dialog
over.

---

## 3. `ProjectState`

Implementation: `unav_pro/core/project_state.py`.

```python
@dataclass
class ProjectState:
    schema_version: int          = 1
    saved_at_iso: str?           = None
    enabled_datasets: List[str]  = []          # registry entry names
    navigator: dict              = {}          # NavigationParams.to_dict()
    route: dict                  = {}          # Route.to_dict()
    visual_encoding: dict        = {}          # asdict(VisualEncodingParams)
    config: dict?                = None        # UnavConfig.to_dict() snapshot
    notes: str                   = ""
```

Each sub-payload is kept as a plain dict so this dataclass does not
couple to the live shapes of the four feature modules. The
`gather_project_state` and `apply_project_state` functions are the
*only* places conversion happens.

### gather → live → apply round trip

`gather_project_state(...)` snapshots the in-memory pieces:

```python
state = gather_project_state(
    registry=DatasetRegistry.load(...),
    navigator=NavigationParams(...),    # read from the active navigator
    route=Route(...),                    # read from the dialog's live route
    encoding=VisualEncodingParams(...),  # read from the dialog's widgets
    config=UnavConfig(...),              # current per-user prefs
)
```

`apply_project_state(state, registry=...)` re-hydrates them:

```python
out = apply_project_state(state, registry=reg)
out["navigator"]  # NavigationParams (clamped)
out["route"]      # Route
out["encoding"]   # VisualEncodingParams (defaults if invalid)
out["config"]     # UnavConfig?  (None when state has no config blob)
out["report"]     # ApplyReport (datasets enabled/disabled/missing, etc.)
```

`apply_project_state` is conservative:

  * Empty / missing payloads → defaults (dialog continues with a
    fresh navigator / route / encoding).
  * Invalid `visual_encoding` (e.g. unknown `color_mode`) → defaults
    + warning + `report.encoding_restored = False`.
  * Out-of-range `navigator` values are run through
    `NavigationParams.clamped()` rather than rejected.
  * If a `registry` is provided, enabled flags are aligned with
    `state.enabled_datasets`. Entries listed in the state but not
    in the registry land in `report.datasets_missing` so the dialog
    can surface them.

`ApplyReport.short_summary()` produces a one-line dialog status:

> `navigator ✓, route ✓, encoding ✓, 2 dataset(s) enabled, 1 dataset(s) missing`

---

## 4. Disk paths

```python
project_state_dir() -> "~/.unav_pro/projects"
sidecar_path_for(scene_path) -> "~/.unav_pro/projects/<stem>.json"
sidecar_path_for(None)        -> "~/.unav_pro/projects/_untitled.json"
```

The `_untitled.json` fallback gives the artist a stable place to
save and reload while a brand-new C4D scene has no document path
yet. When the scene is later named, the next save lands on the
proper stem.

---

## 5. C4D scene-level metadata

The headline feature: project state travels with the .c4d file.
`mock_actions.save_unav_state` writes the JSON-encoded `ProjectState`
into the document's BaseContainer at a private slot
(`_BC_ID_UNAV_STATE = 1000021`). Cinema 4D persists that slot when
the user saves the scene, so reopening the .c4d on another machine
restores the navigator pose, the route, and the active dataset list
even without the sidecar JSON.

`mock_actions.load_unav_state` checks both sources, in order:

  1. The active document's BaseContainer slot.
  2. The sidecar JSON at `~/.unav_pro/projects/<stem>.json`.

If both miss, the action reports `no UNAV state found in scene or
sidecar.` rather than failing.

The sidecar exists as a fallback for two reasons:

  * Scenes that were never saved (sometimes artists save *state*
    before saving the scene file).
  * Cross-machine workflows where the .c4d's BaseContainer entry
    might be stripped by intermediate tools.

---

## 6. UI

The main dialog grows three buttons:

| Button                | Action                                                                                    |
|-----------------------|-------------------------------------------------------------------------------------------|
| **Save UNAV State**   | Reads navigator params (if a navigator exists), the dialog's live `Route`, the encoding picked from the Display group, and the active `DatasetRegistry` from disk. Calls `gather_project_state(...)`, then writes both the scene container slot and the sidecar JSON. Reports both write paths. |
| **Load UNAV State**   | Reads the scene container or sidecar (whichever exists), calls `apply_project_state(state, registry=...)`, and saves the registry back so enabled-flag changes persist. Reports the apply summary. |
| **Reset Preferences** | Calls `reset_config(default_config_path(), delete_file=False)` — wipes preferences back to defaults but **does not** touch project state files or the dataset registry. Reports the file path that was reset. |

Every handler returns a status string and never raises into the
dialog event loop. Save and load each go through `_safe`, so
failures appear as `Save UNAV State FAILED: …` rather than as a
silent bug.

---

## 7. Robustness rules

The persistence layer follows the standing plugin invariants
(`PLUGIN_STRUCTURE.md` §9):

  1. **Every `load_*` falls back to defaults.** Missing, corrupt,
     and forward-incompatible files all yield a default object;
     callers never see exceptions for "no file yet."
  2. **Every `save_*` is best-effort.** Filesystem failures log a
     warning and return `None`/quietly succeed; never raise.
  3. **Hand-edited invalid values are snapped to safe defaults.**
     `default_scale_mode = "warp"` is reverted to `"pc"` on load,
     not on save, so the user-edited file is preserved verbatim
     until the next save.
  4. **Unknown JSON keys are dropped.** A future config / state
     written by a newer plugin opens cleanly in an older plugin
     (with the unknown fields ignored).
  5. **Validation lives in dataclasses.** The persistence module
     never re-implements range checks: `NavigationParams.clamped()`
     repairs invalid navigator values, `VisualEncodingParams`
     rejects unknown modes at construction.
  6. **Two storage paths, one source of truth.** Save writes both
     the scene container *and* the sidecar; load tries scene first,
     sidecar second. Either suffices to round-trip the state.

---

## 8. Test coverage

Two new test files cover the persistence layer end-to-end (43
tests):

`unav_pro/tests/test_config.py` (16 tests):

  * **Defaults.** `UnavConfig()` has the documented values; the
    schema version constant is exposed.
  * **Round-trip.** Save → load preserves every field; parent dirs
    auto-created.
  * **Filesystem failure.** `save_config` on an unwritable parent
    returns `None` rather than raising.
  * **Missing / corrupt.** `load_config` of a missing file returns
    defaults; corrupt JSON returns defaults; unknown keys are
    dropped.
  * **Validation snap-back.** Hand-edited bad
    `default_scale_mode` / `log_level` are restored to defaults on
    next load.
  * **Reset.** `reset_config` rewrites with defaults; `delete_file`
    removes the file; deleting an absent file is a no-op.
  * **JSON helpers.** `to_json` / `from_json` round-trip; garbage
    and empty strings degrade to defaults.

`unav_pro/tests/test_project_state.py` (27 tests):

  * **Dataclass shape.** Default state is empty; round-trip via
    dict and JSON; unknown keys filtered; falsy dataset names
    dropped.
  * **`gather_project_state`.** Collects every piece when full
    inputs given; missing inputs yield empty sub-dicts; saved
    timestamp populated.
  * **`apply_project_state`.** Restores navigator / route /
    encoding correctly; defaults for empty state; report flags
    accurate; registry alignment toggles enabled flags and surfaces
    missing dataset names; bad navigator values are clamped; bad
    encoding falls back to defaults; saved config is returned when
    present.
  * **gather → apply round-trip.** Live state survives a full
    snapshot+restore.
  * **Disk I/O.** `save_project_state` round-trips to JSON;
    creates parent dirs; missing/corrupt loads return defaults;
    unwritable paths fail quietly.
  * **Sidecar paths.** `project_state_dir` is per-user; sidecar
    uses scene stem; handles no-extension scenes; falls back to
    `_untitled.json` for anonymous scenes.
  * **`ApplyReport`.** Summary lists every restored piece and the
    enabled / missing dataset counts.

The c4d-bound paths (`save_unav_state` / `load_unav_state` writing
to `BaseDocument.GetDataInstance()` via `_BC_ID_UNAV_STATE`) are
exercised by loading the plugin in Cinema 4D 2023+; they are not
part of the automated suite.

---

## 9. Future extensions

Tracked as design intent, not promises:

  * **Auto-load on scene open.** When `UnavConfig.auto_load_state`
    is true, a `MessageData` listener triggers `load_unav_state` on
    `MSG_DOCUMENTINFO_TYPE_LOAD`. The hook is reserved by the
    config flag; it just isn't wired up yet.
  * **Migrations.** Bump `PROJECT_SCHEMA_VERSION` and add a
    per-version `migrate(d)` chain on `from_dict` so older saved
    states round-trip cleanly when the schema grows.
  * **Per-scene config overrides.** Today preferences are global;
    a future "scene-pinned scale mode" can ride in the
    `ProjectState.config` blob and override `UnavConfig` only when
    the project state is loaded.
  * **Sign and verify.** Embed a SHA-256 of the catalog file paths
    inside `ProjectState` so loading on another machine can
    cross-check that the same data is on disk before silently
    reinterpreting uids.

The persistence layer is intentionally narrow: two dataclasses, two
JSON files, three buttons. Every future feature listed above slots
in behind the existing `gather_project_state` / `apply_project_state`
interface without touching the dialog plumbing.
