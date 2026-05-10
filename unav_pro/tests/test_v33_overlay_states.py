"""v3.3 overlay-state merge + diff tests."""

from __future__ import annotations

import pytest

from presentation import (
    FLAG_PREFIX,
    FlagDiff,
    apply_overlay_flags,
    apply_science_flags,
    diff_flags,
    resolved_layer_states,
)


# ---------------------------------------------------------------------------
# apply_overlay_flags
# ---------------------------------------------------------------------------


def test_apply_returns_fresh_dict_no_mutation():
    base = {"show_grid": False, "radius_pc": 100.0}
    out = apply_overlay_flags(base, {"show_grid": True})
    assert out["show_grid"] is True
    assert out["radius_pc"] == 100.0
    # base untouched.
    assert base["show_grid"] is False


def test_apply_handles_none_base():
    out = apply_overlay_flags(None, {"show_grid": True})
    assert out == {"show_grid": True}


def test_apply_handles_none_step_flags():
    base = {"show_grid": True}
    out = apply_overlay_flags(base, None)
    assert out == base
    assert out is not base


def test_apply_ignores_non_show_keys():
    """Geometry knobs in the step flag dict are ignored —
    v3.3 never injects radius / segment count from a
    presentation step."""
    out = apply_overlay_flags({}, {"radius_pc": 999})
    assert "radius_pc" not in out


def test_apply_ignores_non_string_keys():
    out = apply_overlay_flags({}, {123: True})  # type: ignore[dict-item]
    assert out == {}


def test_apply_science_flags_uses_same_logic():
    out = apply_science_flags(
        {"show_distance_shells": False, "shell_radii_pc": [10]},
        {"show_distance_shells": True},
    )
    assert out["show_distance_shells"] is True
    assert out["shell_radii_pc"] == [10]


# ---------------------------------------------------------------------------
# diff_flags
# ---------------------------------------------------------------------------


def test_diff_flags_finds_enabled():
    prev = {"show_grid": False, "show_galactic_plane": False}
    cur = {"show_grid": True, "show_galactic_plane": False}
    diff = diff_flags(prev, cur)
    assert diff.enabled == ["show_grid"]
    assert diff.disabled == []


def test_diff_flags_finds_disabled():
    prev = {"show_grid": True}
    cur = {"show_grid": False}
    diff = diff_flags(prev, cur)
    assert diff.disabled == ["show_grid"]


def test_diff_flags_unchanged_skipped_from_summary():
    prev = {"show_grid": True}
    cur = {"show_grid": True}
    diff = diff_flags(prev, cur)
    assert diff.unchanged == ["show_grid"]
    assert diff.is_clean()


def test_diff_flags_with_none_inputs():
    diff = diff_flags(None, None)
    assert diff.is_clean()


def test_diff_flags_handles_first_step():
    diff = diff_flags(None, {"show_grid": True})
    assert diff.enabled == ["show_grid"]


def test_diff_flags_ignores_non_show_keys():
    """Geometry knob changes don't show up in flag diff."""
    prev = {"show_grid": True, "radius_pc": 100}
    cur = {"show_grid": True, "radius_pc": 200}
    diff = diff_flags(prev, cur)
    assert diff.is_clean()


def test_diff_flags_short_summary():
    prev = {"show_grid": False}
    cur = {"show_grid": True, "show_galactic_plane": True}
    diff = diff_flags(prev, cur)
    assert "enable" in diff.short_summary()


def test_diff_flags_clean_summary():
    diff = diff_flags({"show_grid": True}, {"show_grid": True})
    assert diff.short_summary() == "no changes"


# ---------------------------------------------------------------------------
# resolved_layer_states
# ---------------------------------------------------------------------------


def test_resolved_layer_states_returns_both_dicts():
    out = resolved_layer_states(
        base_overlay_settings={"show_grid": False},
        base_science_settings={"show_distance_shells": False},
        overlay_flags={"show_grid": True},
        science_flags={"show_distance_shells": True},
    )
    assert out["overlays"]["show_grid"] is True
    assert out["science_layers"]["show_distance_shells"] is True


def test_resolved_layer_states_handles_missing_flags():
    out = resolved_layer_states(
        base_overlay_settings={"show_grid": True},
        base_science_settings=None,
        overlay_flags=None,
        science_flags=None,
    )
    assert out["overlays"]["show_grid"] is True
    assert out["science_layers"] == {}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_flag_prefix_is_show():
    assert FLAG_PREFIX == "show_"
