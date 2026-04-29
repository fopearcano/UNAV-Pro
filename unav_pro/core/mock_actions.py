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


#: Fallback cap when no navigator is in the scene. Picked so the MVP
#: never accidentally tries to materialize a million catalog objects.
_NAVIGATOR_LESS_FALLBACK_CAP = 5_000


def _load_objects_or_message(
    catalog_path: Optional[str],
):
    """Load the bundled (or specified) catalog. Returns either
    ``(objects, None)`` on success or ``(None, status_message)`` on
    failure."""
    from data.catalog_io import (
        CatalogIOError,
        default_sample_catalog_path,
        load_catalog,
    )

    target = catalog_path or default_sample_catalog_path()
    if not os.path.isfile(target):
        return None, f"catalog not found at {target}"
    try:
        return load_catalog(target), None
    except CatalogIOError as exc:
        return None, f"could not load catalog: {exc}"


def _filter_for_active_navigator(objects):
    """Run the spatial filter against the active navigator, if any.

    Returns ``(filtered_objects, status_fragment, used_filter)``.
    ``status_fragment`` is a short human-friendly suffix appended to
    the action's status line. If no navigator exists the input list is
    returned unchanged with ``used_filter=False`` so the caller can
    decide whether to warn or fall back.
    """
    from c4d import documents  # type: ignore

    from c4d_objects.navigation_null import (
        find_navigator,
        get_navigation_filter_params,
        get_navigation_forward_vector,
        get_navigation_origin,
    )
    from core.spatial_filter import filter_for_navigator

    doc = documents.GetActiveDocument()
    if doc is None:
        return objects, "no active document", False
    nav = find_navigator(doc)
    if nav is None:
        return objects, "no UNAV_Navigator in scene", False

    params = get_navigation_filter_params(nav)
    origin = get_navigation_origin(nav)
    forward = get_navigation_forward_vector(nav)
    result = filter_for_navigator(
        objects,
        origin_c4d=(origin.x, origin.y, origin.z),
        forward=(forward.x, forward.y, forward.z),
        params=params,
    )
    return result.objects, result.stats.short_summary(), True


def generate_point_cloud(
    catalog_path: Optional[str] = None,
    max_objects: Optional[int] = None,
    encoding=None,
) -> str:
    """Build the UNAV_Starfield from the bundled sample catalog.

    Behavior:
      * If a UNAV_Navigator exists, the catalog is filtered against
        the navigator's pose and parameters before building. **The
        full catalog is never materialized in the C4D scene.**
      * If no navigator exists, only the first
        ``_NAVIGATOR_LESS_FALLBACK_CAP`` objects are generated and a
        warning is appended to the status.
      * Missing catalog / missing C4D / empty result are all surfaced
        as status strings rather than raised exceptions.
    """

    def _do() -> str:
        try:
            from c4d import documents  # type: ignore
        except ImportError:
            return "Cinema 4D not available; cannot generate point cloud"

        from c4d_objects.point_cloud_builder import build_starfield

        objects, err = _load_objects_or_message(catalog_path)
        if err is not None:
            return err

        if not objects:
            return "catalog is empty; nothing to generate"

        # Optional explicit cap from caller.
        if max_objects is not None and max_objects >= 0:
            objects = objects[:max_objects]

        filtered, frag, used_filter = _filter_for_active_navigator(objects)

        if not used_filter:
            cap = _NAVIGATOR_LESS_FALLBACK_CAP
            if len(filtered) > cap:
                filtered = filtered[:cap]
                suffix = (
                    f"; warning: {frag}; capped to first {cap} objects "
                    "(create a UNAV_Navigator to filter the full catalog)"
                )
            else:
                suffix = f"; warning: {frag}; using full catalog"
        else:
            suffix = f"; filter: {frag}"

        if not filtered:
            return "no objects remain after filtering" + suffix

        doc = documents.GetActiveDocument()
        if doc is None:
            return "no active document; open a scene first"

        _, count = build_starfield(doc, filtered, encoding=encoding)
        return (
            f"generated {count} point objects under 'UNAV_Starfield'"
            + suffix
        )

    return _safe("Generate Point Cloud", _do)


# ---------------------------------------------------------------------------
# Apply View Filter / Regenerate Visible Field
# ---------------------------------------------------------------------------


def apply_view_filter(catalog_path: Optional[str] = None) -> str:
    """Run the spatial filter against the active navigator and report
    the rejection breakdown without touching the C4D scene.

    Useful for tuning navigator parameters before committing to a
    rebuild. Falls back to a clean status message if the navigator or
    catalog is missing.
    """

    def _do() -> str:
        try:
            from c4d import documents  # type: ignore  # noqa: F401
        except ImportError:
            return "Cinema 4D not available; cannot apply view filter"

        objects, err = _load_objects_or_message(catalog_path)
        if err is not None:
            return err
        if not objects:
            return "catalog is empty"

        _filtered, frag, used_filter = _filter_for_active_navigator(objects)
        if not used_filter:
            return f"cannot filter: {frag}"
        return f"filter result — {frag}"

    return _safe("Apply View Filter", _do)


def sync_visible_sector(
    catalog_path: Optional[str] = None,
    encoding=None,
    show_debug_cone: bool = False,
) -> str:
    """Update the UNAV_VisibleSector in place — diff-and-update without
    a full clear.

    Loads the catalog, filters against the active navigator, then
    calls ``core.scene_sync.sync_visible_sector`` which adds newly
    visible objects, keeps still-visible ones, and removes the rest.
    Reports the add/keep/remove counts in the status line.
    """

    def _do() -> str:
        try:
            from c4d import documents  # type: ignore
        except ImportError:
            return "Cinema 4D not available; cannot sync"

        from core.scene_sync import sync_visible_sector as do_sync

        objects, err = _load_objects_or_message(catalog_path)
        if err is not None:
            return err
        if not objects:
            return "catalog is empty"

        filtered, frag, used_filter = _filter_for_active_navigator(objects)
        if not used_filter:
            return f"cannot sync without navigator: {frag}"

        doc = documents.GetActiveDocument()
        if doc is None:
            return "no active document"

        # Determine the scene scale + max_visible from the navigator
        # so the sync respects the navigator's hard cap.
        from c4d_objects.navigation_null import (
            find_navigator,
            get_navigation_filter_params,
        )

        navigator = find_navigator(doc)
        if navigator is None:
            return "no UNAV_Navigator in scene"
        params = get_navigation_filter_params(navigator)
        diff = do_sync(
            doc,
            filtered,
            encoding=encoding,
            scale_mode=params.c4d_scale,
            max_visible=params.max_visible_objects,
            show_debug_cone=show_debug_cone,
        )
        return f"{diff.short_summary()}; filter: {frag}"

    return _safe("Sync Visible Sector", _do)


def toggle_debug_cone(show: bool) -> str:
    """Show or hide the debug cone independently of a sync pass."""

    def _do() -> str:
        try:
            from c4d import documents  # type: ignore
        except ImportError:
            return "Cinema 4D not available"
        from core.scene_sync import update_debug_cone

        doc = documents.GetActiveDocument()
        if doc is None:
            return "no active document"
        return update_debug_cone(doc, show=bool(show))

    return _safe("Debug Cone", _do)


def regenerate_visible_field(
    catalog_path: Optional[str] = None,
    encoding=None,
) -> str:
    """Clear any existing UNAV_Starfield and rebuild it from the
    current navigator's filter result. Equivalent to Clear Scene
    followed by Generate Point Cloud, packaged as one click for the
    common iterate-and-tweak workflow.
    """

    def _do() -> str:
        try:
            from c4d import documents  # type: ignore
        except ImportError:
            return "Cinema 4D not available; cannot regenerate"

        from c4d_objects.point_cloud_builder import (
            build_starfield,
            clear_starfield,
        )

        objects, err = _load_objects_or_message(catalog_path)
        if err is not None:
            return err
        if not objects:
            return "catalog is empty"

        filtered, frag, used_filter = _filter_for_active_navigator(objects)
        if not used_filter:
            return f"cannot regenerate without navigator: {frag}"
        if not filtered:
            return "no objects remain after filtering; " + frag

        doc = documents.GetActiveDocument()
        if doc is None:
            return "no active document"

        removed = clear_starfield(doc)
        _, count = build_starfield(
            doc, filtered, replace_existing=False, encoding=encoding,
        )
        prefix = f"removed {removed} prior, " if removed else ""
        return (
            f"{prefix}generated {count} point objects under 'UNAV_Starfield'"
            f"; filter: {frag}"
        )

    return _safe("Regenerate Visible Field", _do)


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
