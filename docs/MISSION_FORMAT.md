# Mission JSON Format

The on-disk shape of a v1.4 mission. UNAV writes this format
to `~/.unav_pro/missions/<mission_id>.json` and reads it back
on next launch. The same format flows through the manager's
`export_mission` / `import_mission` helpers — share a mission
file with another artist by emailing it; nothing else needs
to be in sync.

The format is JSON. Every field is documented below. UNAV's
loader is tolerant: unknown fields are ignored, missing
optional fields use defaults, and unrecoverable waypoints
are silently dropped (the count is logged so the artist
notices).

---

## 1. Top-level fields

```json
{
  "schema_version": 1,
  "mission_id": "8f3c7a9c4b1d2e0f",
  "title": "Inner Solar System Tour",
  "description": "A weekly fly-through of the inner planets.",
  "tags": ["solar-system", "demo"],
  "waypoints": [ ... ],
  "created_iso": "2026-04-30T12:00:00Z",
  "modified_iso": "2026-04-30T12:34:56Z"
}
```

| Field            | Type           | Notes                                                |
|------------------|----------------|------------------------------------------------------|
| `schema_version` | int            | Stamped on save. The reader logs a warning when it sees a higher version. |
| `mission_id`     | string         | 16-hex-char unique id. Stable across renames.        |
| `title`          | string         | Required. Displayed in the dialog list. ≤ 200 chars. |
| `description`    | string         | Optional. Free text.                                 |
| `tags`           | list[string]   | Optional. Display-only.                              |
| `waypoints`      | list[object]   | The ordered stop list (see §2).                      |
| `created_iso`    | ISO-8601 UTC   | Set once on creation.                                |
| `modified_iso`   | ISO-8601 UTC   | Updated on every mutation.                           |

---

## 2. Waypoint fields

Each waypoint is one of four `kind`s. The required and
optional fields differ per kind; see the table below.

```json
{
  "kind": "object",
  "label": "Mars 2026",
  "uid": "jpl:Mars:2026",
  "catalog_source": "JPL Horizons",
  "object_type": "planet",
  "epoch_jd": 2461041.5,
  "duration_seconds": 3.0,
  "notes": "closest approach"
}
```

| Field              | Type            | Required when                         |
|--------------------|-----------------|----------------------------------------|
| `kind`             | string          | Always. One of `object` / `coordinate` / `named` / `bookmark`. |
| `label`            | string          | `named` (and recommended elsewhere).   |
| `uid`              | string          | `kind == "object"`.                    |
| `bookmark_id`      | string          | `kind == "bookmark"`.                  |
| `x_c4d/y_c4d/z_c4d`| float           | `kind == "coordinate"`.                |
| `x_pc/y_pc/z_pc`   | float           | Optional cache (parsec coords).        |
| `catalog_source`   | string          | Optional cache (offline display).      |
| `object_type`      | string          | Optional cache (offline display).      |
| `epoch_jd`         | float           | Optional. Threaded through the v1.2 Time Navigator at playback. |
| `orientation_quat` | list[4 floats]  | Optional. `(w, x, y, z)`.              |
| `duration_seconds` | float           | Optional. Defaults to 4.0. Must be > 0.|
| `notes`            | string          | Optional.                              |

The `coordinate` and `named` waypoints don't reference the
catalog — they survive without an active `MetadataLookup`.
The `object` and `bookmark` waypoints carry just an
identifier; the playback path resolves the position at build
time. If resolution fails, the waypoint is silently dropped
from the camera path (the dialog reports the count so the
artist can fix it).

---

## 3. Index file

The directory also contains an `index.json`::

```json
{
  "mission_ids": [
    "8f3c7a9c4b1d2e0f",
    "1a2b3c4d5e6f7081",
    ...
  ]
}
```

Just an ordered list of known mission ids. The manager uses
this for display order; the directory contents are the
authoritative *set* (so a hand-dropped JSON appears in the
list even if it isn't in the index).

---

## 4. Schema versioning

`schema_version` starts at `1` for v1.4. The reader's contract:

* If `schema_version <= MISSION_SCHEMA_VERSION` (current),
  the mission loads normally.
* If `schema_version > MISSION_SCHEMA_VERSION`, a warning is
  logged and the mission still loads with the fields the
  reader recognises — unknown fields are silently ignored.
* If `schema_version` is missing entirely, it's treated as
  `1` (the v1.4 baseline).

Future schema bumps will only add fields, never repurpose
existing ones, so a v1.5 reader can always open a v1.4 file
unchanged.

---

## 5. Determinism

`Mission.to_json` serialises with `sort_keys=True, indent=2`,
so two missions with the same content produce byte-identical
JSON. This is the basis of the v1.4 "deterministic playback"
guarantee — same mission file → same camera path → same
playback output.

If you hand-edit a mission file, the next save will rewrite
it in canonical (sorted-key) form. This is harmless; just be
aware your diff tool may show every line as changed.

---

## 6. Example: a 3-stop mission

```json
{
  "schema_version": 1,
  "mission_id": "8f3c7a9c4b1d2e0f",
  "title": "Pleiades flyby",
  "description": "Three-stop tour of the Pleiades.",
  "tags": ["star-cluster"],
  "waypoints": [
    {
      "kind": "object",
      "uid": "gaia:1234567890",
      "label": "Alcyone",
      "catalog_source": "Gaia DR3",
      "object_type": "star",
      "duration_seconds": 5.0
    },
    {
      "kind": "coordinate",
      "label": "midpoint",
      "x_c4d": 0.0,
      "y_c4d": 100.0,
      "z_c4d": 0.0,
      "duration_seconds": 3.0
    },
    {
      "kind": "bookmark",
      "bookmark_id": "abc12345",
      "label": "Maia",
      "duration_seconds": 5.0
    }
  ],
  "created_iso": "2026-04-30T12:00:00Z",
  "modified_iso": "2026-04-30T12:00:00Z"
}
```

Total runtime: 13 s at speed × 1.0.
