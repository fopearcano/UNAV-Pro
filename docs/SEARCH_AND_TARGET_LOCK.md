# Search and Target Lock

The two halves of the v0.6 "find and focus" workflow:

1. **Search** — locate any object in the active datasets by name,
   uid, source, or type.
2. **Target lock** — pin the navigator's focus on a chosen object,
   compute the new pose, and apply it inside an undoable C4D
   transaction.

Both layers are pure-Python and live in `core/`; the c4d-bound glue
sits in `ui/search_panel.py` and (for the lock-mutation half) in the
main dialog.

---

## 1. Search

### 1.1 The query

`SearchQuery(text, catalog_source_filter, object_type_filter, max_results)`.

* `text` — raw user input. Whitespace splits it into tokens; every
  token must hit at least one searchable field (AND semantics).
* `catalog_source_filter` — optional exact match against
  `catalog_source` (e.g. `"Gaia DR3"`, `"SDSS"`, `"DESI"`,
  `"JPL Horizons"`, `"unav_sample"`).
* `object_type_filter` — optional exact match against
  `object_type` (`"star"`, `"galaxy"`, `"quasar"`, `"planet"`, …).
* `max_results` — caller-controlled cap; clamped to
  `HARD_MAX_RESULTS = 500`.

Empty `text` with one or both filters set is treated as "list every
row that passes the filters", capped to `max_results`.

### 1.2 Searched fields

In order of weight:

| Field           | Weight | Notes                                                    |
|-----------------|--------|----------------------------------------------------------|
| `name`          | 1.00   | Catalog primary identifier (e.g. Gaia source_id).        |
| `common_name`   | 0.95   | Friendly name when present (e.g. "Sirius").              |
| `uid`           | 0.85   | Connector-prefixed uid (`gaia:…`, `sdss:…`, …).          |
| `catalog_source`| 0.55   | Source label.                                            |
| `object_type`   | 0.50   | Object class.                                            |

### 1.3 Scoring

For each token, the matcher evaluates each field:

* exact-equal field → 100 points
* starts-with → 50 points
* substring → 25 points
* no match → 0

Each token's score is added to the row's running total; the field
that produced the highest single-token score is recorded as
`SearchResult.match_field` so the panel can show "matched on uid"
vs "matched on name". Ties break on uid for deterministic output.

### 1.4 Lightweight results

`SearchResult` carries:

```
uid, name, common_name, catalog_source, object_type,
ra_deg, dec_deg, distance_parsec, score, match_field
```

It does **not** carry `metadata_json` or any other heavy field —
clicking a result hands the uid back to the inspector or the lock
acquirer, which pull the full record from the lookup on demand.

### 1.5 The panel

`ui/search_panel.py.run_search(text, ...)` returns a
`PanelSearchOutcome` with the panel-rendered text, the raw results,
and a one-line status for the dialog log. The dialog stores the
last outcome on `_search_outcome` so the per-row "Focus" / "Lock" /
"Bookmark" buttons can act on the right entry.

Empty queries with no filters get a friendly placeholder
("Type a name, uid, or source above and press Search to find
objects in the active datasets."). Capped result lists print
"(capped at N)" so the artist knows to narrow the query.

---

## 2. Target lock

### 2.1 Acquiring a lock

`acquire_target(uid, lookup, *, navigator_position_c4d, scale_mode)`:

* Returns `None` if the uid is empty, missing from the lookup, or
  the resolved object has no usable position even after
  `compute_derived_fields`.
* Otherwise returns a `TargetLock` carrying:
  * `uid`, `catalog_source`, `label`, `object_type`,
  * `position_c4d` (always present),
  * `position_pc` (when the object has parsec coordinates),
  * `distance_c4d` and `distance_pc` (when the caller supplied
    `navigator_position_c4d`).

The `label` falls back through `common_name` → `name` → `uid` so
the panel always has a friendly string.

### 2.2 Computing the pose

`compute_focus_pose(lock, current_position_c4d, *, t, place_at_target, standoff_c4d)`
returns `(new_navigator_position, target_position)`:

| Mode                                      | Behaviour                                                       |
|-------------------------------------------|-----------------------------------------------------------------|
| Default (no extras)                       | Navigator stays at its current position; only the look-at is updated. |
| `place_at_target=True`                    | Navigator snaps to the target.                                  |
| `place_at_target=True`, `t < 1`           | Navigator moves a fraction `t` of the way toward the target.    |
| `standoff_c4d > 0`                        | Navigator moves toward the target but stops `standoff_c4d` short. |
| Default with `0 < t < 1`                  | Navigator drifts a fraction `t` toward the target while continuing to look at it. |

`forward_vector(from_pos, target_pos)` produces the unit direction
the c4d-bound code plugs into the camera matrix's −Z axis. Returns
`None` for coincident points (no defined direction).

### 2.3 Linear interpolation

`interpolate_position(current, target, t)` is the building block.
`t` is clamped to `[0, 1]`; out-of-range values do not crash.
`INSTANT_SNAP_T = 1.0` is exposed as the default.

The interpolation is linear — there are no easing curves, no
animation timelines, no per-frame stepping. The c4d-bound caller
can drive it from a button click for instant motion or from a
timer for smoother motion (the latter is a v0.7+ option).

### 2.4 Safety check vs clip range

`evaluate_target_against_clip(lock, near_clip_pc, far_clip_pc)`
returns a `TargetSafetyReport` with:

* `in_range` — bool;
* `distance_pc` — the lock's pc distance (or `None` if unknown);
* `near_clip_pc` / `far_clip_pc` — echoed back for the panel;
* `short_summary()` — UI-ready one-liner.

The dialog calls this after a successful `acquire_target` so the
artist sees "target 4500 pc away — OUTSIDE clip [0.1, 1000] pc;
adjust far/near_clip_parsec or it will not stream" before the
streaming layer silently refuses to bring the target into the
visible sector.

### 2.5 Applying the lock in C4D

The dialog button paths:

* **Lock Target** (in the Search tab, or "Lock Selected as Target"
  in the Navigation tab) — runs `acquire_target` against the
  active `default_lookup()`, stashes the lock on
  `self._target_lock`, updates the navigation status line.
* **Focus** — runs `acquire_target`, sets the navigator's matrix
  `off` to `position_c4d` inside an `AddUndo(UNDOTYPE_CHANGE)`
  block, fires `c4d.EventAdd()`. Rotation is left untouched (a
  v0.7 item is to derive a look-at rotation from
  `forward_vector`).
* **Unlock Target** — clears `self._target_lock`. The status line
  reverts to "(no target locked)".

---

## 3. Failure modes

| Scenario                                | What happens                                                          |
|-----------------------------------------|-----------------------------------------------------------------------|
| Search query matches nothing            | Panel shows "No matches"; status log echoes the query.                |
| Search returns more than `max_results`  | Panel labels "(capped at N)"; status log says "showing N (capped)…".  |
| Lock target uid not in lookup           | `acquire_target` returns `None`; dispatcher logs "not resolvable".    |
| Lock target has no position             | Same as above — `compute_derived_fields` couldn't fill the gap.       |
| Lock target outside clip range          | `evaluate_target_against_clip(...).in_range == False`; panel warns.   |
| No `UNAV_Navigator` in scene            | Focus dispatcher logs "no UNAV_Navigator in scene."; no mutation.     |
| Coincident target / navigator           | `forward_vector` returns `None`; pose stays untouched.                |

---

## 4. What this layer does not do

* **No live HTTP search.** Search is in-memory across the active
  `MetadataLookup`.
* **No fuzzy match.** Substring + starts-with + exact only — no
  Levenshtein, no phonetic matching.
* **No camera roll.** Forward direction is set; roll is the
  artist's choice.
* **No animation timeline.** The `t` parameter is a "step toward"
  knob, not a per-frame ease.
* **No automatic re-sync after lock.** Use *Sync Visible Sector*
  manually after a long lock to reload the streaming cells around
  the target.
