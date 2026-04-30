# Bookmarks System

Persistent saved-anchor list for the UNAV navigator. v0.6 ships two
kinds of bookmarks:

* **Object bookmarks** — a uid + label that the lookup resolves to
  a position when the user clicks Focus.
* **Coordinate bookmarks** — a fixed 3D point in C4D world units
  (and optional parsec triple) for "remember this scene location."

The implementation lives in `core/bookmarks.py` and the c4d-bound
helpers in `ui/bookmarks_panel.py`.

---

## 1. The data model

```python
@dataclass
class Bookmark:
    kind: str                       # "object" | "coordinate"
    label: str = ""
    uid: Optional[str] = None       # required when kind == "object"
    catalog_source: Optional[str] = None
    object_type: Optional[str] = None
    x_c4d: Optional[float] = None   # required when kind == "coordinate"
    y_c4d: Optional[float] = None
    z_c4d: Optional[float] = None
    x_pc: Optional[float] = None
    y_pc: Optional[float] = None
    z_pc: Optional[float] = None
    id: str = ""                    # auto-assigned hex suffix
    created_iso: Optional[str] = None
    notes: str = ""
```

Validation is enforced at construction:

* `kind` must be `"object"` or `"coordinate"`.
* Object bookmarks require a non-empty `uid`.
* Coordinate bookmarks require all three `*_c4d` values.

`id` defaults to a 12-char hex suffix so two bookmarks named
"Sirius" never collide on the panel.

---

## 2. The list

`BookmarkList` is an ordered list of `Bookmark` plus persistence
helpers. Order matters:

* The panel renders insertion order.
* `move(bookmark_id, new_index)` reorders.
* `add(...)` rejects exact duplicates by `(kind, uid)` for object
  bookmarks and `(kind, x_c4d, y_c4d, z_c4d)` for coordinate
  bookmarks (within `1e-6` tolerance), so re-clicking "Bookmark"
  on the same target is a no-op.

The list exposes:

| Method                                 | Behaviour                                                          |
|----------------------------------------|--------------------------------------------------------------------|
| `add(bookmark)`                        | Returns `(was_added, existing_or_new)`. Skips duplicates.          |
| `remove(bookmark_id)`                  | Returns the popped bookmark, or `None`.                            |
| `move(bookmark_id, new_index)`         | Reorders; clamps `new_index` to the valid range.                   |
| `rename(bookmark_id, new_label)`       | In-place label change.                                             |
| `find(bookmark_id)` / `index_of(...)`  | Lookup helpers.                                                    |
| `clear()`                              | Empty the list; returns the count cleared.                         |
| `to_dict` / `from_dict` / `to_json` / `from_json` | JSON round-trip; corrupt input yields an empty list.    |

---

## 3. On-disk format

Bookmarks live at `~/.unav_pro/bookmarks.json`, alongside
`config.json` (the per-user preferences from v0.1) and the
per-project sidecars in `~/.unav_pro/projects/`.

Format:

```json
{
  "schema_version": 1,
  "bookmarks": [
    {
      "kind": "object",
      "label": "Sirius",
      "uid": "gaia:1234567890",
      "catalog_source": "Gaia DR3",
      "object_type": "star",
      "id": "a1b2c3d4e5f6",
      "created_iso": "2026-04-30T12:00:00"
    },
    {
      "kind": "coordinate",
      "label": "Pleiades centroid",
      "x_c4d": 56.75, "y_c4d": 24.12, "z_c4d": 130.0,
      "x_pc":  56.75, "y_pc":  24.12, "z_pc":  130.0,
      "id": "f6e5d4c3b2a1",
      "created_iso": "2026-04-30T12:01:00"
    }
  ]
}
```

`save_bookmarks(list, path=None)` writes to the default path when
`path` is omitted; failures are logged at WARNING level and the
function returns `None` rather than raising. `load_bookmarks(path=None)`
returns an empty `BookmarkList` for missing or corrupt files.

The format is forward-compatible: unknown keys in a stored
bookmark dict are silently dropped on load (the dataclass's
`fields()`-driven `from_dict` is the gate).

---

## 4. Convenience constructors

| Constructor                                          | When to use                                                        |
|-----------------------------------------------------|---------------------------------------------------------------------|
| `bookmark_from_search_result(result, label=...)`    | The user clicked "Add to Bookmarks" on a search result.            |
| `bookmark_from_target_lock(lock, label=...)`        | The user wants to bookmark the currently locked target — captures the lock's c4d/pc positions. |
| `bookmark_from_coordinate(position_c4d, label, ...)`| The user clicked "Capture Navigator Position".                     |

All three return a fresh `Bookmark` with a unique `id` and
`created_iso`; the caller hands it to `BookmarkList.add()`.

---

## 5. Focus semantics

`ui/bookmarks_panel.focus_pose_for(bookmark, lookup=None)` returns a
`FocusPose` carrying the navigator-position triple plus a status
line. Three resolution paths:

| Bookmark kind                         | Resolution                                                         |
|---------------------------------------|---------------------------------------------------------------------|
| `coordinate` with cached `x/y/z_c4d`  | Returns the cached triple.                                         |
| `coordinate` without cached coords    | Returns unresolved with "has no C4D position."                     |
| `object` resolved via lookup          | Returns the lookup-derived `position_c4d`.                         |
| `object` with lookup miss + cached coords | Returns the cached triple, status notes "from cached coordinates (catalog miss)." |
| `object` with lookup miss + no cache  | Returns unresolved with "load the matching dataset."               |

The dialog plugs the resolved triple into the navigator's matrix
`off` inside an `AddUndo(UNDOTYPE_CHANGE)` block — same undoable
pattern the v0.1 route-focus path uses.

---

## 6. UI surface

The Bookmarks tab exposes:

* The persistent list (multi-line, monospaced).
* A "Pick #" index selector + Focus / Remove buttons.
* "Capture Navigator Position" — adds a coordinate bookmark from
  the navigator's current `off`.
* "Reload" — re-read `~/.unav_pro/bookmarks.json` from disk
  (useful when an external script edited the file).

The Search tab adds an "Add Selected Result to Bookmarks" button
so the typical workflow is: search → focus → bookmark.

---

## 7. Failure modes

| Scenario                                  | What happens                                                       |
|-------------------------------------------|--------------------------------------------------------------------|
| Add a duplicate (same uid or coords)      | `add` returns `(False, existing)`; status log says "already in the list." |
| Remove an unknown id                      | `remove` returns `None`; status log says "id not found."           |
| Focus an unresolved object bookmark       | Status log explains the miss; navigator pose is untouched.         |
| Save fails (permission / OOM / FS)        | Logged at WARNING; the in-memory list is unchanged.                |
| Corrupt `bookmarks.json` on load          | Empty list returned; status log says "(0 entries)" on Reload.      |
| `Bookmark` dict from a future schema      | Unknown keys are dropped; known keys land on the dataclass.        |

---

## 8. What this system intentionally skips

* **No per-project bookmarks file.** The file is per-user; the
  project state (route, navigator, encoding) stays in the C4D
  scene's BaseContainer + sidecar — adding bookmarks there would
  duplicate the global list.
* **No tags / folders.** v0.7 is a natural place for grouping;
  v0.6 keeps it flat.
* **No keyboard shortcuts.** A `MessageData` hook for global
  hotkeys is reserved for a later polish pass.
