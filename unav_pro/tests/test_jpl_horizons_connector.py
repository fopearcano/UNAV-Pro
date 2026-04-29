"""Tests for the JPL Horizons connector. Mocked responses only."""

from __future__ import annotations

import json
import math

import pytest

from data.connectors import jpl_horizons_connector as jpl
from data.connectors.jpl_horizons_connector import (
    AU_TO_PC,
    DEFAULT_CENTER,
    DEFAULT_OBJECT_TYPE,
    JPLBodyQuery,
    JPLHorizonsError,
    SOURCE_NAME,
    build_request_params,
    fetch_and_normalize,
    fetch_response,
    parse_response,
)


# ---------------------------------------------------------------------------
# Test fixture helpers
# ---------------------------------------------------------------------------


def _vectors_response(
    x_au: float = 1.5, y_au: float = 0.0, z_au: float = 0.0,
    vx: float = 0.0, vy: float = 0.017, vz: float = 0.0,
    lt: float = 0.00866, rg: float = 1.5,
    body_name: str = "Mars (499)",
    extra_text: str = "",
    signature: dict = None,
) -> dict:
    """Build a fake Horizons JSON response wrapping a vectors block."""
    body = (
        f"*******************************************************************************\n"
        f"Target body: {body_name}\n"
        f"Center body: Sun (10)\n"
        f"Output units: AU-D\n"
        f"Reference frame: Ecliptic of J2000.0\n"
        f"*******************************************************************************\n"
        f"$$SOE\n"
        f"2461041.500000000 = A.D. 2026-Jan-01 00:00:00.0000 TDB\n"
        f" X ={x_au: .16E} Y ={y_au: .16E} Z ={z_au: .16E}\n"
        f" VX={vx: .16E} VY={vy: .16E} VZ={vz: .16E}\n"
        f" LT={lt: .16E} RG={rg: .16E} RR={0.0: .16E}\n"
        f"$$EOE\n"
        f"*******************************************************************************\n"
        f"{extra_text}"
    )
    return {
        "signature": signature or {"source": "NASA/JPL Horizons", "version": "4.x"},
        "result": body,
    }


def _make_fetcher(payload: dict):
    """Return a fetch_fn returning ``payload`` and capturing call args."""
    captured: dict = {}

    def fetcher(url: str, params: dict) -> str:
        captured["url"] = url
        captured["params"] = params
        return json.dumps(payload)

    return fetcher, captured


# ---------------------------------------------------------------------------
# JPLBodyQuery validation
# ---------------------------------------------------------------------------


def test_query_requires_body():
    with pytest.raises(ValueError):
        JPLBodyQuery(body="", epoch="2026-01-01")


def test_query_requires_epoch():
    with pytest.raises(ValueError):
        JPLBodyQuery(body="Mars", epoch="")


def test_query_rejects_unknown_object_type():
    with pytest.raises(ValueError):
        JPLBodyQuery(body="Mars", epoch="2026-01-01", object_type="exoplanet")


def test_query_accepts_each_documented_type():
    for t in ("planet", "moon", "asteroid", "comet", "spacecraft"):
        JPLBodyQuery(body="X", epoch="2026-01-01", object_type=t)


def test_query_default_object_type_is_planet():
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    assert q.object_type == DEFAULT_OBJECT_TYPE


def test_query_effective_stop_default_appends_one_day():
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    assert q.effective_stop() == "2026-01-01 +1d"


def test_query_effective_stop_uses_explicit_value():
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01", stop_epoch="2026-01-05")
    assert q.effective_stop() == "2026-01-05"


# ---------------------------------------------------------------------------
# Request params
# ---------------------------------------------------------------------------


def test_build_request_params_quotes_strings_and_sets_format():
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    p = build_request_params(q)
    assert p["format"] == "json"
    assert p["COMMAND"] == "'Mars'"
    assert p["START_TIME"] == "'2026-01-01'"
    assert p["STOP_TIME"] == "'2026-01-01 +1d'"
    assert p["EPHEM_TYPE"] == "VECTORS"
    assert p["CENTER"] == f"'{DEFAULT_CENTER}'"
    assert p["REF_PLANE"] == "'FRAME'"
    assert p["OUT_UNITS"] == "'AU-D'"


def test_build_request_params_propagates_custom_center():
    q = JPLBodyQuery(body="Phobos", epoch="2026-01-01", center="500@499")
    p = build_request_params(q)
    assert p["CENTER"] == "'500@499'"


# ---------------------------------------------------------------------------
# fetch_response with injected fetcher
# ---------------------------------------------------------------------------


def test_fetch_response_returns_parsed_dict():
    payload = _vectors_response()
    fetcher, captured = _make_fetcher(payload)
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    out = fetch_response(q, fetch_fn=fetcher)
    assert out["result"].startswith("*****")
    assert captured["url"] == jpl.JPL_HORIZONS_URL
    assert captured["params"]["COMMAND"] == "'Mars'"


def test_fetch_response_invalid_json_raises():
    def fetcher(url, params):
        return "<html>not json</html>"

    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    with pytest.raises(JPLHorizonsError, match="not valid JSON"):
        fetch_response(q, fetch_fn=fetcher)


def test_fetch_response_propagates_fetcher_error():
    def fetcher(url, params):
        raise JPLHorizonsError("simulated network failure")

    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    with pytest.raises(JPLHorizonsError, match="simulated"):
        fetch_response(q, fetch_fn=fetcher)


# ---------------------------------------------------------------------------
# parse_response
# ---------------------------------------------------------------------------


def test_parse_response_full_vector_round_trip():
    # Place a fictitious body at exactly (1.5, 0, 0) AU. The connector
    # should report ra=0, dec=0, distance = 1.5 AU in pc.
    payload = _vectors_response(x_au=1.5, y_au=0.0, z_au=0.0)
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01", object_type="planet")
    obj = parse_response(payload, q)

    assert obj.uid == f"{SOURCE_NAME}:Mars@2026-01-01"
    assert obj.catalog_source == SOURCE_NAME
    assert obj.object_type == "planet"
    assert obj.ra_deg == pytest.approx(0.0, abs=1e-9)
    assert obj.dec_deg == pytest.approx(0.0, abs=1e-9)
    assert obj.distance_parsec == pytest.approx(1.5 * AU_TO_PC, rel=1e-9)
    assert obj.name == "Mars"

    extra = json.loads(obj.metadata_json)
    assert extra["body"] == "Mars"
    assert extra["epoch"] == "2026-01-01"
    assert extra["center"] == DEFAULT_CENTER
    assert extra["ref_plane"] == "ICRF"
    assert extra["vector_au"] == {"X": 1.5, "Y": 0.0, "Z": 0.0}
    assert "horizons_signature" in extra


def test_parse_response_off_axis_vector():
    # Place a body at (0, 0, 1) AU — straight up the +Z axis
    # ⇒ dec = +90°, ra is degenerate but the connector returns 0.
    payload = _vectors_response(x_au=0.0, y_au=0.0, z_au=1.0)
    q = JPLBodyQuery(body="Phantom", epoch="2026-01-01", object_type="asteroid")
    obj = parse_response(payload, q)
    assert obj.dec_deg == pytest.approx(90.0)
    assert obj.distance_parsec == pytest.approx(1.0 * AU_TO_PC, rel=1e-9)
    assert obj.object_type == "asteroid"


def test_parse_response_45deg_vector_distance_correct():
    payload = _vectors_response(x_au=1.0, y_au=1.0, z_au=0.0)
    q = JPLBodyQuery(body="Test", epoch="2026-01-01")
    obj = parse_response(payload, q)
    assert obj.ra_deg == pytest.approx(45.0)
    assert obj.dec_deg == pytest.approx(0.0, abs=1e-9)
    assert obj.distance_parsec == pytest.approx(math.sqrt(2.0) * AU_TO_PC, rel=1e-9)


def test_parse_response_negative_y_wraps_ra_to_positive():
    # (1, -1, 0) ⇒ ra = atan2(-1, 1) = -45°; should wrap to 315°.
    payload = _vectors_response(x_au=1.0, y_au=-1.0, z_au=0.0)
    q = JPLBodyQuery(body="Test", epoch="2026-01-01")
    obj = parse_response(payload, q)
    assert obj.ra_deg == pytest.approx(315.0, abs=1e-9)


def test_parse_response_preserves_velocity_and_lt_metadata():
    payload = _vectors_response(
        x_au=1.5, y_au=0.0, z_au=0.0,
        vx=0.001, vy=0.017, vz=0.002,
        lt=0.00866, rg=1.5,
    )
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    obj = parse_response(payload, q)
    extra = json.loads(obj.metadata_json)
    assert extra["vx_au_per_d"] == pytest.approx(0.001)
    assert extra["lt"] == pytest.approx(0.00866)
    assert extra["rg"] == pytest.approx(1.5)


def test_parse_response_uid_is_filesystem_safe():
    payload = _vectors_response()
    q = JPLBodyQuery(
        body="Voyager 1", epoch="2026/01/01 12:30",
        object_type="spacecraft",
    )
    obj = parse_response(payload, q)
    assert " " not in obj.uid
    assert "/" not in obj.uid
    assert obj.uid.startswith(f"{SOURCE_NAME}:Voyager_1")


# ---------------------------------------------------------------------------
# Error paths in parse_response
# ---------------------------------------------------------------------------


def test_parse_response_no_result_text():
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    with pytest.raises(JPLHorizonsError, match="no 'result' text"):
        parse_response({"signature": {}}, q)


def test_parse_response_missing_soe_eoe_block():
    payload = {"signature": {}, "result": "no ephemeris here"}
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    with pytest.raises(JPLHorizonsError, match=r"\$\$SOE/\$\$EOE"):
        parse_response(payload, q)


def test_parse_response_missing_xyz_label_raises():
    bad = {
        "signature": {},
        "result": (
            "$$SOE\n"
            "2461041.500000 = A.D. 2026-Jan-01\n"
            " X = 1.5  Z = 0.0\n"   # Y missing
            "$$EOE\n"
        ),
    }
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    with pytest.raises(JPLHorizonsError, match="missing 'Y'"):
        parse_response(bad, q)


def test_parse_response_multiple_match_raises():
    payload = {
        "signature": {},
        "result": (
            "Multiple major-bodies match string 'Mars'\n"
            " ID#  Name   ...\n"
            "  4   Mars Barycenter\n"
            "  499 Mars\n"
        ),
    }
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    with pytest.raises(JPLHorizonsError, match="ambiguous"):
        parse_response(payload, q)


def test_parse_response_no_match_raises():
    payload = {
        "signature": {},
        "result": "No matches found.\n",
    }
    q = JPLBodyQuery(body="Tatooine", epoch="2026-01-01")
    with pytest.raises(JPLHorizonsError, match="no body matching"):
        parse_response(payload, q)


# ---------------------------------------------------------------------------
# fetch_and_normalize end-to-end
# ---------------------------------------------------------------------------


def test_fetch_and_normalize_end_to_end_returns_catalog_object():
    payload = _vectors_response(x_au=1.5, y_au=0.0, z_au=0.0)
    fetcher, _ = _make_fetcher(payload)
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01", object_type="planet")
    obj = fetch_and_normalize(q, fetch_fn=fetcher)
    assert obj.catalog_source == SOURCE_NAME
    assert obj.distance_parsec is not None
    assert obj.distance_parsec > 0.0
