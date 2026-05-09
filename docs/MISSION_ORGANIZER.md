# Mission Organizer

The v1.9 ``MissionManager`` extensions that turn the v1.4
mission store into a usable library: duplicate, rename, tag,
search, sort, and full-library packages.

---

## 1. New manager methods

```python
mgr = MissionManager()

clone = mgr.duplicate(mission_id, new_title="Copy")
mgr.rename(mission_id, "New Title")

mgr.add_tags(mission_id, ["solar", "demo"])
mgr.remove_tag(mission_id, "demo")

mgr.search("alpha")                # text query
mgr.search("alpha", tag="solar")   # query + tag
mgr.search(tag="extragalactic")    # tag-only

mgr.sort(by="title")               # alpha
mgr.sort(by="modified")            # most-recent first
mgr.sort(by="waypoints")           # by count

mgr.export_package("/path/to/library.json")  # → returns count
mgr.import_package("/path/to/library.json")  # → returns count
```

Every new method honours the v1.7 fail-closed contract:

* Unknown mission ids return ``False`` / ``None`` rather
  than raising.
* Corrupt or missing package files log + return ``0``.
* Duplicate writes go through ``safe_write_json`` (atomic).

---

## 2. Duplicate

`duplicate(mission_id, *, new_title=None)` creates a fully
*detached* copy:

* The clone goes through ``Mission.from_json(source.to_json())``
  so every nested dataclass (waypoints, scene annotations,
  tags) is a fresh instance.
* The clone gets a fresh ``mission_id`` (16 hex chars).
* The default title is ``"Copy of <original>"``; pass
  ``new_title="…"`` to override.
* The clone inherits the source's ``modified_iso`` — when
  the artist saves, the manager stamps a fresh modified
  time.

Mutating the clone never bleeds into the source. Tests
assert this end-to-end.

---

## 3. Rename

`rename(mission_id, new_title)` updates the title in place,
calls `update()` (which writes the file atomically), and
returns ``True``. Empty / whitespace-only titles return
``False`` without touching anything.

---

## 4. Tags

* `add_tags(mission_id, tags)` — appends the iterable's
  entries to ``mission.tags``, lower-cased + deduplicated.
  Returns ``True`` when at least one tag was added.
* `remove_tag(mission_id, tag)` — drops a single tag.
  Returns ``True`` when the tag was present.

Tag values are always normalised to lower case at write
time. Searches are case-insensitive — the artist can type
"Solar" or "solar" with the same result.

The v1.9 mission JSON keeps tags case-preserved on disk
(only the `MissionWaypoint.tags` field force-lowercases on
construction); the mission-level ``Mission.tags`` round-trips
verbatim so existing missions don't drift on save.

---

## 5. Search

`search(query="", *, tag=None)` filters the mission list:

* ``query`` matches case-insensitively against title,
  description, or any tag.
* ``tag`` requires that tag in the mission's tag list.
* Both empty → return the full list.
* No results → empty list (no exception).

Search results preserve the manager's display order; the
filter is non-destructive (the manager's underlying mission
set is unchanged).

The dialog's **Filter** button calls `search` with the value
in the search input field; the Missions list panel shows the
filtered subset until the artist clears the input.

---

## 6. Sort

`sort(by=…, reverse=False)` reorders the *display list*; the
underlying mission set is unchanged.

| ``by``           | Sort key                                          |
|------------------|---------------------------------------------------|
| ``"title"``      | Alphabetical, case-insensitive.                  |
| ``"modified"``   | ``modified_iso`` — most-recent first by default. |
| ``"waypoints"``  | Waypoint count.                                  |
| ``"id"``         | Lexicographic by ``mission_id``.                 |

Any other value raises ``ValueError`` so the dialog can
surface the typo in the log.

---

## 7. Packages

A *package* is a single JSON file containing every
registered mission. The format is intentionally simple:

```json
{
    "schema_version": 1,
    "missions": [
        {... mission 1 ...},
        {... mission 2 ...}
    ]
}
```

`export_package(path)` writes the package atomically. Returns
the number of missions written.

`import_package(path)` reads each entry through
``Mission.from_dict``; collisions reassign a fresh
``mission_id`` so the import is always non-destructive.
Malformed entries log a warning + skip; the import keeps
going. Returns the number of missions actually registered.

This is the format to use for sharing an entire library
between machines / artists. For a single mission the existing
``export_mission`` / ``import_mission`` helpers remain.

---

## 8. Determinism

Every organizer operation is deterministic:

* `duplicate` produces the same clone given the same source
  (modulo the auto-generated `mission_id`).
* `search` and `sort` produce the same result given the
  same library.
* Package round-trips (export → import → export) produce
  byte-identical files (modulo `mission_id` reassignment on
  collision).

Tests assert these properties.

---

## 9. The dialog wiring

The Missions tab gains four new buttons in v1.9:

* **New From Template** — picks the row from the **Template**
  combo and registers a fresh mission.
* **Duplicate Mission** — clones the active mission.
* **Filter** — re-renders the mission list with the v1.9
  search query.
* **Export Markdown…** / **Export CSV…** — see
  [`V1_9_ADVANCED_VOYAGE_TOOLS.md`](V1_9_ADVANCED_VOYAGE_TOOLS.md) §7.

Tag editing, sort dropdowns, and package export/import don't
have dialog buttons in v1.9 yet; they are reachable via the
manager API and via hand-edit of the on-disk files. The v1.x
mission organizer panel will surface them.

---

## 10. What the organizer is *not*

* **Not a tagging UI.** The dialog has no tag editor in
  v1.9; the artist hand-edits the mission JSON or calls
  ``add_tags`` from a script.
* **Not a multi-select operation.** Each method targets one
  mission. Bulk operations (e.g. "tag every mission with
  X") need iteration on the caller's side.
* **Not a versioning system.** Duplicate copies the current
  state; there is no per-mission revision history.
