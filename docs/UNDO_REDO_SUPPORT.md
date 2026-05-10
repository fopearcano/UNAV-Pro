# UNAV Pro — Undo / Redo Support

How v3.45 standardises Cinema 4D undo behaviour
across every UNAV builder.

For the workflow overview see
[`V3_45_NATIVE_C4D_WORKFLOW.md`](V3_45_NATIVE_C4D_WORKFLOW.md).

---

## 1. The contract

Every scene mutation UNAV performs must:

1. Be wrapped between `doc.StartUndo()` and
   `doc.EndUndo()` so it counts as **one** user-
   visible undo step.
2. Call `doc.AddUndo(c4d.UNDOTYPE_*, obj)` for
   every object the host needs to roll back.
3. End with a `c4d.EventAdd()` so the editor
   refreshes.

Pre-v3.45 each builder open-coded this pattern.
v3.45 introduces `unav_pro/c4d_objects/undo_policy.py`
which:

* declares every UNAV operation in one place
  (`UNDO_POLICY` table);
* provides an `UndoSession` context manager that
  enforces the wrapper contract;
* offers a `UndoTraceEntry` test surface so unit
  tests assert "this operation would record one
  UNDO_NEW" without booting Cinema 4D.

## 2. The policy table

`UNDO_POLICY` maps a stable operation token to the
expected undo types. v3.45 ships 15 operations:

| Op | Expected UNDOTYPE(s) |
| --- | --- |
| `build_navigator` | `UNDO_NEW` |
| `build_visible_sector` | `UNDO_NEW` |
| `remove_visible_sector` | `UNDO_DELETE` |
| `build_overlays` | `UNDO_NEW` |
| `remove_overlays` | `UNDO_DELETE` |
| `build_science_layers` | `UNDO_NEW` |
| `remove_science_layers` | `UNDO_DELETE` |
| `build_mission_preview` | `UNDO_NEW` |
| `remove_mission_preview` | `UNDO_DELETE` |
| `build_debug_cone` | `UNDO_NEW` |
| `remove_debug_cone` | `UNDO_DELETE` |
| `bake_timeline` | `UNDO_CHANGE` |
| `clear_timeline` | `UNDO_CHANGE` |
| `ensure_project_hierarchy` | `UNDO_NEW`, `UNDO_BITS` |
| `cleanup_legacy_roots` | `UNDO_DELETE`, `UNDO_BITS` |

Adding a new operation is a code change: bump the
table, add the test that asserts the policy is
respected, ship.

## 3. UndoSession

```python
from c4d_objects.undo_policy import (
    OP_BUILD_NAVIGATOR, UNDO_NEW, UndoSession,
)

with UndoSession(doc, op=OP_BUILD_NAVIGATOR) as s:
    nav = c4d.BaseObject(c4d.Onull)
    nav.SetName("UNAV_Navigator")
    doc.InsertObject(nav)
    s.add(nav, undo_type=UNDO_NEW, object_label="UNAV_Navigator")
```

The session:

* opens the undo block on `__enter__`;
* validates each `add(...)` against the policy
  (raises if the type isn't in the operation's
  expected set);
* calls `doc.AddUndo(...)` with the resolved
  `c4d.UNDOTYPE_*` constant;
* closes the undo block + emits `EventAdd` on
  `__exit__`;
* records `UndoTraceEntry` records so tests +
  diagnostics can inspect what would happen.

## 4. Outside Cinema 4D

When `c4d` is not importable (CLI, test suite),
`UndoSession` degrades to a pure record collector:

```python
with UndoSession(doc=None, op=OP_BUILD_NAVIGATOR) as s:
    s.add(None, undo_type=UNDO_NEW, object_label="fake")
print(s.trace)   # → [UndoTraceEntry('build_navigator', 'new_object', 'fake')]
```

This makes the v3.45 builders fully unit-testable
without a Cinema 4D host.

## 5. Composite operations

Some operations record multiple undo types:

* `ensure_project_hierarchy` creates new objects
  (`UNDO_NEW`) and may flip the `UNDO_BITS` slot
  on legacy nulls being re-parented.
* `cleanup_legacy_roots` deletes
  (`UNDO_DELETE`) and re-parents (`UNDO_BITS`).

The session validates each `add(...)` call against
the *full set* of allowed types, not just one.

## 6. Recovering from an undo

After Ctrl-Z:

* The host removes the rolled-back objects from the
  document.
* UNAV's in-memory caches (the v3.0 chunk-reuse
  cache, the metadata-lookup default, the dataset-
  registry pointer) are **not** automatically
  invalidated — they don't reference the rolled-
  back objects directly.
* On the next `Sync Visible Sector`, the v3.0
  partial-rebuild planners detect the missing
  scene objects and rebuild them.

If an artist suspects stale state, the v3.4 reset
tools (`Diagnostics → Clear Cache References` +
`Rebuild Scene Hierarchy`) drop everything cleanly.

## 7. Anti-patterns

* **Don't open nested undo blocks.** Cinema 4D
  doesn't nest. If a builder needs to call another
  builder, the *outer* builder owns the undo
  session and the inner builder accepts a session
  parameter (or runs without one when called
  standalone).
* **Don't forget `EventAdd`.** Without it the
  editor doesn't refresh until the next user
  interaction. The v3.45 `UndoSession` emits one
  on successful exit.
* **Don't `AddUndo` after the EndUndo.** Cinema
  4D drops the record silently. The session's
  `add(...)` raises if called outside the
  context.

## 8. Tests

* `test_v345_undo_policy` covers the policy table
  shape, `UndoSession` lifecycle, validation of
  unknown / wrong undo types, trace recording,
  outside-host degradation.
