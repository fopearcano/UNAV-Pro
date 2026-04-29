"""C4D scene-object plugin classes.

Currently exposes the point-cloud builder (creates and clears the
``UNAV_Starfield`` null hierarchy from a catalog). Reserved for the
upcoming ``UnavUniverse`` / ``UnavDataset`` (ObjectData) and
``UnavFilterCone`` (TagData) classes named in PLUGIN_STRATEGY §4.1.
"""

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
    "STARFIELD_NAME",
    "build_point_object",
    "build_starfield",
    "clear_starfield",
    "color_for_object",
    "find_starfield",
    "is_unav_object",
    "marker_for_object",
    "position_for_object",
    "radius_for_object",
]
