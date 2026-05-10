"""v3.7 query-export tests."""

from __future__ import annotations

import csv
import io
import json
import os

import pytest

from data import CatalogObject
from query import (
    AdvancedQuery,
    CSV_FIELDS,
    QueryKind,
    QueryReport,
    QueryResult,
    render_csv,
    render_json,
    render_markdown,
    run_query,
    write_csv_report,
    write_json_report,
    write_markdown_report,
)


def _row(uid, **kw):
    base = dict(
        uid=uid, catalog_source="Test",
        object_type="star", ra_deg=0.0, dec_deg=0.0,
    )
    base.update(kw)
    return CatalogObject(**base)


def _report():
    rows = [
        _row("a", apparent_magnitude=2.0),
        _row("b", apparent_magnitude=4.0),
        _row("c", apparent_magnitude=1.0),
    ]
    q = AdvancedQuery(kind=QueryKind.BRIGHTEST, max_results=10)
    return run_query(q, rows)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def test_csv_header_matches_fields():
    rep = _report()
    text = render_csv(rep)
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    assert header == list(CSV_FIELDS)


def test_csv_one_row_per_result():
    rep = _report()
    text = render_csv(rep)
    rows = list(csv.reader(io.StringIO(text)))
    # Header + 3 results.
    assert len(rows) == 4


def test_csv_orders_match_results():
    rep = _report()
    text = render_csv(rep)
    rows = list(csv.reader(io.StringIO(text)))[1:]
    uids = [r[0] for r in rows]
    assert uids == [r.uid for r in rep.results]


def test_csv_fields_constant():
    assert "uid" in CSV_FIELDS
    assert "distance_pc" in CSV_FIELDS
    assert "apparent_magnitude" in CSV_FIELDS


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def test_json_round_trips():
    rep = _report()
    text = render_json(rep)
    decoded = json.loads(text)
    assert decoded["query"]["kind"] == "brightest"
    assert decoded["returned"] == 3
    assert decoded["candidates_scanned"] == 3
    assert "results" in decoded


def test_json_includes_query_parameters():
    q = AdvancedQuery(
        kind=QueryKind.NEAREST,
        reference_point_pc=(1.0, 2.0, 3.0),
        sources=("Gaia DR3",),
        object_types=("star",),
        max_results=50,
    )
    rep = run_query(q, [])
    decoded = json.loads(render_json(rep))
    assert decoded["query"]["sources"] == ["Gaia DR3"]
    assert decoded["query"]["reference_point_pc"] == [1.0, 2.0, 3.0]
    assert decoded["query"]["max_results"] == 50


def test_json_schema_version_present():
    rep = _report()
    decoded = json.loads(render_json(rep))
    assert decoded["schema_version"] == 1


def test_json_has_generated_at_iso():
    rep = _report()
    decoded = json.loads(render_json(rep))
    assert decoded["generated_at_iso"]


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def test_markdown_includes_heading():
    md = render_markdown(_report())
    assert "# UNAV Pro" in md
    assert "Advanced Query Results" in md


def test_markdown_includes_query_section():
    md = render_markdown(_report())
    assert "## Query" in md
    assert "`brightest`" in md


def test_markdown_includes_counts_section():
    md = render_markdown(_report())
    assert "## Counts" in md
    assert "Candidates scanned" in md


def test_markdown_includes_results_table():
    md = render_markdown(_report())
    assert "## Results" in md
    assert "| # | uid" in md
    assert "`a`" in md
    assert "`b`" in md
    assert "`c`" in md


def test_markdown_no_results_section_handles_empty():
    q = AdvancedQuery(kind=QueryKind.NEAREST, max_results=5)
    rep = run_query(q, [])
    md = render_markdown(rep)
    assert "(no results)" in md


def test_markdown_warnings_section_when_present():
    q = AdvancedQuery(
        kind=QueryKind.NEAREST,
        max_results=5,
        epoch_jd=2461041.5,
        interpolate_ephemeris=False,
    )
    rep = run_query(q, [_row("a")])
    md = render_markdown(rep)
    assert "## Warnings" in md
    assert "static" in md.lower()


# ---------------------------------------------------------------------------
# Atomic file writes
# ---------------------------------------------------------------------------


def test_write_json_report_writes_file(tmp_path):
    rep = _report()
    path = str(tmp_path / "out.json")
    out = write_json_report(rep, path)
    assert os.path.isfile(out)
    with open(out, encoding="utf-8") as fh:
        decoded = json.load(fh)
    assert decoded["returned"] == 3


def test_write_csv_report_writes_file(tmp_path):
    rep = _report()
    path = str(tmp_path / "out.csv")
    out = write_csv_report(rep, path)
    assert os.path.isfile(out)
    with open(out, encoding="utf-8") as fh:
        text = fh.read()
    assert "uid" in text


def test_write_markdown_report_writes_file(tmp_path):
    rep = _report()
    path = str(tmp_path / "out.md")
    out = write_markdown_report(rep, path)
    assert os.path.isfile(out)


def test_atomic_write_no_tmp_left(tmp_path):
    rep = _report()
    path = str(tmp_path / "out.json")
    write_json_report(rep, path)
    leftovers = [
        f for f in os.listdir(tmp_path) if f.endswith(".tmp")
    ]
    assert leftovers == []


def test_write_creates_parent_dir(tmp_path):
    rep = _report()
    path = str(tmp_path / "subdir" / "out.json")
    out = write_json_report(rep, path)
    assert os.path.isfile(out)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_csv_render_deterministic():
    rep = _report()
    a = render_csv(rep)
    b = render_csv(rep)
    assert a == b


def test_markdown_render_deterministic_modulo_timestamp():
    """Markdown carries a UTC timestamp; everything
    else should be byte-stable."""
    rep = _report()
    a = render_markdown(rep)
    b = render_markdown(rep)
    # Strip the *Generated:* line before comparing.
    def _strip_stamp(text):
        return "\n".join(
            line for line in text.splitlines()
            if not line.startswith("*Generated:")
        )
    assert _strip_stamp(a) == _strip_stamp(b)
