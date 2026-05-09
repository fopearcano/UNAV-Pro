"""UNAV Pro v2.1 astrophysical overlay package.

Pure-Python science-aware overlay layers + an orchestrator
that ties them to active datasets. See
``docs/V2_1_ASTROPHYSICAL_OVERLAYS.md``.
"""

from __future__ import annotations

from .overlay_layers import (
    DEFAULT_PM_VECTOR_SCALE_PC,
    LAYER_CATALOG_SOURCE_REGIONS,
    LAYER_CONSTELLATION_BOUNDARIES,
    LAYER_DISTANCE_SHELLS,
    LAYER_MAGNITUDE_SHELLS,
    LAYER_MOTION_VECTORS,
    LAYER_OBJECT_DENSITY_VOLUME,
    LAYER_REDSHIFT_SHELLS,
    LAYER_SOLAR_SYSTEM_ORBITS,
    MAX_MOTION_VECTORS,
    SCIENCE_LAYER_IDS,
    CatalogSourceRegionSettings,
    ConstellationBoundarySettings,
    DistanceShellSettings,
    LayerBuildResult,
    MagnitudeShellSettings,
    MotionVectorSettings,
    ObjectDensityVolumeSettings,
    RedshiftShellSettings,
    SolarSystemOrbitSettings,
    build_catalog_source_regions,
    build_constellation_boundaries,
    build_distance_shells,
    build_magnitude_shells,
    build_motion_vectors,
    build_object_density_volume,
    build_redshift_shells,
    build_solar_system_orbits,
)
from .science_layers import (
    LAYER_SUPPORTED_SOURCES,
    ScienceBundle,
    ScienceLayerSettings,
    build_science_bundle,
    render_warnings,
    to_overlay_bundle,
)

__all__ = [
    "DEFAULT_PM_VECTOR_SCALE_PC",
    "LAYER_CATALOG_SOURCE_REGIONS",
    "LAYER_CONSTELLATION_BOUNDARIES",
    "LAYER_DISTANCE_SHELLS",
    "LAYER_MAGNITUDE_SHELLS",
    "LAYER_MOTION_VECTORS",
    "LAYER_OBJECT_DENSITY_VOLUME",
    "LAYER_REDSHIFT_SHELLS",
    "LAYER_SOLAR_SYSTEM_ORBITS",
    "LAYER_SUPPORTED_SOURCES",
    "MAX_MOTION_VECTORS",
    "SCIENCE_LAYER_IDS",
    "CatalogSourceRegionSettings",
    "ConstellationBoundarySettings",
    "DistanceShellSettings",
    "LayerBuildResult",
    "MagnitudeShellSettings",
    "MotionVectorSettings",
    "ObjectDensityVolumeSettings",
    "RedshiftShellSettings",
    "ScienceBundle",
    "ScienceLayerSettings",
    "SolarSystemOrbitSettings",
    "build_catalog_source_regions",
    "build_constellation_boundaries",
    "build_distance_shells",
    "build_magnitude_shells",
    "build_motion_vectors",
    "build_object_density_volume",
    "build_redshift_shells",
    "build_science_bundle",
    "build_solar_system_orbits",
    "render_warnings",
    "to_overlay_bundle",
]
