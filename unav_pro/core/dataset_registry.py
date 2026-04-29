"""Dataset registry — persistent list of locally available catalogs.

A dataset entry is a name + path + lightweight stats blob + flags
(``enabled``, optional ``index_path``). The registry keeps a list of
entries on disk so the plugin remembers what catalogs the user has
registered between sessions, and a merge helper that loads every
enabled entry into one ``CatalogObject`` list with namespaced uids
to prevent collisions.

No c4d dependency. Pure CPython, fully unit-tested.

JSON-on-disk format
-------------------

::

    {
      "schema_version": 1,
      "datasets": [
        {
          "name": "Gaia Pleiades",
          "path": "/path/to/gaia_pleiades.jsonl",
          "enabled": true,
          "namespace": true,
          "index_path": "/path/to/gaia_pleiades_index",
          "stats": {
            "object_count": 4823,
            "bounding_radius_pc": 425.7,
            "available_fields": ["uid", "ra_deg", ...],
            "sources": ["gaia_dr3"],
            "last_scanned_iso": "2026-01-01T12:00:00"
          },
          "notes": ""
        },
        ...
      ]
    }
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.logging_util import get_logger
from data.catalog_io import (
    CatalogIOError,
    default_sample_catalog_path,
    load_catalog,
)
from data.schema import CatalogObject

_log = get_logger("core.dataset_registry")

REGISTRY_SCHEMA_VERSION = 1
REGISTRY_FILENAME = "datasets.json"


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@dataclass
class DatasetStats:
    """Aggregated counts and ranges scanned from a catalog file."""

    object_count: int = 0
    bounding_radius_pc: float = 0.0
    available_fields: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    last_scanned_iso: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> Optional["DatasetStats"]:
        if not d:
            return None
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in d.items() if k in known}
        return cls(**clean)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


@dataclass
class DatasetEntry:
    """One registered catalog file plus its current state."""

    name: str
    path: str
    enabled: bool = True
    namespace: bool = True
    index_path: Optional[str] = None
    stats: Optional[DatasetStats] = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("dataset name must be non-empty")
        if not self.path:
            raise ValueError("dataset path must be non-empty")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "enabled": bool(self.enabled),
            "namespace": bool(self.namespace),
            "index_path": self.index_path,
            "stats": self.stats.to_dict() if self.stats else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DatasetEntry":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (d or {}).items() if k in known}
        if "stats" in clean:
            clean["stats"] = DatasetStats.from_dict(clean["stats"])
        return cls(**clean)

    @property
    def is_indexed(self) -> bool:
        return bool(self.index_path) and os.path.isdir(self.index_path or "")

    @property
    def file_exists(self) -> bool:
        return bool(self.path) and os.path.isfile(self.path)


# ---------------------------------------------------------------------------
# Stats scanning
# ---------------------------------------------------------------------------


_FIELD_BLACKLIST = {"display_color_rgb"}


def _populated_fields(objects: Sequence[CatalogObject]) -> List[str]:
    """Return the schema fields that have at least one non-None /
    non-empty value across ``objects``. Computed and cosmetic fields
    (``display_color_rgb``) are excluded — the inspector cares about
    *catalog* fields, not viewport caches."""
    if not objects:
        return []
    seen: List[str] = []
    sample_obj = objects[0]
    field_names = [f.name for f in fields(sample_obj)]
    for name in field_names:
        if name in _FIELD_BLACKLIST:
            continue
        for obj in objects:
            v = getattr(obj, name, None)
            if v is None:
                continue
            if isinstance(v, str) and not v:
                continue
            if isinstance(v, str) and name == "metadata_json" and v == "{}":
                continue
            seen.append(name)
            break
    return seen


def _bounding_radius_pc(objects: Sequence[CatalogObject]) -> float:
    """Largest catartesian-pc distance from origin across ``objects``.

    Objects without a usable position contribute 0 (they sit at the
    placeholder sphere or below)."""
    radius = 0.0
    for obj in objects:
        x, y, z = obj.cartesian_x, obj.cartesian_y, obj.cartesian_z
        if x is None or y is None or z is None:
            continue
        r = math.sqrt(x * x + y * y + z * z)
        if r > radius:
            radius = r
    return radius


def scan_dataset_stats(path: str) -> DatasetStats:
    """Load ``path`` and compute a ``DatasetStats``.

    Raises ``CatalogIOError`` for missing / unreadable files; callers
    that want to keep going (the registry's add path) should catch
    and stash the error in ``notes``.
    """
    objects = load_catalog(path)
    sources = sorted({o.catalog_source for o in objects if o.catalog_source})
    return DatasetStats(
        object_count=len(objects),
        bounding_radius_pc=_bounding_radius_pc(objects),
        available_fields=_populated_fields(objects),
        sources=sources,
        last_scanned_iso=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


@dataclass
class MergeResult:
    """Outcome of ``DatasetRegistry.merge_active``."""

    objects: List[CatalogObject] = field(default_factory=list)
    per_dataset_counts: Dict[str, int] = field(default_factory=dict)
    total_objects: int = 0
    duplicates_skipped: int = 0
    errors: Dict[str, str] = field(default_factory=dict)

    def short_summary(self) -> str:
        parts = [f"{self.total_objects} objects from {len(self.per_dataset_counts)} dataset(s)"]
        if self.duplicates_skipped:
            parts.append(f"{self.duplicates_skipped} duplicate uid(s) skipped")
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        return "; ".join(parts)


def _namespaced_uid(entry: DatasetEntry, original: str) -> str:
    """Build a collision-free uid: ``<entry.name>:<original>``.

    ``entry.name`` is what the user typed in the registry. We do not
    try to be clever about double-prefixing (e.g. ``gaia_dr3:1234``
    becoming ``Gaia Pleiades:gaia_dr3:1234``) — the goal is to
    *guarantee* uniqueness across registry entries; aesthetics come
    second.
    """
    if not entry.namespace:
        return original
    return f"{entry.name}:{original}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass
class DatasetRegistry:
    """An ordered list of ``DatasetEntry`` plus a JSON persister.

    Order matters for two reasons:
      * Display order in the dialog matches insertion order.
      * Merge order matches insertion order, so an entry added later
        cannot displace an earlier entry's uid (we *skip*
        duplicates, never overwrite).
    """

    entries: List[DatasetEntry] = field(default_factory=list)

    # ------------------------------------------------------------------ size
    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    # --------------------------------------------------------------- finders
    def names(self) -> List[str]:
        return [e.name for e in self.entries]

    def find(self, name: str) -> Optional[DatasetEntry]:
        for e in self.entries:
            if e.name == name:
                return e
        return None

    def enabled_entries(self) -> List[DatasetEntry]:
        return [e for e in self.entries if e.enabled]

    # ------------------------------------------------------------------ CRUD
    def add(self, entry: DatasetEntry) -> DatasetEntry:
        if self.find(entry.name) is not None:
            raise ValueError(f"dataset '{entry.name}' is already registered")
        self.entries.append(entry)
        return entry

    def add_path(
        self,
        path: str,
        name: Optional[str] = None,
        enabled: bool = True,
        namespace: bool = True,
        scan: bool = True,
    ) -> DatasetEntry:
        """Register a catalog file. Optional immediate scan for stats.

        Defaults pick a friendly ``name`` from the basename when one
        is not provided; if a same-named entry already exists, a
        ``ValueError`` is raised. Scan failures land in
        ``entry.notes`` rather than aborting registration.
        """
        if not name:
            base = os.path.basename(path) or "dataset"
            name = os.path.splitext(base)[0]
            # Make sure the name is unique — append _N if needed.
            taken = set(self.names())
            stem = name
            i = 2
            while name in taken:
                name = f"{stem}_{i}"
                i += 1

        entry = DatasetEntry(
            name=name, path=path, enabled=enabled, namespace=namespace,
        )
        if scan:
            try:
                entry.stats = scan_dataset_stats(path)
            except (CatalogIOError, FileNotFoundError, OSError) as exc:
                entry.notes = f"scan failed: {exc}"
                _log.warning("Could not scan %s: %s", path, exc)
        self.add(entry)
        return entry

    def remove(self, name: str) -> Optional[DatasetEntry]:
        for i, e in enumerate(self.entries):
            if e.name == name:
                return self.entries.pop(i)
        return None

    def set_enabled(self, name: str, enabled: bool) -> bool:
        e = self.find(name)
        if e is None:
            return False
        e.enabled = bool(enabled)
        return True

    def set_index_path(self, name: str, path: Optional[str]) -> bool:
        e = self.find(name)
        if e is None:
            return False
        e.index_path = path
        return True

    def rescan(self, name: str) -> Optional[DatasetEntry]:
        e = self.find(name)
        if e is None:
            return None
        try:
            e.stats = scan_dataset_stats(e.path)
            e.notes = ""
        except Exception as exc:  # noqa: BLE001 — boundary
            e.notes = f"scan failed: {exc}"
        return e

    # -------------------------------------------------------------- (de)ser
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "datasets": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DatasetRegistry":
        d = d or {}
        entries: List[DatasetEntry] = []
        for raw in d.get("datasets", []) or []:
            try:
                entries.append(DatasetEntry.from_dict(raw))
            except Exception as exc:  # noqa: BLE001
                _log.warning("Skipping malformed dataset entry: %s", exc)
        return cls(entries=entries)

    def save(self, path: str) -> str:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, sort_keys=True)
        return path

    @classmethod
    def load(cls, path: str) -> "DatasetRegistry":
        if not os.path.isfile(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return cls.from_dict(json.load(fh))
        except (OSError, ValueError, TypeError) as exc:
            _log.warning("Could not read registry %s: %s", path, exc)
            return cls()

    # ----------------------------------------------------------------- merge
    def merge_active(
        self,
        on_error: str = "record",
    ) -> MergeResult:
        """Load every enabled entry into one ``CatalogObject`` list,
        with namespaced uids to prevent collisions.

        ``on_error="record"`` collects the load failure into
        ``MergeResult.errors`` and continues with the remaining
        entries. ``on_error="raise"`` re-raises the first failure.
        """
        result = MergeResult()
        seen_uids: set = set()

        for entry in self.enabled_entries():
            try:
                objects = load_catalog(entry.path)
            except (CatalogIOError, FileNotFoundError, OSError) as exc:
                msg = f"could not load: {exc}"
                if on_error == "raise":
                    raise
                result.errors[entry.name] = msg
                continue

            count = 0
            for obj in objects:
                original_uid = obj.uid or ""
                ns_uid = _namespaced_uid(entry, original_uid)
                if not ns_uid:
                    continue
                if ns_uid in seen_uids:
                    result.duplicates_skipped += 1
                    continue
                obj.uid = ns_uid
                result.objects.append(obj)
                seen_uids.add(ns_uid)
                count += 1
            result.per_dataset_counts[entry.name] = count

        result.total_objects = len(result.objects)
        return result


# ---------------------------------------------------------------------------
# Default location
# ---------------------------------------------------------------------------


def default_registry_path() -> str:
    """Per-user registry path. Survives plugin reloads."""
    base = os.path.expanduser("~/.unav_pro")
    return os.path.join(base, REGISTRY_FILENAME)


# ---------------------------------------------------------------------------
# Convenience: a registry seeded with the bundled sample
# ---------------------------------------------------------------------------


def bootstrap_with_sample() -> DatasetRegistry:
    """Build a fresh registry containing only the bundled sample
    catalog. Used as the default the first time the dialog opens
    without an existing on-disk registry."""
    reg = DatasetRegistry()
    sample_path = default_sample_catalog_path()
    if os.path.isfile(sample_path):
        try:
            reg.add_path(sample_path, name="UNAV Sample (bundled)")
        except ValueError:
            pass
    return reg


# ---------------------------------------------------------------------------
# Pretty rendering for the dialog
# ---------------------------------------------------------------------------


def render_registry(reg: DatasetRegistry) -> str:
    """Multi-line table-style summary of every entry. Used by the
    dataset manager dialog's panel."""
    if len(reg) == 0:
        return (
            "No datasets registered. Click 'Add Dataset' to register a "
            "JSONL or CSV catalog file."
        )
    lines: List[str] = []
    lines.append(f"=== Datasets ({len(reg)} registered, "
                 f"{len(reg.enabled_entries())} enabled) ===")
    for i, e in enumerate(reg.entries):
        flags = "ON " if e.enabled else "off"
        idx = "idx" if e.is_indexed else "-  "
        miss = "" if e.file_exists else "  [missing file]"
        lines.append(f"  [{i}] {flags} {idx} {e.name}{miss}")
        lines.append(f"        path : {e.path}")
        if e.stats is not None:
            sources = ",".join(e.stats.sources) or "—"
            lines.append(
                f"        stats: {e.stats.object_count} objects, "
                f"r ≤ {e.stats.bounding_radius_pc:.3g} pc, "
                f"sources: {sources}"
            )
            field_n = len(e.stats.available_fields)
            lines.append(
                f"        fields: {field_n} populated"
            )
        if e.notes:
            lines.append(f"        note : {e.notes}")
    return "\n".join(lines)
