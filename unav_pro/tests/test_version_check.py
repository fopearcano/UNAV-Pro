"""Tests for the host version check. Runs without Cinema 4D."""

from __future__ import annotations

from core import version_check


def test_minimum_supported():
    assert version_check.is_supported(26000) is True
    assert version_check.is_supported(2024100) is True
    assert version_check.is_supported(25000) is False
    assert version_check.is_supported(0) is False


def test_non_int_rejected():
    assert version_check.is_supported("26000") is False  # type: ignore[arg-type]
    assert version_check.is_supported(None) is False  # type: ignore[arg-type]


def test_describe_legacy_and_modern():
    assert "R26" in version_check.describe(26000)
    assert "2024" in version_check.describe(2024100)
    assert "legacy" in version_check.describe(20000)


def test_check_host_with_explicit_version():
    ok, msg = version_check.check_host(26000)
    assert ok
    assert "Host OK" in msg

    ok, msg = version_check.check_host(20000)
    assert not ok
    assert "Unsupported" in msg


def test_check_host_without_c4d_returns_false():
    # In the test environment c4d is not installed; passing version=None
    # must return cleanly rather than raise.
    ok, msg = version_check.check_host(None)
    assert ok is False
    assert isinstance(msg, str) and msg
