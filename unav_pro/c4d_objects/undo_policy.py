"""v3.45 undo policy + UndoSession.

Cinema 4D's undo subsystem is a sequence of typed
records the host stores in the document's undo stack.
Each scene mutation must:

1. Be wrapped between ``doc.StartUndo()`` and
   ``doc.EndUndo()`` (the boundary defines a single
   user-visible undo step).
2. Call ``doc.AddUndo(UNDOTYPE_*, obj)`` for **every**
   change the host needs to roll back.
3. End with a ``c4d.EventAdd()`` so the editor refreshes.

Pre-v3.45 every UNAV builder open-coded this pattern.
v3.45 centralises the policy:

* ``UNDO_POLICY`` is a declarative table mapping every
  named UNAV operation to the UNDOTYPE it must record.
  Tests assert the table has full coverage.
* ``UndoSession`` is a tiny context manager that wraps
  ``StartUndo`` / ``EndUndo`` / ``EventAdd`` so the
  builder bodies just call ``session.add(obj, type=…)``.
* ``UndoTraceEntry`` lets tests + diagnostics record
  what an operation *would* do without touching Cinema
  4D.

This module is pure stdlib outside the host. Inside
Cinema 4D the helpers translate to the documented
``c4d.UNDOTYPE_*`` constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False


# ---------------------------------------------------------------------------
# Undo type tokens (mirror c4d.UNDOTYPE_* outside the host)
# ---------------------------------------------------------------------------


#: Stable symbolic names for undo types. Inside Cinema
#: 4D each maps to the matching ``c4d.UNDOTYPE_*``
#: constant; outside the host the strings are used
#: directly so tests can assert them without faking
#: the c4d module.
UNDO_NEW: str = "new_object"
UNDO_DELETE: str = "delete_object"
UNDO_CHANGE: str = "change_object"
UNDO_BITS: str = "bits_change"
UNDO_HIERARCHY: str = "hierarchy_change"

UNDO_TYPES: Tuple[str, ...] = (
    UNDO_NEW, UNDO_DELETE, UNDO_CHANGE,
    UNDO_BITS, UNDO_HIERARCHY,
)


def resolve_undo_constant(token: str) -> Any:
    """Translate a v3.45 symbolic token into the
    matching ``c4d.UNDOTYPE_*`` constant when running
    inside Cinema 4D.

    Outside the host, the token is returned verbatim so
    tests + diagnostics can assert what the operation
    *would* record.
    """
    if not _C4D_AVAILABLE:
        return token
    mapping = {
        UNDO_NEW: getattr(c4d, "UNDOTYPE_NEWOBJ", token),
        UNDO_DELETE: getattr(c4d, "UNDOTYPE_DELETE", token),
        UNDO_CHANGE: getattr(c4d, "UNDOTYPE_CHANGE", token),
        UNDO_BITS: getattr(c4d, "UNDOTYPE_BITS", token),
        UNDO_HIERARCHY: getattr(c4d, "UNDOTYPE_HIERARCHY_PSR", token),
    }
    return mapping.get(token, token)


# ---------------------------------------------------------------------------
# Operation policy table
# ---------------------------------------------------------------------------


#: Stable symbolic names for the v3.45 scene-mutating
#: operations. The dialog calls these by name; the
#: builders look the names up in ``UNDO_POLICY`` to
#: discover what undo records they must add.
OP_BUILD_NAVIGATOR: str = "build_navigator"
OP_BUILD_VISIBLE_SECTOR: str = "build_visible_sector"
OP_REMOVE_VISIBLE_SECTOR: str = "remove_visible_sector"
OP_BUILD_OVERLAYS: str = "build_overlays"
OP_REMOVE_OVERLAYS: str = "remove_overlays"
OP_BUILD_SCIENCE_LAYERS: str = "build_science_layers"
OP_REMOVE_SCIENCE_LAYERS: str = "remove_science_layers"
OP_BUILD_MISSION_PREVIEW: str = "build_mission_preview"
OP_REMOVE_MISSION_PREVIEW: str = "remove_mission_preview"
OP_BUILD_DEBUG_CONE: str = "build_debug_cone"
OP_REMOVE_DEBUG_CONE: str = "remove_debug_cone"
OP_BAKE_TIMELINE: str = "bake_timeline"
OP_CLEAR_TIMELINE: str = "clear_timeline"
OP_ENSURE_PROJECT_HIERARCHY: str = "ensure_project_hierarchy"
OP_CLEANUP_LEGACY_ROOTS: str = "cleanup_legacy_roots"


#: Map of operation → expected undo types. Tests assert
#: the table includes every operation the dialog calls;
#: the builders read it to validate self-consistency.
UNDO_POLICY: Dict[str, Tuple[str, ...]] = {
    OP_BUILD_NAVIGATOR: (UNDO_NEW,),
    OP_BUILD_VISIBLE_SECTOR: (UNDO_NEW,),
    OP_REMOVE_VISIBLE_SECTOR: (UNDO_DELETE,),
    OP_BUILD_OVERLAYS: (UNDO_NEW,),
    OP_REMOVE_OVERLAYS: (UNDO_DELETE,),
    OP_BUILD_SCIENCE_LAYERS: (UNDO_NEW,),
    OP_REMOVE_SCIENCE_LAYERS: (UNDO_DELETE,),
    OP_BUILD_MISSION_PREVIEW: (UNDO_NEW,),
    OP_REMOVE_MISSION_PREVIEW: (UNDO_DELETE,),
    OP_BUILD_DEBUG_CONE: (UNDO_NEW,),
    OP_REMOVE_DEBUG_CONE: (UNDO_DELETE,),
    OP_BAKE_TIMELINE: (UNDO_CHANGE,),
    OP_CLEAR_TIMELINE: (UNDO_CHANGE,),
    OP_ENSURE_PROJECT_HIERARCHY: (UNDO_NEW, UNDO_BITS),
    OP_CLEANUP_LEGACY_ROOTS: (UNDO_DELETE, UNDO_BITS),
}


def policy_for(op: str) -> Tuple[str, ...]:
    """Return the expected undo type tuple for ``op``.

    Raises ``KeyError`` for unknown operations so a
    typo at the call site fails fast at test time."""
    return UNDO_POLICY[op]


def known_operations() -> List[str]:
    """List of every documented operation, sorted."""
    return sorted(UNDO_POLICY.keys())


# ---------------------------------------------------------------------------
# Trace entry (test + diagnostics surface)
# ---------------------------------------------------------------------------


@dataclass
class UndoTraceEntry:
    """One simulated undo record. Tests use these to
    assert "build_navigator added one UNDO_NEW" without
    needing a real Cinema 4D document.

    The c4d-bound ``UndoSession`` records these
    alongside calling the real ``doc.AddUndo`` so a
    diagnostics panel can render the trace after the
    fact.
    """

    operation: str
    undo_type: str
    object_label: str = ""

    def short_summary(self) -> str:
        bits = [f"{self.operation}:{self.undo_type}"]
        if self.object_label:
            bits.append(self.object_label)
        return " · ".join(bits)


# ---------------------------------------------------------------------------
# UndoSession context manager
# ---------------------------------------------------------------------------


class UndoSession:
    """Context manager that wraps ``StartUndo`` /
    ``EndUndo`` / ``EventAdd`` and validates each
    ``add(obj, type=…)`` call against the v3.45
    policy.

    Usage::

        with UndoSession(doc, op=OP_BUILD_NAVIGATOR) as s:
            null = c4d.BaseObject(c4d.Onull)
            doc.InsertObject(null)
            s.add(null, undo_type=UNDO_NEW)

    The session also collects ``UndoTraceEntry`` records
    so tests can inspect what would happen without
    Cinema 4D loaded.

    Outside Cinema 4D the session degrades to a pure
    record collector — useful for unit tests of
    builders that construct dummy objects.
    """

    def __init__(
        self,
        doc: Any,
        *,
        op: str,
        require_event_add: bool = True,
    ) -> None:
        if op not in UNDO_POLICY:
            raise KeyError(f"unknown undo operation: {op!r}")
        self._doc = doc
        self._op = op
        self._require_event_add = bool(require_event_add)
        self._trace: List[UndoTraceEntry] = []
        self._open: bool = False
        self._observed_types: List[str] = []

    # ---------------------------------------------------- properties
    @property
    def operation(self) -> str:
        return self._op

    @property
    def trace(self) -> List[UndoTraceEntry]:
        return list(self._trace)

    @property
    def is_open(self) -> bool:
        return self._open

    # ---------------------------------------------------- context
    def __enter__(self) -> "UndoSession":
        self._open = True
        if self._doc is not None and _C4D_AVAILABLE:
            try:
                self._doc.StartUndo()
            except Exception:  # noqa: BLE001 — host boundary
                pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._open = False
        if self._doc is not None and _C4D_AVAILABLE:
            try:
                self._doc.EndUndo()
            except Exception:  # noqa: BLE001
                pass
            if exc_type is None and self._require_event_add:
                try:
                    c4d.EventAdd()
                except Exception:  # noqa: BLE001
                    pass

    # ---------------------------------------------------- mutation
    def add(
        self,
        obj: Any,
        *,
        undo_type: str,
        object_label: str = "",
    ) -> UndoTraceEntry:
        """Record one undo entry. Validates the type
        against the policy; raises if the type isn't
        in the documented set for this operation."""
        if not self._open:
            raise RuntimeError(
                "UndoSession.add() called outside the context"
            )
        expected = UNDO_POLICY[self._op]
        if undo_type not in expected:
            raise ValueError(
                f"undo_type {undo_type!r} not allowed for "
                f"op {self._op!r}; expected one of {expected}"
            )
        self._observed_types.append(undo_type)
        entry = UndoTraceEntry(
            operation=self._op,
            undo_type=undo_type,
            object_label=str(object_label or ""),
        )
        self._trace.append(entry)
        if self._doc is not None and _C4D_AVAILABLE:
            try:
                self._doc.AddUndo(
                    resolve_undo_constant(undo_type), obj,
                )
            except Exception:  # noqa: BLE001
                pass
        return entry

    # ---------------------------------------------------- validation
    def covered_types(self) -> Tuple[str, ...]:
        """Return the unique undo types observed during
        this session, in insertion order. Tests use this
        to assert the session matched the policy."""
        seen: List[str] = []
        for t in self._observed_types:
            if t not in seen:
                seen.append(t)
        return tuple(seen)

    def is_policy_satisfied(self) -> bool:
        """True iff at least one of the expected undo
        types was recorded. Empty sessions count as
        satisfied — a no-op operation has no undo records
        to add."""
        if not self._trace:
            return True
        expected = set(UNDO_POLICY[self._op])
        observed = set(self._observed_types)
        return bool(observed & expected)
