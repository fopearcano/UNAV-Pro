"""v3.8 audience-overlay tests."""

from __future__ import annotations

import pytest

from presentation import (
    AUDIENCE_HIDDEN_OVERLAY_FLAGS,
    AUDIENCE_HIDDEN_SCIENCE_FLAGS,
    AudienceOverlayFlags,
    ExhibitionState,
    HighlightInstruction,
    ViewMode,
    apply_audience_overlays,
    flags_for_state,
    highlight_for_state,
)


# ---------------------------------------------------------------------------
# AudienceOverlayFlags defaults
# ---------------------------------------------------------------------------


def test_default_flags_are_presenter_safe():
    flags = AudienceOverlayFlags()
    assert flags.simplified_labels is False
    assert flags.highlight_focus_object is True
    assert flags.emphasise_route is False
    assert flags.presenter_notes_visible is True
    assert flags.debug_helpers_visible is True


def test_flags_short_summary_shape():
    flags = AudienceOverlayFlags(
        simplified_labels=True,
        emphasise_route=True,
    )
    s = flags.short_summary()
    assert "simplified" in s
    assert "emphasised" in s


def test_flags_default_short_summary():
    flags = AudienceOverlayFlags()
    s = flags.short_summary()
    assert "presenter" in s.lower() or "notes=on" in s


# ---------------------------------------------------------------------------
# flags_for_state — idle
# ---------------------------------------------------------------------------


def test_flags_idle_state_returns_defaults():
    state = ExhibitionState()
    flags = flags_for_state(state)
    assert flags.simplified_labels is False
    assert flags.debug_helpers_visible is True


# ---------------------------------------------------------------------------
# flags_for_state — presenter view
# ---------------------------------------------------------------------------


def test_flags_presenter_with_highlight():
    state = ExhibitionState()
    state.activate(view_mode=ViewMode.PRESENTER)
    state.highlight("uid:42")
    flags = flags_for_state(state)
    assert flags.highlight_focus_object is True
    assert flags.simplified_labels is False
    assert flags.debug_helpers_visible is True


def test_flags_presenter_with_chapter():
    state = ExhibitionState()
    state.activate(view_mode=ViewMode.PRESENTER)
    state.set_current_chapter("ch-1")
    flags = flags_for_state(state)
    assert flags.chapter_title_visible is True


def test_flags_presenter_notes_off():
    state = ExhibitionState()
    state.activate(
        view_mode=ViewMode.PRESENTER,
        show_presenter_notes=False,
    )
    flags = flags_for_state(state)
    assert flags.presenter_notes_visible is False


# ---------------------------------------------------------------------------
# flags_for_state — audience view
# ---------------------------------------------------------------------------


def test_flags_audience_simplifies_labels():
    state = ExhibitionState()
    state.activate(view_mode=ViewMode.AUDIENCE)
    flags = flags_for_state(state)
    assert flags.simplified_labels is True
    assert flags.emphasise_route is True
    assert flags.debug_helpers_visible is False
    assert flags.presenter_notes_visible is False


def test_flags_audience_highlights_when_uid_set():
    state = ExhibitionState()
    state.activate(view_mode=ViewMode.AUDIENCE)
    assert flags_for_state(state).highlight_focus_object is False
    state.highlight("x")
    assert flags_for_state(state).highlight_focus_object is True


# ---------------------------------------------------------------------------
# apply_audience_overlays
# ---------------------------------------------------------------------------


def test_apply_overlays_pass_through_when_simple_off():
    overlay_in = {"show_grid": True, "show_galactic_plane": True}
    science_in = {"show_distance_shells": True}
    flags = AudienceOverlayFlags(simplified_labels=False)
    out = apply_audience_overlays(
        overlay_settings=overlay_in,
        science_settings=science_in,
        flags=flags,
    )
    assert out["overlays"] == overlay_in
    assert out["science_layers"] == science_in


def test_apply_overlays_strips_hidden_flags_in_audience():
    overlay_in = {"show_grid": True, "show_galactic_plane": True}
    science_in = {"show_motion_vectors": True, "show_distance_shells": True}
    flags = AudienceOverlayFlags(simplified_labels=True)
    out = apply_audience_overlays(
        overlay_settings=overlay_in,
        science_settings=science_in,
        flags=flags,
    )
    assert out["overlays"]["show_grid"] is False
    # show_galactic_plane is NOT in the strip list — preserved.
    assert out["overlays"]["show_galactic_plane"] is True
    assert out["science_layers"]["show_motion_vectors"] is False
    assert out["science_layers"]["show_distance_shells"] is True


def test_apply_overlays_does_not_mutate_input():
    overlay_in = {"show_grid": True}
    science_in = {}
    flags = AudienceOverlayFlags(simplified_labels=True)
    apply_audience_overlays(
        overlay_settings=overlay_in,
        science_settings=science_in,
        flags=flags,
    )
    assert overlay_in == {"show_grid": True}


def test_apply_overlays_handles_none_inputs():
    flags = AudienceOverlayFlags(simplified_labels=True)
    out = apply_audience_overlays(
        overlay_settings=None,
        science_settings=None,
        flags=flags,
    )
    assert out["overlays"] == {}
    assert out["science_layers"] == {}


def test_hidden_overlay_flag_constants_complete():
    assert "show_grid" in AUDIENCE_HIDDEN_OVERLAY_FLAGS
    assert "show_distance_rings" in AUDIENCE_HIDDEN_OVERLAY_FLAGS


def test_hidden_science_flag_constants_complete():
    assert "show_motion_vectors" in AUDIENCE_HIDDEN_SCIENCE_FLAGS
    assert "show_object_density_volume" in AUDIENCE_HIDDEN_SCIENCE_FLAGS


# ---------------------------------------------------------------------------
# HighlightInstruction
# ---------------------------------------------------------------------------


def test_highlight_for_state_with_uid():
    state = ExhibitionState()
    state.activate(view_mode=ViewMode.AUDIENCE)
    state.highlight("uid:42")
    inst = highlight_for_state(state)
    assert inst.target_uid == "uid:42"
    assert inst.is_active() is True


def test_highlight_for_state_no_uid():
    state = ExhibitionState()
    state.activate()
    inst = highlight_for_state(state)
    assert inst.target_uid == ""
    assert inst.is_active() is False


def test_highlight_audience_intensity_higher():
    state_p = ExhibitionState()
    state_p.activate(view_mode=ViewMode.PRESENTER)
    state_p.highlight("x")
    state_a = ExhibitionState()
    state_a.activate(view_mode=ViewMode.AUDIENCE)
    state_a.highlight("x")
    assert (
        highlight_for_state(state_a).halo_intensity
        > highlight_for_state(state_p).halo_intensity
    )


def test_highlight_label_visible_in_presenter_view():
    state = ExhibitionState()
    state.activate(view_mode=ViewMode.PRESENTER)
    state.highlight("x")
    inst = highlight_for_state(state)
    assert inst.label_visible is True


def test_highlight_label_hidden_in_audience_when_notes_off():
    state = ExhibitionState()
    state.activate(view_mode=ViewMode.AUDIENCE, show_presenter_notes=False)
    state.highlight("x")
    inst = highlight_for_state(state)
    assert inst.label_visible is False
