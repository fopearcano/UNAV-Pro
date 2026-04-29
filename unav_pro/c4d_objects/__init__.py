"""C4D scene-object plugin classes.

Currently exposes the point-cloud builder (creates and clears the
``UNAV_Starfield`` null hierarchy from a catalog) and the navigation
null hierarchy. Reserved for the upcoming ``UnavUniverse`` /
``UnavDataset`` (ObjectData) and ``UnavFilterCone`` (TagData) classes
named in PLUGIN_STRATEGY §4.1.
"""

from .navigation_null import (
    CAMERA_NAME,
    NAVIGATOR_NAME,
    RAY_NAME,
    USER_DATA_FIELD_NAMES,
    ensure_navigator,
    find_navigator,
    get_navigation_filter_params,
    get_navigation_forward_vector,
    get_navigation_origin,
    user_data_defaults,
)
from .point_cloud_builder import (
    STARFIELD_NAME,
    build_point_object,
    build_starfield,
    clear_starfield,
    color_for_object,
    find_starfield,
    is_unav_object,
    marker_for_object,
    position_for_object,
    radius_for_object,
)

__all__ = [
    "CAMERA_NAME",
    "NAVIGATOR_NAME",
    "RAY_NAME",
    "STARFIELD_NAME",
    "USER_DATA_FIELD_NAMES",
    "build_point_object",
    "build_starfield",
    "clear_starfield",
    "color_for_object",
    "ensure_navigator",
    "find_navigator",
    "find_starfield",
    "get_navigation_filter_params",
    "get_navigation_forward_vector",
    "get_navigation_origin",
    "is_unav_object",
    "marker_for_object",
    "position_for_object",
    "radius_for_object",
    "user_data_defaults",
]
