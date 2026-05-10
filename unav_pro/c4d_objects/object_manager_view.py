"""v3.45 Object Manager view + summary helpers.

Pure-Python summarisers for the Cinema 4D Object
Manager hierarchy. The c4d-bound walk lives in the
existing ``scene_structure`` module; this layer takes
a *node tree description* (each node is a name + its
children) and produces:

* ``count_unav_objects`` — count of UNAV-owned objects
  by category (visible-sector, overlays, science,
  missions, debug).
* ``flatten_unav_tree`` — depth-first list of every
  UNAV-prefixed node for the diagnostics panel.
* ``deduplicate_root_groups`` — pure planner that
  reports duplicate top-level UNAV roots so the
  cleanup pass can prune them.
* ``orphan_detector`` — finds UNAV-marked nodes whose
  parent role doesn't match the canonical hierarchy.

The c4d-bound builder feeds in ``ObjectNode`` records
synthesised from a defensive ``GetDown`` / ``GetNext``
walk; the pure helpers compute the diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from .scene_structure import (
    CANONICAL_CHILD_GROUPS,
    DEBUG_GROUP_NAME,
    MISSIONS_GROUP_NAME,
    NAVIGATION_GROUP_NAME,
    OVERLAYS_GROUP_NAME,
    PROJECT_ROOT_NAME,
    SCIENCE_LAYERS_GROUP_NAME,
    VISIBLE_SECTOR_GROUP_NAME,
)


# ---------------------------------------------------------------------------
# Node model
# ---------------------------------------------------------------------------


@dataclass
class ObjectNode:
    """One node in the Object Manager. Pure data; the
    c4d-bound walk synthesises these by reading
    ``BaseObject.GetName()`` + ``GetDown`` / ``GetNext``
    siblings.
    """

    name: str
    children: List["ObjectNode"] = field(default_factory=list)

    def descendants(self) -> List["ObjectNode"]:
        """Depth-first list of every descendant
        (excluding ``self``)."""
        out: List[ObjectNode] = []
        stack = list(self.children)
        while stack:
            node = stack.pop(0)
            out.append(node)
            stack[0:0] = node.children
        return out


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------


#: Map of canonical group name → category label the
#: diagnostics panel renders.
GROUP_CATEGORIES: Dict[str, str] = {
    NAVIGATION_GROUP_NAME: "navigation",
    VISIBLE_SECTOR_GROUP_NAME: "visible_sector",
    OVERLAYS_GROUP_NAME: "overlays",
    SCIENCE_LAYERS_GROUP_NAME: "science_layers",
    MISSIONS_GROUP_NAME: "missions",
    DEBUG_GROUP_NAME: "debug",
}


@dataclass
class UNAVObjectCounts:
    """Aggregate counts of UNAV-owned objects under the
    canonical project root."""

    by_category: Dict[str, int] = field(default_factory=dict)
    total_unav_owned: int = 0
    project_root_present: bool = False

    def short_summary(self) -> str:
        if not self.project_root_present:
            return "no UNAV_Project root"
        if self.total_unav_owned == 0:
            return "UNAV_Project present; no children"
        bits = [
            f"{label}={self.by_category[label]}"
            for label in sorted(self.by_category)
            if self.by_category[label]
        ]
        return f"total={self.total_unav_owned}; " + ", ".join(bits)


def count_unav_objects(roots: Iterable[ObjectNode]) -> UNAVObjectCounts:
    """Walk ``roots`` (the document's top-level objects)
    and produce a per-category count of UNAV-owned
    children.

    Counts only objects under the canonical project
    root — legacy roots are reported separately by
    ``find_legacy_roots``.
    """
    counts = UNAVObjectCounts()
    counts.by_category = {label: 0 for label in GROUP_CATEGORIES.values()}
    project: Optional[ObjectNode] = None
    for r in roots:
        if r.name == PROJECT_ROOT_NAME:
            project = r
            break
    if project is None:
        return counts
    counts.project_root_present = True
    for child in project.children:
        category = GROUP_CATEGORIES.get(child.name)
        if category is None:
            continue
        descendants = child.descendants()
        unav_descendants = sum(
            1 for d in descendants if d.name.startswith("UNAV_")
        )
        # The child itself counts; descendants that look
        # like UNAV-owned content also count.
        counts.by_category[category] = 1 + unav_descendants
        counts.total_unav_owned += counts.by_category[category]
    return counts


# ---------------------------------------------------------------------------
# Tree flattening
# ---------------------------------------------------------------------------


@dataclass
class FlatNode:
    """One row in the flattened tree. Used by the
    diagnostics panel's "what UNAV created in this
    document" view."""

    name: str
    depth: int
    category: str = ""

    def render(self) -> str:
        indent = "  " * self.depth
        cat = f"  [{self.category}]" if self.category else ""
        return f"{indent}{self.name}{cat}"


def flatten_unav_tree(roots: Iterable[ObjectNode]) -> List[FlatNode]:
    """Walk ``roots`` and produce a depth-first list of
    every UNAV-prefixed node + its category."""
    out: List[FlatNode] = []
    for r in roots:
        if not r.name.startswith("UNAV_"):
            continue
        category = GROUP_CATEGORIES.get(r.name, "")
        out.append(FlatNode(name=r.name, depth=0, category=category))
        _walk_unav(r, depth=1, out=out, parent_category=category)
    return out


def _walk_unav(
    node: ObjectNode, *, depth: int, out: List[FlatNode],
    parent_category: str,
) -> None:
    for child in node.children:
        if not child.name.startswith("UNAV_"):
            continue
        category = GROUP_CATEGORIES.get(child.name, parent_category)
        out.append(FlatNode(
            name=child.name, depth=depth, category=category,
        ))
        _walk_unav(
            child, depth=depth + 1, out=out,
            parent_category=category,
        )


def render_object_manager_view(roots: Iterable[ObjectNode]) -> str:
    """Render the flattened tree as multiline text the
    diagnostics panel embeds verbatim."""
    rows = flatten_unav_tree(roots)
    if not rows:
        return "(no UNAV objects in document)"
    return "\n".join(r.render() for r in rows)


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


@dataclass
class DuplicateRootReport:
    """Plan for the cleanup pass. ``duplicates`` is the
    list of names that appear twice or more at the
    document root; the dispatcher removes the second
    occurrence of each."""

    duplicates: List[str] = field(default_factory=list)
    legacy_roots: List[str] = field(default_factory=list)

    def is_clean(self) -> bool:
        return not self.duplicates and not self.legacy_roots

    def short_summary(self) -> str:
        bits: List[str] = []
        if self.duplicates:
            bits.append(f"duplicates: {', '.join(self.duplicates)}")
        if self.legacy_roots:
            bits.append(f"legacy roots: {', '.join(self.legacy_roots)}")
        return "; ".join(bits) if bits else "object manager clean"


def find_duplicate_roots(roots: Iterable[ObjectNode]) -> DuplicateRootReport:
    """Pure helper — given the document's top-level
    object names, find UNAV-owned duplicates and legacy
    roots that should be migrated under
    ``UNAV_Project``."""
    from .scene_structure import LEGACY_ROOT_TO_CANONICAL
    rep = DuplicateRootReport()
    seen: Dict[str, int] = {}
    for r in roots:
        if not isinstance(r.name, str):
            continue
        if not r.name.startswith("UNAV_"):
            continue
        seen[r.name] = seen.get(r.name, 0) + 1
    for name, n in seen.items():
        if n > 1:
            rep.duplicates.append(name)
        if name in LEGACY_ROOT_TO_CANONICAL:
            rep.legacy_roots.append(name)
    rep.duplicates.sort()
    rep.legacy_roots.sort()
    return rep


# ---------------------------------------------------------------------------
# Orphan detection
# ---------------------------------------------------------------------------


@dataclass
class OrphanReport:
    """UNAV-owned nodes whose parent isn't a canonical
    container. The dispatcher offers to re-parent them
    or drop them."""

    orphans: List[Tuple[str, str]] = field(default_factory=list)
    """List of (orphan_name, parent_name) pairs."""

    def is_clean(self) -> bool:
        return not self.orphans

    def short_summary(self) -> str:
        if self.is_clean():
            return "no orphans"
        return f"{len(self.orphans)} orphan(s)"


def find_orphans(roots: Iterable[ObjectNode]) -> OrphanReport:
    """Walk every UNAV-prefixed node under
    ``UNAV_Project`` and report any whose parent isn't
    one of the six canonical children.

    Determinism: same input ⇒ same output.
    """
    rep = OrphanReport()
    project: Optional[ObjectNode] = None
    for r in roots:
        if r.name == PROJECT_ROOT_NAME:
            project = r
            break
    if project is None:
        return rep
    canonical = set(CANONICAL_CHILD_GROUPS)
    for child in project.children:
        if child.name in canonical:
            continue
        if not child.name.startswith("UNAV_"):
            continue
        # A non-canonical UNAV-prefixed child of the
        # project root is an orphan.
        rep.orphans.append((child.name, PROJECT_ROOT_NAME))
    rep.orphans.sort()
    return rep
