"""v3.45 undo-policy tests."""

from __future__ import annotations

import pytest

from c4d_objects.undo_policy import (
    OP_BAKE_TIMELINE,
    OP_BUILD_NAVIGATOR,
    OP_BUILD_OVERLAYS,
    OP_BUILD_VISIBLE_SECTOR,
    OP_CLEAR_TIMELINE,
    OP_REMOVE_VISIBLE_SECTOR,
    UNDO_BITS,
    UNDO_CHANGE,
    UNDO_DELETE,
    UNDO_HIERARCHY,
    UNDO_NEW,
    UNDO_POLICY,
    UNDO_TYPES,
    UndoSession,
    UndoTraceEntry,
    known_operations,
    policy_for,
    resolve_undo_constant,
)


# ---------------------------------------------------------------------------
# Policy table shape
# ---------------------------------------------------------------------------


def test_policy_includes_every_documented_op():
    expected = {
        "build_navigator", "build_visible_sector",
        "remove_visible_sector",
        "build_overlays", "remove_overlays",
        "build_science_layers", "remove_science_layers",
        "build_mission_preview", "remove_mission_preview",
        "build_debug_cone", "remove_debug_cone",
        "bake_timeline", "clear_timeline",
        "ensure_project_hierarchy", "cleanup_legacy_roots",
    }
    assert expected.issubset(set(UNDO_POLICY))


def test_policy_for_known_op_returns_tuple():
    pol = policy_for(OP_BUILD_NAVIGATOR)
    assert UNDO_NEW in pol


def test_policy_for_unknown_op_raises():
    with pytest.raises(KeyError):
        policy_for("does_not_exist")


def test_known_operations_sorted():
    ops = known_operations()
    assert ops == sorted(ops)


def test_undo_types_constant_complete():
    assert UNDO_NEW in UNDO_TYPES
    assert UNDO_DELETE in UNDO_TYPES
    assert UNDO_CHANGE in UNDO_TYPES
    assert UNDO_BITS in UNDO_TYPES
    assert UNDO_HIERARCHY in UNDO_TYPES


def test_every_policy_type_is_a_known_undo_type():
    for op, types in UNDO_POLICY.items():
        for t in types:
            assert t in UNDO_TYPES, f"op {op!r} uses unknown undo type {t!r}"


# ---------------------------------------------------------------------------
# resolve_undo_constant
# ---------------------------------------------------------------------------


def test_resolve_outside_c4d_returns_token():
    """Outside Cinema 4D, the token is returned
    verbatim so tests can assert it directly."""
    assert resolve_undo_constant(UNDO_NEW) == UNDO_NEW


def test_resolve_unknown_returns_token():
    assert resolve_undo_constant("custom") == "custom"


# ---------------------------------------------------------------------------
# UndoSession lifecycle
# ---------------------------------------------------------------------------


def test_session_constructs_for_known_op():
    s = UndoSession(doc=None, op=OP_BUILD_NAVIGATOR)
    assert s.operation == OP_BUILD_NAVIGATOR
    assert s.is_open is False


def test_session_rejects_unknown_op():
    with pytest.raises(KeyError):
        UndoSession(doc=None, op="not_a_real_op")


def test_session_open_close_via_context():
    s = UndoSession(doc=None, op=OP_BUILD_NAVIGATOR)
    with s:
        assert s.is_open is True
    assert s.is_open is False


def test_session_records_trace_entries():
    s = UndoSession(doc=None, op=OP_BUILD_NAVIGATOR)
    with s:
        s.add(None, undo_type=UNDO_NEW, object_label="Navigator")
    assert len(s.trace) == 1
    assert s.trace[0].operation == OP_BUILD_NAVIGATOR
    assert s.trace[0].undo_type == UNDO_NEW
    assert s.trace[0].object_label == "Navigator"


def test_session_add_outside_context_raises():
    s = UndoSession(doc=None, op=OP_BUILD_NAVIGATOR)
    with pytest.raises(RuntimeError):
        s.add(None, undo_type=UNDO_NEW)


def test_session_add_with_wrong_type_raises():
    s = UndoSession(doc=None, op=OP_BUILD_NAVIGATOR)
    with s:
        with pytest.raises(ValueError):
            s.add(None, undo_type=UNDO_DELETE)


def test_session_records_multiple_entries():
    s = UndoSession(doc=None, op=OP_BUILD_OVERLAYS)
    with s:
        s.add(None, undo_type=UNDO_NEW, object_label="grid")
        s.add(None, undo_type=UNDO_NEW, object_label="ecliptic")
    assert len(s.trace) == 2


def test_session_records_composite_op():
    """Composite ops like ``ensure_project_hierarchy``
    accept multiple undo types."""
    from c4d_objects.undo_policy import OP_ENSURE_PROJECT_HIERARCHY
    s = UndoSession(doc=None, op=OP_ENSURE_PROJECT_HIERARCHY)
    with s:
        s.add(None, undo_type=UNDO_NEW, object_label="Project")
        s.add(None, undo_type=UNDO_BITS, object_label="legacy")
    assert s.covered_types() == (UNDO_NEW, UNDO_BITS)


def test_session_covered_types_dedupes():
    s = UndoSession(doc=None, op=OP_BUILD_VISIBLE_SECTOR)
    with s:
        s.add(None, undo_type=UNDO_NEW, object_label="a")
        s.add(None, undo_type=UNDO_NEW, object_label="b")
    assert s.covered_types() == (UNDO_NEW,)


def test_session_policy_satisfied_when_no_records():
    s = UndoSession(doc=None, op=OP_BUILD_NAVIGATOR)
    with s:
        pass  # no-op
    assert s.is_policy_satisfied()


def test_session_policy_satisfied_when_records_match():
    s = UndoSession(doc=None, op=OP_BUILD_NAVIGATOR)
    with s:
        s.add(None, undo_type=UNDO_NEW)
    assert s.is_policy_satisfied()


# ---------------------------------------------------------------------------
# UndoTraceEntry
# ---------------------------------------------------------------------------


def test_trace_entry_short_summary():
    e = UndoTraceEntry(
        operation="build_navigator",
        undo_type="new_object",
        object_label="Navigator",
    )
    assert "build_navigator" in e.short_summary()
    assert "Navigator" in e.short_summary()


def test_trace_entry_summary_without_label():
    e = UndoTraceEntry(
        operation="bake_timeline", undo_type="change_object",
    )
    assert "bake_timeline" in e.short_summary()


# ---------------------------------------------------------------------------
# Bake / clear shape
# ---------------------------------------------------------------------------


def test_bake_timeline_uses_undo_change():
    assert UNDO_CHANGE in policy_for(OP_BAKE_TIMELINE)


def test_clear_timeline_uses_undo_change():
    assert UNDO_CHANGE in policy_for(OP_CLEAR_TIMELINE)


def test_remove_visible_sector_uses_undo_delete():
    assert UNDO_DELETE in policy_for(OP_REMOVE_VISIBLE_SECTOR)
