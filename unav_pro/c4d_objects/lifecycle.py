"""v3.45 scene lifecycle planner.

Cinema 4D documents go through a small set of lifecycle
events the plugin must respond to:

* **Open** — a fresh document was loaded (or the user
  hit File → Open). UNAV state should reload from the
  document's sidecar.
* **Close** — the active document is closing. UNAV
  state should be flushed and detached.
* **Switch** — the active document changed (the user
  Cmd-clicked another tab). UNAV state should rebind
  to the new document.
* **Reload** — the plugin itself reloaded (after a
  source-file edit during development). UNAV state
  should be reset and re-discovered from the active
  document.
* **Multi-document** — two documents are open at the
  same time. The state-manager + scene-walker must
  scope every operation to the *active* document so
  edits in one don't leak into the other.

Pre-v3.45 each builder open-coded ``GetActiveDocument``
calls. v3.45 captures the policy as a small set of
**pure planners** the c4d-bound dispatcher consumes.

Pure stdlib; no Cinema 4D imports. The c4d-bound
hook lives in ``unav_pro/unav_plugin.pyp`` and reads
the planners here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------


class LifecycleEvent(str, Enum):
    """The five document lifecycle events UNAV reacts
    to. ``str`` base so dataclass equality + JSON
    serialisation just work."""

    OPENED = "opened"
    CLOSED = "closed"
    SWITCHED = "switched"
    RELOADED = "reloaded"
    SAVED = "saved"


VALID_EVENTS: Tuple[LifecycleEvent, ...] = tuple(LifecycleEvent)


# ---------------------------------------------------------------------------
# Action plan
# ---------------------------------------------------------------------------


@dataclass
class LifecycleActionPlan:
    """What the plugin should do in response to one
    lifecycle event. Pure data; the c4d-bound dispatcher
    walks the booleans + lists and runs each step.

    Determinism: same event + same prior state ⇒ same
    plan, byte for byte.
    """

    event: LifecycleEvent
    rebind_state_manager: bool = False
    reload_workspace: bool = False
    flush_workspace: bool = False
    rediscover_scene_objects: bool = False
    reset_caches: bool = False
    notes: List[str] = field(default_factory=list)

    def is_noop(self) -> bool:
        return not (
            self.rebind_state_manager
            or self.reload_workspace
            or self.flush_workspace
            or self.rediscover_scene_objects
            or self.reset_caches
        )

    def short_summary(self) -> str:
        bits: List[str] = []
        if self.rebind_state_manager:
            bits.append("rebind state-manager")
        if self.reload_workspace:
            bits.append("reload workspace")
        if self.flush_workspace:
            bits.append("flush workspace")
        if self.rediscover_scene_objects:
            bits.append("rediscover scene objects")
        if self.reset_caches:
            bits.append("reset caches")
        prefix = f"[{self.event.value}]"
        if not bits:
            return f"{prefix} no-op"
        return f"{prefix} " + ", ".join(bits)


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


def plan_for_event(
    event: LifecycleEvent,
    *,
    workspace_active: bool = False,
    multi_document_open: bool = False,
) -> LifecycleActionPlan:
    """Pure planner — produces the action plan for one
    event.

    * ``workspace_active`` is True when a v3.1 workspace
      is currently bound to the dialog.
    * ``multi_document_open`` is True when the host has
      more than one document open (drives the
      "rediscover scene objects" flag for switches).
    """
    if event is LifecycleEvent.OPENED:
        plan = LifecycleActionPlan(
            event=event,
            rebind_state_manager=True,
            reload_workspace=workspace_active,
            rediscover_scene_objects=True,
            reset_caches=True,
        )
        plan.notes.append(
            "fresh document opened; reload sidecar state if present"
        )
        return plan
    if event is LifecycleEvent.CLOSED:
        plan = LifecycleActionPlan(
            event=event,
            flush_workspace=workspace_active,
            rebind_state_manager=True,
            reset_caches=True,
        )
        plan.notes.append(
            "document closed; flush sidecar + drop in-memory pointers"
        )
        return plan
    if event is LifecycleEvent.SWITCHED:
        plan = LifecycleActionPlan(
            event=event,
            rebind_state_manager=True,
            rediscover_scene_objects=multi_document_open,
            reset_caches=True,
        )
        plan.notes.append(
            "active document switched; rebind to new document"
            + (" (multi-doc)" if multi_document_open else "")
        )
        return plan
    if event is LifecycleEvent.RELOADED:
        plan = LifecycleActionPlan(
            event=event,
            rebind_state_manager=True,
            reload_workspace=workspace_active,
            rediscover_scene_objects=True,
            reset_caches=True,
        )
        plan.notes.append("plugin reloaded; full state re-bind")
        return plan
    # SAVED: minimal — refresh the workspace's mtime so
    # an external editor noticing the bump knows the
    # plugin owned the write.
    plan = LifecycleActionPlan(event=event)
    if workspace_active:
        plan.notes.append("document saved; workspace mtime refreshed")
    return plan


# ---------------------------------------------------------------------------
# Multi-document scope
# ---------------------------------------------------------------------------


@dataclass
class DocumentScope:
    """One open Cinema 4D document the plugin tracks.

    Identified by ``doc_id`` (a stable hash the c4d-
    bound hook computes from the document path or
    object id). Carries a small per-document state
    bundle the dialog reads when the artist switches
    tabs.
    """

    doc_id: str
    title: str = ""
    is_active: bool = False
    has_unav_state: bool = False
    last_seen_iso: str = ""

    def short_summary(self) -> str:
        marker = "*" if self.is_active else " "
        unav = " [UNAV]" if self.has_unav_state else ""
        return f"{marker} {self.title or self.doc_id}{unav}"


@dataclass
class MultiDocumentReport:
    """Snapshot of the documents the plugin currently
    knows about. The diagnostics panel renders this so
    the artist can confirm "yes, my edits go to the
    Voyager scene, not the Saturn scene."""

    documents: List[DocumentScope] = field(default_factory=list)
    active_doc_id: str = ""

    @property
    def count(self) -> int:
        return len(self.documents)

    def active(self) -> Optional[DocumentScope]:
        for d in self.documents:
            if d.is_active or d.doc_id == self.active_doc_id:
                return d
        return None

    def short_summary(self) -> str:
        if not self.documents:
            return "no documents tracked"
        active = self.active()
        return (
            f"{self.count} document(s) tracked; active: "
            + (active.short_summary() if active else "none")
        )

    def render(self) -> str:
        lines: List[str] = ["Documents:"]
        for d in self.documents:
            lines.append("  " + d.short_summary())
        return "\n".join(lines)


def build_multi_document_report(
    documents: List[DocumentScope],
) -> MultiDocumentReport:
    """Pure helper: validate the document list, mark
    the active document, return the report."""
    rep = MultiDocumentReport()
    seen: set = set()
    active_id = ""
    for doc in documents:
        if not doc.doc_id or doc.doc_id in seen:
            continue
        seen.add(doc.doc_id)
        rep.documents.append(doc)
        if doc.is_active:
            active_id = doc.doc_id
    rep.active_doc_id = active_id
    return rep
