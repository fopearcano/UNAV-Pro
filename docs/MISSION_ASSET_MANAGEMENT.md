# UNAV Pro — Mission Asset Management

How v3.1 makes mission assets reusable across projects
and artists.

For the workspace overview see
[`V3_1_PROJECT_WORKSPACES.md`](V3_1_PROJECT_WORKSPACES.md).

---

## 1. Mission packs

A *mission pack* is a JSON document that bundles one or
more missions for sharing:

```json
{
  "schema_version": 1,
  "pack_name": "Solar System Tours",
  "description": "Curated set of inner / outer solar tours.",
  "created_at_iso": "2026-05-10T12:00:00",
  "missions": [
    { ...full Mission JSON v1.4... },
    { ...full Mission JSON v1.4... }
  ]
}
```

The pack format **wraps** the v1.4 `Mission.to_dict()`
output verbatim. No information is lost; the importer
turns each mission dict back into a `Mission` object via
`Mission.from_dict`.

## 2. Producing a pack

```python
from project import build_pack_from_missions, write_pack

pack = build_pack_from_missions(
    missions=[mission_a, mission_b, mission_c],
    pack_name="My Voyages",
    description="Pack for the Voyager cinematic.",
)
write_pack(pack, "/path/to/voyages.unavpack.json")
```

Packs are plain JSON — version-control them in git, share
them via email, post them on a site. They contain no
catalog data, just mission metadata + waypoints.

## 3. Importing a pack (duplicate-safe)

```python
from project import read_pack, import_pack
from voyage import Mission

pack = read_pack("/path/to/voyages.unavpack.json")
report = import_pack(
    pack,
    existing_ids=manager.list_ids(),
    mission_factory=Mission.from_dict,
    create_callback=manager.create,
    update_callback=manager.update,
    on_collision="rename",  # or "skip", "replace"
)
print(report.short_summary())
```

`import_pack` is **storage-agnostic**: callbacks tell it
how to persist a brand-new mission and how to overwrite
an existing one. The same call works against the legacy
`MissionManager` and against a workspace-aware storage
layer.

## 4. Collision strategies

`on_collision` controls behaviour when an imported
mission's `mission_id` already exists locally:

* **`"skip"`** — leave the existing mission alone, log
  the collision in `ImportReport.skipped`.
* **`"replace"`** — overwrite the existing mission.
  Requires `update_callback`.
* **`"rename"`** — assign a fresh `mission_id` (e.g.
  `X-2`, `X-3`, …, falling back to a uuid suffix) and
  create the imported mission. Original is untouched.

## 5. Reusable missions inside a workspace

A workspace's `missions/` directory holds the project's
canonical missions. The manifest's `missions` list
references them by relative path:

```json
{
  "missions": [
    {
      "mission_id": "voyager-arrival",
      "path": "missions/voyager-arrival.json",
      "title": "Voyager Arrival",
      "tags": ["cinematic", "outer-solar"],
      "notes": "draft 1; needs Saturn beat"
    }
  ]
}
```

Tags + notes are part of the manifest, not the mission
JSON itself, so they don't pollute the v1.4 schema.

## 6. Project-relative references

Mission JSONs ship with absolute object UIDs (e.g.
`gaia:5853498713160606720`); these are dataset-relative,
not file-relative, and don't change when a workspace
moves.

The mission's *file path*, however, lives inside the
workspace. The manifest stores it relative
(`missions/<id>.json`), so moving the workspace to a new
machine doesn't break the references.

## 7. Acceptance + tests

* `test_v31_mission_packs` covers pack
  serialisation, round-trip, importer collision
  strategies, error containment, and the
  `ImportReport` summary.
