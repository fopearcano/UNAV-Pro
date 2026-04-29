"""Tests for the DESI connector. Mocked responses only."""

from __future__ import annotations

import json

import pytest

from data.connectors import desi_connector as desi
from data.connectors.desi_connector import (
    DEFAULT_DESI_RELEASE,
    MAX_RADIUS_DEG,
    MAX_ROW_LIMIT,
    DESIQuery,
    DESIQueryError,
    build_adql,
    fetch_and_normalize,
    fetch_rows,
    normalize_rows,
    safe_redshift_to_distance,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_HEADER = (
    "targetid,target_ra,target_dec,z,zerr,zwarn,"
    "spectype,subtype,desi_target,survey,program,healpix"
)


def _csv(*rows: str) -> str:
    return "\n".join((_HEADER, *rows)) + "\n"


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


def test_query_validates_basic_ranges():
    with pytest.raises(ValueError):
        DESIQuery(ra_deg=400, dec_deg=0, radius_deg=0.5)
    with pytest.raises(ValueError):
        DESIQuery(ra_deg=0, dec_deg=-91, radius_deg=0.5)
    with pytest.raises(ValueError):
        DESIQuery(ra_deg=0, dec_deg=0, radius_deg=0.0)
    with pytest.raises(ValueError):
        DESIQuery(ra_deg=0, dec_deg=0, radius_deg=MAX_RADIUS_DEG + 1)
    with pytest.raises(ValueError):
        DESIQuery(ra_deg=0, dec_deg=0, radius_deg=0.5, limit=0)
    with pytest.raises(ValueError):
        DESIQuery(ra_deg=0, dec_deg=0, radius_deg=0.5, limit=MAX_ROW_LIMIT + 1)


def test_query_rejects_unknown_release():
    with pytest.raises(ValueError):
        DESIQuery(ra_deg=0, dec_deg=0, radius_deg=0.5, release="desi_dr99")


def test_query_normalizes_spectype_to_uppercase():
    q = DESIQuery(ra_deg=0, dec_deg=0, radius_deg=0.5, spectype="galaxy")
    assert q.spectype == "GALAXY"


def test_query_rejects_unknown_spectype():
    with pytest.raises(ValueError):
        DESIQuery(ra_deg=0, dec_deg=0, radius_deg=0.5, spectype="UFO")


# ---------------------------------------------------------------------------
# ADQL builder
# ---------------------------------------------------------------------------


def test_build_adql_includes_columns_and_geometry():
    q = DESIQuery(ra_deg=180.0, dec_deg=30.0, radius_deg=1.0, limit=500)
    sql = build_adql(q)
    for col in (
        "targetid", "target_ra", "target_dec", "z", "zerr", "zwarn",
        "spectype", "subtype", "desi_target", "survey", "program", "healpix",
    ):
        assert col in sql
    assert "1=CONTAINS(POINT('ICRS', target_ra, target_dec)" in sql
    assert "CIRCLE('ICRS', 180.0, 30.0, 1.0)" in sql
    assert "TOP 500" in sql
    assert "FROM desi_edr.zpix" in sql
    assert "ORDER BY z ASC" in sql


def test_build_adql_appends_spectype_filter():
    q = DESIQuery(
        ra_deg=10.0, dec_deg=20.0, radius_deg=0.5, spectype="GALAXY",
    )
    sql = build_adql(q)
    assert "spectype = 'GALAXY'" in sql


def test_build_adql_uses_release_table():
    q = DESIQuery(
        ra_deg=10.0, dec_deg=20.0, radius_deg=0.5, release="desi_dr1",
    )
    sql = build_adql(q)
    assert "FROM desi_dr1.zpix" in sql


# ---------------------------------------------------------------------------
# safe_redshift_to_distance
# ---------------------------------------------------------------------------


def test_safe_redshift_zero_or_missing():
    assert safe_redshift_to_distance(None) is None
    assert safe_redshift_to_distance(0.0) is None
    assert safe_redshift_to_distance(-0.01) is None


def test_safe_redshift_above_max_z():
    assert safe_redshift_to_distance(0.5) is None


def test_safe_redshift_zwarn_nonzero_rejects():
    assert safe_redshift_to_distance(0.05, zwarn=4) is None


def test_safe_redshift_clean_low_z_accepted():
    d = safe_redshift_to_distance(0.05, zwarn=0)
    assert d is not None and d > 0


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------


def test_normalize_galaxy_row():
    row = {
        "targetid": "39633072104341543",
        "target_ra": "180.0",
        "target_dec": "30.0",
        "z": "0.05",
        "zerr": "0.0001",
        "zwarn": "0",
        "spectype": "GALAXY",
        "subtype": "BGS",
        "desi_target": "1",
        "survey": "main",
        "program": "bright",
        "healpix": "12345",
    }
    objs = normalize_rows([row])
    assert len(objs) == 1
    o = objs[0]
    assert o.uid == "desi_edr:39633072104341543"
    assert o.catalog_source == "desi_edr"
    assert o.object_type == "galaxy"
    assert o.redshift == pytest.approx(0.05)
    assert o.distance_parsec is not None and o.distance_parsec > 0
    extra = json.loads(o.metadata_json)
    assert extra["survey"] == "main"
    assert extra["program"] == "bright"
    assert extra["spectype"] == "GALAXY"
    assert extra["subtype"] == "BGS"
    assert extra["zwarn"] == 0
    assert extra["healpix"] == 12345


def test_normalize_quasar_at_high_z_no_distance():
    row = {
        "targetid": "1", "target_ra": "10", "target_dec": "20",
        "z": "1.5", "zerr": "0.001", "zwarn": "0", "spectype": "QSO",
    }
    o = normalize_rows([row])[0]
    assert o.object_type == "quasar"
    assert o.redshift == pytest.approx(1.5)
    assert o.distance_parsec is None


def test_normalize_zwarn_blocks_distance_but_keeps_row():
    row = {
        "targetid": "1", "target_ra": "10", "target_dec": "20",
        "z": "0.05", "zerr": "0.0001", "zwarn": "1",
        "spectype": "GALAXY",
    }
    o = normalize_rows([row])[0]
    assert o.distance_parsec is None
    assert o.redshift == pytest.approx(0.05)
    extra = json.loads(o.metadata_json)
    assert extra["zwarn"] == 1


def test_normalize_star_object_type():
    row = {
        "targetid": "1", "target_ra": "10", "target_dec": "20",
        "spectype": "STAR",
    }
    assert normalize_rows([row])[0].object_type == "star"


def test_normalize_unknown_for_missing_spectype():
    row = {"targetid": "1", "target_ra": "10", "target_dec": "20"}
    assert normalize_rows([row])[0].object_type == "unknown"


def test_normalize_skips_missing_id_or_position():
    bad = [
        {"targetid": "", "target_ra": "10", "target_dec": "20"},
        {"targetid": "x", "target_ra": "", "target_dec": "20"},
        {"targetid": "y", "target_ra": "999", "target_dec": "20"},
    ]
    assert normalize_rows(bad) == []


def test_normalize_accepts_uppercase_column_names():
    # NOIRLab TAP responses sometimes echo column names back uppercased.
    row = {
        "TARGETID": "abc",
        "TARGET_RA": "10",
        "TARGET_DEC": "20",
        "Z": "0.05",
        "ZWARN": "0",
        "SPECTYPE": "GALAXY",
    }
    objs = normalize_rows([row])
    assert len(objs) == 1
    assert objs[0].uid == "desi_edr:abc"
    assert objs[0].object_type == "galaxy"


# ---------------------------------------------------------------------------
# fetch_rows / fetch_and_normalize
# ---------------------------------------------------------------------------


def test_fetch_rows_parses_csv_response():
    body = _csv(
        "1,180.0,30.0,0.05,0.0001,0,GALAXY,BGS,1,main,bright,12345",
        "2,180.1,30.1,1.2,0.001,0,QSO,,,sv1,dark,12346",
    )
    fetcher, captured = _make_fetcher(body)
    q = DESIQuery(ra_deg=180.0, dec_deg=30.0, radius_deg=1.0, limit=10)
    rows = fetch_rows(q, fetch_fn=fetcher)
    assert len(rows) == 2
    assert rows[0]["targetid"] == "1"
    assert captured["url"] == desi.DESI_TAP_SYNC_URL
    assert captured["params"]["LANG"] == "ADQL"
    assert "CIRCLE('ICRS', 180.0, 30.0, 1.0)" in captured["params"]["QUERY"]


def test_fetch_rows_empty_body():
    fetcher, _ = _make_fetcher("")
    q = DESIQuery(ra_deg=10, dec_deg=20, radius_deg=0.5, limit=5)
    assert fetch_rows(q, fetch_fn=fetcher) == []


def test_fetch_rows_propagates_fetcher_error():
    def boom(url, params):
        raise DESIQueryError("simulated network failure")

    q = DESIQuery(ra_deg=10, dec_deg=20, radius_deg=0.5, limit=5)
    with pytest.raises(DESIQueryError, match="simulated"):
        fetch_rows(q, fetch_fn=boom)


def test_fetch_and_normalize_end_to_end():
    body = _csv(
        "1,180.0,30.0,0.05,0.0001,0,GALAXY,BGS,1,main,bright,12345",
        "2,bad,30.0,0.05,0.0001,0,GALAXY,,,,,,",   # bad ra → skipped
        "3,180.0,30.0,1.2,0.001,0,QSO,,,sv1,dark,12346",
    )
    fetcher, _ = _make_fetcher(body)
    q = DESIQuery(ra_deg=180.0, dec_deg=30.0, radius_deg=1.0, limit=10)
    objs = fetch_and_normalize(q, fetch_fn=fetcher)
    assert [o.uid for o in objs] == ["desi_edr:1", "desi_edr:3"]
    assert {o.object_type for o in objs} == {"galaxy", "quasar"}
    assert all(o.catalog_source == DEFAULT_DESI_RELEASE for o in objs)
