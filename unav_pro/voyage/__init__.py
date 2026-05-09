"""UNAV Pro v1.4 voyage system.

Mission + cinematic camera + deterministic playback layered on
top of the v1.0–v1.3 stack. See ``docs/V1_4_GUIDED_VOYAGES.md``
for the milestone overview.
"""

from __future__ import annotations

from .camera_path import (
    CameraPath,
    CameraPathConfig,
    CameraSample,
    IDENTITY_QUAT,
    INTERP_LINEAR,
    INTERP_MODES,
    INTERP_SMOOTH,
    PREVIEW_SPLINE_NAME,
    Quaternion,
    build_camera_path,
    build_preview_spline_data,
    build_route_from_mission,
    tessellate_path,
)
from .mission import (
    MAX_WAYPOINTS_PER_MISSION,
    MISSION_SCHEMA_VERSION,
    MISSION_WAYPOINT_KINDS,
    Mission,
    MissionWaypoint,
)
from .mission_manager import (
    MISSIONS_DIRNAME,
    MISSIONS_INDEX_FILENAME,
    MissionManager,
    default_missions_dir,
    waypoint_from_object,
    waypoints_from_bookmarks,
)
from .playback import (
    DEFAULT_MAX_VISIBLE_OBJECTS,
    DEFAULT_STEPS_PER_SECOND,
    DEFAULT_SYNC_EVERY_N_STEPS,
    MIN_INTERVAL_SECONDS_FOR_FULL_SYNC,
    Playback,
    PlaybackConfig,
    PlaybackTick,
    make_playback,
)

__all__ = [
    "CameraPath", "CameraPathConfig", "CameraSample",
    "IDENTITY_QUAT", "Quaternion",
    "build_camera_path", "build_route_from_mission",
    "MAX_WAYPOINTS_PER_MISSION", "MISSION_SCHEMA_VERSION",
    "MISSION_WAYPOINT_KINDS",
    "Mission", "MissionWaypoint",
    "MISSIONS_DIRNAME", "MISSIONS_INDEX_FILENAME",
    "MissionManager", "default_missions_dir",
    "waypoint_from_object", "waypoints_from_bookmarks",
    "DEFAULT_MAX_VISIBLE_OBJECTS", "DEFAULT_STEPS_PER_SECOND",
    "DEFAULT_SYNC_EVERY_N_STEPS", "MIN_INTERVAL_SECONDS_FOR_FULL_SYNC",
    "Playback", "PlaybackConfig", "PlaybackTick", "make_playback",
]
