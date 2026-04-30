"""Tests for core.render_mode (v0.7 render-mode policy)."""

from __future__ import annotations

import pytest

from core.render_mode import (
    CAPABILITIES,
    DEBUG_OBJECTS_SOFT_WARNING,
    DEFAULT_CAPS,
    DEFAULT_RENDER_MODE,
    INSTANCES_SOFT_WARNING,
    NATIVE_VIEWER_SOFT_WARNING,
    RENDER_MODES,
    RENDER_MODE_DEBUG_OBJECTS,
    RENDER_MODE_INSTANCES,
    RENDER_MODE_LABELS,
    RENDER_MODE_NATIVE_VIEWER,
    RENDER_MODE_POINT_CLOUD,
    RenderModePolicy,
    cap_for_mode,
    capabilities_for,
    label_for_render_mode,
    render_mode_for_label,
    soft_warning_for_mode,
    validate_mode,
)


# ---------------------------------------------------------------------------
# Tokens / labels
# ---------------------------------------------------------------------------


def test_render_modes_tuple_contains_four_known_tokens():
    """v0.7 shipped three modes; v0.9 adds the Native Point Viewer."""
    assert RENDER_MODE_DEBUG_OBJECTS in RENDER_MODES
    assert RENDER_MODE_INSTANCES in RENDER_MODES
    assert RENDER_MODE_POINT_CLOUD in RENDER_MODES
    assert RENDER_MODE_NATIVE_VIEWER in RENDER_MODES
    assert len(RENDER_MODES) == 4


def test_default_mode_is_debug_objects_for_v01_parity():
    assert DEFAULT_RENDER_MODE == RENDER_MODE_DEBUG_OBJECTS


def test_validate_mode_passes_known_tokens_through():
    for token in RENDER_MODES:
        assert validate_mode(token) == token


def test_validate_mode_falls_back_for_unknown():
    assert validate_mode("not_a_mode") == DEFAULT_RENDER_MODE
    assert validate_mode(None) == DEFAULT_RENDER_MODE
    assert validate_mode("") == DEFAULT_RENDER_MODE


def test_label_token_round_trip():
    for label, token in RENDER_MODE_LABELS:
        assert render_mode_for_label(label) == token
        assert label_for_render_mode(token) == label


# ---------------------------------------------------------------------------
# Caps
# ---------------------------------------------------------------------------


def test_caps_are_strictly_increasing_across_modes():
    """Lighter backends MUST allow more visible objects than heavier ones."""
    debug = DEFAULT_CAPS[RENDER_MODE_DEBUG_OBJECTS]
    inst = DEFAULT_CAPS[RENDER_MODE_INSTANCES]
    cloud = DEFAULT_CAPS[RENDER_MODE_POINT_CLOUD]
    native = DEFAULT_CAPS[RENDER_MODE_NATIVE_VIEWER]
    assert debug < inst < cloud
    # Native viewer is the new top-end performance budget.
    assert native >= cloud


def test_cap_for_mode_returns_default_for_known_modes():
    for mode in RENDER_MODES:
        assert cap_for_mode(mode) == DEFAULT_CAPS[mode]


def test_cap_for_mode_falls_back_for_unknown():
    assert cap_for_mode("garbage") == DEFAULT_CAPS[DEFAULT_RENDER_MODE]


def test_debug_objects_soft_warning_is_below_hard_cap():
    assert DEBUG_OBJECTS_SOFT_WARNING < DEFAULT_CAPS[RENDER_MODE_DEBUG_OBJECTS]


def test_soft_warning_for_mode_tracks_mode():
    assert soft_warning_for_mode(RENDER_MODE_DEBUG_OBJECTS) == DEBUG_OBJECTS_SOFT_WARNING
    assert soft_warning_for_mode(RENDER_MODE_INSTANCES) == INSTANCES_SOFT_WARNING
    assert soft_warning_for_mode(RENDER_MODE_NATIVE_VIEWER) == NATIVE_VIEWER_SOFT_WARNING
    # Point cloud has no soft warning — the cap is the cap.
    assert soft_warning_for_mode(RENDER_MODE_POINT_CLOUD) is None


# ---------------------------------------------------------------------------
# RenderModePolicy
# ---------------------------------------------------------------------------


def test_policy_default_uses_debug_objects():
    p = RenderModePolicy()
    assert p.mode == RENDER_MODE_DEBUG_OBJECTS
    assert p.effective_cap == DEFAULT_CAPS[RENDER_MODE_DEBUG_OBJECTS]


def test_policy_explicit_max_visible_overrides_cap():
    p = RenderModePolicy(mode=RENDER_MODE_INSTANCES, max_visible=42)
    assert p.effective_cap == 42


def test_policy_negative_max_visible_rejected():
    with pytest.raises(ValueError):
        RenderModePolicy(max_visible=-1)


def test_policy_normalizes_unknown_mode():
    p = RenderModePolicy(mode="garbage")
    assert p.mode == DEFAULT_RENDER_MODE


def test_policy_should_warn_for_above_threshold_in_debug_mode():
    p = RenderModePolicy(mode=RENDER_MODE_DEBUG_OBJECTS)
    assert p.should_warn_for(DEBUG_OBJECTS_SOFT_WARNING + 1)
    assert not p.should_warn_for(DEBUG_OBJECTS_SOFT_WARNING - 1)


def test_policy_should_warn_for_above_threshold_in_instance_mode():
    p = RenderModePolicy(mode=RENDER_MODE_INSTANCES)
    assert p.should_warn_for(INSTANCES_SOFT_WARNING + 1)
    assert not p.should_warn_for(INSTANCES_SOFT_WARNING - 1)


def test_policy_never_warns_for_point_cloud():
    p = RenderModePolicy(mode=RENDER_MODE_POINT_CLOUD)
    assert not p.should_warn_for(10_000_000)


def test_policy_can_silence_soft_warning():
    p = RenderModePolicy(
        mode=RENDER_MODE_DEBUG_OBJECTS, surface_soft_warning=False,
    )
    assert not p.should_warn_for(DEBUG_OBJECTS_SOFT_WARNING + 1)


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


def test_capabilities_have_one_entry_per_mode():
    for mode in RENDER_MODES:
        assert mode in CAPABILITIES


def test_debug_objects_supports_per_object_selection_and_metadata():
    caps = capabilities_for(RENDER_MODE_DEBUG_OBJECTS)
    assert caps.supports_per_object_selection is True
    assert caps.supports_per_instance_metadata is True


def test_instance_mode_supports_selection_but_not_full_metadata():
    """v0.7 contract: instances carry uid only; full metadata comes
    from the lookup, not the marker."""
    caps = capabilities_for(RENDER_MODE_INSTANCES)
    assert caps.supports_per_object_selection is True
    assert caps.supports_per_instance_metadata is False


def test_point_cloud_supports_no_per_object_selection():
    caps = capabilities_for(RENDER_MODE_POINT_CLOUD)
    assert caps.supports_per_object_selection is False
    assert caps.supports_per_instance_metadata is False
