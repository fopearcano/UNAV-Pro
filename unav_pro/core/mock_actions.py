"""Action handlers wired to the main dialog buttons.

Originally a pure-mock module; now a mixed module:

  * ``load_dataset`` — loads the bundled local sample catalog (no
    network access). Falls back to a clear status message when the
    sample is missing.
  * ``generate_point_cloud`` — builds the ``UNAV_Starfield`` null
    hierarchy in the active C4D document.
  * ``clear_scene`` — removes only UNAV-tagged objects from the
    active document.
  * ``create_navigation_null`` — still a stub; the navigation
    controller lands in a later phase.

Every handler returns a short status string; failures are reported as
strings so the dialog event loop never sees an exception.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from .logging_util import get_logger

_log = get_logger("actions")


def _safe(label: str, fn, *args, **kwargs) -> str:
    started = time.monotonic()
    try:
        result = fn(*args, **kwargs)
        elapsed_ms = (time.monotonic() - started) * 1000.0
        msg = f"{label}: {result} ({elapsed_ms:.1f} ms)"
        _log.info(msg)
        return msg
    except Exception as exc:  # noqa: BLE001 — boundary handler
        msg = f"{label} FAILED: {exc!r}"
        _log.exception(msg)
        return msg


# ---------------------------------------------------------------------------
# Load Dataset
# ---------------------------------------------------------------------------


def load_dataset(path: Optional[str] = None) -> str:
    """Load a UNAV catalog. ``path=None`` loads the bundled sample.

    Reports the row count and source. Missing or corrupt files surface
    as a status message rather than an exception.
    """

    def _do() -> str:
        # Local imports keep the module importable in environments where
        # the data layer's dependencies (none today) might not be set up.
        from data.catalog_io import (
            CatalogIOError,
            default_sample_catalog_path,
            load_catalog,
        )

        target = path or default_sample_catalog_path()
        if not os.path.isfile(target):
            return (
                f"sample catalog not found at {target}; "
                "run sample_catalog_generator.write_sample_catalog() to create it"
            )
        try:
            objects = load_catalog(target)
        except CatalogIOError as exc:
            return f"could not load catalog: {exc}"
        return f"loaded {len(objects)} objects from {os.path.basename(target)}"

    return _safe("Load Dataset", _do)


# ---------------------------------------------------------------------------
# Create Navigation Null (still a stub)
# ---------------------------------------------------------------------------


def create_navigation_null() -> str:
    """Ensure the UNAV_Navigator hierarchy exists in the active scene.

    If the navigator already exists, it is selected rather than
    duplicated. Reports whether the hierarchy was created or already
    present.
    """

    def _do() -> str:
        try:
            from c4d import documents  # type: ignore
        except ImportError:
            return "Cinema 4D not available; cannot create navigation null"

        from c4d_objects.navigation_null import (
            CAMERA_NAME,
            NAVIGATOR_NAME,
            RAY_NAME,
            ensure_navigator,
        )

        doc = documents.GetActiveDocument()
        if doc is None:
            return "no active document; open a scene first"

        _, was_created = ensure_navigator(doc)
        if was_created:
            return (
                f"created '{NAVIGATOR_NAME}' with child "
                f"'{CAMERA_NAME}' and '{RAY_NAME}'"
            )
        return f"'{NAVIGATOR_NAME}' already exists; selected it"

    return _safe("Create Navigation Null", _do)


# ---------------------------------------------------------------------------
# Generate Point Cloud
# ---------------------------------------------------------------------------


def generate_point_cloud(
    catalog_path: Optional[str] = None,
    max_objects: Optional[int] = None,
) -> str:
    """Build the UNAV_Starfield from the bundled sample catalog (or
    ``catalog_path`` if provided). Returns a status string.

    Behavior:
      * If Cinema 4D is unavailable (e.g. running outside the host),
        reports the limitation and exits cleanly.
      * If the catalog file is missing, reports it and exits cleanly.
      * On success, builds the starfield and reports the count.
    """

    def _do() -> str:
        try:
            import c4d  # type: ignore
            from c4d import documents  # type: ignore
        except ImportError:
            return "Cinema 4D not available; cannot generate point cloud"

        from data.catalog_io import (
            CatalogIOError,
            default_sample_catalog_path,
            load_catalog,
        )
        from c4d_objects.point_cloud_builder import build_starfield

        target = catalog_path or default_sample_catalog_path()
        if not os.path.isfile(target):
            return f"catalog not found at {target}"

        try:
            objects = load_catalog(target)
        except CatalogIOError as exc:
            return f"could not load catalog: {exc}"

        if max_objects is not None and max_objects >= 0:
            objects = objects[:max_objects]

        if not objects:
            return "catalog is empty; nothing to generate"

        doc = documents.GetActiveDocument()
        if doc is None:
            return "no active document; open a scene first"

        _, count = build_starfield(doc, objects)
        return f"generated {count} point objects under 'UNAV_Starfield'"

    return _safe("Generate Point Cloud", _do)


# ---------------------------------------------------------------------------
# Clear Scene (UNAV objects only)
# ---------------------------------------------------------------------------


def clear_scene() -> str:
    """Remove every UNAV-tagged object from the active document. Other
    objects in the scene are untouched."""

    def _do() -> str:
        try:
            from c4d import documents  # type: ignore
        except ImportError:
            return "Cinema 4D not available; cannot clear scene"

        from c4d_objects.point_cloud_builder import clear_starfield

        doc = documents.GetActiveDocument()
        if doc is None:
            return "no active document"
        removed = clear_starfield(doc)
        if removed == 0:
            return "no UNAV objects in scene"
        return f"removed {removed} UNAV objects"

    return _safe("Clear Scene", _do)
