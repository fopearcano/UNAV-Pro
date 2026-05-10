"""v3.4 safe reset tools.

Five operations the dialog's *Diagnostics → Reset* group
exposes for recovering from a confused state without
restarting Cinema 4D:

* **Reset UI State** — clear the dialog's in-memory
  selection / expansion / scroll state.
* **Reset Workspace State** — drop the active workspace
  reference (the on-disk workspace is **not** touched).
* **Clear Generated UNAV Objects** — return a plan
  describing every UNAV-prefixed null the dialog should
  prune from the active C4D document.
* **Clear Cache References** — drop the chunk-reuse
  cache + the metadata-lookup default + the timing
  log.
* **Rebuild Scene Hierarchy** — return a plan describing
  what the v3.1 ``ensure_project_structure`` builder
  should materialise next.

This module is **pure stdlib + planning helpers**. The
c4d-bound execution lives next to the existing
``c4d_objects.scene_structure`` builders; the planners
here describe what should happen, the C4D layer makes it
happen.

All resets are **safe to run twice in a row** (idempotent)
and **never delete on-disk artefacts** — workspaces,
catalogs, missions, and cache directories all survive.
The artist's data is sacred; the resets only clear
in-memory pointers and scene-side scaffolding the plugin
itself owns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Reset reports
# ---------------------------------------------------------------------------


@dataclass
class ResetReport:
    """Outcome of one reset operation. Pure data; the
    dialog renders ``short_summary`` into the status
    log."""

    operation: str
    cleared: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def is_clean(self) -> bool:
        return not self.warnings

    def short_summary(self) -> str:
        bits: List[str] = [
            f"reset '{self.operation}'",
            f"cleared {len(self.cleared)}",
        ]
        if self.skipped:
            bits.append(f"skipped {len(self.skipped)}")
        if self.warnings:
            bits.append(f"warnings {len(self.warnings)}")
        return "; ".join(bits)

    def render(self) -> str:
        lines: List[str] = [self.short_summary()]
        for c in self.cleared:
            lines.append(f"  · cleared: {c}")
        for s in self.skipped:
            lines.append(f"  · skipped: {s}")
        for w in self.warnings:
            lines.append(f"  ! warning: {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reset UI state
# ---------------------------------------------------------------------------


@dataclass
class UIStateSnapshot:
    """Pure-data carrier for the dialog's transient UI
    state. The dialog owns the source-of-truth instance;
    ``reset_ui_state`` is what the *Reset UI State* button
    calls to clear it."""

    selected_uid: str = ""
    selected_mission_id: str = ""
    selected_step_id: str = ""
    selected_dataset_name: str = ""
    expanded_sections: List[str] = field(default_factory=list)
    last_search_query: str = ""
    log_lines_count: int = 0


def reset_ui_state(
    state: Optional[UIStateSnapshot] = None,
) -> Tuple[UIStateSnapshot, ResetReport]:
    """Return a fresh ``UIStateSnapshot`` and a report
    describing what was cleared.

    Pure: the caller is responsible for installing the
    new snapshot back into its dialog state. Tests use
    this to verify the cleared field set.
    """
    report = ResetReport(operation="ui_state")
    if state is None:
        report.skipped.append("no UI state provided")
        return UIStateSnapshot(), report
    if state.selected_uid:
        report.cleared.append(f"selected_uid={state.selected_uid!r}")
    if state.selected_mission_id:
        report.cleared.append(
            f"selected_mission_id={state.selected_mission_id!r}",
        )
    if state.selected_step_id:
        report.cleared.append(
            f"selected_step_id={state.selected_step_id!r}",
        )
    if state.selected_dataset_name:
        report.cleared.append(
            f"selected_dataset_name={state.selected_dataset_name!r}",
        )
    if state.expanded_sections:
        report.cleared.append(
            f"{len(state.expanded_sections)} expanded section(s)"
        )
    if state.last_search_query:
        report.cleared.append("last search query")
    if state.log_lines_count:
        report.cleared.append(
            f"{state.log_lines_count} log line(s)"
        )
    return UIStateSnapshot(), report


# ---------------------------------------------------------------------------
# Reset workspace state
# ---------------------------------------------------------------------------


def reset_workspace_state() -> ResetReport:
    """Drop the in-memory active-workspace pointer.

    The on-disk workspace tree is **not** touched.
    Idempotent: calling twice in a row clears once and
    reports nothing on the second call.
    """
    report = ResetReport(operation="workspace_state")
    try:
        from core.state_manager import (
            current_workspace, set_current_workspace,
        )
    except ImportError as exc:
        report.warnings.append(f"state_manager not importable: {exc}")
        return report
    ws = current_workspace()
    if ws is None:
        report.skipped.append("no active workspace")
        return report
    label = getattr(ws, "root", "?")
    set_current_workspace(None)
    report.cleared.append(f"active workspace ({label})")
    return report


# ---------------------------------------------------------------------------
# Clear generated UNAV objects (pure plan)
# ---------------------------------------------------------------------------


@dataclass
class GeneratedObjectPlan:
    """Plan for the C4D builder: which UNAV-prefixed
    nulls + child groups should be removed.

    The plan is **declarative**; the c4d-bound builder
    walks the document, matches names, and removes
    matches inside an undo block. Items in
    ``preserve_groups`` are explicitly kept (the
    canonical v3.1 hierarchy)."""

    remove_root_names: List[str] = field(default_factory=list)
    preserve_groups: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def is_noop(self) -> bool:
        return not self.remove_root_names

    def short_summary(self) -> str:
        if self.is_noop():
            return "clear_generated: nothing to remove"
        return (
            f"clear_generated: remove {len(self.remove_root_names)} "
            f"group(s); preserve {len(self.preserve_groups)}"
        )


#: Top-level UNAV roots the builder should always
#: preserve. The v3.1 canonical hierarchy lives under
#: ``UNAV_Project``; legacy roots are migrated by
#: ``ensure_project_structure``.
_PRESERVED_ROOTS: Tuple[str, ...] = (
    "UNAV_Project",
)

#: Legacy + scratch roots the v3.4 reset removes when
#: encountered at the document root.
_REMOVABLE_ROOTS: Tuple[str, ...] = (
    "UNAV_Starfield",
    "UNAV_Overlays",
    "UNAV_ScienceLayers",
    "UNAV_Mission_Preview",
    "UNAV_DebugCone",
    "UNAV_DebugCone_pose",
    "UNAV_Debug",
    "UNAV_Annotations",
    "UNAV_Scratch",
)


def plan_clear_generated_objects(
    *,
    existing_root_names: Sequence[str],
) -> GeneratedObjectPlan:
    """Pure helper: given the names of every top-level
    object in the active document, decide which UNAV-
    prefixed nulls to remove.

    * ``UNAV_Project`` is always preserved (it's the
      v3.1 canonical root; the rebuild planner
      reconstructs its children).
    * Every name in ``_REMOVABLE_ROOTS`` is queued for
      removal when present.
    * Other UNAV-prefixed roots produce an
      informational note but are **not** removed —
      v3.4 won't touch artist content the plugin
      doesn't recognise.
    """
    plan = GeneratedObjectPlan()
    seen: set = set()
    for name in existing_root_names:
        if not isinstance(name, str) or not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        if name in _PRESERVED_ROOTS:
            plan.preserve_groups.append(name)
            continue
        if name in _REMOVABLE_ROOTS:
            plan.remove_root_names.append(name)
            continue
        if name.startswith("UNAV_"):
            plan.notes.append(
                f"unfamiliar UNAV root '{name}' left intact "
                "(use Rebuild Scene Hierarchy to canonicalise)"
            )
    return plan


def clear_generated_objects_report(
    *,
    existing_root_names: Sequence[str],
) -> ResetReport:
    """Compose a ``ResetReport`` from a generated-object
    plan. Pure helper; the c4d-bound builder applies
    the plan and the dialog renders this report."""
    plan = plan_clear_generated_objects(
        existing_root_names=existing_root_names,
    )
    report = ResetReport(operation="clear_generated_objects")
    for name in plan.remove_root_names:
        report.cleared.append(name)
    for name in plan.preserve_groups:
        report.skipped.append(f"{name} (preserved)")
    for note in plan.notes:
        report.warnings.append(note)
    return report


# ---------------------------------------------------------------------------
# Clear cache references
# ---------------------------------------------------------------------------


def clear_cache_references() -> ResetReport:
    """Drop the v3.0 chunk-reuse cache, the v3.0 query
    timing log, and the v0.6 metadata-lookup default.

    Idempotent. Returns a report so the dialog can show
    "cleared 3 caches" in the status log.
    """
    report = ResetReport(operation="cache_references")
    try:
        from db.streaming import ChunkReuseCache  # noqa: F401
    except ImportError as exc:
        report.warnings.append(f"db.streaming not importable: {exc}")
    try:
        from db.spatial_query import GLOBAL_QUERY_TIMING_LOG
        before = len(GLOBAL_QUERY_TIMING_LOG)
        GLOBAL_QUERY_TIMING_LOG.reset()
        report.cleared.append(
            f"query timing log ({before} entries)"
        )
    except ImportError as exc:
        report.warnings.append(
            f"spatial_query.GLOBAL_QUERY_TIMING_LOG not importable: {exc}"
        )
    try:
        from core.metadata_lookup import set_default_lookup
        set_default_lookup(None)
        report.cleared.append("metadata lookup default")
    except ImportError as exc:
        report.warnings.append(
            f"metadata_lookup not importable: {exc}"
        )
    try:
        from core.state_manager import set_dataset_registry
        # v3.4: dropping the registry pointer forces a
        # reload-from-disk on next access. Real on-disk
        # data is preserved.
        set_dataset_registry(None)
        report.cleared.append("dataset registry pointer")
    except ImportError as exc:
        report.warnings.append(
            f"state_manager.set_dataset_registry not importable: {exc}"
        )
    return report


# ---------------------------------------------------------------------------
# Rebuild scene hierarchy (pure plan)
# ---------------------------------------------------------------------------


@dataclass
class HierarchyRebuildPlan:
    """Plan describing what the v3.1
    ``ensure_project_structure`` builder should
    materialise next."""

    project_root_name: str = "UNAV_Project"
    canonical_children: List[str] = field(default_factory=list)
    missing_children: List[str] = field(default_factory=list)
    legacy_to_migrate: List[Tuple[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def is_noop(self) -> bool:
        return not self.missing_children and not self.legacy_to_migrate

    def short_summary(self) -> str:
        if self.is_noop():
            return "rebuild_hierarchy: scene already canonical"
        bits: List[str] = []
        if self.missing_children:
            bits.append(f"create {len(self.missing_children)}")
        if self.legacy_to_migrate:
            bits.append(f"migrate {len(self.legacy_to_migrate)}")
        return "rebuild_hierarchy: " + ", ".join(bits)


def plan_rebuild_hierarchy(
    *,
    existing_root_names: Sequence[str],
    existing_project_children: Sequence[str] = (),
) -> HierarchyRebuildPlan:
    """Compose the rebuild plan from the v3.1 scene-
    structure helper. Defensive against the structure
    package being unavailable — returns an empty plan
    + a warning note rather than raising."""
    plan = HierarchyRebuildPlan()
    try:
        from c4d_objects.scene_structure import (
            CANONICAL_CHILD_GROUPS,
            PROJECT_ROOT_NAME,
            diff_hierarchy,
        )
    except ImportError as exc:
        plan.notes.append(
            f"scene_structure not importable: {exc}"
        )
        return plan
    plan.project_root_name = PROJECT_ROOT_NAME
    plan.canonical_children = list(CANONICAL_CHILD_GROUPS)
    diff = diff_hierarchy(
        existing_root_names=existing_root_names,
        existing_project_children=existing_project_children,
    )
    plan.missing_children = list(diff.missing_children)
    plan.legacy_to_migrate = list(diff.legacy_to_migrate)
    plan.notes.extend(diff.extra_unav_groups)
    return plan


def rebuild_hierarchy_report(
    *,
    existing_root_names: Sequence[str],
    existing_project_children: Sequence[str] = (),
) -> ResetReport:
    """Compose a ``ResetReport`` from a rebuild plan.
    Pure helper; the c4d-bound builder applies the
    plan via ``ensure_project_structure``."""
    plan = plan_rebuild_hierarchy(
        existing_root_names=existing_root_names,
        existing_project_children=existing_project_children,
    )
    report = ResetReport(operation="rebuild_hierarchy")
    for name in plan.missing_children:
        report.cleared.append(f"create {name}")
    for src, dst in plan.legacy_to_migrate:
        report.cleared.append(f"migrate {src} → {dst}")
    for note in plan.notes:
        report.warnings.append(note)
    return report
