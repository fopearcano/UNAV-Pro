"""v3.1 mission packs.

A mission pack is a small JSON document that bundles one
or more missions for sharing across projects / artists.
Pack format:

::

    {
      "schema_version": 1,
      "pack_name": "Solar System Tours",
      "description": "...",
      "created_at_iso": "...",
      "missions": [
        { ...full Mission JSON... },
        { ...full Mission JSON... }
      ]
    }

The pack format wraps the v1.4 ``Mission.to_dict()`` output
verbatim — no information loss. v3.1 introduces packs so
artists can:

* share a curated set of missions across projects;
* version-control mission collections in git;
* import a vendor's pack into a workspace without
  manually copying mission JSONs.

**Duplicate-safe imports.** ``import_pack(...)`` collides
on ``mission_id``; the caller picks the strategy
(``"skip"``, ``"replace"``, or ``"rename"``).

Pure stdlib; no Cinema 4D, no networking.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


MISSION_PACK_SCHEMA_VERSION: int = 1


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MissionPackError(ValueError):
    """Raised for malformed mission-pack JSON."""


# ---------------------------------------------------------------------------
# Pack dataclass
# ---------------------------------------------------------------------------


@dataclass
class MissionPack:
    """One mission pack. ``missions`` is a list of raw
    ``Mission`` dicts; the importer turns them into
    ``Mission`` objects via ``Mission.from_dict``."""

    pack_name: str
    description: str = ""
    created_at_iso: str = ""
    schema_version: int = MISSION_PACK_SCHEMA_VERSION
    missions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "pack_name": self.pack_name,
            "description": self.description,
            "created_at_iso": self.created_at_iso,
            "missions": [dict(m) for m in self.missions],
        }

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "MissionPack":
        if not isinstance(d, dict):
            raise MissionPackError("mission pack payload is not an object")
        version = d.get("schema_version", MISSION_PACK_SCHEMA_VERSION)
        try:
            version_i = int(version)
        except (TypeError, ValueError) as exc:
            raise MissionPackError(
                f"mission pack schema_version not an integer: {version!r}",
            ) from exc
        if version_i > MISSION_PACK_SCHEMA_VERSION:
            raise MissionPackError(
                f"mission pack schema_version {version_i} is newer "
                f"than this build understands "
                f"({MISSION_PACK_SCHEMA_VERSION})."
            )
        missions_in = d.get("missions") or []
        if not isinstance(missions_in, list):
            raise MissionPackError("mission pack 'missions' is not a list")
        clean_missions: List[Dict[str, Any]] = []
        for entry in missions_in:
            if not isinstance(entry, dict):
                continue
            clean_missions.append(dict(entry))
        return cls(
            schema_version=version_i,
            pack_name=str(d.get("pack_name", "") or "Untitled Pack"),
            description=str(d.get("description", "") or ""),
            created_at_iso=str(d.get("created_at_iso", "") or ""),
            missions=clean_missions,
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=False,
        )

    @classmethod
    def from_json(cls, text: str) -> "MissionPack":
        try:
            d = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MissionPackError(
                f"mission pack JSON parse failed: {exc}",
            ) from exc
        return cls.from_dict(d)


# ---------------------------------------------------------------------------
# Build / write
# ---------------------------------------------------------------------------


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def build_pack_from_missions(
    missions: Sequence[Any],
    *,
    pack_name: str,
    description: str = "",
) -> MissionPack:
    """Build a ``MissionPack`` from a sequence of v1.4
    ``Mission`` objects (anything with ``.to_dict()``).

    Mission objects are serialised verbatim; the pack does
    not strip / mutate fields.
    """
    if not pack_name.strip():
        raise ValueError("pack_name is required")
    payloads: List[Dict[str, Any]] = []
    for m in missions:
        to_dict = getattr(m, "to_dict", None)
        if not callable(to_dict):
            raise TypeError(
                f"missions must implement .to_dict(); got {type(m).__name__}"
            )
        d = to_dict()
        if not isinstance(d, dict):
            raise TypeError(
                f"to_dict() returned {type(d).__name__}, expected dict"
            )
        payloads.append(dict(d))
    return MissionPack(
        pack_name=pack_name.strip(),
        description=description,
        created_at_iso=_utc_iso(),
        missions=payloads,
    )


def write_pack(pack: MissionPack, path: str) -> None:
    """Atomic write a pack to ``path``."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(pack.to_json())
        fh.write("\n")
    os.replace(tmp, path)


def read_pack(path: str) -> MissionPack:
    """Read + parse a pack. Raises ``MissionPackError`` on
    parse failure."""
    if not os.path.isfile(path):
        raise MissionPackError(f"mission pack not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return MissionPack.from_json(fh.read())


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


@dataclass
class ImportReport:
    """Outcome of one ``import_pack`` call."""

    pack_name: str = ""
    imported: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    replaced: List[str] = field(default_factory=list)
    renamed: List[Tuple[str, str]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def total_imported(self) -> int:
        return (
            len(self.imported)
            + len(self.replaced)
            + len(self.renamed)
        )

    def short_summary(self) -> str:
        parts = [
            f"imported={len(self.imported)}",
            f"replaced={len(self.replaced)}",
            f"renamed={len(self.renamed)}",
            f"skipped={len(self.skipped)}",
        ]
        if self.errors:
            parts.append(f"errors={len(self.errors)}")
        return ", ".join(parts)


#: Strategies for handling mission_id collisions on import.
COLLISION_STRATEGIES: Tuple[str, ...] = ("skip", "replace", "rename")


def _new_mission_id_for_collision(
    base: str, taken: Sequence[str], *, max_attempts: int = 32,
) -> str:
    """Pick a fresh mission_id when the import collides
    with an existing one. Tries ``base-2``, ``base-3``, …
    before falling back to a uuid suffix."""
    taken_set = set(taken)
    for i in range(2, max_attempts + 1):
        candidate = f"{base}-{i}"
        if candidate not in taken_set:
            return candidate
    return f"{base}-{uuid.uuid4().hex[:8]}"


def import_pack(
    pack: MissionPack,
    *,
    existing_ids: Sequence[str],
    mission_factory: Callable[[Dict[str, Any]], Any],
    create_callback: Callable[[Any], None],
    update_callback: Optional[Callable[[Any], None]] = None,
    on_collision: str = "skip",
) -> ImportReport:
    """Import every mission from ``pack`` using the supplied
    callbacks.

    The function is **storage-agnostic**:
    ``mission_factory`` turns a mission dict into a Mission
    object (typically ``Mission.from_dict``);
    ``create_callback`` persists a brand-new mission;
    ``update_callback`` overwrites an existing one (only
    consulted under ``on_collision="replace"``).

    ``on_collision`` ∈ ``COLLISION_STRATEGIES``:

    * ``"skip"`` — leave the existing mission alone, report
      the collision in ``skipped``.
    * ``"replace"`` — overwrite the existing mission with
      the imported one. Requires ``update_callback``.
    * ``"rename"`` — assign a fresh mission_id (e.g.
      ``X-2``) to the imported mission and create it.

    The callbacks are intentionally separate so the same
    ``import_pack`` works against the existing
    ``MissionManager`` *and* against a workspace-aware
    storage layer.
    """
    if on_collision not in COLLISION_STRATEGIES:
        raise ValueError(
            f"on_collision must be one of {COLLISION_STRATEGIES}; "
            f"got {on_collision!r}"
        )
    if on_collision == "replace" and update_callback is None:
        raise ValueError(
            "on_collision='replace' requires update_callback"
        )

    report = ImportReport(pack_name=pack.pack_name)
    known_ids = list(existing_ids)
    for raw in pack.missions:
        try:
            mission = mission_factory(raw)
        except Exception as exc:  # noqa: BLE001 — boundary
            report.errors.append(
                f"failed to deserialise mission: {exc!r}"
            )
            continue
        mid = getattr(mission, "mission_id", None) or str(raw.get("mission_id", ""))
        if not mid:
            report.errors.append("mission has no mission_id; skipping")
            continue
        if mid in known_ids:
            if on_collision == "skip":
                report.skipped.append(mid)
                continue
            if on_collision == "replace":
                try:
                    update_callback(mission)  # type: ignore[misc]
                    report.replaced.append(mid)
                except Exception as exc:  # noqa: BLE001
                    report.errors.append(
                        f"replace failed for {mid}: {exc!r}"
                    )
                continue
            # rename
            new_id = _new_mission_id_for_collision(mid, known_ids)
            try:
                # Mission objects in v1.4 expose mission_id
                # as a writable attribute.
                mission.mission_id = new_id  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                report.errors.append(
                    f"rename failed for {mid} → {new_id}: {exc!r}"
                )
                continue
            try:
                create_callback(mission)
                known_ids.append(new_id)
                report.renamed.append((mid, new_id))
            except Exception as exc:  # noqa: BLE001
                report.errors.append(
                    f"create after rename failed for {new_id}: {exc!r}"
                )
            continue
        # No collision.
        try:
            create_callback(mission)
            known_ids.append(mid)
            report.imported.append(mid)
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"create failed for {mid}: {exc!r}")
    return report
