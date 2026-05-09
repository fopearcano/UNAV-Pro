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
    PATH_CONTRIBUTING_KINDS,
    Mission,
    MissionWaypoint,
)
from .annotations import (
    MissionAnnotations,
    SceneAnnotation,
    WaypointAnnotation,
    add_scene_annotation,
    build_mission_annotations,
    derive_notes,
    get_scene_annotations,
    remove_scene_annotation_at,
)
from .export import (
    CSV_FIELDS,
    mission_to_csv,
    mission_to_json_file,
    mission_to_markdown,
    write_csv,
    write_markdown,
)
from .route_analytics import (
    DEFAULT_TRAVEL_SPEED_PC_PER_S,
    EPOCH_SPREAD_WARN_THRESHOLD_DAYS,
    RouteAnalytics,
    SegmentMetric,
    analyse_route,
)
from .templates import (
    DEFAULT_TEMPLATE_EPOCH_ISO,
    DEFAULT_TEMPLATE_EPOCH_JD,
    NEAREST_STARS,
    REDSHIFT_ANCHORS,
    SOLAR_SYSTEM_BODIES,
    TEMPLATE_REGISTRY,
    TemplateDescriptor,
    empty_voyage,
    get_template,
    list_templates,
    nearest_stars_tour,
    redshift_tour,
    selected_objects_tour,
    solar_system_tour,
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
