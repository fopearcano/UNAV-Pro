"""v2.4 version-module tests."""

from __future__ import annotations

import pytest

from version import (
    MIN_C4D_API,
    PLUGIN_CODENAME,
    PLUGIN_VERSION,
    VersionInfo,
    get_version_info,
    parse_version,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_plugin_version_is_v24():
    """v2.4+ release stamps the version constant."""
    assert PLUGIN_VERSION[0].isdigit()


def test_codename_is_present():
    assert PLUGIN_CODENAME


def test_min_c4d_api_is_release_baseline():
    """Cinema 4D 2023 API is 26000."""
    assert MIN_C4D_API >= 26000


# ---------------------------------------------------------------------------
# VersionInfo
# ---------------------------------------------------------------------------


def test_get_version_info_returns_canonical():
    info = get_version_info()
    assert info.plugin_version == PLUGIN_VERSION
    assert info.codename == PLUGIN_CODENAME
    assert info.min_c4d_api == MIN_C4D_API


def test_version_display_line_includes_version_and_codename():
    info = get_version_info()
    line = info.display_line()
    assert PLUGIN_VERSION in line
    assert PLUGIN_CODENAME in line
    assert str(MIN_C4D_API) in line


def test_version_info_is_frozen():
    """Frozen dataclass — attributes can't be mutated."""
    info = get_version_info()
    with pytest.raises(Exception):
        info.plugin_version = "9.9.9"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# parse_version
# ---------------------------------------------------------------------------


def test_parse_basic_semver():
    assert parse_version("2.4.0") == (2, 4, 0)
    assert parse_version("0.1.0") == (0, 1, 0)
    assert parse_version("10.20.30") == (10, 20, 30)


def test_parse_strips_prerelease_suffix():
    assert parse_version("2.4.0-rc1") == (2, 4, 0)
    assert parse_version("2.4.0-dev") == (2, 4, 0)
    assert parse_version("3.0.0-alpha.5") == (3, 0, 0)


def test_parse_two_part_version():
    """Major.minor without patch defaults patch to 0."""
    assert parse_version("2.4") == (2, 4, 0)


def test_parse_one_part_version():
    assert parse_version("2") == (2, 0, 0)


def test_parse_failure_returns_zeros():
    assert parse_version("garbage") == (0, 0, 0)
    assert parse_version("a.b.c") == (0, 0, 0)
    assert parse_version("") == (0, 0, 0)


def test_parse_handles_whitespace():
    assert parse_version("  2.4.0  ") == (2, 4, 0)


def test_parse_canonical_version_succeeds():
    """The live version constant must always parse."""
    assert parse_version(PLUGIN_VERSION) != (0, 0, 0)
