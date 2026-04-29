"""Tests for the Gaia connector. Mocked responses only — no network."""

from __future__ import annotations

import json

import pytest

from data.connectors import gaia_connector as gc
from data.connectors.gaia_connector import (
    DEFAULT_GAIA_RELEASE,
    GaiaQuery,
    GaiaQueryError,
    MAX_RADIUS_DEG,
    MAX_ROW_LIMIT,
    build_adql,
    fetch_and_normalize,
    fetch_rows,
    normalize_rows,
    safe_parallax_to_distance,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_FAKE_CSV_HEADER = (
    "source_id,ra,dec,parallax,parallax_error,pmra,pmdec,"
    "radial_velocity,phot_g_mean_mag,bp_rp"
)


def _csv(*rows: str) -> str:
    """Build a fake Gaia CSV body with the canonical header."""
    return "\n".join((_FAKE_CSV_HEADER, *rows)) + "\n"


def _make_fetcher(body: str):
    """Return a deterministic ``fetch_fn`` that captures its call args."""
    captured = {}

    def fetcher(url: str, params: dict) -> str:
        captured["url"] = url
        captured["params"] = params
        return body

    return fetcher, captured


# ---------------------------------------------------------------------------
# GaiaQuery validation
# ---------------------------------------------------------------------------


def test_query_validates_ra_range():
    with pytest.raises(ValueError):
        GaiaQuery(ra_deg=400.0, dec_deg=0.0, radius_deg=1.0)


def test_query_validates_dec_range():
    with pytest.raises(ValueError):
        GaiaQuery(ra_deg=0.0, dec_deg=-91.0, radius_deg=1.0)


def test_query_validates_radius_range():
    with pytest.raises(ValueError):
        GaiaQuery(ra_deg=0.0, dec_deg=0.0, radius_deg=0.0)
    with pytest.raises(ValueError):
        GaiaQuery(ra_deg=0.0, dec_deg=0.0, radius_deg=MAX_RADIUS_DEG + 1)


def test_query_validates_limit_range():
    with pytest.raises(ValueError):
        GaiaQuery(ra_deg=0.0, dec_deg=0.0, radius_deg=1.0, limit=0)
    with pytest.raises(ValueError):
        GaiaQuery(
            ra_deg=0.0, dec_deg=0.0, radius_deg=1.0, limit=MAX_ROW_LIMIT + 1,
        )


def test_query_rejects_unknown_release():
    with pytest.raises(ValueError):
        GaiaQuery(ra_deg=0.0, dec_deg=0.0, radius_deg=1.0, release="gaia_dr5")


# ---------------------------------------------------------------------------
# ADQL builder
# ---------------------------------------------------------------------------


def test_build_adql_includes_columns_and_geometry():
    q = GaiaQuery(ra_deg=56.75, dec_deg=24.12, radius_deg=1.0, limit=5000)
    sql = build_adql(q)
    # All expected columns appear.
    for col in (
        "source_id", "ra", "dec", "parallax", "parallax_error",
        "pmra", "pmdec", "radial_velocity",
        "phot_g_mean_mag", "bp_rp",
    ):
        assert col in sql
    # Cone geometry uses CONTAINS / POINT / CIRCLE on ICRS.
    assert "CONTAINS" in sql and "POINT('ICRS', ra, dec)" in sql
    assert "CIRCLE('ICRS', 56.75, 24.12, 1.0)" in sql
    # Brightest first so --limit truncates noise, not signal.
    assert "ORDER BY phot_g_mean_mag ASC" in sql
    # Row cap matches the request.
    assert "TOP 5000" in sql


def test_build_adql_uses_release_table():
    q = GaiaQuery(ra_deg=0.0, dec_deg=0.0, radius_deg=0.5, release="gaia_dr2")
    sql = build_adql(q)
    assert "gaiadr2.gaia_source" in sql


# ---------------------------------------------------------------------------
# safe_parallax_to_distance
# ---------------------------------------------------------------------------


def test_safe_parallax_returns_none_for_negative():
    assert safe_parallax_to_distance(-0.5) is None
    assert safe_parallax_to_distance(0.0) is None


def test_safe_parallax_returns_none_for_missing():
    assert safe_parallax_to_distance(None) is None


def test_safe_parallax_returns_none_below_snr_floor():
    # parallax/error = 2 < default snr_min 5
    assert safe_parallax_to_distance(2.0, parallax_error_mas=1.0) is None


def test_safe_parallax_returns_distance_above_snr_floor():
    d = safe_parallax_to_distance(10.0, parallax_error_mas=1.0)
    assert d == pytest.approx(100.0, rel=1e-9)


def test_safe_parallax_ignores_error_when_disabled():
    # snr_min=0 disables the SNR cut.
    d = safe_parallax_to_distance(2.0, parallax_error_mas=1.0, snr_min=0.0)
    assert d == pytest.approx(500.0, rel=1e-9)


def test_safe_parallax_rejects_implausibly_large_distance():
    # tiny positive parallax => distance > 1e5 pc => rejected.
    assert safe_parallax_to_distance(0.001) is None


# ---------------------------------------------------------------------------
# Normalize one row
# ---------------------------------------------------------------------------


def test_normalize_full_row():
    row = {
        "source_id": "1234567890",
        "ra": "56.75",
        "dec": "24.12",
        "parallax": "10.0",
        "parallax_error": "1.0",
        "pmra": "5.5",
        "pmdec": "-3.2",
        "radial_velocity": "12.7",
        "phot_g_mean_mag": "8.4",
        "bp_rp": "0.9",
    }
    objs = normalize_rows([row])
    assert len(objs) == 1
    o = objs[0]
    assert o.uid == "gaia_dr3:1234567890"
    assert o.catalog_source == "gaia_dr3"
    assert o.object_type == "star"
    assert o.ra_deg == 56.75
    assert o.dec_deg == 24.12
    assert o.parallax_mas == 10.0
    assert o.distance_parsec == pytest.approx(100.0)
    assert o.proper_motion_ra == 5.5
    assert o.proper_motion_dec == -3.2
    assert o.radial_velocity_kms == 12.7
    assert o.apparent_magnitude == 8.4
    assert o.color_index == 0.9
    extra = json.loads(o.metadata_json)
    assert extra["source_id"] == "1234567890"
    assert extra["release"] == "gaia_dr3"
    assert extra["parallax_error_mas"] == 1.0


def test_normalize_skips_row_missing_identifier():
    row = {"source_id": "", "ra": "10.0", "dec": "20.0"}
    assert normalize_rows([row]) == []


def test_normalize_skips_row_missing_position():
    row = {"source_id": "abc", "ra": "", "dec": "20.0"}
    assert normalize_rows([row]) == []


def test_normalize_skips_row_with_out_of_range_position():
    row = {"source_id": "abc", "ra": "999.0", "dec": "20.0"}
    assert normalize_rows([row]) == []


def test_normalize_handles_missing_optional_fields():
    row = {"source_id": "abc", "ra": "10.0", "dec": "20.0"}
    objs = normalize_rows([row])
    assert len(objs) == 1
    o = objs[0]
    assert o.parallax_mas is None
    assert o.distance_parsec is None
    assert o.proper_motion_ra is None
    assert o.apparent_magnitude is None


def test_normalize_negative_parallax_yields_no_distance():
    row = {
        "source_id": "abc", "ra": "10.0", "dec": "20.0",
        "parallax": "-0.5", "parallax_error": "0.1",
    }
    objs = normalize_rows([row])
    assert objs[0].distance_parsec is None
    assert objs[0].parallax_mas == -0.5  # raw value preserved


def test_normalize_low_snr_parallax_yields_no_distance():
    row = {
        "source_id": "abc", "ra": "10.0", "dec": "20.0",
        "parallax": "2.0", "parallax_error": "1.0",  # SNR=2
    }
    objs = normalize_rows([row])
    assert objs[0].distance_parsec is None
    assert objs[0].parallax_mas == 2.0


def test_normalize_treats_null_strings_as_missing():
    row = {
        "source_id": "abc", "ra": "10.0", "dec": "20.0",
        "parallax": "null", "parallax_error": "NaN",
        "pmra": "None",
    }
    objs = normalize_rows([row])
    assert objs[0].parallax_mas is None
    assert objs[0].proper_motion_ra is None


# ---------------------------------------------------------------------------
# fetch_rows with injected fetcher
# ---------------------------------------------------------------------------


def test_fetch_rows_parses_csv_response():
    body = _csv(
        "1,10.0,20.0,5.0,0.5,1.1,2.2,30.0,8.0,0.5",
        "2,11.0,21.0,,,,,,9.0,",
    )
    fetcher, captured = _make_fetcher(body)
    q = GaiaQuery(ra_deg=10.0, dec_deg=20.0, radius_deg=0.5, limit=10)
    rows = fetch_rows(q, fetch_fn=fetcher)
    assert len(rows) == 2
    assert rows[0]["source_id"] == "1"
    assert rows[1]["parallax"] == ""
    # The fetcher saw the right URL + ADQL params.
    assert captured["url"] == gc.GAIA_TAP_SYNC_URL
    assert captured["params"]["FORMAT"] == "csv"
    assert captured["params"]["LANG"] == "ADQL"
    assert "CIRCLE('ICRS', 10.0, 20.0, 0.5)" in captured["params"]["QUERY"]


def test_fetch_rows_handles_empty_body():
    fetcher, _ = _make_fetcher("")
    q = GaiaQuery(ra_deg=0.0, dec_deg=0.0, radius_deg=0.5, limit=10)
    assert fetch_rows(q, fetch_fn=fetcher) == []


def test_fetch_rows_propagates_fetcher_error():
    def failing(url, params):
        raise GaiaQueryError("simulated network failure")

    q = GaiaQuery(ra_deg=0.0, dec_deg=0.0, radius_deg=0.5, limit=10)
    with pytest.raises(GaiaQueryError, match="simulated"):
        fetch_rows(q, fetch_fn=failing)


# ---------------------------------------------------------------------------
# fetch_and_normalize
# ---------------------------------------------------------------------------


def test_fetch_and_normalize_returns_catalog_objects():
    body = _csv(
        "1,10.0,20.0,5.0,0.5,1.1,2.2,30.0,8.0,0.5",
        "2,bad,21.0,,,,,,9.0,",          # bad ra -> skipped
        ",11.0,21.0,,,,,,9.0,",          # missing source_id -> skipped
        "3,11.0,21.0,8.0,1.0,,,,9.0,0.4",
    )
    fetcher, _ = _make_fetcher(body)
    q = GaiaQuery(ra_deg=10.0, dec_deg=20.0, radius_deg=0.5, limit=10)
    objs = fetch_and_normalize(q, fetch_fn=fetcher)
    assert [o.uid for o in objs] == ["gaia_dr3:1", "gaia_dr3:3"]
    assert all(o.catalog_source == DEFAULT_GAIA_RELEASE for o in objs)
    assert all(o.object_type == "star" for o in objs)


def test_fetch_and_normalize_passes_release_through():
    body = _csv("9,10.0,20.0,,,,,,9.0,")
    fetcher, _ = _make_fetcher(body)
    q = GaiaQuery(
        ra_deg=10.0, dec_deg=20.0, radius_deg=0.5,
        limit=10, release="gaia_dr2",
    )
    objs = fetch_and_normalize(q, fetch_fn=fetcher)
    assert objs[0].uid == "gaia_dr2:9"
    assert objs[0].catalog_source == "gaia_dr2"
