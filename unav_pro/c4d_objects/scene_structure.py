"""v3.1 standardised scene hierarchy.

UNAV's pre-v3.1 builders sprinkled scene-root nulls
opportunistically:

* ``UNAV_Starfield`` (v0.1) — point cloud + visible sector.
* ``UNAV_Overlays`` (v2.0) — procedural overlays.
* ``UNAV_ScienceLayers`` (v2.1) — science layers.
* ``UNAV_DebugCone`` (v0.6) — debug visualisation.
* ``UNAV_Mission_Preview`` (v1.4) — mission preview.

v3.1 declares the **canonical hierarchy** so production
scenes look the same across artists. The standard root is
``UNAV_Project`` containing six well-known children:

::

    UNAV_Project                       (single project root)
    ├── UNAV_Navigation                 (the navigator + its targets)
    ├── UNAV_VisibleSector              (materialised point set)
    ├── UNAV_Overlays                   (procedural overlays)
    ├── UNAV_ScienceLayers              (science layers)
    ├── UNAV_Missions                   (mission previews + voyages)
    └── UNAV_Debug                      (debug helpers; cone, etc.)

Two layers:

1. **Pure planning helpers** (``HierarchyPlan``,
   ``plan_hierarchy``, ``HierarchyNode``). Stdlib-only;
   describe what should be in the scene without touching
   Cinema 4D.
2. **C4D-bound builders** (``ensure_project_structure``,
   ``cleanup_project_structure``). Materialise the
   hierarchy under the scene's root document. Raise
   ``RuntimeError`` outside Cinema 4D.

The pure layer is what tests exercise; the c4d-bound
layer is a thin wrapper that translates the plan into
``BaseObject`` calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False


# ---------------------------------------------------------------------------
# Canonical names
# ---------------------------------------------------------------------------


PROJECT_ROOT_NAME: str = "UNAV_Project"
NAVIGATION_GROUP_NAME: str = "UNAV_Navigation"
VISIBLE_SECTOR_GROUP_NAME: str = "UNAV_VisibleSector"
OVERLAYS_GROUP_NAME: str = "UNAV_Overlays"
SCIENCE_LAYERS_GROUP_NAME: str = "UNAV_ScienceLayers"
MISSIONS_GROUP_NAME: str = "UNAV_Missions"
DEBUG_GROUP_NAME: str = "UNAV_Debug"

#: The six canonical child group names, in display order.
CANONICAL_CHILD_GROUPS: Tuple[str, ...] = (
    NAVIGATION_GROUP_NAME,
    VISIBLE_SECTOR_GROUP_NAME,
    OVERLAYS_GROUP_NAME,
    SCIENCE_LAYERS_GROUP_NAME,
    MISSIONS_GROUP_NAME,
    DEBUG_GROUP_NAME,
)

#: Legacy v0.1 → v3.0 root names that v3.1 absorbs into the
#: canonical children. The ``ensure_project_structure``
#: helper migrates these in place — existing scenes keep
#: their geometry under the new structure.
LEGACY_ROOT_TO_CANONICAL: Dict[str, str] = {
    "UNAV_Starfield": VISIBLE_SECTOR_GROUP_NAME,
    "UNAV_Overlays": OVERLAYS_GROUP_NAME,
    "UNAV_ScienceLayers": SCIENCE_LAYERS_GROUP_NAME,
}


# ---------------------------------------------------------------------------
# Pure planning helpers
# ---------------------------------------------------------------------------


@dataclass
class HierarchyNode:
    """One node in the standard hierarchy plan. Pure data."""

    name: str
    role: str
    children: List["HierarchyNode"] = field(default_factory=list)


@dataclass
class HierarchyPlan:
    """The full standard plan — one project root + six
    canonical children.

    The ``ensure_project_structure`` builder walks this and
    creates / re-parents nodes to match. The plan itself is
    immutable: tests can compare two plans for equality.
    """

    root: HierarchyNode
    expected_child_groups: Tuple[str, ...] = CANONICAL_CHILD_GROUPS

    def child_names(self) -> List[str]:
        return [c.name for c in self.root.children]

    def has_child(self, name: str) -> bool:
        return any(c.name == name for c in self.root.children)


def plan_hierarchy() -> HierarchyPlan:
    """Return the canonical v3.1 hierarchy plan. Pure
    helper; the c4d-bound builder reads this to decide
    what to create."""
    children = [
        HierarchyNode(name=NAVIGATION_GROUP_NAME, role="navigation"),
        HierarchyNode(name=VISIBLE_SECTOR_GROUP_NAME, role="visible_sector"),
        HierarchyNode(name=OVERLAYS_GROUP_NAME, role="overlays"),
        HierarchyNode(name=SCIENCE_LAYERS_GROUP_NAME, role="science_layers"),
        HierarchyNode(name=MISSIONS_GROUP_NAME, role="missions"),
        HierarchyNode(name=DEBUG_GROUP_NAME, role="debug"),
    ]
    root = HierarchyNode(
        name=PROJECT_ROOT_NAME,
        role="project_root",
        children=children,
    )
    return HierarchyPlan(root=root)


@dataclass
class HierarchyDiff:
    """What the builder would do to bring the scene into
    line with the plan. Pure data; no Cinema 4D types."""

    missing_children: List[str] = field(default_factory=list)
    legacy_to_migrate: List[Tuple[str, str]] = field(default_factory=list)
    extra_unav_groups: List[str] = field(default_factory=list)

    def is_clean(self) -> bool:
        return (
            not self.missing_children
            and not self.legacy_to_migrate
            and not self.extra_unav_groups
        )

    def short_summary(self) -> str:
        if self.is_clean():
            return "scene already matches v3.1 hierarchy"
        parts: List[str] = []
        if self.missing_children:
            parts.append(f"create: {', '.join(self.missing_children)}")
        if self.legacy_to_migrate:
            parts.append(
                "migrate: "
                + ", ".join(
                    f"{src} → {dst}" for src, dst in self.legacy_to_migrate
                )
            )
        if self.extra_unav_groups:
            parts.append(
                "non-canonical UNAV groups: "
                + ", ".join(self.extra_unav_groups)
            )
        return "; ".join(parts)


def diff_hierarchy(
    *,
    existing_root_names: Sequence[str],
    existing_project_children: Sequence[str] = (),
) -> HierarchyDiff:
    """Compute the diff between the scene's current top-
    level UNAV groups and the canonical plan.

    ``existing_root_names`` is every UNAV-prefixed null
    that lives directly under the document root.
    ``existing_project_children`` is what's already inside
    a ``UNAV_Project`` root, if one exists.

    Pure helper; the c4d-bound builder collects the inputs
    and feeds them to this function.
    """
    diff = HierarchyDiff()
    have = set(existing_project_children or ())
    for name in CANONICAL_CHILD_GROUPS:
        if name not in have:
            diff.missing_children.append(name)
    for legacy_name, canonical in LEGACY_ROOT_TO_CANONICAL.items():
        if legacy_name in existing_root_names:
            diff.legacy_to_migrate.append((legacy_name, canonical))
    # Anything UNAV-prefixed that isn't in our known map and
    # isn't a canonical child is "extra" — the dialog logs
    # it but the builder leaves it alone.
    known: set = (
        set(LEGACY_ROOT_TO_CANONICAL)
        | set(CANONICAL_CHILD_GROUPS)
        | {PROJECT_ROOT_NAME}
    )
    for name in existing_root_names:
        if name in known:
            continue
        if not name.startswith("UNAV_"):
            continue
        diff.extra_unav_groups.append(name)
    return diff


def is_canonical_name(name: str) -> bool:
    """True iff ``name`` is one of the canonical hierarchy
    names (root or child group)."""
    return name == PROJECT_ROOT_NAME or name in CANONICAL_CHILD_GROUPS


# ---------------------------------------------------------------------------
# Cleanup planning
# ---------------------------------------------------------------------------


@dataclass
class CleanupPlan:
    """Plan returned by ``plan_cleanup``. Each list lives
    under the canonical project root.

    ``orphan_uids`` is a list of point uids whose driver
    catalog is no longer enabled — the v3.1 dialog can
    show them in a confirmation dialog before pruning."""

    remove_groups: List[str] = field(default_factory=list)
    orphan_uids: List[str] = field(default_factory=list)
    keep_groups: List[str] = field(default_factory=list)

    def is_noop(self) -> bool:
        return not self.remove_groups and not self.orphan_uids


def plan_cleanup(
    *,
    project_children: Sequence[str],
    enabled_dataset_uids: Sequence[str] = (),
    materialised_uids: Sequence[str] = (),
) -> CleanupPlan:
    """Pure helper that decides what cleanup actions the
    builder should take.

    * Any project-child that isn't canonical is queued for
      removal (artist-renamed groups are left alone — only
      *non*-canonical UNAV-prefixed groups land here).
    * Any materialised uid not present in the enabled set
      is queued as an orphan.
    """
    plan = CleanupPlan()
    enabled_set = set(enabled_dataset_uids)
    for name in project_children:
        if name in CANONICAL_CHILD_GROUPS:
            plan.keep_groups.append(name)
        elif name.startswith("UNAV_"):
            plan.remove_groups.append(name)
        # else: artist content; leave alone.
    for uid in materialised_uids:
        if not uid:
            continue
        if uid not in enabled_set:
            plan.orphan_uids.append(uid)
    return plan


# ---------------------------------------------------------------------------
# C4D-bound builders
# ---------------------------------------------------------------------------


def _require_c4d() -> None:
    if not _C4D_AVAILABLE:
        raise RuntimeError(
            "scene_structure: this code path requires Cinema 4D; "
            "use the pure-Python helpers (plan_hierarchy, "
            "diff_hierarchy) outside the host."
        )


def _find_child_by_name(
    parent: "c4d.BaseObject", name: str,
) -> Optional["c4d.BaseObject"]:
    """Walk immediate children of ``parent`` and return the
    first whose ``GetName()`` matches. Tolerates the half-
    torn-down nodes the v1.7 defensive walk handles."""
    _require_c4d()
    child = parent.GetDown()
    while child is not None:
        nxt = child.GetNext()
        try:
            if child.GetName() == name:
                return child
        except Exception:  # noqa: BLE001
            pass
        child = nxt
    return None


def _find_root_by_name(
    doc: "c4d.documents.BaseDocument", name: str,
) -> Optional["c4d.BaseObject"]:
    _require_c4d()
    obj = doc.GetFirstObject()
    while obj is not None:
        try:
            if obj.GetName() == name:
                return obj
        except Exception:  # noqa: BLE001
            pass
        obj = obj.GetNext()
    return None


def ensure_project_structure(
    doc: "c4d.documents.BaseDocument",
) -> "c4d.BaseObject":
    """Create / reuse the ``UNAV_Project`` root and its six
    canonical children. Returns the root.

    Idempotent: calling twice in a row is a no-op past the
    first creation. Migrates legacy roots
    (``UNAV_Starfield`` → ``UNAV_VisibleSector``,
    ``UNAV_Overlays`` → kept verbatim under the project,
    ``UNAV_ScienceLayers`` → kept verbatim) into the new
    structure when found at the document root.
    """
    _require_c4d()
    project = _find_root_by_name(doc, PROJECT_ROOT_NAME)
    if project is None:
        project = c4d.BaseObject(c4d.Onull)
        project.SetName(PROJECT_ROOT_NAME)
        doc.InsertObject(project)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, project)
    # Migrate legacy roots: re-parent them under the new
    # project. The plugin's existing builders continue to
    # work because every reader walks UP the parent chain
    # to find their owning null, not down from the document
    # root.
    for legacy_name in tuple(LEGACY_ROOT_TO_CANONICAL.keys()):
        legacy = _find_root_by_name(doc, legacy_name)
        if legacy is None:
            continue
        if legacy.GetUp() == project:
            continue  # already migrated
        legacy.Remove()
        legacy.InsertUnder(project)
        doc.AddUndo(c4d.UNDOTYPE_BITS, legacy)
    # Ensure each canonical child exists.
    for name in CANONICAL_CHILD_GROUPS:
        child = _find_child_by_name(project, name)
        if child is not None:
            continue
        # If a legacy root migrated into the project under a
        # different name, accept it as the child.
        legacy_match = next(
            (
                src for (src, dst) in LEGACY_ROOT_TO_CANONICAL.items()
                if dst == name
            ),
            None,
        )
        if legacy_match is not None:
            existing = _find_child_by_name(project, legacy_match)
            if existing is not None:
                existing.SetName(name)
                continue
        new = c4d.BaseObject(c4d.Onull)
        new.SetName(name)
        new.InsertUnder(project)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, new)
    return project


def get_project_child(
    doc: "c4d.documents.BaseDocument", group_name: str,
) -> Optional["c4d.BaseObject"]:
    """Return the canonical child group with ``group_name``
    if it exists, else None. Read-only — does not create."""
    _require_c4d()
    project = _find_root_by_name(doc, PROJECT_ROOT_NAME)
    if project is None:
        return None
    return _find_child_by_name(project, group_name)


def cleanup_project_structure(
    doc: "c4d.documents.BaseDocument",
    *,
    plan: CleanupPlan,
) -> int:
    """Apply a ``CleanupPlan`` to the scene. Returns the
    number of nodes removed.

    The plan is consulted as the source of truth; the
    builder removes only what the plan listed. Orphan-uid
    pruning is handed off to the visible-sector backend
    (since the backend owns the materialised geometry);
    this helper only handles top-level group removal.
    """
    _require_c4d()
    if plan.is_noop():
        return 0
    project = _find_root_by_name(doc, PROJECT_ROOT_NAME)
    if project is None:
        return 0
    removed = 0
    for name in plan.remove_groups:
        node = _find_child_by_name(project, name)
        if node is None:
            continue
        doc.AddUndo(c4d.UNDOTYPE_DELETE, node)
        node.Remove()
        removed += 1
    return removed
