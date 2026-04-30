"""Tests for the v1.3 ``knowledge.physical_interpretation``."""

from __future__ import annotations

import pytest

from knowledge.physical_interpretation import (
    distance_quality,
    motion_summary,
    spectral_class_hint,
)


# ---------------------------------------------------------------------------
# Spectral class
# ---------------------------------------------------------------------------


def test_spectral_class_hint_for_g2v_mentions_sun_like():
    hint = spectral_class_hint("G2V")
    assert hint is not None
    assert "yellow" in hint.lower()
    assert "Sun-like" in hint


def test_spectral_class_hint_for_m_class():
    hint = spectral_class_hint("M5")
    assert hint is not None
    assert "red" in hint.lower()


def test_spectral_class_hint_giant_suffix():
    hint = spectral_class_hint("M5III")
    assert hint is not None
    assert "giant" in hint.lower()


def test_spectral_class_hint_unknown_letter_returns_none():
    assert spectral_class_hint("Z9") is None


def test_spectral_class_hint_empty_returns_none():
    assert spectral_class_hint(None) is None
    assert spectral_class_hint("") is None


# ---------------------------------------------------------------------------
# Distance quality
# ---------------------------------------------------------------------------


def test_distance_quality_explicit():
    label, note = distance_quality(
        distance_parsec=100.0, parallax_mas=None,
        distance_method=None,
    )
    assert label == "explicit"
    assert "directly" in note.lower()


def test_distance_quality_parallax_with_good_snr():
    label, note = distance_quality(
        distance_parsec=100.0, parallax_mas=10.0,
        parallax_error_mas=0.5, distance_method=None,
    )
    assert label == "parallax"
    assert "SNR" in note
    assert "caution" not in note.lower()


def test_distance_quality_parallax_with_bad_snr():
    label, note = distance_quality(
        distance_parsec=100.0, parallax_mas=10.0,
        parallax_error_mas=5.0, distance_method=None,
    )
    assert label == "parallax"
    assert "caution" in note.lower()


def test_distance_quality_redshift_proxy():
    label, note = distance_quality(
        distance_parsec=300_000_000.0, parallax_mas=None,
        distance_method="redshift_hubble_proxy",
    )
    assert label == "redshift_proxy"
    assert "approximate" in note.lower()


def test_distance_quality_placeholder():
    label, note = distance_quality(
        distance_parsec=1e6, parallax_mas=None,
        distance_method="placeholder_sphere",
    )
    assert label == "placeholder"
    assert "celestial-sphere" in note.lower()


def test_distance_quality_unknown():
    label, note = distance_quality(
        distance_parsec=None, parallax_mas=None,
        distance_method=None,
    )
    assert label == "unknown"


# ---------------------------------------------------------------------------
# Motion summary
# ---------------------------------------------------------------------------


def test_motion_summary_none_when_both_missing():
    assert motion_summary(None, None) is None


def test_motion_summary_negligible_for_small_drift():
    summary = motion_summary(0.5, 0.2)
    assert summary is not None
    assert "negligible" in summary


def test_motion_summary_slow_for_a_few_masyr():
    summary = motion_summary(3.0, 4.0)  # |pm| = 5 mas/yr
    assert "slow" in summary
    assert "5.0" in summary


def test_motion_summary_moderate_for_tens_masyr():
    summary = motion_summary(30.0, 40.0)  # |pm| = 50 mas/yr
    assert "moderate" in summary


def test_motion_summary_fast_for_hundreds_masyr():
    summary = motion_summary(0.0, 500.0)
    assert "fast" in summary
    # NOT "very fast"
    assert "very fast" not in summary


def test_motion_summary_very_fast_for_barnards_star():
    summary = motion_summary(0.0, 10_000.0)
    assert "very fast" in summary
