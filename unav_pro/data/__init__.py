"""Data layer for UNAV Pro.

Exposes the local catalog schema, the JSONL/CSV reader/writer, and the
synthetic sample-catalog generator. The data layer never imports
``c4d`` so all of it is unit-testable in plain CPython.
"""

from .catalog_io import (
    CatalogIOError,
    default_sample_catalog_path,
    load_catalog,
    load_sample_catalog,
    validate_catalog,
    write_catalog,
)
from .sample_catalog_generator import generate_objects, write_sample_catalog
from .schema import (
    CatalogObject,
    CSV_FIELDS,
    OBJECT_TYPES,
    REQUIRED_FIELDS,
    SCALE_MODES,
    SCHEMA_VERSION,
    compute_derived_fields,
    compute_derived_for_all,
    display_color_for,
    equatorial_to_cartesian_pc,
    pc_to_c4d_units,
    render_radius_from_magnitude,
    resolve_distance_pc,
    validate_object,
)

__all__ = [
    "CatalogIOError",
    "CatalogObject",
    "CSV_FIELDS",
    "OBJECT_TYPES",
    "REQUIRED_FIELDS",
    "SCALE_MODES",
    "SCHEMA_VERSION",
    "compute_derived_fields",
    "compute_derived_for_all",
    "default_sample_catalog_path",
    "display_color_for",
    "equatorial_to_cartesian_pc",
    "generate_objects",
    "load_catalog",
    "load_sample_catalog",
    "pc_to_c4d_units",
    "render_radius_from_magnitude",
    "resolve_distance_pc",
    "validate_catalog",
    "validate_object",
    "write_catalog",
    "write_sample_catalog",
]
