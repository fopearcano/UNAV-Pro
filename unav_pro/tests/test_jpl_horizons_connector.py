"""Tests for the JPL Horizons connector. Mocked responses only."""

from __future__ import annotations

import json
import math

import pytest

from data.connectors import jpl_horizons_connector as jpl
from data.connectors.jpl_horizons_connector import (
    AU_TO_PC,
    CATALOG_SOURCE_LABEL,
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

    assert obj.uid == "jpl:Mars:2026-01-01"
    assert obj.catalog_source == CATALOG_SOURCE_LABEL
    assert obj.catalog_source == "JPL Horizons"
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
    assert obj.uid.startswith("jpl:Voyager_1")


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
    assert obj.catalog_source == CATALOG_SOURCE_LABEL
    assert obj.distance_parsec is not None
    assert obj.distance_parsec > 0.0


# ---------------------------------------------------------------------------
# v0.4 — uid + catalog_source + cartesian/c4d direct population
# ---------------------------------------------------------------------------


def test_uid_format_is_jpl_body_epoch_per_v04_spec():
    payload = _vectors_response()
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01T00:00:00")
    obj = parse_response(payload, q)
    # Spec format: jpl:{body}:{epoch} — release-agnostic, registry
    # namespaces it later. ISO timestamp colons survive the slug.
    assert obj.uid == "jpl:Mars:2026-01-01T00:00:00"


def test_uid_whitespace_in_epoch_becomes_underscore():
    payload = _vectors_response()
    q = JPLBodyQuery(body="Mars", epoch="2026 Jan 01")
    obj = parse_response(payload, q)
    assert obj.uid == "jpl:Mars:2026_Jan_01"
    assert " " not in obj.uid


def test_catalog_source_is_human_readable_label():
    payload = _vectors_response()
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    obj = parse_response(payload, q)
    assert obj.catalog_source == "JPL Horizons"


def test_cartesian_xyz_populated_directly_from_horizons_vector():
    """Per v0.4: cartesian_x/y/z come from the Horizons vector (in pc),
    not via the schema's RA/Dec→Cartesian inference."""
    payload = _vectors_response(x_au=1.5, y_au=0.0, z_au=0.0)
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    obj = parse_response(payload, q)
    assert obj.cartesian_x == pytest.approx(1.5 * AU_TO_PC, rel=1e-12)
    assert obj.cartesian_y == pytest.approx(0.0, abs=1e-15)
    assert obj.cartesian_z == pytest.approx(0.0, abs=1e-15)


def test_c4d_xyz_default_pc_scale_matches_cartesian():
    """In default scale_mode='pc', c4d_x/y/z equals cartesian_x/y/z."""
    payload = _vectors_response(x_au=1.0, y_au=2.0, z_au=3.0)
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    obj = parse_response(payload, q)
    assert obj.c4d_x == obj.cartesian_x
    assert obj.c4d_y == obj.cartesian_y
    assert obj.c4d_z == obj.cartesian_z


def test_metadata_json_includes_epoch_center_and_units():
    payload = _vectors_response(x_au=1.5)
    q = JPLBodyQuery(
        body="Mars", epoch="2026-01-01T00:00:00",
        center="500@10", object_type="planet",
    )
    obj = parse_response(payload, q)
    extra = json.loads(obj.metadata_json)
    assert extra["epoch"] == "2026-01-01T00:00:00"
    assert extra["center"] == "500@10"
    assert extra["out_units"] == "AU-D"
    assert extra["ref_plane"] == "ICRF"
    assert extra["release"] == SOURCE_NAME
    # Vector preserved in BOTH au and pc form for downstream tooling.
    assert extra["vector_au"]["X"] == pytest.approx(1.5, rel=1e-12)
    assert extra["vector_pc"]["X"] == pytest.approx(1.5 * AU_TO_PC, rel=1e-12)
    assert extra["distance_au"] == pytest.approx(1.5, rel=1e-12)
    # 1 AU = 1.49597870700e8 km (IAU 2012). Allow 1e-3 relative.
    assert extra["distance_km"] == pytest.approx(1.5 * 1.49597870700e8, rel=1e-3)


def test_metadata_json_preserves_velocity_and_lt():
    payload = _vectors_response(
        x_au=1.5, vx=0.001, vy=0.017, vz=0.002,
        lt=0.00866, rg=1.5,
    )
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01")
    obj = parse_response(payload, q)
    extra = json.loads(obj.metadata_json)
    assert extra["vx_au_per_d"] == pytest.approx(0.001)
    assert extra["lt"] == pytest.approx(0.00866)
    assert extra["rg"] == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Batch helpers (partial failure)
# ---------------------------------------------------------------------------


def test_batch_fetches_multiple_bodies_at_one_epoch():
    from data.connectors.jpl_horizons_connector import (
        BatchBodyRequest, fetch_batch_and_normalize,
    )

    # A fetcher whose response depends on the COMMAND param.
    def fetcher(url, params):
        body = params["COMMAND"].strip("'")
        x = {"Mercury": 0.4, "Venus": 0.7, "Earth": 1.0, "Mars": 1.5}[body]
        return json.dumps(_vectors_response(x_au=x, body_name=body))

    requests = [
        BatchBodyRequest(body="Mercury"),
        BatchBodyRequest(body="Venus"),
        BatchBodyRequest(body="Earth"),
        BatchBodyRequest(body="Mars"),
    ]
    result = fetch_batch_and_normalize(
        requests, epoch="2026-01-01", fetch_fn=fetcher,
    )
    assert result.kept == 4
    assert result.failed == 0
    uids = [o.uid for o in result.objects]
    assert uids == [
        "jpl:Mercury:2026-01-01",
        "jpl:Venus:2026-01-01",
        "jpl:Earth:2026-01-01",
        "jpl:Mars:2026-01-01",
    ]


def test_batch_records_per_body_failures_and_continues():
    from data.connectors.jpl_horizons_connector import (
        BatchBodyRequest, fetch_batch_and_normalize, JPLHorizonsError,
    )

    def fetcher(url, params):
        body = params["COMMAND"].strip("'")
        if body == "Tatooine":
            return json.dumps({"signature": {}, "result": "No matches found.\n"})
        return json.dumps(_vectors_response(x_au=1.0, body_name=body))

    requests = [
        BatchBodyRequest(body="Mars"),
        BatchBodyRequest(body="Tatooine"),  # this one fails
        BatchBodyRequest(body="Earth"),
    ]
    result = fetch_batch_and_normalize(
        requests, epoch="2026-01-01", fetch_fn=fetcher,
    )
    assert result.kept == 2
    assert result.failed == 1
    failed_bodies = [b for b, _msg in result.errors]
    assert "Tatooine" in failed_bodies
    # Surviving rows are intact.
    assert {o.uid for o in result.objects} == {
        "jpl:Mars:2026-01-01", "jpl:Earth:2026-01-01",
    }


def test_batch_warns_when_too_many_bodies():
    from data.connectors.jpl_horizons_connector import (
        BatchBodyRequest, SOFT_BATCH_WARNING, fetch_batch_and_normalize,
    )

    def fetcher(url, params):
        return json.dumps(_vectors_response())

    bodies = [BatchBodyRequest(body=f"B{i}") for i in range(SOFT_BATCH_WARNING + 5)]
    result = fetch_batch_and_normalize(
        bodies, epoch="2026-01-01", fetch_fn=fetcher,
    )
    assert any("soft threshold" in w for w in result.warnings)


def test_batch_short_summary_renders():
    from data.connectors.jpl_horizons_connector import BatchResult

    r = BatchResult()
    r.objects = [parse_response(_vectors_response(), JPLBodyQuery(
        body="Mars", epoch="2026-01-01"))]
    r.errors = [("Tatooine", "No matches found.")]
    r.warnings = ["heads up"]
    text = r.short_summary()
    assert "kept 1" in text and "1 failed" in text and "1 warning" in text


# ---------------------------------------------------------------------------
# CLI-friendly one-shots — single + batch + optional index
# ---------------------------------------------------------------------------


def test_fetch_single_normalize_and_write_writes_jsonl(tmp_path):
    from data.connectors.jpl_horizons_connector import (
        fetch_single_normalize_and_write,
    )

    fetcher, _ = _make_fetcher(_vectors_response(x_au=1.5))
    q = JPLBodyQuery(body="Mars", epoch="2026-01-01T00:00:00", center="500@10")

    out = tmp_path / "mars.jsonl"
    report = fetch_single_normalize_and_write(q, str(out), fetch_fn=fetcher)
    assert report.object_count == 1
    assert out.exists()
    row = json.loads(out.read_text().splitlines()[0])
    assert row["uid"] == "jpl:Mars:2026-01-01T00:00:00"
    assert row["catalog_source"] == "JPL Horizons"
    # Cartesian baked into the JSONL — sector streaming reads these
    # directly without recomputing from RA/Dec/distance.
    assert row["cartesian_x"] == pytest.approx(1.5 * AU_TO_PC, rel=1e-12)
    assert row["c4d_x"] == row["cartesian_x"]


def test_fetch_single_normalize_and_write_with_index(tmp_path):
    from data.connectors.jpl_horizons_connector import (
        fetch_single_normalize_and_write,
    )

    fetcher, _ = _make_fetcher(_vectors_response(x_au=1.0))
    q = JPLBodyQuery(body="Earth", epoch="2026-01-01")
    idx = tmp_path / "idx"
    report = fetch_single_normalize_and_write(
        q, str(tmp_path / "out.jsonl"),
        fetch_fn=fetcher, build_index_dir=str(idx),
    )
    assert report.index_path == str(idx)
    assert report.index_total_objects == 1
    assert (idx / "index.json").exists()


def test_fetch_batch_normalize_and_write_partial_failure(tmp_path):
    from data.connectors.jpl_horizons_connector import (
        BatchBodyRequest, fetch_batch_normalize_and_write,
    )

    def fetcher(url, params):
        body = params["COMMAND"].strip("'")
        if body == "Ghost":
            return json.dumps({"signature": {}, "result": "No matches found.\n"})
        return json.dumps(_vectors_response(x_au=1.0, body_name=body))

    out = tmp_path / "batch.jsonl"
    idx = tmp_path / "batch_idx"
    report = fetch_batch_normalize_and_write(
        [
            BatchBodyRequest("Mars"),
            BatchBodyRequest("Ghost"),
            BatchBodyRequest("Earth"),
            BatchBodyRequest("Moon", object_type="moon"),
        ],
        epoch="2026-01-01",
        output_path=str(out),
        fetch_fn=fetcher,
        build_index_dir=str(idx),
    )
    assert report.object_count == 3
    assert report.failed == 1
    # The 3 surviving rows are written and indexed.
    assert out.exists()
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert {r["uid"] for r in rows} == {
        "jpl:Mars:2026-01-01",
        "jpl:Earth:2026-01-01",
        "jpl:Moon:2026-01-01",
    }
    # Per-object types preserved.
    by_uid = {r["uid"]: r for r in rows}
    assert by_uid["jpl:Moon:2026-01-01"]["object_type"] == "moon"
    assert by_uid["jpl:Mars:2026-01-01"]["object_type"] == "planet"
    assert (idx / "index.json").exists()
    assert report.index_total_objects == 3


def test_fetch_batch_normalize_and_write_all_failed(tmp_path):
    from data.connectors.jpl_horizons_connector import (
        BatchBodyRequest, fetch_batch_normalize_and_write,
    )

    def boom(url, params):
        return json.dumps({"signature": {}, "result": "No matches found.\n"})

    report = fetch_batch_normalize_and_write(
        [BatchBodyRequest("A"), BatchBodyRequest("B")],
        epoch="2026-01-01",
        output_path=str(tmp_path / "x.jsonl"),
        fetch_fn=boom,
    )
    assert report.object_count == 0
    assert report.failed == 2
    # No index built when the batch is empty.
    assert report.index_path is None


# ---------------------------------------------------------------------------
# Mixed Gaia + JPL UID namespace handling
# ---------------------------------------------------------------------------


def test_mixed_gaia_jpl_uids_do_not_collide():
    """A scene that loads both a Gaia subset and a JPL solar system
    must never produce duplicate uids. Their prefixes are 'gaia:'
    and 'jpl:' respectively, and the registry's namespacing
    prepends the dataset name on top."""
    from data.connectors.gaia_connector import normalize_rows as gaia_normalize
    from data.connectors.gaia_connector import GaiaQuery  # noqa: F401

    gaia_row = {
        "source_id": "1234",
        "ra": "10.0", "dec": "20.0",
        "phot_g_mean_mag": "8.0",
    }
    gaia_obj = gaia_normalize([gaia_row])[0]

    payload = _vectors_response(x_au=1.0, body_name="Earth")
    jpl_obj = parse_response(payload, JPLBodyQuery(
        body="Earth", epoch="2026-01-01",
    ))

    # uid prefixes are disjoint by design.
    assert gaia_obj.uid.startswith("gaia:")
    assert jpl_obj.uid.startswith("jpl:")
    assert gaia_obj.uid != jpl_obj.uid

    # Even with deliberately-colliding source identifiers, the
    # prefixes keep them apart.
    crash_gaia = gaia_normalize([{
        "source_id": "Earth", "ra": "0.0", "dec": "0.0",
    }])[0]
    assert crash_gaia.uid != jpl_obj.uid
    assert crash_gaia.uid == "gaia:Earth"


def test_mixed_dataset_metadata_lookup_finds_both():
    """A MetadataLookup populated with both connector outputs
    resolves both uids to the right CatalogObject."""
    from core.metadata_lookup import MetadataLookup
    from data.connectors.gaia_connector import normalize_rows as gaia_normalize

    gaia_obj = gaia_normalize([{
        "source_id": "42",
        "ra": "10.0", "dec": "20.0",
        "phot_g_mean_mag": "8.0",
    }])[0]
    jpl_obj = parse_response(
        _vectors_response(x_au=1.5, body_name="Mars"),
        JPLBodyQuery(body="Mars", epoch="2026-01-01"),
    )
    lk = MetadataLookup([gaia_obj, jpl_obj])
    assert lk.lookup("gaia:42") is gaia_obj
    assert lk.lookup("jpl:Mars:2026-01-01") is jpl_obj
    assert sorted(lk.sources()) == ["Gaia DR3", "JPL Horizons"]


# ---------------------------------------------------------------------------
# CLI main() — single + batch
# ---------------------------------------------------------------------------


def _import_cli(name):
    """Import one of the tools/ CLIs as a module without depending on
    tools/ being on sys.path."""
    import importlib.util
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(here, os.pardir, os.pardir))
    cli_path = os.path.join(repo_root, "tools", f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"tools_{name}", cli_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_single_body_cli_writes_jsonl_and_index(monkeypatch, tmp_path):
    cli = _import_cli("fetch_jpl_body")

    def fake_fetch(url, params):
        return json.dumps(_vectors_response(x_au=1.5, body_name="Mars"))

    monkeypatch.setattr(
        "data.connectors.jpl_horizons_connector._http_fetch", fake_fetch,
    )

    out = tmp_path / "mars.jsonl"
    idx = tmp_path / "mars_idx"
    rc = cli.main([
        "--body", "Mars",
        "--epoch", "2026-01-01T00:00:00",
        "--center", "500@10",
        "--output", str(out),
        "--build-index", str(idx),
        "--quiet",
    ])
    assert rc == 0
    assert out.exists()
    assert (idx / "index.json").exists()


def test_single_body_cli_invalid_args_returns_2(tmp_path):
    cli = _import_cli("fetch_jpl_body")
    rc = cli.main([
        "--body", "",  # empty body
        "--epoch", "2026-01-01",
        "--output", str(tmp_path / "x.jsonl"),
        "--quiet",
    ])
    assert rc == 2


def test_batch_cli_writes_jsonl(monkeypatch, tmp_path):
    cli = _import_cli("fetch_jpl_solar_system")

    def fake_fetch(url, params):
        body = params["COMMAND"].strip("'")
        x = {"Mercury": 0.4, "Venus": 0.7, "Earth": 1.0, "Moon": 1.0}[body]
        return json.dumps(_vectors_response(x_au=x, body_name=body))

    monkeypatch.setattr(
        "data.connectors.jpl_horizons_connector._http_fetch", fake_fetch,
    )

    out = tmp_path / "ss.jsonl"
    rc = cli.main([
        "--epoch", "2026-01-01T00:00:00",
        "--bodies", "Mercury,Venus,Earth,Moon=moon",
        "--center", "500@10",
        "--output", str(out),
        "--quiet",
    ])
    assert rc == 0
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 4
    types = {r["uid"]: r["object_type"] for r in rows}
    assert types["jpl:Moon:2026-01-01T00:00:00"] == "moon"
    assert types["jpl:Earth:2026-01-01T00:00:00"] == "planet"


def test_batch_cli_partial_failure_still_returns_0(monkeypatch, tmp_path, capsys):
    cli = _import_cli("fetch_jpl_solar_system")

    def fake_fetch(url, params):
        body = params["COMMAND"].strip("'")
        if body == "Tatooine":
            return json.dumps({"signature": {}, "result": "No matches found.\n"})
        return json.dumps(_vectors_response(x_au=1.0, body_name=body))

    monkeypatch.setattr(
        "data.connectors.jpl_horizons_connector._http_fetch", fake_fetch,
    )

    out = tmp_path / "ss.jsonl"
    rc = cli.main([
        "--epoch", "2026-01-01",
        "--bodies", "Mars,Tatooine,Earth",
        "--output", str(out),
        "--quiet",
    ])
    assert rc == 0
    err = capsys.readouterr().err
    assert "Tatooine" in err


def test_batch_cli_all_failed_returns_3(monkeypatch, tmp_path):
    cli = _import_cli("fetch_jpl_solar_system")

    def boom(url, params):
        return json.dumps({"signature": {}, "result": "No matches found.\n"})

    monkeypatch.setattr(
        "data.connectors.jpl_horizons_connector._http_fetch", boom,
    )

    rc = cli.main([
        "--epoch", "2026-01-01",
        "--bodies", "Tatooine,Krypton",
        "--output", str(tmp_path / "x.jsonl"),
        "--quiet",
    ])
    assert rc == 3


def test_batch_cli_invalid_object_type_returns_2(tmp_path):
    cli = _import_cli("fetch_jpl_solar_system")
    rc = cli.main([
        "--epoch", "2026-01-01",
        "--bodies", "Mars=warp_drive",
        "--output", str(tmp_path / "x.jsonl"),
        "--quiet",
    ])
    assert rc == 2


def test_batch_cli_empty_bodies_returns_2(tmp_path):
    cli = _import_cli("fetch_jpl_solar_system")
    rc = cli.main([
        "--epoch", "2026-01-01",
        "--bodies", "  ,, ",
        "--output", str(tmp_path / "x.jsonl"),
        "--quiet",
    ])
    assert rc == 2
