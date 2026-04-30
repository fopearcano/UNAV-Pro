"""UNAV Pro metadata inspection panel.

Reads the active C4D selection's UNAV marker container, looks up the
full record in a ``MetadataLookup``, and produces:

  * A multi-line text rendering for the dialog's metadata panel
    (``InspectionResult.display_text``).
  * A short status line for the dialog's log area
    (``InspectionResult.status_line``).
  * A JSON blob suitable for "Copy Metadata JSON" buttons
    (``InspectionResult.clipboard_json``).

The c4d-bound entry point is ``inspect_active_selection``; pure
formatters operate on plain Python data and are unit-tested without
Cinema 4D.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False

from c4d_objects.point_cloud_builder import (
    MARKER_KEY_CATALOG_SOURCE,
    MARKER_KEY_DEC_DEG,
    MARKER_KEY_DISTANCE_PC,
    MARKER_KEY_IS_UNAV,
    MARKER_KEY_KIND,
    MARKER_KEY_METADATA_JSON,
    MARKER_KEY_NAME,
    MARKER_KEY_OBJECT_TYPE,
    MARKER_KEY_RA_DEG,
    MARKER_KEY_UID,
)
from core.logging_util import get_logger
from core.metadata_lookup import MetadataLookup, default_lookup
from core.plugin_ids import BC_ID_UNAV_MARKER
from data.connectors.redshift_distance import (
    DISTANCE_METHOD_REDSHIFT_PROXY,
    DISTANCE_PROXY_WARNING_TEXT,
)
from data.schema import CatalogObject

_log = get_logger("ui.metadata_panel")

# ---------------------------------------------------------------------------
# Status enum (string constants — easier to assert in tests)
# ---------------------------------------------------------------------------

STATUS_NO_DOC = "no_doc"
STATUS_NO_SELECTION = "no_selection"
STATUS_NOT_UNAV = "not_unav"
STATUS_FOUND_MARKER_ONLY = "found_marker_only"
STATUS_FOUND_FULL = "found_full"

#: A status the dialog should report cleanly when the user clicks
#: Copy without inspecting anything first.
STATUS_NO_INSPECTION = "no_inspection"

# Cap the inline JSON preview so the panel doesn't blow up on
# pathological raw blobs. The clipboard copy is always full-fidelity.
_INLINE_JSON_MAX_CHARS = 2000


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


_MARKER_KEY_NAMES = {
    MARKER_KEY_IS_UNAV: "is_unav",
    MARKER_KEY_KIND: "kind",
    MARKER_KEY_UID: "uid",
    MARKER_KEY_CATALOG_SOURCE: "catalog_source",
    MARKER_KEY_OBJECT_TYPE: "object_type",
    MARKER_KEY_NAME: "name",
    MARKER_KEY_METADATA_JSON: "metadata_json",
    MARKER_KEY_RA_DEG: "ra_deg",
    MARKER_KEY_DEC_DEG: "dec_deg",
    MARKER_KEY_DISTANCE_PC: "distance_parsec",
}


@dataclass
class InspectionResult:
    """Outcome of inspecting a C4D selection.

    Pure data; no c4d types. The panel populates one of these in the
    c4d-bound path and the dialog reads the formatted strings from
    its properties.
    """

    status: str
    object_name: Optional[str] = None
    marker: Optional[Dict[int, Any]] = None
    catalog_object: Optional[CatalogObject] = None

    @property
    def display_text(self) -> str:
        """Multi-line text rendering for the dialog's metadata panel."""
        return _format_display_text(self)

    @property
    def status_line(self) -> str:
        """One-line status the dialog appends to its log after each
        inspection."""
        return _format_status_line(self)

    @property
    def clipboard_json(self) -> str:
        """JSON payload the **Copy Metadata JSON** button emits."""
        return _format_clipboard_json(self)


# ---------------------------------------------------------------------------
# Pure formatters
# ---------------------------------------------------------------------------


def _format_status_line(result: InspectionResult) -> str:
    if result.status == STATUS_NO_DOC:
        return "Inspect: no active document."
    if result.status == STATUS_NO_SELECTION:
        return "Inspect: nothing selected."
    if result.status == STATUS_NOT_UNAV:
        return f"Inspect: '{result.object_name or '<unnamed>'}' is not a UNAV object."
    uid = (result.marker or {}).get(MARKER_KEY_UID, "")
    name = result.object_name or "<unnamed>"
    if result.status == STATUS_FOUND_FULL:
        return f"Inspect: '{name}' [{uid}] — full record loaded."
    if result.status == STATUS_FOUND_MARKER_ONLY:
        return f"Inspect: '{name}' [{uid}] — marker only (no catalog match)."
    if result.status == STATUS_NO_INSPECTION:
        return "Inspect: nothing to copy; click Inspect first."
    return f"Inspect: status={result.status}"


def _fmt_optional_float(value: Any, fmt: str = "{:.6g}") -> Optional[str]:
    if value is None:
        return None
    try:
        return fmt.format(float(value))
    except (TypeError, ValueError):
        return None


def _safe_parse_meta(blob: Optional[str]) -> Dict[str, Any]:
    """Parse a ``metadata_json`` string blob; return ``{}`` on any
    failure. Used by the inspector to look up survey / object class /
    distance-method tags without aborting the whole render."""
    if not blob:
        return {}
    try:
        parsed = json.loads(blob)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _format_display_text(result: InspectionResult) -> str:
    if result.status == STATUS_NO_DOC:
        return "No active document. Open a scene to inspect a UNAV object."
    if result.status == STATUS_NO_SELECTION:
        return (
            "Nothing selected. Pick a UNAV object in the Object Manager, "
            "then click Inspect Selected Object."
        )
    if result.status == STATUS_NOT_UNAV:
        return (
            f"'{result.object_name or '<unnamed>'}' is not a UNAV object.\n"
            "Select an object created by 'Generate Point Cloud'."
        )

    obj = result.catalog_object
    marker = result.marker or {}
    name = result.object_name or "<unnamed>"

    lines: List[str] = []
    lines.append("=== UNAV Object Inspector ===")
    lines.append(f"Selection      : {name}")
    if result.status == STATUS_FOUND_MARKER_ONLY:
        lines.append("(catalog lookup miss — showing marker data only)")
    lines.append("")

    # --- Identity ----------------------------------------------------
    lines.append("--- Identity ---")
    if obj is not None:
        lines.append(f"UID            : {obj.uid}")
        lines.append(f"Catalog source : {obj.catalog_source}")
        lines.append(f"Object type    : {obj.object_type}")
        if obj.name:
            lines.append(f"Name           : {obj.name}")
        if obj.common_name and obj.common_name != obj.name:
            lines.append(f"Common name    : {obj.common_name}")
    else:
        lines.append(f"UID            : {marker.get(MARKER_KEY_UID, '?')}")
        lines.append(f"Catalog source : {marker.get(MARKER_KEY_CATALOG_SOURCE, '?')}")
        lines.append(f"Object type    : {marker.get(MARKER_KEY_OBJECT_TYPE, '?')}")
        if marker.get(MARKER_KEY_NAME):
            lines.append(f"Name           : {marker[MARKER_KEY_NAME]}")

    # --- Astrometry --------------------------------------------------
    lines.append("")
    lines.append("--- Astrometry ---")
    parsed_meta = _safe_parse_meta(obj.metadata_json) if obj is not None else {}
    if obj is not None:
        lines.append(f"RA  (deg)      : {obj.ra_deg:.6f}")
        lines.append(f"Dec (deg)      : {obj.dec_deg:.6f}")
        for label, value, fmt in (
            ("Distance (pc)  ", obj.distance_parsec, "{:.4g}"),
            ("Parallax (mas) ", obj.parallax_mas, "{:.4g}"),
            ("Redshift z     ", obj.redshift, "{:.6f}"),
            ("RV (km/s)      ", obj.radial_velocity_kms, "{:.4g}"),
        ):
            shown = _fmt_optional_float(value, fmt)
            if shown is not None:
                lines.append(f"{label}: {shown}")
        if parsed_meta.get("distance_method") == DISTANCE_METHOD_REDSHIFT_PROXY:
            lines.append(
                "Distance note  : APPROXIMATE — "
                + DISTANCE_PROXY_WARNING_TEXT
            )
        if obj.proper_motion_ra is not None or obj.proper_motion_dec is not None:
            pm_ra = obj.proper_motion_ra if obj.proper_motion_ra is not None else 0.0
            pm_dec = obj.proper_motion_dec if obj.proper_motion_dec is not None else 0.0
            lines.append(f"PM (mas/yr)    : RA {pm_ra:+.3f}, Dec {pm_dec:+.3f}")
    else:
        ra = _fmt_optional_float(marker.get(MARKER_KEY_RA_DEG), "{:.6f}")
        dec = _fmt_optional_float(marker.get(MARKER_KEY_DEC_DEG), "{:.6f}")
        d = _fmt_optional_float(marker.get(MARKER_KEY_DISTANCE_PC), "{:.4g}")
        if ra is not None:
            lines.append(f"RA  (deg)      : {ra}")
        if dec is not None:
            lines.append(f"Dec (deg)      : {dec}")
        # The marker stores 0.0 as the sentinel for "no distance"; show
        # only when it is meaningful.
        if d is not None and float(marker.get(MARKER_KEY_DISTANCE_PC, 0.0)) > 0:
            lines.append(f"Distance (pc)  : {d}")

    # --- Photometry --------------------------------------------------
    if obj is not None and any((
        obj.apparent_magnitude is not None,
        obj.absolute_magnitude is not None,
        obj.color_index is not None,
        obj.spectral_type,
    )):
        lines.append("")
        lines.append("--- Photometry ---")
        for label, value, fmt in (
            ("Apparent mag   ", obj.apparent_magnitude, "{:.3f}"),
            ("Absolute mag   ", obj.absolute_magnitude, "{:.3f}"),
            ("Color index    ", obj.color_index, "{:+.3f}"),
        ):
            shown = _fmt_optional_float(value, fmt)
            if shown is not None:
                lines.append(f"{label}: {shown}")
        if obj.spectral_type:
            lines.append(f"Spectral type  : {obj.spectral_type}")

    # --- Survey / class (extragalactic catalogs) --------------------
    if obj is not None and parsed_meta:
        survey_lines: List[str] = []
        # SDSS spec class / subclass.
        spec_class = parsed_meta.get("spec_class")
        spec_subclass = parsed_meta.get("spec_subclass")
        # DESI spectype / subtype.
        spectype = parsed_meta.get("spectype")
        subtype = parsed_meta.get("subtype")
        survey = parsed_meta.get("survey")
        program = parsed_meta.get("program")
        release = parsed_meta.get("release")
        if spec_class:
            survey_lines.append(f"Spec class     : {spec_class}")
        if spec_subclass:
            survey_lines.append(f"Spec subclass  : {spec_subclass}")
        if spectype:
            survey_lines.append(f"Spec type      : {spectype}")
        if subtype:
            survey_lines.append(f"Spec subtype   : {subtype}")
        if survey:
            survey_lines.append(f"Survey         : {survey}")
        if program:
            survey_lines.append(f"Program        : {program}")
        if release:
            survey_lines.append(f"Release        : {release}")
        if survey_lines:
            lines.append("")
            lines.append("--- Survey / Class ---")
            lines.extend(survey_lines)

    # --- Raw metadata JSON preview ----------------------------------
    raw = _format_clipboard_json(result)
    if raw:
        lines.append("")
        lines.append("--- Raw metadata JSON ---")
        if len(raw) > _INLINE_JSON_MAX_CHARS:
            preview = raw[:_INLINE_JSON_MAX_CHARS]
            lines.append(preview)
            lines.append("... (truncated; use Copy Metadata JSON for full)")
        else:
            lines.append(raw)

    return "\n".join(lines)


def _marker_to_named_dict(marker: Dict[int, Any]) -> Dict[str, Any]:
    """Translate integer marker keys to readable names for JSON output."""
    out: Dict[str, Any] = {}
    for key, value in marker.items():
        out[_MARKER_KEY_NAMES.get(key, str(key))] = value
    return out


def _format_clipboard_json(result: InspectionResult) -> str:
    obj = result.catalog_object
    marker = result.marker
    if obj is not None:
        d = obj.to_dict()
        # The schema's metadata_json is stored as a JSON-encoded string
        # field. Surface its parsed form too so the clipboard payload
        # is genuinely useful in one step.
        try:
            d["metadata_json_parsed"] = json.loads(obj.metadata_json or "{}")
        except (TypeError, ValueError):
            pass
        return json.dumps(d, indent=2, sort_keys=True, default=str)
    if marker:
        translated = _marker_to_named_dict(marker)
        # The marker's "metadata_json" is also a string blob — parse for
        # convenience.
        if "metadata_json" in translated:
            try:
                translated["metadata_json_parsed"] = json.loads(
                    translated.get("metadata_json") or "{}"
                )
            except (TypeError, ValueError):
                pass
        return json.dumps(translated, indent=2, sort_keys=True, default=str)
    return "{}"


# ---------------------------------------------------------------------------
# C4D-bound code
# ---------------------------------------------------------------------------


def _read_marker_from_object(c4d_obj: "c4d.BaseObject") -> Optional[Dict[int, Any]]:
    """Pull the UNAV marker BaseContainer off a selected object.

    Returns ``None`` if the object was not generated by UNAV Pro.
    """
    if not _C4D_AVAILABLE:
        return None
    try:
        data = c4d_obj.GetDataInstance()
    except Exception:  # noqa: BLE001 — defensive
        return None
    if data is None:
        return None
    sub = data.GetContainerInstance(BC_ID_UNAV_MARKER)
    if sub is None:
        return None
    out: Dict[int, Any] = {}
    for key, value in sub:
        out[key] = value
    if not out.get(MARKER_KEY_IS_UNAV):
        return None
    return out


def inspect_active_selection(
    doc: "c4d.documents.BaseDocument" = None,
    lookup: Optional[MetadataLookup] = None,
) -> InspectionResult:
    """Inspect the active selection in ``doc`` (defaults to the active
    C4D document) using ``lookup`` (defaults to the lazy default).

    Returns an ``InspectionResult`` whose status field tells the
    caller what happened: ``no_doc`` / ``no_selection`` / ``not_unav``
    / ``found_marker_only`` / ``found_full``.
    """
    if not _C4D_AVAILABLE:
        return InspectionResult(status=STATUS_NO_DOC)

    if doc is None:
        try:
            from c4d import documents  # type: ignore
        except ImportError:  # pragma: no cover
            return InspectionResult(status=STATUS_NO_DOC)
        doc = documents.GetActiveDocument()
    if doc is None:
        return InspectionResult(status=STATUS_NO_DOC)

    selected = doc.GetActiveObject()
    if selected is None:
        return InspectionResult(status=STATUS_NO_SELECTION)

    name = selected.GetName()
    marker = _read_marker_from_object(selected)
    if marker is None:
        return InspectionResult(status=STATUS_NOT_UNAV, object_name=name)

    uid = str(marker.get(MARKER_KEY_UID) or "")
    table = lookup if lookup is not None else default_lookup()

    if uid and table is not None:
        full = table.lookup(uid)
        if full is not None:
            return InspectionResult(
                status=STATUS_FOUND_FULL,
                object_name=name,
                marker=marker,
                catalog_object=full,
            )

    return InspectionResult(
        status=STATUS_FOUND_MARKER_ONLY,
        object_name=name,
        marker=marker,
    )


def copy_to_clipboard(text: str) -> bool:
    """Best-effort copy ``text`` to the system clipboard via C4D.

    Returns True on success, False if the host's clipboard helper
    refused or is unavailable. Never raises.
    """
    if not _C4D_AVAILABLE:
        return False
    try:
        c4d.CopyStringToClipboard(text)
        return True
    except Exception:  # noqa: BLE001 — boundary handler
        _log.exception("CopyStringToClipboard failed")
        return False


# ---------------------------------------------------------------------------
# Convenience used by the dialog
# ---------------------------------------------------------------------------


def empty_panel_text() -> str:
    """Placeholder shown in the metadata panel before the user has
    inspected anything."""
    return (
        "Select a UNAV object in the Object Manager and click "
        "'Inspect Selected Object' to view its astrophysical metadata."
    )


def no_inspection_result() -> InspectionResult:
    """Sentinel result for 'user clicked Copy without inspecting first'."""
    return InspectionResult(status=STATUS_NO_INSPECTION)


def point_cloud_search_hint() -> str:
    """Search-based inspection fallback used when the active render
    mode is Point Cloud and the click did not resolve to a uid.

    Point Cloud Mode does not create per-object selectable nodes, so
    the v0.1 Inspect-by-click path returns marker-only or not-UNAV.
    The dialog appends this hint to the status log so the artist
    knows to use the v0.6 Search tab to find the object by name /
    uid / source instead.
    """
    return (
        "Inspect: Point Cloud Mode has no per-object selection. "
        "Use the Search tab to find the object by name, uid, or "
        "source, then click Inspect from there."
    )


def point_cloud_panel_text() -> str:
    """Multi-line panel text for the inspector under Point Cloud
    mode when the user clicked without resolving a selection."""
    return (
        "=== UNAV Object Inspector ===\n"
        "Selection      : (point-cloud placeholder)\n"
        "(Point Cloud Mode does not expose per-object selection.)\n"
        "\n"
        "Use the Search tab to look up an object by name / uid / "
        "source / object_type. The full record is still resolvable "
        "via the active MetadataLookup."
    )
