"""Tests for the SDSS connector. Mocked responses only."""

from __future__ import annotations

import json

import pytest

from data.connectors import sdss_connector as sdss
from data.connectors.sdss_connector import (
    DEFAULT_SDSS_RELEASE,
    MAX_RADIUS_DEG,
    MAX_ROW_LIMIT,
    SDSSQuery,
    SDSSQueryError,
    build_sql,
    fetch_and_normalize,
    fetch_rows,
    normalize_rows,
    safe_redshift_to_distance,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_PHOTO_HEADER = (
    "objID,ra,dec,type,modelMag_u,modelMag_g,modelMag_r,modelMag_i,modelMag_z"
)
_PHOTO_SPEC_HEADER = (
    "objID,ra,dec,type,modelMag_u,modelMag_g,modelMag_r,modelMag_i,modelMag_z,"
    "specObjID,spec_z,spec_zerr,spec_class,spec_subclass"
)


def _csv(header: str, *rows: str) -> str:
    return "\n".join((header, *rows)) + "\n"


def _make_fetcher(body: str):
    captured = {}

    def fetcher(url: str, params: dict) -> str:
        captured["url"] = url
        captured["params"] = params
        return body

    return fetcher, captured


# ---------------------------------------------------------------------------
# Query validation
# ---------------------------------------------------------------------------


def test_query_validates_ra_dec_radius_limit():
    with pytest.raises(ValueError):
        SDSSQuery(ra_deg=400, dec_deg=0, radius_deg=0.1)
    with pytest.raises(ValueError):
        SDSSQuery(ra_deg=0, dec_deg=-91, radius_deg=0.1)
    with pytest.raises(ValueError):
        SDSSQuery(ra_deg=0, dec_deg=0, radius_deg=0.0)
    with pytest.raises(ValueError):
        SDSSQuery(ra_deg=0, dec_deg=0, radius_deg=MAX_RADIUS_DEG + 1)
    with pytest.raises(ValueError):
        SDSSQuery(ra_deg=0, dec_deg=0, radius_deg=0.1, limit=0)
    with pytest.raises(ValueError):
        SDSSQuery(ra_deg=0, dec_deg=0, radius_deg=0.1, limit=MAX_ROW_LIMIT + 1)


def test_query_rejects_unknown_release():
    with pytest.raises(ValueError):
        SDSSQuery(ra_deg=0, dec_deg=0, radius_deg=0.1, release="sdss_dr20")


# ---------------------------------------------------------------------------
# SQL builder
# ---------------------------------------------------------------------------


def test_build_sql_uses_cone_function_and_radius_in_arcmin():
    q = SDSSQuery(ra_deg=180.0, dec_deg=30.0, radius_deg=0.5, limit=100)
    sql = build_sql(q)
    # Cone search uses fGetNearbyObjEq with arcminute radius.
    assert "dbo.fGetNearbyObjEq(180.0, 30.0, 30.0)" in sql  # 0.5° = 30'
    # Photometry columns present.
    assert "p.modelMag_g" in sql and "p.modelMag_r" in sql
    # Spectro join is on by default.
    assert "LEFT JOIN SpecObj" in sql
    assert "TOP 100" in sql


def test_build_sql_omits_spectro_join_when_disabled():
    q = SDSSQuery(
        ra_deg=10.0, dec_deg=20.0, radius_deg=0.1, include_spectro=False,
    )
    sql = build_sql(q)
    assert "SpecObj" not in sql
    assert "spec_z" not in sql


# ---------------------------------------------------------------------------
# safe_redshift_to_distance
# ---------------------------------------------------------------------------


def test_safe_redshift_zero_or_missing():
    assert safe_redshift_to_distance(None) is None
    assert safe_redshift_to_distance(0.0) is None
    assert safe_redshift_to_distance(-0.01) is None


def test_safe_redshift_above_max_z():
    assert safe_redshift_to_distance(0.5) is None  # default max_z=0.1


def test_safe_redshift_at_low_z_uses_hubble_law():
    d = safe_redshift_to_distance(0.05, h0_km_s_mpc=70.0)
    # c*z/H0 = 3e5 * 0.05 / 70 = 214.14 Mpc
    assert d is not None
    expected_pc = (299_792.458 * 0.05 / 70.0) * 1.0e6
    assert d == pytest.approx(expected_pc, rel=1e-9)


def test_safe_redshift_respects_custom_max_z():
    d = safe_redshift_to_distance(0.3, max_z=0.5)
    assert d is not None and d > 0


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------


def test_normalize_galaxy_row_with_spectro():
    row = {
        "objID": "1237660025074876421",
        "ra": "180.0",
        "dec": "30.0",
        "type": "3",  # photometric "galaxy"
        "modelMag_u": "20.5",
        "modelMag_g": "19.2",
        "modelMag_r": "18.7",
        "modelMag_i": "18.4",
        "modelMag_z": "18.2",
        "specObjID": "299493011468288000",
        "spec_z": "0.05",
        "spec_zerr": "0.0001",
        "spec_class": "GALAXY",
        "spec_subclass": "STARBURST",
    }
    objs = normalize_rows([row])
    assert len(objs) == 1
    o = objs[0]
    assert o.uid == "sdss_dr18:1237660025074876421"
    assert o.catalog_source == "sdss_dr18"
    assert o.object_type == "galaxy"
    assert o.ra_deg == 180.0 and o.dec_deg == 30.0
    assert o.redshift == pytest.approx(0.05)
    # Hubble-law distance applied (z < 0.1).
    assert o.distance_parsec is not None
    assert o.distance_parsec > 0
    assert o.apparent_magnitude == pytest.approx(18.7)  # modelMag_r
    assert o.color_index == pytest.approx(0.5)  # g - r
    extra = json.loads(o.metadata_json)
    assert extra["spec_class"] == "GALAXY"
    assert extra["spec_subclass"] == "STARBURST"
    assert extra["modelMag_g"] == 19.2


def test_normalize_quasar_via_spec_class_overrides_photo_type():
    # Photometric type=3 (galaxy) but SpecObj.class=QSO ⇒ quasar.
    row = {
        "objID": "abc", "ra": "10", "dec": "20",
        "type": "3",
        "modelMag_r": "20.0",
        "spec_class": "QSO",
        "spec_z": "1.5",
    }
    objs = normalize_rows([row])
    assert objs[0].object_type == "quasar"
    # Hubble fallback rejected (z > 0.1) — distance stays None.
    assert objs[0].distance_parsec is None
    assert objs[0].redshift == pytest.approx(1.5)


def test_normalize_star_via_photo_type_when_no_spectro():
    row = {
        "objID": "abc", "ra": "10", "dec": "20",
        "type": "6",  # star
        "modelMag_r": "15.0",
    }
    objs = normalize_rows([row])
    assert objs[0].object_type == "star"
    assert objs[0].redshift is None
    assert objs[0].distance_parsec is None


def test_normalize_unknown_when_neither_class_nor_type_match():
    row = {"objID": "abc", "ra": "10", "dec": "20", "type": "0"}
    assert normalize_rows([row])[0].object_type == "unknown"


def test_normalize_skips_missing_id_or_position():
    bad = [
        {"objID": "", "ra": "10", "dec": "20"},
        {"objID": "x", "ra": "", "dec": "20"},
        {"objID": "y", "ra": "999", "dec": "20"},
    ]
    assert normalize_rows(bad) == []


def test_normalize_handles_null_strings():
    row = {
        "objID": "x", "ra": "10", "dec": "20", "type": "null",
        "modelMag_g": "NaN", "modelMag_r": "None",
    }
    objs = normalize_rows([row])
    assert objs[0].apparent_magnitude is None
    assert objs[0].color_index is None
    assert objs[0].object_type == "unknown"


# ---------------------------------------------------------------------------
# fetch_rows / fetch_and_normalize
# ---------------------------------------------------------------------------


def test_fetch_rows_strips_leading_comment_lines():
    body = (
        "# SDSS SkyServer SQL service header line\n"
        + _csv(_PHOTO_HEADER,
               "1,180.0,30.0,3,20.0,19.0,18.5,18.0,17.5",
               "2,180.1,30.1,6,18.0,17.5,17.0,16.5,16.0")
    )
    fetcher, captured = _make_fetcher(body)
    q = SDSSQuery(
        ra_deg=180.0, dec_deg=30.0, radius_deg=0.5, limit=10,
        include_spectro=False,
    )
    rows = fetch_rows(q, fetch_fn=fetcher)
    assert len(rows) == 2
    assert rows[0]["objID"] == "1"
    # Fetcher saw the right URL + SQL.
    assert "skyserver.sdss.org/dr18" in captured["url"]
    assert "fGetNearbyObjEq(180.0, 30.0, 30.0)" in captured["params"]["cmd"]
    assert captured["params"]["format"] == "csv"


def test_fetch_rows_handles_empty_body():
    fetcher, _ = _make_fetcher("")
    q = SDSSQuery(ra_deg=10.0, dec_deg=20.0, radius_deg=0.1, limit=5)
    assert fetch_rows(q, fetch_fn=fetcher) == []


def test_fetch_rows_propagates_fetcher_error():
    def boom(url, params):
        raise SDSSQueryError("simulated network failure")

    q = SDSSQuery(ra_deg=10, dec_deg=20, radius_deg=0.1, limit=5)
    with pytest.raises(SDSSQueryError, match="simulated"):
        fetch_rows(q, fetch_fn=boom)


def test_fetch_and_normalize_returns_catalog_objects():
    # Build the CSV programmatically so we can't miscount commas.
    cols = [
        "objID", "ra", "dec", "type",
        "modelMag_u", "modelMag_g", "modelMag_r",
        "modelMag_i", "modelMag_z",
        "specObjID", "spec_z", "spec_zerr",
        "spec_class", "spec_subclass",
    ]
    assert cols == _PHOTO_SPEC_HEADER.split(",")

    def row(**kw):
        return ",".join(str(kw.get(c, "")) for c in cols)

    body = "\n".join([
        _PHOTO_SPEC_HEADER,
        row(  # galaxy with valid low-z spectrum
            objID="1", ra="180.0", dec="30.0", type="3",
            modelMag_u="20.5", modelMag_g="19.2", modelMag_r="18.7",
            modelMag_i="18.4", modelMag_z="18.2",
            specObjID="9001", spec_z="0.05", spec_zerr="0.0001",
            spec_class="GALAXY", spec_subclass="STARBURST",
        ),
        row(objID="2", ra="bad", dec="30.0", type="3"),  # bad ra → skipped
        row(ra="10", dec="20", type="3"),                # missing id → skipped
        row(  # quasar
            objID="3", ra="10", dec="20", type="3",
            specObjID="9002", spec_z="1.2", spec_zerr="0.001",
            spec_class="QSO",
        ),
    ]) + "\n"
    fetcher, _ = _make_fetcher(body)
    q = SDSSQuery(ra_deg=180.0, dec_deg=30.0, radius_deg=0.5, limit=10)
    objs = fetch_and_normalize(q, fetch_fn=fetcher)
    assert [o.uid for o in objs] == ["sdss_dr18:1", "sdss_dr18:3"]
    assert {o.object_type for o in objs} == {"galaxy", "quasar"}
    assert all(o.catalog_source == DEFAULT_SDSS_RELEASE for o in objs)
