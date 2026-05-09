"""Mission + Waypoint data model for the v1.4 guided-voyage system.

A *mission* is an ordered sequence of *mission waypoints*. Each
mission waypoint can reference a catalog object by uid, a
free-floating coordinate, a bookmark, or a named anchor. Each
waypoint optionally carries an epoch (so the artist can replay
"Mars in 2026 → Mars in 2030"), an orientation hint for the
cinematic camera, a duration, and free-form notes.

The mission is the **input** to the v1.4 ``camera_path`` and
``playback`` modules. It is also the persistence unit: the
``MissionManager`` reads / writes JSON files from
``~/.unav_pro/missions/`` (one file per mission, plus an
index file).

Compared to the v0.6 ``core/route``:

* A route's waypoints are spatial-only; a mission waypoint
  carries time + camera + duration in addition to the spatial
  reference.
* The route's ``WAYPOINT_KINDS`` set (``object`` /
  ``coordinate`` / ``named``) is a strict subset of the
  mission waypoint set (``object`` / ``coordinate`` /
  ``named`` / ``bookmark``).
* Routes are the rendered C4D spline; missions are the
  artist's intent. The v1.4 ``camera_path.build_route_from_mission``
  helper converts a mission to a route for spline rendering.

Everything here is pure stdlib; no Cinema 4D, no external
deps. Fully unit-tested.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: On-disk schema version. Incremented when the JSON layout changes.
MISSION_SCHEMA_VERSION = 1

#: Allowed waypoint kinds. The original v1.4 four (``object`` /
#: ``coordinate`` / ``named`` / ``bookmark``) are unchanged.
#: v1.9 adds three more:
#:
#:   * ``search_result`` — a uid-backed waypoint that also
#:     remembers the search query that produced it. Behaves
#:     identically to ``object`` at playback time but lets the
#:     analytics / annotations layers explain "this came from
#:     a search for X".
#:   * ``orbital`` — placeholder for an epoch-driven body whose
#:     position is resolved at playback time from the v1.2
#:     ``object_states`` table or from an external ephemeris.
#:     Today the playback path treats it like ``object`` (uid
#:     lookup); v1.x will plug a real propagator behind it.
#:   * ``annotation`` — a text / metadata-only waypoint that
#:     never participates in the camera path. Used to attach
#:     prose to a mission stop without inserting another camera
#:     anchor.
MISSION_WAYPOINT_KINDS: Tuple[str, ...] = (
    "object", "coordinate", "named", "bookmark",
    "search_result", "orbital", "annotation",
)

#: Subset of kinds whose position is *consumed by the camera
#: path*. ``annotation`` waypoints are skipped at build time.
PATH_CONTRIBUTING_KINDS: Tuple[str, ...] = (
    "object", "coordinate", "named", "bookmark",
    "search_result", "orbital",
)

#: Hard cap on per-mission waypoint count. Above this the dialog
#: refuses to add more (the artist can split into two missions).
#: 200 is plenty for a cinematic flythrough.
MAX_WAYPOINTS_PER_MISSION = 200


# ---------------------------------------------------------------------------
# MissionWaypoint
# ---------------------------------------------------------------------------


@dataclass
class MissionWaypoint:
    """One stop on a mission.

    Required fields:

    * ``kind`` — one of ``MISSION_WAYPOINT_KINDS``.

    Per-kind required fields:

    * ``object`` → ``uid``.
    * ``coordinate`` → ``(x_c4d, y_c4d, z_c4d)``.
    * ``named`` → ``label`` (a free name).
    * ``bookmark`` → ``bookmark_id`` (the id field on the
      ``Bookmark`` dataclass).

    Optional fields:

    * ``label`` — display label override.
    * ``epoch_jd`` — the Julian Date the waypoint should be
      observed at; the playback path threads this through to
      the v1.2 Time Navigator.
    * ``orientation_quat`` — ``(w, x, y, z)`` quaternion for
      the cinematic camera. ``None`` means "let the camera
      look toward the next waypoint."
    * ``duration_seconds`` — how long the playback dwells on
      this waypoint. Defaults to ``DEFAULT_DURATION_SECONDS``.
    * ``notes`` — free text the dialog renders below the
      waypoint label.
    * ``catalog_source`` / ``object_type`` — caches so the
      mission survives without an active ``MetadataLookup``.
    * ``x_c4d/y_c4d/z_c4d`` / ``x_pc/y_pc/z_pc`` — cached
      positions; the playback resolver uses them when present
      and re-resolves when missing.
    """

    kind: str
    label: str = ""

    # Object-kind reference.
    uid: Optional[str] = None
    catalog_source: Optional[str] = None
    object_type: Optional[str] = None

    # Bookmark-kind reference.
    bookmark_id: Optional[str] = None

    # Cached position (any kind).
    x_c4d: Optional[float] = None
    y_c4d: Optional[float] = None
    z_c4d: Optional[float] = None
    x_pc: Optional[float] = None
    y_pc: Optional[float] = None
    z_pc: Optional[float] = None

    # Optional time-domain pose.
    epoch_jd: Optional[float] = None

    # Optional cinematic camera hints.
    orientation_quat: Optional[Tuple[float, float, float, float]] = None
    duration_seconds: float = 4.0

    # v1.8 cinematic-polish fields. All optional; the camera-path
    # builder honours them when present and falls back to the
    # v1.4 behaviour when they are not set, so existing missions
    # round-trip unchanged.
    #
    # ``pause_seconds`` is the dwell time at the waypoint *after*
    # arrival but before motion to the next waypoint resumes.
    # Distinct from ``duration_seconds`` (which is travel time).
    # Defaults to 0.0 (no dwell).
    pause_seconds: float = 0.0
    # ``look_at_uid`` and ``look_at_position`` define a camera
    # target the cinematic builder will point the camera at while
    # the cursor is on this waypoint. ``look_at_uid`` resolves
    # via the active MetadataLookup; ``look_at_position`` is a
    # free 3D point in C4D world units. ``orientation_quat``
    # still wins when explicitly set — the look-at is a fallback
    # for "I want to track Mars but I don't want to compute the
    # quaternion myself".
    look_at_uid: Optional[str] = None
    look_at_position: Optional[Tuple[float, float, float]] = None
    # Camera roll about the forward axis, in degrees. Applied
    # after the look-at / orientation step. Defaults to 0.
    roll_deg: float = 0.0

    # v1.9 fields. Additive; v1.4 / v1.8 missions round-trip
    # byte-identical when these are absent.
    #
    # ``camera_offset`` shifts the camera away from the
    # waypoint's position by a fixed (dx, dy, dz) in C4D world
    # units. Useful for "frame Mars from a few units behind" —
    # the navigator still anchors at the waypoint, but the
    # camera path samples the offset position.
    camera_offset: Optional[Tuple[float, float, float]] = None
    # ``tags`` are free-form labels the route-analytics +
    # mission-organizer surfaces use to filter / group
    # waypoints. Lower-cased on entry to keep search consistent.
    tags: List[str] = field(default_factory=list)
    # ``search_query`` is populated when the waypoint kind is
    # ``search_result``; the analytics renderer cites it as the
    # "found via" provenance line.
    search_query: Optional[str] = None

    # Free-form notes.
    notes: str = ""

    def __post_init__(self) -> None:
        if self.kind not in MISSION_WAYPOINT_KINDS:
            raise ValueError(
                f"unknown mission waypoint kind '{self.kind}'; "
                f"valid: {', '.join(MISSION_WAYPOINT_KINDS)}"
            )
        if self.kind == "object" and not self.uid:
            raise ValueError("object waypoint requires non-empty uid")
        if self.kind == "coordinate" and not self.has_c4d_position():
            raise ValueError(
                "coordinate waypoint requires x/y/z_c4d"
            )
        if self.kind == "named" and not (self.label or self.has_c4d_position()):
            raise ValueError(
                "named waypoint requires either a label or a position"
            )
        if self.kind == "bookmark" and not self.bookmark_id:
            raise ValueError("bookmark waypoint requires non-empty bookmark_id")
        # v1.9: search_result and orbital both require a uid
        # (search-result kind also accepts an explicitly cached
        # position so the playback path can resolve it offline).
        if self.kind == "search_result" and not self.uid:
            raise ValueError("search_result waypoint requires non-empty uid")
        if self.kind == "orbital" and not self.uid:
            raise ValueError("orbital waypoint requires non-empty uid")
        # Annotation-only waypoints don't participate in the
        # camera path; they still need a label so the dialog can
        # render them.
        if self.kind == "annotation" and not (self.label or self.notes):
            raise ValueError(
                "annotation waypoint requires either a label or notes"
            )
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be > 0")
        if self.orientation_quat is not None:
            if len(self.orientation_quat) != 4:
                raise ValueError("orientation_quat must be a 4-tuple (w, x, y, z)")
        # v1.8 fields.
        if self.pause_seconds < 0:
            raise ValueError("pause_seconds must be >= 0")
        if self.look_at_position is not None:
            if len(self.look_at_position) != 3:
                raise ValueError(
                    "look_at_position must be a 3-tuple (x, y, z)"
                )
        # v1.9 fields.
        if self.camera_offset is not None:
            if len(self.camera_offset) != 3:
                raise ValueError(
                    "camera_offset must be a 3-tuple (dx, dy, dz)"
                )
        # Tags are normalised once on construction so subsequent
        # search / sort logic can rely on the lower-case form.
        if self.tags:
            self.tags = [
                str(t).strip().lower() for t in self.tags
                if str(t).strip()
            ]

    # ---------------------------------------------------------- predicates
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

    def has_orientation(self) -> bool:
        return self.orientation_quat is not None

    def has_epoch(self) -> bool:
        return self.epoch_jd is not None

    def is_path_contributing(self) -> bool:
        """v1.9: True when the waypoint participates in the
        camera path. ``annotation`` waypoints return False and
        the path builder skips them."""
        return self.kind in PATH_CONTRIBUTING_KINDS

    def has_tag(self, tag: str) -> bool:
        if not tag:
            return False
        return tag.strip().lower() in self.tags

    # ------------------------------------------------------------- friendly
    def display_label(self) -> str:
        if self.label:
            return self.label
        if self.kind == "object" and self.uid:
            return self.uid
        if self.kind == "search_result" and self.uid:
            return self.uid
        if self.kind == "orbital" and self.uid:
            return f"orbital:{self.uid}"
        if self.kind == "bookmark" and self.bookmark_id:
            return f"bookmark:{self.bookmark_id[:8]}"
        if self.kind == "annotation":
            return "annotation"
        return f"<{self.kind}>"

    # -------------------------------------------------------------- (de)ser
    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "kind": self.kind,
            "label": self.label,
            "duration_seconds": float(self.duration_seconds),
        }
        for k in (
            "uid", "catalog_source", "object_type",
            "bookmark_id",
            "x_c4d", "y_c4d", "z_c4d",
            "x_pc", "y_pc", "z_pc",
            "epoch_jd",
            "look_at_uid",
            "search_query",
            "notes",
        ):
            v = getattr(self, k)
            if v is not None and v != "":
                out[k] = v
        if self.orientation_quat is not None:
            out["orientation_quat"] = list(self.orientation_quat)
        if self.look_at_position is not None:
            out["look_at_position"] = list(self.look_at_position)
        # v1.8 fields — only emit when non-default to keep
        # existing v1.4 missions byte-identical on round-trip.
        if self.pause_seconds:
            out["pause_seconds"] = float(self.pause_seconds)
        if self.roll_deg:
            out["roll_deg"] = float(self.roll_deg)
        # v1.9 fields — same convention.
        if self.camera_offset is not None:
            out["camera_offset"] = list(self.camera_offset)
        if self.tags:
            out["tags"] = list(self.tags)
        return out

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MissionWaypoint":
        known = {f.name for f in fields(cls)}
        clean: Dict[str, Any] = {}
        for k, v in (d or {}).items():
            if k not in known:
                continue
            if k == "orientation_quat" and v is not None:
                v = tuple(float(x) for x in v)
            if k == "look_at_position" and v is not None:
                v = tuple(float(x) for x in v)
            if k == "camera_offset" and v is not None:
                v = tuple(float(x) for x in v)
            if k == "tags" and v is not None:
                v = [str(t) for t in v]
            clean[k] = v
        return cls(**clean)


# ---------------------------------------------------------------------------
# Mission
# ---------------------------------------------------------------------------


def _new_mission_id() -> str:
    return uuid.uuid4().hex[:16]


def _now_iso() -> str:
    """ISO8601 UTC timestamp without timezone offset. Stable
    enough for the on-disk created/modified fields; the dialog
    only renders this verbatim."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class Mission:
    """One guided voyage.

    A mission is metadata + a list of ``MissionWaypoint``s. The
    ``mission_id`` is a stable hex string the manager keys off
    (so renames / edits don't break references).

    The ``schema_version`` field is stamped on save and checked
    on load; missions saved with a higher schema version log a
    warning and are loaded best-effort.
    """

    title: str = "Untitled Mission"
    description: str = ""
    waypoints: List[MissionWaypoint] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    mission_id: str = field(default_factory=_new_mission_id)
    created_iso: str = field(default_factory=_now_iso)
    modified_iso: str = field(default_factory=_now_iso)
    schema_version: int = MISSION_SCHEMA_VERSION
    # v1.9: free 3D labels the artist wants to remember at
    # specific scene coordinates. Distinct from waypoints —
    # these don't drive the camera path. Stored as a list of
    # plain dicts here so the mission round-trips through JSON
    # without dragging the SceneAnnotation type into mission.py.
    # The ``annotations`` module wraps them in dataclasses on
    # access.
    scene_annotations: List[Any] = field(default_factory=list)

    # ------------------------------------------------------------ size
    def __len__(self) -> int:
        return len(self.waypoints)

    def __iter__(self):
        return iter(self.waypoints)

    # ------------------------------------------------------------ writes
    def add(self, waypoint: MissionWaypoint) -> MissionWaypoint:
        if len(self.waypoints) >= MAX_WAYPOINTS_PER_MISSION:
            raise ValueError(
                f"mission already has {MAX_WAYPOINTS_PER_MISSION} "
                "waypoints; split into two missions"
            )
        self.waypoints.append(waypoint)
        self._touch()
        return waypoint

    def insert_at(self, index: int, waypoint: MissionWaypoint) -> MissionWaypoint:
        if len(self.waypoints) >= MAX_WAYPOINTS_PER_MISSION:
            raise ValueError(
                f"mission already has {MAX_WAYPOINTS_PER_MISSION} "
                "waypoints; split into two missions"
            )
        index = max(0, min(index, len(self.waypoints)))
        self.waypoints.insert(index, waypoint)
        self._touch()
        return waypoint

    def remove_at(self, index: int) -> Optional[MissionWaypoint]:
        if 0 <= index < len(self.waypoints):
            wp = self.waypoints.pop(index)
            self._touch()
            return wp
        return None

    def move(self, src: int, dst: int) -> bool:
        """Move waypoint ``src`` to position ``dst``. Returns True
        on success (clamps ``dst`` into range)."""
        if not (0 <= src < len(self.waypoints)):
            return False
        wp = self.waypoints.pop(src)
        dst = max(0, min(dst, len(self.waypoints)))
        self.waypoints.insert(dst, wp)
        self._touch()
        return True

    def replace_at(
        self, index: int, waypoint: MissionWaypoint,
    ) -> Optional[MissionWaypoint]:
        if not (0 <= index < len(self.waypoints)):
            return None
        old = self.waypoints[index]
        self.waypoints[index] = waypoint
        self._touch()
        return old

    def clear(self) -> None:
        self.waypoints.clear()
        self._touch()

    def _touch(self) -> None:
        self.modified_iso = _now_iso()

    # ------------------------------------------------------------ totals
    def total_duration_seconds(self) -> float:
        return float(sum(w.duration_seconds for w in self.waypoints))

    def epoch_range(self) -> Optional[Tuple[float, float]]:
        """Return ``(min_epoch_jd, max_epoch_jd)`` over the
        waypoints that carry an explicit epoch, or ``None`` if
        none do."""
        epochs = [w.epoch_jd for w in self.waypoints if w.epoch_jd is not None]
        if not epochs:
            return None
        return (min(epochs), max(epochs))

    # ------------------------------------------------------------ (de)ser
    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "schema_version": int(self.schema_version),
            "mission_id": self.mission_id,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "waypoints": [w.to_dict() for w in self.waypoints],
            "created_iso": self.created_iso,
            "modified_iso": self.modified_iso,
        }
        # v1.9: scene annotations round-trip as plain dicts.
        if self.scene_annotations:
            out["scene_annotations"] = [
                a.to_dict() if hasattr(a, "to_dict") else dict(a)
                for a in self.scene_annotations
            ]
        return out

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Mission":
        d = d or {}
        m = cls(
            title=str(d.get("title") or "Untitled Mission"),
            description=str(d.get("description") or ""),
            tags=[str(t) for t in (d.get("tags") or []) if str(t)],
            mission_id=str(d.get("mission_id") or _new_mission_id()),
            created_iso=str(d.get("created_iso") or _now_iso()),
            modified_iso=str(d.get("modified_iso") or _now_iso()),
            schema_version=int(d.get("schema_version") or MISSION_SCHEMA_VERSION),
        )
        for raw_wp in d.get("waypoints") or []:
            try:
                m.waypoints.append(MissionWaypoint.from_dict(raw_wp))
            except (ValueError, TypeError):
                # Drop unrecoverable waypoints rather than aborting
                # the whole mission load — the dialog logs the count.
                continue
        # v1.9: scene_annotations are plain dicts on disk; the
        # annotations module wraps them in SceneAnnotation
        # dataclasses on demand.
        for raw_a in d.get("scene_annotations") or []:
            if isinstance(raw_a, dict):
                m.scene_annotations.append(raw_a)
        return m

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    @classmethod
    def from_json(cls, s: str) -> "Mission":
        try:
            return cls.from_dict(json.loads(s or "{}"))
        except (TypeError, ValueError):
            return cls()
