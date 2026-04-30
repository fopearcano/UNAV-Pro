"""Persistent bookmarks for the UNAV navigator.

A bookmark is one of:

  * an **object bookmark** — a uid (with optional source / type tags)
    that the lookup will resolve to a position when the user clicks
    "Focus";
  * a **coordinate bookmark** — a fixed 3D point in C4D world units
    (and optional parsec triple), used for "remember this scene
    location."

Storage lives at ``~/.unav_pro/bookmarks.json`` next to ``config.json``
and the per-project sidecars. The format mirrors the rest of the
plugin's persistence layer: pure data, JSON, no c4d types, never
raises on load — corrupt files yield an empty bookmark list.

No c4d dependency. Fully unit-tested.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional, Tuple

from core.config import default_config_dir
from core.logging_util import get_logger

_log = get_logger("core.bookmarks")

BOOKMARK_SCHEMA_VERSION = 1
BOOKMARKS_FILENAME = "bookmarks.json"

#: Allowed kinds. ``object`` requires a uid; ``coordinate`` requires
#: at least the c4d position triple.
BOOKMARK_KINDS: Tuple[str, ...] = ("object", "coordinate")


# ---------------------------------------------------------------------------
# Bookmark
# ---------------------------------------------------------------------------


@dataclass
class Bookmark:
    """One saved navigator anchor.

    ``id`` is a stable identifier the UI keys off (so deletes / moves
    don't depend on label uniqueness). It defaults to a short hex
    suffix so two bookmarks named "Sirius" don't collide.
    """

    kind: str
    label: str = ""

    # Object-kind fields.
    uid: Optional[str] = None
    catalog_source: Optional[str] = None
    object_type: Optional[str] = None

    # Coordinate-kind fields. C4D coords are required for the
    # ``coordinate`` kind; pc coords are optional (but recommended).
    x_c4d: Optional[float] = None
    y_c4d: Optional[float] = None
    z_c4d: Optional[float] = None
    x_pc: Optional[float] = None
    y_pc: Optional[float] = None
    z_pc: Optional[float] = None

    # Bookkeeping.
    id: str = ""
    created_iso: Optional[str] = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.kind not in BOOKMARK_KINDS:
            raise ValueError(
                f"unknown bookmark kind '{self.kind}'; "
                f"valid: {', '.join(BOOKMARK_KINDS)}"
            )
        if self.kind == "object" and not (self.uid or "").strip():
            raise ValueError("object bookmark requires a non-empty uid")
        if self.kind == "coordinate" and not self.has_c4d_position():
            raise ValueError("coordinate bookmark requires x/y/z_c4d")
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.created_iso:
            self.created_iso = time.strftime("%Y-%m-%dT%H:%M:%S")

    # ------------------------------------------------------------ helpers
    def has_c4d_position(self) -> bool:
        return (
            self.x_c4d is not None
            and self.y_c4d is not None
            and self.z_c4d is not None
        )

    def has_pc_position(self) -> bool:
        return (
            self.x_pc is not None
            and self.y_pc is not None
            and self.z_pc is not None
        )

    def display_label(self) -> str:
        if self.label:
            return self.label
        if self.kind == "object" and self.uid:
            return self.uid
        if self.kind == "coordinate" and self.has_c4d_position():
            return (
                f"({self.x_c4d:.3g}, {self.y_c4d:.3g}, {self.z_c4d:.3g})"
            )
        return f"<{self.kind}>"

    # --------------------------------------------------------- (de)serialize
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Strip None and empty-string fields to keep the on-disk file tidy.
        return {k: v for k, v in d.items() if v not in (None, "")}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Bookmark":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (d or {}).items() if k in known}
        return cls(**clean)


# ---------------------------------------------------------------------------
# BookmarkList
# ---------------------------------------------------------------------------


@dataclass
class BookmarkList:
    """Ordered list of ``Bookmark`` plus persistence helpers.

    Order matters: the panel renders insertion order, and ``move``
    lets the user reorder. ``add`` rejects exact duplicates by
    ``(kind, uid, x_c4d, y_c4d, z_c4d)`` so re-clicking "Bookmark"
    on the same target is a no-op.
    """

    bookmarks: List[Bookmark] = field(default_factory=list)

    # ----------------------------------------------------------------- size
    def __len__(self) -> int:
        return len(self.bookmarks)

    def __iter__(self):
        return iter(self.bookmarks)

    # ---------------------------------------------------------------- find
    def find(self, bookmark_id: str) -> Optional[Bookmark]:
        for b in self.bookmarks:
            if b.id == bookmark_id:
                return b
        return None

    def index_of(self, bookmark_id: str) -> int:
        for i, b in enumerate(self.bookmarks):
            if b.id == bookmark_id:
                return i
        return -1

    # ----------------------------------------------------------------- CRUD
    def add(self, bookmark: Bookmark) -> Tuple[bool, Bookmark]:
        """Append ``bookmark``. Returns ``(was_added, existing_or_new)``.

        Duplicates (same uid, or same coordinate triple) are rejected
        and the existing entry is returned instead — the caller can
        decide whether to surface a "already bookmarked" status.
        """
        for existing in self.bookmarks:
            if _is_duplicate(existing, bookmark):
                return False, existing
        self.bookmarks.append(bookmark)
        return True, bookmark

    def remove(self, bookmark_id: str) -> Optional[Bookmark]:
        idx = self.index_of(bookmark_id)
        if idx == -1:
            return None
        return self.bookmarks.pop(idx)

    def clear(self) -> int:
        n = len(self.bookmarks)
        self.bookmarks.clear()
        return n

    def move(self, bookmark_id: str, new_index: int) -> bool:
        """Reorder ``bookmark_id`` to ``new_index`` (clamped to the
        valid range). Returns True on success."""
        idx = self.index_of(bookmark_id)
        if idx == -1:
            return False
        if new_index < 0:
            new_index = 0
        if new_index >= len(self.bookmarks):
            new_index = len(self.bookmarks) - 1
        if idx == new_index:
            return True
        item = self.bookmarks.pop(idx)
        self.bookmarks.insert(new_index, item)
        return True

    def rename(self, bookmark_id: str, new_label: str) -> bool:
        b = self.find(bookmark_id)
        if b is None:
            return False
        b.label = new_label
        return True

    # ------------------------------------------------------------- (de)ser
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": BOOKMARK_SCHEMA_VERSION,
            "bookmarks": [b.to_dict() for b in self.bookmarks],
        }

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "BookmarkList":
        d = d or {}
        out: List[Bookmark] = []
        for raw in d.get("bookmarks", []) or []:
            try:
                out.append(Bookmark.from_dict(raw))
            except (TypeError, ValueError) as exc:
                _log.warning("Skipping malformed bookmark: %s", exc)
        return cls(bookmarks=out)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "BookmarkList":
        try:
            return cls.from_dict(json.loads(s or "{}"))
        except (TypeError, ValueError):
            return cls()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_duplicate(a: Bookmark, b: Bookmark) -> bool:
    """Identical (kind, identity) — used by ``add`` to reject
    no-op re-bookmarks."""
    if a.kind != b.kind:
        return False
    if a.kind == "object":
        return (a.uid or "") == (b.uid or "")
    # coordinate
    return (
        _approx(a.x_c4d, b.x_c4d)
        and _approx(a.y_c4d, b.y_c4d)
        and _approx(a.z_c4d, b.z_c4d)
    )


def _approx(a: Optional[float], b: Optional[float], tol: float = 1e-6) -> bool:
    if a is None or b is None:
        return a == b
    return abs(a - b) <= tol


# ---------------------------------------------------------------------------
# Disk I/O
# ---------------------------------------------------------------------------


def default_bookmarks_path() -> str:
    """Per-user bookmarks file. Lives next to ``config.json``."""
    return os.path.join(default_config_dir(), BOOKMARKS_FILENAME)


def load_bookmarks(path: Optional[str] = None) -> BookmarkList:
    """Load the bookmarks file. Missing or corrupt files yield an
    empty list — never raises."""
    p = path or default_bookmarks_path()
    if not os.path.isfile(p):
        return BookmarkList()
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return BookmarkList.from_dict(json.load(fh))
    except (OSError, ValueError, TypeError) as exc:
        _log.warning("Could not read bookmarks %s: %s", p, exc)
        return BookmarkList()


def save_bookmarks(
    bookmarks: BookmarkList, path: Optional[str] = None,
) -> Optional[str]:
    """Persist the bookmark list. Returns the path on success or
    ``None`` on failure. Failures are logged, never raised."""
    p = path or default_bookmarks_path()
    parent = os.path.dirname(os.path.abspath(p))
    try:
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(bookmarks.to_json())
    except OSError as exc:
        _log.warning("Could not write bookmarks %s: %s", p, exc)
        return None
    return p


# ---------------------------------------------------------------------------
# Pretty rendering
# ---------------------------------------------------------------------------


def render_bookmarks(bookmarks: BookmarkList) -> str:
    """Multi-line text rendering for the dialog's bookmarks panel."""
    if len(bookmarks) == 0:
        return (
            "No bookmarks yet. Search for an object and click 'Add to "
            "Bookmarks', or 'Save Current Position'."
        )
    lines: List[str] = []
    lines.append(f"=== Bookmarks ({len(bookmarks)}) ===")
    for i, b in enumerate(bookmarks):
        line = f"  [{i}] {b.display_label()}  ({b.kind})"
        details: List[str] = []
        if b.catalog_source:
            details.append(b.catalog_source)
        if b.object_type:
            details.append(b.object_type)
        if details:
            line += "  — " + ", ".join(details)
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------


def bookmark_from_search_result(result, label: Optional[str] = None) -> Bookmark:
    """Convert a ``search.SearchResult`` into an object bookmark."""
    return Bookmark(
        kind="object",
        label=label or (result.common_name or result.name or result.uid),
        uid=result.uid,
        catalog_source=result.catalog_source,
        object_type=result.object_type,
    )


def bookmark_from_target_lock(lock, label: Optional[str] = None) -> Bookmark:
    """Convert a ``target_lock.TargetLock`` into an object bookmark
    with the target's last-known c4d / pc positions captured."""
    bm = Bookmark(
        kind="object",
        label=label or lock.label,
        uid=lock.uid,
        catalog_source=lock.catalog_source,
        object_type=lock.object_type,
        x_c4d=lock.position_c4d[0] if lock.position_c4d else None,
        y_c4d=lock.position_c4d[1] if lock.position_c4d else None,
        z_c4d=lock.position_c4d[2] if lock.position_c4d else None,
    )
    if lock.position_pc is not None:
        bm.x_pc, bm.y_pc, bm.z_pc = lock.position_pc
    return bm


def bookmark_from_coordinate(
    position_c4d: Tuple[float, float, float],
    label: str,
    *,
    position_pc: Optional[Tuple[float, float, float]] = None,
) -> Bookmark:
    """Build a coordinate bookmark from a raw position triple."""
    bm = Bookmark(
        kind="coordinate",
        label=label,
        x_c4d=float(position_c4d[0]),
        y_c4d=float(position_c4d[1]),
        z_c4d=float(position_c4d[2]),
    )
    if position_pc is not None:
        bm.x_pc = float(position_pc[0])
        bm.y_pc = float(position_pc[1])
        bm.z_pc = float(position_pc[2])
    return bm
