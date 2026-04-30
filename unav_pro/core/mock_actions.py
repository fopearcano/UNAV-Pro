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

# v0.7 — last render-backend stats from the most recent
# ``sync_visible_sector`` call. The dialog's render-stats strip
# reads this; tests can inspect it directly.
_LAST_RENDER_STATS = None
_LAST_RENDER_BACKEND_MODE = None


def last_render_stats():
    """Return the ``BackendStats`` from the most recent
    ``sync_visible_sector`` call, or ``None`` if none has run yet."""
    return _LAST_RENDER_STATS


def last_render_backend_mode():
    """Return the render-mode token used by the most recent sync, or
    ``None``. Useful for the dialog and for v0.7 diagnostics."""
    return _LAST_RENDER_BACKEND_MODE


def _safe(label: str, fn, *args, **kwargs) -> str:
    """Wrap an action body so exceptions never leak into the dialog.

    Adds the ``label`` prefix and the elapsed-ms suffix the dialog's
    status log expects. Returns ``"<label> FAILED: <repr>"`` on any
    raise; the traceback is logged at ``ERROR`` level so the
    diagnostics dialog can show it.
    """
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


def _active_document(label: str):
    """Return ``(doc, error_message)``.

    ``doc`` is the active C4D ``BaseDocument`` when the host is
    available and a document is open; ``error_message`` is a status
    string ready to return from the action when either is missing.
    Exactly one of the two is non-None.

    Centralizes the c4d-not-available + no-active-document path that
    every scene-touching action would otherwise duplicate.
    """
    try:
        from c4d import documents  # type: ignore
    except ImportError:
        verb = label.lower() if label else "perform action"
        return None, f"Cinema 4D not available; cannot {verb}"
    doc = documents.GetActiveDocument()
    if doc is None:
        return None, "no active document; open a scene first"
    return doc, None


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
        doc, err = _active_document("create navigation null")
        if err is not None:
            return err

        from c4d_objects.navigation_null import (
            CAMERA_NAME,
            NAVIGATOR_NAME,
            RAY_NAME,
            ensure_navigator,
        )

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


def _stream_for_active_navigator(doc):
    """v0.2 sector-streaming entry point.

    Resolves the active navigator + the persisted dataset registry,
    streams candidates through the spatial index when possible, and
    returns ``(filtered_objects, status_fragment, used_filter,
    stream_result)``. Falls back to the same shape as
    ``_filter_for_active_navigator`` when no navigator or no enabled
    datasets exist, so callers can keep the old fallback path.
    """
    from c4d_objects.navigation_null import (
        find_navigator,
        get_navigation_filter_params,
        get_navigation_forward_vector,
        get_navigation_origin,
    )
    from core.dataset_registry import (
        DatasetRegistry, default_registry_path,
    )
    from core.sector_streaming import (
        DEFAULT_DATASET_SIZE_WARNING,
        stream_sector_for_active_datasets,
    )

    nav = find_navigator(doc)
    if nav is None:
        return [], "no UNAV_Navigator in scene", False, None

    registry = DatasetRegistry.load(default_registry_path())
    if not registry.enabled_entries():
        return [], "no enabled datasets in registry", False, None

    params = get_navigation_filter_params(nav)
    origin = get_navigation_origin(nav)
    forward = get_navigation_forward_vector(nav)

    stream = stream_sector_for_active_datasets(
        registry, params,
        origin_c4d=(origin.x, origin.y, origin.z),
        forward=(forward.x, forward.y, forward.z),
        dataset_size_warning=DEFAULT_DATASET_SIZE_WARNING,
    )
    frag = stream.short_summary()
    return stream.objects, frag, True, stream


def _publish_streamed_lookup(stream) -> None:
    """Side-effect: install the streamed objects into the default
    metadata lookup so the inspector can show full records for any
    visible-sector object the user clicks. Marker-only fallback
    still applies for objects outside the visible sector."""
    if stream is None or not stream.objects:
        return
    try:
        from core.metadata_lookup import MetadataLookup, set_default_lookup

        set_default_lookup(MetadataLookup(stream.objects))
    except Exception:  # noqa: BLE001 — boundary; logger only
        _log.exception("Failed to install streamed lookup")


def _format_stream_warnings(stream) -> str:
    """Concatenate warnings + errors from a stream result into a
    short, human-friendly suffix for the dialog log."""
    if stream is None:
        return ""
    parts = []
    for w in stream.warnings():
        parts.append(f"warn: {w}")
    for e in stream.errors():
        parts.append(f"err: {e}")
    if not parts:
        return ""
    return " | " + " | ".join(parts)


def generate_point_cloud(
    catalog_path: Optional[str] = None,
    max_objects: Optional[int] = None,
    encoding=None,
    safety_limits=None,
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
        doc, err = _active_document("generate point cloud")
        if err is not None:
            return err

        from c4d_objects.navigation_null import find_navigator
        from c4d_objects.point_cloud_builder import build_starfield
        from core.safety import (
            LEVEL_BLOCKED, LEVEL_WARN, SafetyLimits, evaluate_generate,
        )

        limits = safety_limits or SafetyLimits()

        # v0.2: prefer registry-driven streaming. If no enabled
        # datasets, fall back to the bundled-sample path so the
        # quick-start workflow still works on a brand-new install.
        filtered, frag, used_filter, stream = _stream_for_active_navigator(doc)
        used_streaming = used_filter and stream is not None
        warning_suffix = _format_stream_warnings(stream)

        if not used_filter or not filtered:
            objects, load_err = _load_objects_or_message(catalog_path)
            if load_err is not None:
                return load_err
            if not objects:
                return "catalog is empty; nothing to generate"
            if max_objects is not None and max_objects >= 0:
                objects = objects[:max_objects]
            filtered, frag, used_filter = _filter_for_active_navigator(objects)
            warning_suffix = ""  # streaming did not run

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
            tag = "stream" if used_streaming else "filter"
            suffix = f"; {tag}: {frag}{warning_suffix}"

        if not filtered:
            return "no objects remain after filtering" + suffix

        # Safety gate. Block / warn / allow based on the active limits.
        has_navigator = find_navigator(doc) is not None
        decision = evaluate_generate(
            len(filtered), limits=limits, has_navigator=has_navigator,
        )
        if decision.level == LEVEL_BLOCKED:
            return f"safety: {decision.short_summary()}"
        if decision.level == LEVEL_WARN:
            suffix = f"; safety: {decision.short_summary()}" + suffix

        if used_streaming:
            _publish_streamed_lookup(stream)

        _, count = build_starfield(
            doc, filtered, encoding=encoding,
            include_full_metadata=limits.embed_full_metadata_in_marker,
        )
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
        doc, err = _active_document("apply view filter")
        if err is not None:
            return err
        del doc  # only used to surface "no active document" cleanly

        objects, load_err = _load_objects_or_message(catalog_path)
        if load_err is not None:
            return load_err
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
    render_mode: Optional[str] = None,
) -> str:
    """Update the UNAV_VisibleSector in place — diff-and-update without
    a full clear.

    Loads the catalog, filters against the active navigator, then
    calls ``core.scene_sync.sync_visible_sector`` which adds newly
    visible objects, keeps still-visible ones, and removes the rest.
    Reports the add/keep/remove counts in the status line.
    """

    def _do() -> str:
        doc, err = _active_document("sync visible sector")
        if err is not None:
            return err

        from core.scene_sync import sync_visible_sector as do_sync
        from c4d_objects.navigation_null import (
            find_navigator,
            get_navigation_filter_params,
        )

        # v0.2 streaming path. When the registry has enabled
        # datasets, only the chunks the cone touches reach the
        # plugin; the rest stays on disk.
        filtered, frag, used_filter, stream = _stream_for_active_navigator(doc)
        used_streaming = used_filter and stream is not None
        warning_suffix = _format_stream_warnings(stream)

        if not used_filter:
            # Fall back to the bundled-sample path so brand-new
            # users still get a working sync on day zero.
            objects, load_err = _load_objects_or_message(catalog_path)
            if load_err is not None:
                return load_err
            if not objects:
                return "catalog is empty"
            filtered, frag, used_filter = _filter_for_active_navigator(objects)
            warning_suffix = ""

        if not used_filter:
            return f"cannot sync without navigator: {frag}"

        navigator = find_navigator(doc)
        if navigator is None:
            return "no UNAV_Navigator in scene"
        params = get_navigation_filter_params(navigator)

        if used_streaming:
            _publish_streamed_lookup(stream)

        diff = do_sync(
            doc,
            filtered,
            encoding=encoding,
            scale_mode=params.c4d_scale,
            max_visible=params.max_visible_objects,
            show_debug_cone=show_debug_cone,
            render_mode=render_mode,
        )
        global _LAST_RENDER_STATS, _LAST_RENDER_BACKEND_MODE
        _LAST_RENDER_STATS = diff.backend_stats
        _LAST_RENDER_BACKEND_MODE = diff.backend_mode
        tag = "stream" if used_streaming else "filter"
        return f"{diff.short_summary()}; {tag}: {frag}{warning_suffix}"

    return _safe("Sync Visible Sector", _do)


def toggle_debug_cone(show: bool) -> str:
    """Show or hide the debug cone independently of a sync pass."""

    def _do() -> str:
        doc, err = _active_document("toggle debug cone")
        if err is not None:
            return err
        from core.scene_sync import update_debug_cone
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
        doc, err = _active_document("regenerate visible field")
        if err is not None:
            return err

        from c4d_objects.point_cloud_builder import (
            build_starfield,
            clear_starfield,
        )

        # v0.2: streaming path first; fall back to bundled-sample
        # when no registry entries are enabled.
        filtered, frag, used_filter, stream = _stream_for_active_navigator(doc)
        used_streaming = used_filter and stream is not None
        warning_suffix = _format_stream_warnings(stream)

        if not used_filter:
            objects, load_err = _load_objects_or_message(catalog_path)
            if load_err is not None:
                return load_err
            if not objects:
                return "catalog is empty"
            filtered, frag, used_filter = _filter_for_active_navigator(objects)
            warning_suffix = ""

        if not used_filter:
            return f"cannot regenerate without navigator: {frag}"
        if not filtered:
            return "no objects remain after filtering; " + frag

        if used_streaming:
            _publish_streamed_lookup(stream)

        removed = clear_starfield(doc)
        _, count = build_starfield(
            doc, filtered, replace_existing=False, encoding=encoding,
        )
        prefix = f"removed {removed} prior, " if removed else ""
        tag = "stream" if used_streaming else "filter"
        return (
            f"{prefix}generated {count} point objects under 'UNAV_Starfield'"
            f"; {tag}: {frag}{warning_suffix}"
        )

    return _safe("Regenerate Visible Field", _do)


# ---------------------------------------------------------------------------
# Clear Scene (UNAV objects only)
# ---------------------------------------------------------------------------


def clear_scene() -> str:
    """Remove every UNAV-tagged object from the active document. Other
    objects in the scene are untouched."""

    def _do() -> str:
        doc, err = _active_document("clear scene")
        if err is not None:
            return err

        from c4d_objects.point_cloud_builder import clear_starfield

        removed = clear_starfield(doc)
        if removed == 0:
            return "no UNAV objects in scene"
        return f"removed {removed} UNAV objects"

    return _safe("Clear Scene", _do)


# ---------------------------------------------------------------------------
# Save / Load UNAV State, Reset Preferences
# ---------------------------------------------------------------------------


_BC_ID_UNAV_STATE = 1000021  # private slot on the BaseDocument


def save_unav_state(
    *,
    route=None,
    encoding=None,
    config=None,
    notes: str = "",
) -> str:
    """Persist the current UNAV state to a sidecar file next to the
    scene **and** into the document's BaseContainer so it travels
    with the .c4d file.

    Failures are surfaced as status strings. Missing pieces (no
    navigator in scene, empty route) are recorded but do not block
    the save.
    """

    def _do() -> str:
        doc, err = _active_document("save UNAV state")
        if err is not None:
            return err

        from core.dataset_registry import (
            DatasetRegistry, default_registry_path,
        )
        from core.project_state import (
            gather_project_state, save_project_state, sidecar_path_for,
        )

        # Read live navigator params, if any.
        navigator_params = None
        try:
            from c4d_objects.navigation_null import (
                find_navigator, get_navigation_filter_params,
            )
            nav = find_navigator(doc)
            if nav is not None:
                navigator_params = get_navigation_filter_params(nav)
        except Exception:  # noqa: BLE001 — defensive
            navigator_params = None

        registry = DatasetRegistry.load(default_registry_path())

        state = gather_project_state(
            registry=registry,
            navigator=navigator_params,
            route=route,
            encoding=encoding,
            config=config,
            notes=notes,
        )

        # Sidecar JSON.
        scene_path = doc.GetDocumentPath() and doc.GetDocumentName()
        if scene_path:
            scene_path = doc.GetDocumentName()
        sidecar = sidecar_path_for(scene_path)
        wrote = save_project_state(state, sidecar)

        # Scene-level BaseContainer slot. Failures here mean the
        # state will not travel with the .c4d save, but the sidecar
        # JSON still survives — log + report rather than silently
        # claim success.
        scene_container_ok = True
        try:
            doc.GetDataInstance()[_BC_ID_UNAV_STATE] = state.to_json()
        except Exception as exc:  # noqa: BLE001 — boundary handler
            scene_container_ok = False
            _log.warning("Could not write state to scene container: %s", exc)

        scene_marker = "✓" if scene_container_ok else "FAILED"
        if wrote is None:
            return (
                f"Save UNAV State: scene container {scene_marker}; "
                "sidecar write failed."
            )
        return (
            f"Save UNAV State: scene container {scene_marker}; "
            f"sidecar at {wrote}"
        )

    return _safe("Save UNAV State", _do)


def load_unav_state() -> str:
    """Reload the project state into the live registry. The dialog
    handler picks up the returned dict via the ``_state_apply``
    side-channel when running inside C4D; this wrapper only reports
    a status."""

    def _do() -> str:
        doc, err = _active_document("load UNAV state")
        if err is not None:
            return err

        from core.dataset_registry import (
            DatasetRegistry, default_registry_path,
        )
        from core.project_state import (
            ProjectState, apply_project_state, load_project_state,
            sidecar_path_for,
        )

        # 1. Try the document's BaseContainer (scene-level metadata).
        state: ProjectState = ProjectState()
        source = "none"
        try:
            raw = doc.GetDataInstance().GetString(_BC_ID_UNAV_STATE)
        except Exception as exc:  # noqa: BLE001 — boundary handler
            _log.warning("Could not read state from scene container: %s", exc)
            raw = ""
        if raw:
            state = ProjectState.from_json(raw)
            source = "scene container"
        else:
            # 2. Fall back to sidecar JSON.
            sidecar = sidecar_path_for(doc.GetDocumentName())
            if os.path.isfile(sidecar):
                state = load_project_state(sidecar)
                source = sidecar

        if state.schema_version == 0 or (
            not state.navigator and not state.route
            and not state.visual_encoding and not state.enabled_datasets
        ):
            return "Load UNAV State: no UNAV state found in scene or sidecar."

        registry_path = default_registry_path()
        registry = DatasetRegistry.load(registry_path)
        applied = apply_project_state(state, registry=registry)
        # Persist registry's enabled-flag changes so the dataset
        # manager picks them up.
        try:
            registry.save(registry_path)
        except OSError:
            pass
        return (
            f"Load UNAV State (from {source}): "
            f"{applied['report'].short_summary()}"
        )

    return _safe("Load UNAV State", _do)


def reset_preferences(*, delete_file: bool = False) -> str:
    """Wipe the per-user config back to defaults. Does **not** touch
    project state files or the dataset registry — those are owned by
    different surfaces."""

    def _do() -> str:
        from core.config import default_config_path, reset_config

        path = default_config_path()
        reset_config(path, delete_file=delete_file)
        suffix = " (file removed)" if delete_file else " (rewritten with defaults)"
        return f"Reset Preferences: {path}{suffix}"

    return _safe("Reset Preferences", _do)
