# UNAV Pro v1.7 — Stabilization & Architecture Cleanup

UNAV's v1.7 milestone is **not a feature release**. It is a
reliability, consistency, and maintainability pass over the
v1.0–v1.4 stack. The goal is to turn a growing prototype
into a stable professional plugin: same features, fewer
fragile edges, one source of truth for state, consistent
terminology, deterministic cleanup.

For the as-is internal picture see
[`V1_7_ARCHITECTURE_AUDIT.md`](V1_7_ARCHITECTURE_AUDIT.md).
For the per-surface lifecycle (open / load / sync / close)
see [`PLUGIN_LIFECYCLE.md`](PLUGIN_LIFECYCLE.md). For the
acknowledged shortcomings v1.7 chooses not to fix see
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

---

## 1. What v1.7 actually delivers

| Surface | Change |
|---------|--------|
| `core/state_manager.py` | New central facade for every UNAV singleton (config, bookmarks, registry, lookup, time navigator, missions). |
| `core/config.safe_write_json` | Atomic JSON writer (temp file + rename) shared by every persistence surface. |
| `core/dataset_registry.reload()` | New method: re-read ``datasets.json`` from disk in place. |
| `core/time_navigator.default_state(reload=True)` | Reload semantics matched to ``metadata_lookup``. |
| `core/scene_sync._current_visible_objects` | Defensive walk: half-deleted children are logged and skipped, not raised. |
| `db/spatial_query.query_cone` | When ``max_visible_objects`` is set but ``bbox_max_rows`` isn't, the SQL ``LIMIT`` is auto-derived as `4 × cap` to bound memory before the cone refine. |
| UI dialog | Bookmark "Reload" button renamed "Sync" for verb consistency. |
| Tests | New `test_v17_stability.py` covers repeated sync, render-mode switch, dataset reload, config corruption, mission reload. |
| Docs | Three new docs (this file + audit + limitations + lifecycle), four existing docs touched. |

**No new features. No renderer integrations. No on-disk
format changes.** DB schema v2, binary v3, mission schema v1
are all untouched.

---

## 2. The state-manager facade

Every UNAV singleton is now reachable through one module:

```python
from core.state_manager import (
    get_dataset_registry,
    health_summary,
    dataset_summary,
    visible_sector_summary,
    reload_all,
    validate_config,
    validate_bookmarks,
    validate_registry,
)
```

The dialog used to import each lazy initialiser from its own
module. v1.7 keeps those modules unchanged — they remain the
authoritative implementations — but adds a single import
surface for the diagnostics panel and for the
"Reload State" button.

`health_summary()` returns one `StateHealthEntry` per
subsystem (config, bookmarks, datasets, time_navigator,
metadata_lookup, missions). The diagnostics panel renders
this verbatim. `is_healthy()` answers the question "is
anything broken right now?"; `summary_line()` is the one-
liner the dialog can drop into its log.

`reload_all()` resets every singleton this facade tracks —
useful for tests and for the diagnostics panel's "Reload
State" button.

---

## 3. Atomic writes

The four persistence surfaces (config, bookmarks, project
state, dataset registry) used to write directly. A crash
mid-write could leave a half-written file on disk that the
loader couldn't parse; the loader's fail-closed contract
would then drop the artist's preferences silently.

v1.7 routes every write through
`core.config.safe_write_json(path, payload)`:

```python
def safe_write_json(path, payload):
    tmp = path + ".tmp"
    write tmp
    os.replace(tmp, path)   # atomic on POSIX + NTFS
```

A crash mid-write leaves the previous valid file intact (or
no file at all, if there was none). The loader's fail-closed
contract still applies; the difference is that it now fires
only when the file genuinely never existed.

---

## 4. Bounded-memory cone queries

`db/spatial_query.query_cone` had two caps in v1.6:
``bbox_max_rows`` (SQL-level) and ``max_visible_objects``
(post-refine). When the caller set the second but not the
first, the bbox query could materialise a million-row
catalog into Python before the exact-cone-refine had a
chance to trim.

v1.7 derives ``bbox_max_rows`` from ``max_visible_objects``
when it isn't explicitly set:

```python
effective_bbox_cap = bbox_max_rows
if effective_bbox_cap is None and max_visible_objects:
    effective_bbox_cap = int(max_visible_objects) * 4
```

The 4× headroom keeps slack for the cone refine: the bbox is
a loose superset of the cone, so we expect ~25% of bbox rows
to survive the refine. The factor is documented in
`SPATIAL_QUERY_STRATEGY.md`.

---

## 5. Tests added

`unav_pro/tests/test_v17_stability.py` covers:

* `test_repeated_compute_diff_idempotent` — applying the
  same input twice produces identical (added/removed/kept)
  sets.
* `test_mode_switch_diff_chain` — three diff cycles
  (debug → instances → cloud) end with no orphan UIDs.
* `test_registry_reload_picks_up_disk_changes` — write a
  fresh registry to disk; call `reload()`; entries match.
* `test_safe_write_json_is_atomic` — partial writes are
  cleaned up; existing valid files are preserved.
* `test_health_summary_reflects_subsystem_status` — flips
  one subsystem to error and asserts the summary line
  changes.

`unav_pro/tests/test_v17_state_manager.py` covers the
facade in isolation: `get_dataset_registry`, `reload_all`,
the validators.

---

## 6. Acceptance criteria

* [x] Repeated `sync_visible_sector()` produces consistent
  diffs (no leaks, no double-add).
* [x] Render-mode switching never leaves orphan
  `UNAV_*` children in the OM.
* [x] `~/.unav_pro/config.json` survives a simulated crash
  mid-write.
* [x] Corrupt persistence files fail closed at every
  layer.
* [x] Invalid datasets fail gracefully and stay registered.
* [x] UI verbs are consistent across panels (Sync / Apply
  / Reload, with documented meanings).
* [x] Logs are routed through `core.logging_util`; no
  bare `print(` in production code; no `except:` that
  swallows errors silently.
* [x] `V1_7_ARCHITECTURE_AUDIT.md` matches the live
  codebase.

---

## 7. What v1.7 does **not** do

* No new features.
* No renderer integrations.
* No conceptual redesign of the plugin.
* No on-disk format bumps.
* No re-organisation of `core/` ↔ `c4d_objects/` boundaries.
* No GPU work; the v1.x renderer milestone is unchanged.
