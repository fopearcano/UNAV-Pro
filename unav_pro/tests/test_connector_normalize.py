"""Tests for data.connectors._normalize. Pure CPython, no C4D."""

from __future__ import annotations

import math

import pytest

from data.connectors._normalize import NULL_TOKENS, parse_csv, to_float, to_int


# ---------------------------------------------------------------------------
# to_float
# ---------------------------------------------------------------------------


def test_to_float_parses_decimal_strings():
    assert to_float("1.5") == 1.5
    assert to_float("-2.5e1") == -25.0


def test_to_float_passthrough_for_numeric_inputs():
    assert to_float(3.14) == 3.14
    assert to_float(7) == 7.0
    assert to_float(True) == 1.0
    assert to_float(False) == 0.0


def test_to_float_strips_whitespace():
    assert to_float("  42.0  ") == 42.0


def test_to_float_returns_none_for_empty_or_null_tokens():
    assert to_float("") is None
    assert to_float(None) is None
    for token in ("null", "NULL", "Null", "nan", "NaN", "none", "None"):
        assert to_float(token) is None


def test_to_float_returns_none_for_unparsable():
    assert to_float("not a number") is None
    assert to_float("12.3abc") is None


def test_to_float_returns_none_for_nan_floats():
    assert to_float(float("nan")) is None


def test_null_tokens_are_lowercase():
    # The constant is the source of truth; case-sensitivity of the
    # comparison is handled inside ``to_float``.
    assert all(t == t.lower() for t in NULL_TOKENS)


# ---------------------------------------------------------------------------
# to_int
# ---------------------------------------------------------------------------


def test_to_int_parses_decimal_strings():
    assert to_int("42") == 42
    assert to_int("-7") == -7


def test_to_int_truncates_floats_toward_zero():
    assert to_int("3.9") == 3
    assert to_int("-3.9") == -3


def test_to_int_returns_none_for_missing():
    assert to_int(None) is None
    assert to_int("") is None
    assert to_int("null") is None
    assert to_int("nan") is None


def test_to_int_returns_none_for_unparsable():
    assert to_int("warp") is None


def test_to_int_handles_overflow():
    assert to_int(float("inf")) is None
    assert to_int(float("-inf")) is None


# ---------------------------------------------------------------------------
# Connector parity — the helpers feed every connector
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# parse_csv
# ---------------------------------------------------------------------------


def test_parse_csv_returns_dict_rows():
    body = "a,b,c\n1,2,3\n4,5,6\n"
    rows = list(parse_csv(body))
    assert rows == [
        {"a": "1", "b": "2", "c": "3"},
        {"a": "4", "b": "5", "c": "6"},
    ]


def test_parse_csv_empty_body_returns_empty_iter():
    assert list(parse_csv("")) == []


def test_parse_csv_no_header_returns_empty_iter():
    # csv.DictReader treats a single line as the header; explicitly
    # pass content that has no header row by exhausting the body.
    assert list(parse_csv("\n")) == []


def test_parse_csv_strip_leading_comments_drops_banner():
    body = "# comment line\n# more banner\na,b\n1,2\n"
    rows = list(parse_csv(body, strip_leading_comments=True))
    assert rows == [{"a": "1", "b": "2"}]


def test_parse_csv_strip_leading_comments_off_keeps_them():
    body = "# banner\na,b\n1,2\n"
    rows = list(parse_csv(body))
    # Without stripping, the banner becomes the "header", and the
    # actual header row becomes a data row.
    assert rows[0].get("# banner") in {"a", None}


def test_parse_csv_strip_leading_comments_only_banner_returns_empty():
    body = "# banner only\n# more banner\n"
    assert list(parse_csv(body, strip_leading_comments=True)) == []


# ---------------------------------------------------------------------------
# Connector parity
# ---------------------------------------------------------------------------


def test_connectors_share_one_implementation():
    """Regression guard: every connector uses the same helpers so a
    change to numeric parsing only needs to land in one place."""
    from data.connectors import desi_connector, gaia_connector, sdss_connector

    assert gaia_connector._to_float is to_float
    assert sdss_connector._to_float is to_float
    assert desi_connector._to_float is to_float
    assert sdss_connector._to_int is to_int
    assert desi_connector._to_int is to_int
