"""Tests for the isolated redshift→proxy distance helper (v0.5)."""

from __future__ import annotations

import pytest

from data.connectors.redshift_distance import (
    DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
    DISTANCE_METHOD_REDSHIFT_PROXY,
    DISTANCE_PROXY_WARNING_TEXT,
    HUBBLE_KM_S_MPC,
    SPEED_OF_LIGHT_KM_S,
    is_proxy_distance,
    safe_redshift_to_distance_pc,
    stamp_proxy_metadata,
)


# ---------------------------------------------------------------------------
# safe_redshift_to_distance_pc
# ---------------------------------------------------------------------------


def test_safe_returns_none_for_missing_or_nonpositive():
    assert safe_redshift_to_distance_pc(None) is None
    assert safe_redshift_to_distance_pc(0.0) is None
    assert safe_redshift_to_distance_pc(-0.01) is None


def test_safe_returns_none_above_default_max_z():
    assert safe_redshift_to_distance_pc(0.5) is None  # default max_z=0.1


def test_safe_returns_none_when_zwarn_nonzero():
    assert safe_redshift_to_distance_pc(0.05, zwarn=4) is None
    assert safe_redshift_to_distance_pc(0.05, zwarn=1) is None


def test_safe_returns_pc_at_low_z_clean():
    d = safe_redshift_to_distance_pc(0.05, zwarn=0)
    assert d is not None
    expected = (SPEED_OF_LIGHT_KM_S * 0.05 / HUBBLE_KM_S_MPC) * 1.0e6
    assert d == pytest.approx(expected, rel=1e-9)


def test_safe_respects_custom_max_z():
    assert safe_redshift_to_distance_pc(0.3, max_z=0.5) is not None
    assert safe_redshift_to_distance_pc(0.6, max_z=0.5) is None


def test_safe_respects_custom_h0():
    a = safe_redshift_to_distance_pc(0.05, h0_km_s_mpc=70.0)
    b = safe_redshift_to_distance_pc(0.05, h0_km_s_mpc=67.0)
    # Lower H0 → larger distance.
    assert a is not None and b is not None
    assert b > a


def test_default_max_z_is_zero_point_one():
    assert DEFAULT_REDSHIFT_DISTANCE_MAX_Z == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# stamp_proxy_metadata
# ---------------------------------------------------------------------------


def test_stamp_adds_method_and_warning():
    extra: dict = {"survey": "main"}
    out = stamp_proxy_metadata(extra, z=0.05)
    # Mutates and returns the same dict.
    assert out is extra
    assert extra["distance_method"] == DISTANCE_METHOD_REDSHIFT_PROXY
    assert extra["distance_proxy_warning"] == DISTANCE_PROXY_WARNING_TEXT
    assert extra["distance_proxy_z"] == pytest.approx(0.05)
    assert extra["distance_proxy_h0_km_s_mpc"] == pytest.approx(HUBBLE_KM_S_MPC)
    assert extra["distance_proxy_max_z"] == pytest.approx(
        DEFAULT_REDSHIFT_DISTANCE_MAX_Z
    )
    # Pre-existing keys survive.
    assert extra["survey"] == "main"


def test_stamp_records_caller_constants():
    out: dict = {}
    stamp_proxy_metadata(out, z=0.07, h0_km_s_mpc=67.4, max_z=0.08)
    assert out["distance_proxy_h0_km_s_mpc"] == pytest.approx(67.4)
    assert out["distance_proxy_max_z"] == pytest.approx(0.08)


# ---------------------------------------------------------------------------
# is_proxy_distance predicate
# ---------------------------------------------------------------------------


def test_is_proxy_distance_recognizes_stamped_blob():
    assert is_proxy_distance({"distance_method": DISTANCE_METHOD_REDSHIFT_PROXY})


def test_is_proxy_distance_rejects_other_methods():
    assert not is_proxy_distance({"distance_method": "placeholder_sphere"})
    assert not is_proxy_distance({"distance_method": "explicit"})
    assert not is_proxy_distance({})
    assert not is_proxy_distance(None)
    assert not is_proxy_distance("a string, not a dict")  # type: ignore[arg-type]
