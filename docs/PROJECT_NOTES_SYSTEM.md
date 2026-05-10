# UNAV Pro — Project Notes System

How v3.1 stores artist-owned notes alongside an UNAV
workspace.

For the workspace overview see
[`V3_1_PROJECT_WORKSPACES.md`](V3_1_PROJECT_WORKSPACES.md).

---

## 1. Three kinds of notes

* **Project notes** — one workspace-wide markdown file at
  `notes/project.md`. Use this for the project's
  overall plan, todo list, decisions log, etc.
* **Mission notes** — one file per mission at
  `notes/missions/<mission_id>.md`. Use this for
  per-mission shot notes, blocking, beats.
* **Dataset notes** — one file per dataset at
  `notes/datasets/<dataset-name>.md`. Use this for
  provenance, reference URLs, "why we chose this catalog
  cut", etc.

Notes are **plain markdown / text files**. The plugin
reads and writes them but never interprets the body.
Filename gives a note its scope.

## 2. NotesStore API

```python
from project import NotesStore

store = NotesStore(workspace.notes_dir())

# Write.
store.write_project_note("# Voyager Cinematic\n\n- Beat 1 ...")
store.write_mission_note("voyager-arrival", "## Notes\n...")
store.write_dataset_note("Gaia DR3", "Vendor cut ...")

# Read.
project = store.read_project_note()
mission = store.read_mission_note("voyager-arrival")

# Enumerate.
for entry in store.list_notes():
    print(entry.short_summary())

# Aggregate.
print(store.annotation_summary())
```

Every write is **atomic** (temp + rename), so a crash
mid-write doesn't truncate the previous note. Reads from
a missing file return `None`. Deletes are idempotent.

## 3. Filename safety

Mission ids and dataset names can contain characters that
aren't filesystem-safe (`:`, `/`, `*`). The store maps
those to underscores via a single canonical
sanitiser:

```python
from project import relative_path_for_note, NOTE_KIND_MISSION

rel = relative_path_for_note(NOTE_KIND_MISSION, "Gaia DR3 + tour")
# → "notes/missions/Gaia_DR3_tour.md"
```

Same input always maps to the same filename, so two
calls with the same mission id always hit the same
file.

## 4. Annotation summaries

`store.annotation_summary()` renders a multi-line
markdown document concatenating every note in the
store:

```
# Project Notes Summary

## [project] (workspace)
*Updated: 2026-05-10T12:00:00*

# Voyager Cinematic
- Beat 1 ...

## [mission] voyager-arrival
*Updated: 2026-05-10T12:01:00*
...
```

The dialog's *Project → Notes Summary* button writes
this to a temp file and opens it in the host editor.

## 5. Storage choice

Markdown was picked over JSON / sqlite for three
reasons:

* **Diff-friendly.** Notes go into git happily.
* **Editor-agnostic.** Any text editor works; no UNAV
  build needed.
* **Lightweight.** No schema migration concerns; a
  note that says "TODO" weighs ~10 bytes on disk.

The trade-off is no structured fields. The plugin can
parse front-matter or tags out of the body in a future
release; v3.1 doesn't.

## 6. Acceptance + tests

* `test_v31_notes` covers safe-filename mapping, write
  / read / delete, list ordering, the annotation
  summary, and atomic-write behaviour.
