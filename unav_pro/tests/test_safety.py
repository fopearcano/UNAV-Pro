"""Tests for core.safety. Pure CPython, no Cinema 4D."""

from __future__ import annotations

import pytest

from core.safety import (
    DEFAULT_DATASET_SIZE_WARNING,
    DEFAULT_FILE_SIZE_WARNING_BYTES,
    DEFAULT_MAX_GENERATED_OBJECTS,
    DEFAULT_MAX_SCENE_OBJECT_COUNT,
    DEFAULT_WARNING_THRESHOLD,
    LEVEL_BLOCKED,
    LEVEL_OK,
    LEVEL_WARN,
    SafetyDecision,
    SafetyLimits,
    evaluate_dataset_load,
    evaluate_file_size,
    evaluate_generate,
    evaluate_scene_state,
    status_line,
)


# ---------------------------------------------------------------------------
# SafetyLimits dataclass
# ---------------------------------------------------------------------------


def test_safety_limits_defaults():
    s = SafetyLimits()
    assert s.max_generated_objects == DEFAULT_MAX_GENERATED_OBJECTS
    assert s.warning_threshold == DEFAULT_WARNING_THRESHOLD
    assert s.dataset_size_warning == DEFAULT_DATASET_SIZE_WARNING
    assert s.max_scene_object_count == DEFAULT_MAX_SCENE_OBJECT_COUNT
    assert s.max_c4d_file_size_warning_bytes == DEFAULT_FILE_SIZE_WARNING_BYTES
    assert s.visible_sector_only is True
    assert s.allow_full_catalog is False
    assert s.embed_full_metadata_in_marker is False


def test_safety_limits_rejects_negative_caps():
    with pytest.raises(ValueError):
        SafetyLimits(max_generated_objects=-1)
    with pytest.raises(ValueError):
        SafetyLimits(warning_threshold=-1)
    with pytest.raises(ValueError):
        SafetyLimits(dataset_size_warning=-1)
    with pytest.raises(ValueError):
        SafetyLimits(max_scene_object_count=-1)
    with pytest.raises(ValueError):
        SafetyLimits(max_c4d_file_size_warning_bytes=-1)


def test_safety_limits_warning_threshold_clamped_to_cap():
    # A typo where the warning threshold exceeds the cap is silently
    # repaired so the user is never trapped.
    s = SafetyLimits(max_generated_objects=100, warning_threshold=500)
    assert s.warning_threshold == 100


def test_safety_limits_round_trip_dict():
    s = SafetyLimits(
        max_generated_objects=42_000,
        warning_threshold=5_000,
        visible_sector_only=False,
        allow_full_catalog=True,
        embed_full_metadata_in_marker=True,
    )
    out = SafetyLimits.from_dict(s.to_dict())
    assert out == s


def test_safety_limits_from_dict_unknown_keys_dropped():
    out = SafetyLimits.from_dict({
        "max_generated_objects": 1000,
        "warp_drive": True,
    })
    assert out.max_generated_objects == 1000


def test_safety_limits_from_dict_invalid_values_fall_back():
    out = SafetyLimits.from_dict({"max_generated_objects": -1})
    # Bad values => defaults rather than raise.
    assert out == SafetyLimits()


def test_safety_limits_mode_label_default():
    label = SafetyLimits().mode_label()
    assert "Visible-sector only" in label


def test_safety_limits_mode_label_full_override():
    label = SafetyLimits(allow_full_catalog=True).mode_label()
    assert "FULL CATALOG OVERRIDE" in label


def test_safety_limits_mode_label_sector_aware_no_navigator_gate():
    label = SafetyLimits(
        visible_sector_only=False, allow_full_catalog=False,
    ).mode_label()
    assert "Sector-aware" in label
    assert "no navigator gate" in label


# ---------------------------------------------------------------------------
# SafetyDecision
# ---------------------------------------------------------------------------


def test_safety_decision_short_summary_states():
    d = SafetyDecision(allowed=True, level=LEVEL_OK,
                       requested=10, effective=10)
    assert "ok" in d.short_summary()
    d2 = SafetyDecision(allowed=True, level=LEVEL_WARN,
                        requested=20_000, effective=20_000,
                        messages=["heavy"])
    text = d2.short_summary()
    assert "WARN" in text and "heavy" in text
    d3 = SafetyDecision(allowed=False, level=LEVEL_BLOCKED,
                        requested=1_000_000, effective=0,
                        messages=["over the cap"])
    text = d3.short_summary()
    assert "BLOCKED" in text and "over the cap" in text


# ---------------------------------------------------------------------------
# evaluate_generate — cap enforcement
# ---------------------------------------------------------------------------


def test_evaluate_generate_under_warning_is_ok():
    d = evaluate_generate(100, has_navigator=True)
    assert d.allowed is True
    assert d.level == LEVEL_OK
    assert d.effective == 100


def test_evaluate_generate_warning_band():
    limits = SafetyLimits(warning_threshold=1_000, max_generated_objects=10_000)
    d = evaluate_generate(2_500, limits=limits, has_navigator=True)
    assert d.allowed is True
    assert d.level == LEVEL_WARN
    assert d.effective == 2_500
    assert any("warning threshold" in m for m in d.messages)


def test_evaluate_generate_above_cap_is_blocked():
    limits = SafetyLimits(max_generated_objects=10_000, warning_threshold=1_000)
    d = evaluate_generate(20_000, limits=limits, has_navigator=True)
    assert d.allowed is False
    assert d.level == LEVEL_BLOCKED
    assert d.effective == 0
    assert any("hard cap" in m for m in d.messages)
    # The message should mention the override the user can flip.
    assert any("Allow Full Catalog" in m for m in d.messages)


def test_evaluate_generate_full_catalog_override_allows_above_cap():
    limits = SafetyLimits(
        max_generated_objects=10_000,
        warning_threshold=1_000,
        allow_full_catalog=True,
    )
    d = evaluate_generate(2_000_000, limits=limits, has_navigator=False)
    assert d.allowed is True
    assert d.level == LEVEL_WARN  # still warns, doesn't silently allow
    assert d.effective == 2_000_000
    assert any("Override active" in m for m in d.messages)


def test_evaluate_generate_full_catalog_override_below_warning_is_ok_with_note():
    limits = SafetyLimits(
        warning_threshold=1_000_000,
        allow_full_catalog=True,
    )
    d = evaluate_generate(100, limits=limits, has_navigator=False)
    assert d.allowed is True
    assert d.level == LEVEL_OK  # below warning even with override
    assert any("Override active" in m for m in d.messages)


# ---------------------------------------------------------------------------
# evaluate_generate — visible-sector-only mode
# ---------------------------------------------------------------------------


def test_evaluate_generate_blocks_without_navigator_in_default_mode():
    d = evaluate_generate(100, has_navigator=False)
    assert d.allowed is False
    assert d.level == LEVEL_BLOCKED
    assert any("UNAV_Navigator" in m for m in d.messages)
    assert any("Allow Full Catalog" in m for m in d.messages)


def test_evaluate_generate_allows_without_navigator_when_sector_only_off():
    limits = SafetyLimits(visible_sector_only=False)
    d = evaluate_generate(100, limits=limits, has_navigator=False)
    assert d.allowed is True
    assert d.level == LEVEL_OK


def test_evaluate_generate_zero_objects_is_ok():
    d = evaluate_generate(0, has_navigator=True)
    assert d.allowed is True
    assert d.effective == 0


def test_evaluate_generate_negative_request_clamped_to_zero():
    d = evaluate_generate(-5, has_navigator=True)
    assert d.requested == 0
    assert d.effective == 0
    assert d.level == LEVEL_OK


def test_evaluate_generate_at_cap_exactly_is_warn_not_block():
    limits = SafetyLimits(max_generated_objects=10_000, warning_threshold=1_000)
    d = evaluate_generate(10_000, limits=limits, has_navigator=True)
    assert d.allowed is True
    assert d.level == LEVEL_WARN


# ---------------------------------------------------------------------------
# evaluate_dataset_load
# ---------------------------------------------------------------------------


def test_evaluate_dataset_load_below_threshold_is_ok():
    d = evaluate_dataset_load(100)
    assert d.level == LEVEL_OK
    assert d.allowed is True


def test_evaluate_dataset_load_above_threshold_warns():
    d = evaluate_dataset_load(2_000_000)
    assert d.level == LEVEL_WARN
    assert d.allowed is True  # advisory only, never blocks
    assert any("rows" in m for m in d.messages)


def test_evaluate_dataset_load_respects_custom_threshold():
    limits = SafetyLimits(dataset_size_warning=10)
    d = evaluate_dataset_load(50, limits=limits)
    assert d.level == LEVEL_WARN


# ---------------------------------------------------------------------------
# evaluate_scene_state
# ---------------------------------------------------------------------------


def test_evaluate_scene_state_below_threshold_is_ok():
    d = evaluate_scene_state(100)
    assert d.level == LEVEL_OK


def test_evaluate_scene_state_above_threshold_warns():
    d = evaluate_scene_state(500_000)
    assert d.level == LEVEL_WARN
    assert any("scene already contains" in m.lower() for m in d.messages)


# ---------------------------------------------------------------------------
# evaluate_file_size
# ---------------------------------------------------------------------------


def test_evaluate_file_size_below_threshold_is_ok():
    d = evaluate_file_size(1024)
    assert d.level == LEVEL_OK


def test_evaluate_file_size_above_threshold_warns_in_mb():
    d = evaluate_file_size(500 * 1024 * 1024)
    assert d.level == LEVEL_WARN
    assert any("MB" in m for m in d.messages)


# ---------------------------------------------------------------------------
# status_line
# ---------------------------------------------------------------------------


def test_status_line_includes_mode_and_cap():
    text = status_line(SafetyLimits())
    assert "Visible-sector only" in text
    assert "Cap" in text


def test_status_line_includes_generated_when_provided():
    text = status_line(SafetyLimits(), generated_now=42)
    assert "Generated 42" in text
    assert "/ cap" in text


def test_status_line_with_override_warns():
    text = status_line(SafetyLimits(allow_full_catalog=True), generated_now=10)
    assert "FULL CATALOG OVERRIDE" in text


# ---------------------------------------------------------------------------
# End-to-end: full-catalog generation blocked by default
# ---------------------------------------------------------------------------


def test_full_catalog_generation_blocked_by_default():
    """Heart of the spec: by default, a 'whole catalog' build is
    refused outright when there's no navigator."""
    huge = 5_000_000
    d = evaluate_generate(huge, has_navigator=False)
    assert d.allowed is False
    assert d.level == LEVEL_BLOCKED
    assert d.effective == 0


def test_full_catalog_generation_allowed_only_with_explicit_override():
    huge = 5_000_000
    limits = SafetyLimits(allow_full_catalog=True)
    d = evaluate_generate(huge, limits=limits, has_navigator=False)
    assert d.allowed is True
    assert d.effective == huge
