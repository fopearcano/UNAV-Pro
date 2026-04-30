"""Mission CRUD + persistence for the v1.4 voyage system.

The ``MissionManager`` is the in-memory authority for the
artist's missions. It loads the index file on startup, exposes
``create`` / ``get`` / ``update`` / ``delete`` / ``list_all``
methods, and writes one JSON file per mission to
``~/.unav_pro/missions/``.

Persistence layout::

    ~/.unav_pro/
        missions/
            index.json                 # {"mission_ids": [...]}
            <mission_id>.json          # one file per mission

The split lets the dialog enumerate missions without parsing
every file, and lets the artist hand-edit a single mission's
JSON without disturbing the rest. Missing / corrupt files
yield empty results rather than raising — same convention the
bookmarks layer uses.

No Cinema 4D dependency. Pure stdlib + the v1.4 ``Mission``
dataclass.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Iterable, List, Optional

from core.config import default_config_dir
from core.logging_util import get_logger

from .mission import Mission, MissionWaypoint

_log = get_logger("voyage.mission_manager")

#: Subdirectory under ``default_config_dir()`` where missions live.
MISSIONS_DIRNAME = "missions"

#: Index file name. The file lists the manager's known mission
#: ids in display order.
MISSIONS_INDEX_FILENAME = "index.json"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def default_missions_dir() -> str:
    """Per-user missions directory. Lives next to ``config.json``."""
    return os.path.join(default_config_dir(), MISSIONS_DIRNAME)


def _index_path(missions_dir: str) -> str:
    return os.path.join(missions_dir, MISSIONS_INDEX_FILENAME)


def _mission_path(missions_dir: str, mission_id: str) -> str:
    return os.path.join(missions_dir, f"{mission_id}.json")


# ---------------------------------------------------------------------------
# MissionManager
# ---------------------------------------------------------------------------


class MissionManager:
    """In-memory + on-disk mission store.

    Construct with an optional ``missions_dir`` (the default is
    ``~/.unav_pro/missions/``). Tests pass a ``tmp_path`` to
    keep the user's real config untouched.

    The manager is a thin CRUD wrapper. Concurrency: the v1.4
    dialog is single-threaded; the manager does not lock or
    arbitrate. If two C4D sessions write at the same time, the
    last writer wins.
    """

    def __init__(self, missions_dir: Optional[str] = None) -> None:
        self._dir: str = missions_dir or default_missions_dir()
        self._missions: Dict[str, Mission] = {}
        self._order: List[str] = []
        self.reload()

    # -------------------------------------------------------- properties
    @property
    def missions_dir(self) -> str:
        return self._dir

    # ---------------------------------------------------------- introspection
    def __len__(self) -> int:
        return len(self._order)

    def __contains__(self, mission_id: str) -> bool:
        return mission_id in self._missions

    def list_all(self) -> List[Mission]:
        """Return missions in display order. Mutating the
        returned list does not alter the manager's state, but
        mutating the missions themselves does (they are the
        live objects)."""
        return [self._missions[mid] for mid in self._order if mid in self._missions]

    def get(self, mission_id: str) -> Optional[Mission]:
        return self._missions.get(mission_id)

    # ------------------------------------------------------------ CRUD
    def create(self, mission: Mission) -> Mission:
        """Register ``mission`` and persist it. Raises if the
        mission_id is already in use (the dialog's "New" path
        always assigns a fresh id)."""
        if mission.mission_id in self._missions:
            raise ValueError(
                f"mission_id '{mission.mission_id}' already exists"
            )
        self._missions[mission.mission_id] = mission
        self._order.append(mission.mission_id)
        self._save_mission(mission)
        self._save_index()
        return mission

    def update(self, mission: Mission) -> Mission:
        """Persist ``mission`` (must already be registered).
        Updates the in-memory copy and rewrites the on-disk
        file. Raises if ``mission_id`` is unknown."""
        if mission.mission_id not in self._missions:
            raise KeyError(f"unknown mission_id '{mission.mission_id}'")
        mission._touch()  # noqa: SLF001 — manager owns the mtime stamp
        self._missions[mission.mission_id] = mission
        self._save_mission(mission)
        self._save_index()
        return mission

    def delete(self, mission_id: str) -> bool:
        """Drop ``mission_id`` from memory and unlink its file.
        Returns True if the mission existed, False otherwise."""
        if mission_id not in self._missions:
            return False
        self._missions.pop(mission_id, None)
        try:
            self._order.remove(mission_id)
        except ValueError:
            pass
        path = _mission_path(self._dir, mission_id)
        try:
            if os.path.isfile(path):
                os.unlink(path)
        except OSError as exc:
            _log.warning("Could not delete mission %s: %s", path, exc)
        self._save_index()
        return True

    def move(self, src: int, dst: int) -> bool:
        """Reorder missions in the display list. Bounds-checked;
        no-op if ``src`` is out of range."""
        if not (0 <= src < len(self._order)):
            return False
        mid = self._order.pop(src)
        dst = max(0, min(dst, len(self._order)))
        self._order.insert(dst, mid)
        self._save_index()
        return True

    # ---------------------------------------------------------- import/export
    def export_mission(self, mission_id: str, path: str) -> bool:
        """Write a single mission's JSON to an arbitrary path
        (e.g. for sharing). Returns True on success, False if
        the mission is unknown or the write fails."""
        mission = self.get(mission_id)
        if mission is None:
            return False
        try:
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(mission.to_json())
            return True
        except OSError as exc:
            _log.warning("Could not export mission to %s: %s", path, exc)
            return False

    def import_mission(self, path: str) -> Optional[Mission]:
        """Read a mission JSON from an arbitrary path and
        register it. Returns the registered ``Mission``, or
        ``None`` on failure.

        If the imported mission's ``mission_id`` collides with
        an existing one, a fresh id is assigned (so import is
        always non-destructive)."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            _log.warning("Could not read mission %s: %s", path, exc)
            return None
        try:
            mission = Mission.from_json(raw)
        except (TypeError, ValueError) as exc:
            _log.warning("Mission file %s is malformed: %s", path, exc)
            return None
        if mission.mission_id in self._missions:
            from .mission import _new_mission_id  # noqa: PLC0415
            mission.mission_id = _new_mission_id()
        return self.create(mission)

    # ---------------------------------------------------------- persistence
    def reload(self) -> None:
        """Re-read the index + per-mission files from disk.
        Missing files yield an empty store; corrupt files are
        skipped with a warning."""
        self._missions = {}
        self._order = []
        if not os.path.isdir(self._dir):
            return
        index_path = _index_path(self._dir)
        try:
            with open(index_path, "r", encoding="utf-8") as fh:
                index = json.load(fh)
        except (OSError, ValueError, TypeError):
            index = {}
        ordered_ids = list(index.get("mission_ids") or [])

        # Load every JSON file in the directory; the index
        # gives us order, but we trust the directory contents
        # as the authoritative set (so a hand-dropped JSON file
        # appears).
        seen: List[str] = []
        for fname in sorted(os.listdir(self._dir)):
            if fname == MISSIONS_INDEX_FILENAME:
                continue
            if not fname.endswith(".json"):
                continue
            full = os.path.join(self._dir, fname)
            try:
                with open(full, "r", encoding="utf-8") as fh:
                    raw = fh.read()
                # Parse strictly here (not via Mission.from_json,
                # which swallows JSON errors and returns a default
                # mission). A broken file should be skipped, not
                # silently materialise as a blank mission.
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError("top-level JSON must be an object")
                mission = Mission.from_dict(parsed)
            except (OSError, ValueError, TypeError) as exc:
                _log.warning("Skipping corrupt mission file %s: %s", full, exc)
                continue
            mid = mission.mission_id
            if mid in self._missions:
                # Duplicate id on disk — shouldn't happen with the
                # one-file-per-id layout. Take whichever was newer.
                existing = self._missions[mid]
                if mission.modified_iso <= existing.modified_iso:
                    continue
            self._missions[mid] = mission
            seen.append(mid)

        # Rebuild order: indexed ids first (those still on
        # disk), then any newcomers in lexicographic order.
        for mid in ordered_ids:
            if mid in self._missions and mid not in self._order:
                self._order.append(mid)
        for mid in seen:
            if mid not in self._order:
                self._order.append(mid)

    def _save_mission(self, mission: Mission) -> None:
        os.makedirs(self._dir, exist_ok=True)
        path = _mission_path(self._dir, mission.mission_id)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(mission.to_json())
        except OSError as exc:
            _log.warning("Could not write mission %s: %s", path, exc)

    def _save_index(self) -> None:
        os.makedirs(self._dir, exist_ok=True)
        path = _index_path(self._dir)
        payload = {"mission_ids": list(self._order)}
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, sort_keys=True, indent=2)
        except OSError as exc:
            _log.warning("Could not write mission index %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def waypoints_from_bookmarks(
    bookmark_ids: Iterable[str], duration_seconds: float = 4.0,
) -> List[MissionWaypoint]:
    """Build a list of bookmark-kind ``MissionWaypoint``s.
    The dialog uses this when "Add selected bookmarks as
    waypoints" fires."""
    out: List[MissionWaypoint] = []
    for bid in bookmark_ids:
        bid = (bid or "").strip()
        if not bid:
            continue
        out.append(MissionWaypoint(
            kind="bookmark",
            bookmark_id=bid,
            duration_seconds=duration_seconds,
        ))
    return out


def waypoint_from_object(
    *, uid: str, label: str = "",
    catalog_source: Optional[str] = None,
    object_type: Optional[str] = None,
    epoch_jd: Optional[float] = None,
    duration_seconds: float = 4.0,
    notes: str = "",
) -> MissionWaypoint:
    """Build an ``object``-kind waypoint from a search result
    or selected scene object. The cached position will be
    populated by the resolver at playback time."""
    return MissionWaypoint(
        kind="object",
        uid=uid,
        label=label or uid,
        catalog_source=catalog_source,
        object_type=object_type,
        epoch_jd=epoch_jd,
        duration_seconds=duration_seconds,
        notes=notes,
    )
