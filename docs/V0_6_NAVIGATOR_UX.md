# UNAV Pro v0.6 — Navigator UX Layer

The first user-experience layer on top of v0.1 – v0.5. Turns UNAV Pro
from a data viewer into a navigation tool: cross-dataset search,
target-lock, persistent bookmarks, refined route planning, and
step-based navigation controls.

For the per-feature deep docs see:

* [`SEARCH_AND_TARGET_LOCK.md`](SEARCH_AND_TARGET_LOCK.md) — search +
  target-lock contracts and UI surface.
* [`BOOKMARKS_SYSTEM.md`](BOOKMARKS_SYSTEM.md) — persistent bookmarks,
  on-disk format, focus semantics.
* [`ROUTE_WORKFLOW_V2.md`](ROUTE_WORKFLOW_V2.md) — insert / replace /
  reorder, segment table, distance summary.

---

## 1. What v0.6 ships

### 1.1 Search

`core/search.py` + `ui/search_panel.py`.

* Searches the active `MetadataLookup` across `name`, `common_name`,
  `uid`, `catalog_source`, `object_type`.
* Case-insensitive partial matching with **AND** semantics on
  whitespace-split tokens.
* Optional exact filters on catalog source and object type.
* Lightweight result rows (no `metadata_json` blob); the inspector
  pulls the full record on click.
* Hard cap (`HARD_MAX_RESULTS = 500`) plus a per-query cap
  (`DEFAULT_MAX_RESULTS = 50`) so a one-character query never
  produces a huge UI list.

### 1.2 Target lock

`core/target_lock.py`.

* `acquire_target(uid, lookup)` resolves a uid to a `TargetLock`
  with `position_c4d`, `position_pc`, distance from the navigator,
  and `label`.
* `compute_focus_pose(...)` produces the new navigator position
  with three behaviours:
  * default — navigator stays put, only forward axis changes;
  * `place_at_target=True` — navigator snaps to the target;
  * `standoff_c4d=...` — navigator stops short of the target by
    that many C4D units.
* Linear interpolation via `t ∈ [0, 1]` for "drift toward target"
  workflows (no animation timeline; one click = one step).
* `evaluate_target_against_clip(...)` reports whether the target is
  inside `[near_clip_pc, far_clip_pc]` so the UI can warn before
  the artist locks on something the streaming layer will never
  load.

### 1.3 Bookmarks

`core/bookmarks.py` + `ui/bookmarks_panel.py`.

* Two kinds: `object` (uid) and `coordinate` (free 3D point).
* Persistent JSON at `~/.unav_pro/bookmarks.json`, alongside
  `config.json` and the per-project sidecars.
* Add / remove / reorder / rename, plus a duplicate-guard so
  re-clicking "Bookmark" on the same target is a no-op.
* Convenience constructors from `SearchResult` and `TargetLock`
  so the UI doesn't have to thread fields manually.

### 1.4 Route refinements

Updates to `core/route.py` + `ui/route_panel.py`:

* `Route.insert_at(index, waypoint)` — for "add between A and B"
  workflows.
* `Route.replace_at(index, waypoint)` — swap a waypoint without
  changing the route order.
* `Route.move(from_idx, to_idx)` — reorder.
* `render_summary_v2(route, summary)` — adds a per-segment table
  (with C4D and parsec distances when both endpoints carry pc
  coords) under the existing v0.1 header.

The c4d-bound `add_selected_as_waypoint` / `clear_route` /
`build_route_spline` / `focus_navigator_on` helpers are unchanged;
existing scenes continue to work.

### 1.5 Navigation controller

`core/navigation_controller.py`.

* `StepSpeed(step_distance_pc, acceleration)` — validated dataclass.
  Defaults: 1 pc per step, 1.0 acceleration.
* `step_position(current_pc, forward, speed, direction)` — pure
  linear addition along the forward unit vector.
* `forward_from_yaw_pitch(yaw_deg, pitch_deg)` — converts spherical
  controls to a unit forward vector matching the navigator null's
  −Z convention.
* `check_step_safety(...)` — reports whether the proposed
  post-step distance from the barycentric origin is inside
  `[near_clip_pc, far_clip_pc]`.
* `NavigationController` — stateful wrapper used by the dialog.
  `step_forward` / `step_backward` / `set_speed` / `reset`.

The c4d-bound side reads the navigator's local −Z as the world-space
forward, converts the active scale (`pc` units per C4D unit) at the
boundary, and applies the step inside an `AddUndo` block so the
artist can `Ctrl+Z` past a misclick.

---

## 2. UI structure

The dialog adds a `TabGroupBegin` block for the v0.6 tabs:

* **Search** — query input, source filter, result list, "Focus"
  / "Lock Target" / "Add to Bookmarks".
* **Bookmarks** — saved-list view, "Focus" / "Remove" / "Capture
  Navigator Position" / "Reload".
* **Navigation** — step distance, acceleration, "Step Forward",
  "Step Backward", "Lock Selected as Target", "Unlock Target",
  active-target status line.

The pre-v0.6 controls (Visual Encoding, Safety, Sync, Action grid,
Status Log, Route Planner, Metadata Inspector) remain in their
existing groups above the tabs so the working sector-streaming flow
is unaffected. A future polish pass can consolidate every group
under `TabGroupBegin` to match the full six-tab plan
(Dataset / Navigator / Search / Bookmarks / Route / Diagnostics);
until then this hybrid layout keeps the v0.6 surface visible
without risking a layout regression.

---

## 3. Safety integration

Every navigation action respects the existing v0.1 safety contract:

* **Visible-sector-only mode.** Focus / lock / step actions all
  require a `UNAV_Navigator` in the scene. Without one the
  c4d-bound dispatcher logs "no UNAV_Navigator in scene." and
  exits cleanly.
* **`max_visible_objects`.** The navigation controller never
  generates new C4D nodes — the limit is enforced by the
  visible-sector builder, not by any v0.6 surface.
* **Sector streaming.** `acquire_target` /
  `evaluate_target_against_clip` / `check_step_safety` all
  surface "outside clip" warnings in the dialog log, so the
  artist sees that streaming will not bring the target into the
  scene unless they widen `far_clip_parsec`.
* **Auto-sync after move.** `Auto Sync` remains user-toggled (a
  v0.7 polish item is to wire it into the post-step path so the
  visible sector refreshes automatically; v0.6 keeps the manual
  *Sync Visible Sector* click as the explicit checkpoint).

The undo system is honoured: navigator pose changes happen inside
`doc.StartUndo() / EndUndo()` blocks with `AddUndo(UNDOTYPE_CHANGE)`
so a misstep is reversible.

---

## 4. What v0.6 deliberately skips

* **Animation timelines.** No per-frame stepping; one click = one
  step.
* **Relativistic physics.** Distances are linear Euclidean
  additions. No light-time correction, no time dilation.
* **Real-time auto-step.** The `MessageData` hook reserved by the
  Auto Sync checkbox stays dormant.
* **Camera roll / banking.** Forward direction is set; roll is the
  artist's responsibility.
* **Server-side search.** Search is in-memory across the active
  `MetadataLookup`. A future tile-aware path can plug into the
  same `Iterable[CatalogObject]` input without changing callers.

---

## 5. Test coverage

Every v0.6 module ships pure-Python tests, mocked where needed:

| Module                          | Tests file                                  |
|---------------------------------|---------------------------------------------|
| `core/search.py`                | `tests/test_search.py`                      |
| `core/target_lock.py`           | `tests/test_target_lock.py`                 |
| `core/bookmarks.py`             | `tests/test_bookmarks.py`                   |
| `core/navigation_controller.py` | `tests/test_navigation_controller.py`       |
| `core/route.py` (refinements)   | `tests/test_route_v06_refinements.py`       |

`pytest unav_pro/tests/` runs the full suite; the v0.6 additions
join the existing 600+ tests without breaking any prior contract.
