"""v3.8 audience-friendly overlay flags.

Pure-data layer that decides what's visible to a
v3.8 audience-mode viewer vs. the presenter.

The dialog reads ``AudienceOverlayFlags`` after
each step transition and forwards the resulting
booleans to the existing v2.0 / v2.1 overlay
builders. Nothing here renders; the v2.0 builders
materialise the geometry as before.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .exhibition_mode import ExhibitionState, ViewMode


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AudienceOverlayFlags:
    """Pure-data flags the v3.8 layer hands to the
    overlays / annotations / route-emphasis
    builders.

    All fields default to "presenter view" so
    constructing without arguments produces no
    behavioural change.
    """

    simplified_labels: bool = False
    highlight_focus_object: bool = True
    emphasise_route: bool = False
    chapter_title_visible: bool = False
    presenter_notes_visible: bool = True
    debug_helpers_visible: bool = True

    def short_summary(self) -> str:
        bits: List[str] = []
        if self.simplified_labels:
            bits.append("labels=simplified")
        if self.highlight_focus_object:
            bits.append("focus=highlighted")
        if self.emphasise_route:
            bits.append("route=emphasised")
        if self.chapter_title_visible:
            bits.append("chapter-title=on")
        if self.presenter_notes_visible:
            bits.append("notes=on")
        else:
            bits.append("notes=off")
        if not self.debug_helpers_visible:
            bits.append("debug=hidden")
        return " · ".join(bits) if bits else "presenter defaults"


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def flags_for_state(state: ExhibitionState) -> AudienceOverlayFlags:
    """Translate an ``ExhibitionState`` into the
    overlay flags the dialog should apply.

    Pure helper; the dialog calls this after each
    step transition and any time the view-mode or
    presenter-notes toggle flips.
    """
    if not state.active:
        return AudienceOverlayFlags()
    if state.view_mode is ViewMode.PRESENTER:
        return AudienceOverlayFlags(
            simplified_labels=False,
            highlight_focus_object=bool(state.highlighted_uid),
            emphasise_route=False,
            chapter_title_visible=bool(state.current_chapter_id),
            presenter_notes_visible=state.show_presenter_notes,
            debug_helpers_visible=True,
        )
    # AUDIENCE view
    return AudienceOverlayFlags(
        simplified_labels=True,
        highlight_focus_object=bool(state.highlighted_uid),
        emphasise_route=True,
        chapter_title_visible=bool(state.current_chapter_id),
        presenter_notes_visible=False,
        debug_helpers_visible=False,
    )


# ---------------------------------------------------------------------------
# Apply over an existing settings dict
# ---------------------------------------------------------------------------


#: Overlay flags the v3.8 audience-mode layer can
#: switch off. The list is curated — anything that
#: would visibly distract the audience.
AUDIENCE_HIDDEN_OVERLAY_FLAGS: tuple = (
    "show_grid",
    "show_distance_rings",
)

#: Same for science layers — heavyweight
#: visualisations the audience doesn't need.
AUDIENCE_HIDDEN_SCIENCE_FLAGS: tuple = (
    "show_motion_vectors",
    "show_object_density_volume",
)


def apply_audience_overlays(
    *,
    overlay_settings: Optional[Dict[str, Any]],
    science_settings: Optional[Dict[str, Any]],
    flags: AudienceOverlayFlags,
) -> Dict[str, Dict[str, Any]]:
    """Compose the overlay + science settings dicts
    the v2.0 / v2.1 builders consume.

    Audience mode strips a curated list of
    distracting flags; presenter mode passes the
    incoming dicts through unchanged.
    """
    overlay_out: Dict[str, Any] = dict(overlay_settings or {})
    science_out: Dict[str, Any] = dict(science_settings or {})
    if not flags.simplified_labels:
        return {
            "overlays": overlay_out,
            "science_layers": science_out,
        }
    # Audience-mode strips:
    for key in AUDIENCE_HIDDEN_OVERLAY_FLAGS:
        if key in overlay_out:
            overlay_out[key] = False
    for key in AUDIENCE_HIDDEN_SCIENCE_FLAGS:
        if key in science_out:
            science_out[key] = False
    return {
        "overlays": overlay_out,
        "science_layers": science_out,
    }


# ---------------------------------------------------------------------------
# Highlighted-object emphasis
# ---------------------------------------------------------------------------


@dataclass
class HighlightInstruction:
    """Plain-data instruction the dialog forwards to
    the v0.7 visible-sector backend so the highlighted
    object renders with extra emphasis (a halo /
    enlarged size / colour shift).

    Pure data; the c4d-bound builder reads this and
    flips a UNAV marker bit on the matching point
    object."""

    target_uid: str
    halo_radius_pc: float = 0.5
    halo_intensity: float = 1.0
    label_visible: bool = True

    def is_active(self) -> bool:
        return bool(self.target_uid)


def highlight_for_state(state: ExhibitionState) -> HighlightInstruction:
    """Build the highlight instruction for the
    current exhibition state."""
    return HighlightInstruction(
        target_uid=str(state.highlighted_uid or ""),
        halo_radius_pc=0.5,
        halo_intensity=1.0 if state.is_audience_view else 0.6,
        label_visible=state.is_presenter_view or state.show_presenter_notes,
    )
