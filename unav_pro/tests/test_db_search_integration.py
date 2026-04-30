"""Integration tests across the v1.1 DB layer.

Exercises:

* ``core.search.search_db`` end-to-end against a freshly-imported
  DB,
* ``core.dataset_registry`` recognising a DB-backed entry,
* ``core.sector_streaming.stream_sector_for_dataset`` routing
  through the SQL spatial query when a DB is attached,
* ``ui.search_panel.run_db_search`` rendering the panel text.
"""

from __future__ import annotations

import json
import os

import pytest

from core.dataset_registry import (
    DatasetEntry, DatasetRegistry, scan_db_stats,
)
from core.navigation_state import NavigationParams
from core.search import DBSearchOutcome, search_db
from core.sector_streaming import stream_sector_for_dataset
from data.catalog_io import write_catalog
from data.schema import CatalogObject, compute_derived_fields
from db.db_manager import DBManager, iter_jsonl
from db.query_builder import DBSearchQuery
from ui.search_panel import run_db_search, render_db_indicator


def _seed_jsonl(tmp_path, count: int = 10) -> str:
    path = str(tmp_path / "src.jsonl")
    objects = []
    for i in range(count):
        o = CatalogObject(
            uid=f"gaia:{i}", catalog_source="Gaia DR3",
            object_type="star",
            ra_deg=float(i * 5 % 360),
            dec_deg=float((i * 3) % 89),
            distance_parsec=10.0 + float(i),
            apparent_magnitude=5.0 + i * 0.1,
            redshift=0.0,
            name=f"star{i}",
            metadata_json=json.dumps({"foo": "bar", "i": i}),
        )
        compute_derived_fields(o)
        objects.append(o)
    write_catalog(objects, path)
    return path


def _seed_db(tmp_path, count: int = 10) -> str:
    src = _seed_jsonl(tmp_path, count=count)
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        db.import_iter(iter_jsonl(src))
    return db_path


# ---------------------------------------------------------------------------
# search_db round-trip
# ---------------------------------------------------------------------------


def test_search_db_returns_results_in_uniform_shape(tmp_path):
    db_path = _seed_db(tmp_path, count=20)
    out: DBSearchOutcome = search_db(
        db_path,
        DBSearchQuery(text="star1", limit=5),
    )
    assert isinstance(out, DBSearchOutcome)
    # All hits start with "star1": star1, star10..star19 → 11 total,
    # capped at 5.
    assert len(out.results) == 5
    assert out.capped is True
    # Display labels match.
    labels = [r.display_label() for r in out.results]
    assert all(l.startswith("star1") for l in labels)


def test_search_db_with_filter_reduces_set(tmp_path):
    db_path = _seed_db(tmp_path, count=20)
    out: DBSearchOutcome = search_db(
        db_path,
        DBSearchQuery(magnitude_max=5.5, limit=100),
    )
    # mag = 5.0, 5.1, 5.2, 5.3, 5.4, 5.5 → 6 rows (<= 5.5 inclusive).
    assert len(out.results) == 6


def test_search_db_pagination_advances_offset(tmp_path):
    db_path = _seed_db(tmp_path, count=10)
    page1 = search_db(db_path, DBSearchQuery(limit=4, offset=0))
    page2 = search_db(db_path, DBSearchQuery(limit=4, offset=4))
    assert len(page1.results) == 4
    assert len(page2.results) == 4
    uids1 = {r.uid for r in page1.results}
    uids2 = {r.uid for r in page2.results}
    assert uids1.isdisjoint(uids2)


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def test_dataset_entry_recognises_db_backed_path(tmp_path):
    db_path = _seed_db(tmp_path, count=5)
    e = DatasetEntry(name="Test", path=db_path, db_path=db_path)
    assert e.is_db_backed is True
    assert e.is_indexed is False
    assert e.file_exists is True


def test_dataset_registry_add_db_creates_entry(tmp_path):
    db_path = _seed_db(tmp_path, count=5)
    reg = DatasetRegistry()
    e = reg.add_db(db_path, name="t")
    assert e.is_db_backed
    assert e.stats is not None
    assert e.stats.object_count == 5


def test_scan_db_stats_returns_bounding_radius(tmp_path):
    db_path = _seed_db(tmp_path, count=5)
    st = scan_db_stats(db_path)
    assert st.object_count == 5
    assert st.bounding_radius_pc > 0


# ---------------------------------------------------------------------------
# Sector streaming via DB
# ---------------------------------------------------------------------------


def test_stream_sector_uses_db_path_when_present(tmp_path):
    db_path = _seed_db(tmp_path, count=20)
    entry = DatasetEntry(
        name="Test", path=db_path, db_path=db_path,
    )
    params = NavigationParams(
        far_clip_parsec=200.0,
        cone_angle_deg=89.0,
        selected_catalog_sources=[],
    )
    result = stream_sector_for_dataset(
        entry, params,
        origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    assert result.error is None
    assert result.used_db is True
    assert result.used_index is False
    assert len(result.objects) > 0
    assert result.bbox_elapsed_ms is not None
    assert result.refine_elapsed_ms is not None


def test_stream_sector_db_namespace_is_applied(tmp_path):
    db_path = _seed_db(tmp_path, count=5)
    entry = DatasetEntry(
        name="MyDB", path=db_path, db_path=db_path,
        namespace=True,
    )
    params = NavigationParams(
        far_clip_parsec=200.0,
        cone_angle_deg=89.0,
        selected_catalog_sources=[],
    )
    result = stream_sector_for_dataset(
        entry, params,
        origin_c4d=(0.0, 0.0, 0.0),
        forward=(1.0, 0.0, 0.0),
    )
    assert all(o.uid.startswith("MyDB:") for o in result.objects)


def test_stream_sector_db_propagates_query_error(tmp_path):
    """A non-existent DB path must not raise; the stream result
    records ``error`` and the rest of the pipeline stays alive."""
    entry = DatasetEntry(
        name="missing", path=str(tmp_path / "x.db"),
        db_path=str(tmp_path / "x.db"),
    )
    params = NavigationParams(
        far_clip_parsec=200.0, selected_catalog_sources=[],
    )
    result = stream_sector_for_dataset(
        entry, params,
        origin_c4d=(0, 0, 0), forward=(1, 0, 0),
    )
    assert result.error is not None


# ---------------------------------------------------------------------------
# UI panel
# ---------------------------------------------------------------------------


def test_run_db_search_renders_panel_text_with_timing(tmp_path):
    db_path = _seed_db(tmp_path, count=10)
    outcome = run_db_search(db_path, text="star", limit=3)
    assert "match(es)" in outcome.panel_text or "No matches" in outcome.panel_text
    assert "[SQL]" in outcome.panel_text
    assert "ms" in outcome.status_line


def test_render_db_indicator_summarises_split():
    assert render_db_indicator(db_backed_count=0, total_enabled=3) == "3 JSONL dataset(s)"
    assert render_db_indicator(db_backed_count=3, total_enabled=3) == "3 DB-backed dataset(s)"
    out = render_db_indicator(db_backed_count=2, total_enabled=5)
    assert "2 of 5" in out


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


def test_import_cli_writes_db(tmp_path):
    from tools import import_catalog_to_db
    src = _seed_jsonl(tmp_path, count=15)
    db_path = str(tmp_path / "out.db")
    rc = import_catalog_to_db.main([
        "--input", src,
        "--db", db_path,
        "--quiet",
    ])
    assert rc == 0
    with DBManager(db_path) as db:
        assert db.stats().row_count == 15


def test_import_cli_handles_multiple_inputs(tmp_path):
    from tools import import_catalog_to_db
    src1 = _seed_jsonl(tmp_path, count=5)
    src2_dir = tmp_path / "second"
    src2_dir.mkdir()
    # Reuse seeder against a different subdirectory by relabelling uids.
    objects = []
    for i in range(7):
        o = CatalogObject(
            uid=f"sdss:{i}", catalog_source="SDSS", object_type="galaxy",
            ra_deg=10.0, dec_deg=20.0, distance_parsec=100.0,
        )
        compute_derived_fields(o)
        objects.append(o)
    src2 = str(src2_dir / "src.jsonl")
    write_catalog(objects, src2)
    db_path = str(tmp_path / "out.db")
    rc = import_catalog_to_db.main([
        "--input", src1, "--input", src2,
        "--db", db_path, "--quiet",
    ])
    assert rc == 0
    with DBManager(db_path) as db:
        st = db.stats()
        assert st.row_count == 12
        assert set(st.sources) == {"Gaia DR3", "SDSS"}
