"""Tests for unav_pro.db.db_manager (v1.1)."""

from __future__ import annotations

import json
import os

import pytest

from data.schema import CatalogObject, compute_derived_fields
from data.catalog_io import write_catalog
from db.db_manager import (
    DBError,
    DBManager,
    DBStats,
    SCHEMA_VERSION,
    is_unav_db,
    iter_jsonl,
    open_db,
)


def _obj(uid: str, **kw) -> CatalogObject:
    base = dict(
        uid=uid, catalog_source="Gaia DR3", object_type="star",
        ra_deg=10.0, dec_deg=20.0, distance_parsec=10.0,
    )
    base.update(kw)
    o = CatalogObject(**base)
    compute_derived_fields(o)
    return o


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------


def test_apply_schema_creates_tables_and_indexes(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        cur = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "ORDER BY name"
        )
        tables = {r[0] for r in cur.fetchall()}
        assert "objects" in tables
        assert "metadata" in tables
        assert "unav_meta" in tables


def test_apply_schema_is_idempotent(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        db.apply_schema()  # second call must not raise


def test_apply_schema_records_schema_version(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        cur = db.execute(
            "SELECT value FROM unav_meta WHERE key='schema_version'"
        )
        assert int(cur.fetchone()[0]) == SCHEMA_VERSION


def test_apply_schema_rejects_mismatched_version(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        cur = db.execute("UPDATE unav_meta SET value='99' WHERE key='schema_version'")
        db.conn.commit()
    # Re-open: the validate must reject.
    with DBManager(db_path) as db:
        with pytest.raises(DBError, match="schema version mismatch"):
            db.apply_schema()


# ---------------------------------------------------------------------------
# Insert
# ---------------------------------------------------------------------------


def test_insert_objects_writes_rows(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        objects = [_obj(f"gaia:{i}") for i in range(5)]
        n, _ = db.insert_objects(objects)
        assert n == 5
        st = db.stats()
        assert st.row_count == 5
        assert st.sources == ["Gaia DR3"]


def test_insert_dedupes_on_uid_when_or_ignore(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        n1, _ = db.insert_objects([_obj("gaia:1"), _obj("gaia:1")])
        # Both rows attempted; one inserted, one ignored.
        assert n1 in (1, 2)  # rowcount semantics differ; final row count is what matters.
        st = db.stats()
        assert st.row_count == 1


def test_insert_or_replace_overwrites_existing(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        db.insert_objects([_obj("gaia:1", name="old")])
        db.insert_objects(
            [_obj("gaia:1", name="new")], replace=True,
        )
        obj = db.fetch_object("gaia:1")
        assert obj is not None
        assert obj.name == "new"


def test_insert_writes_metadata_row_when_present(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        obj = _obj("gaia:1", metadata_json=json.dumps({"k": "v"}))
        db.insert_objects([obj])
        meta = db.fetch_metadata("gaia:1")
        assert meta == {"k": "v"}


def test_insert_skips_metadata_when_empty(tmp_path):
    """Default ``metadata_json='{}'`` means "no metadata"; the
    parallel table stays empty."""
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        db.insert_objects([_obj("gaia:1")])
        st = db.stats()
        assert st.metadata_row_count == 0


def test_skip_metadata_flag_disables_metadata_writes(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        obj = _obj("gaia:1", metadata_json='{"k":"v"}')
        db.insert_objects([obj], metadata=False)
        st = db.stats()
        assert st.metadata_row_count == 0


# ---------------------------------------------------------------------------
# Stream import
# ---------------------------------------------------------------------------


def test_iter_jsonl_streams_rows(tmp_path):
    src = str(tmp_path / "src.jsonl")
    objs = [_obj(f"gaia:{i}") for i in range(10)]
    write_catalog(objs, src)
    streamed = list(iter_jsonl(src))
    assert len(streamed) == 10
    assert all(o.uid.startswith("gaia:") for o in streamed)


def test_import_iter_handles_large_input(tmp_path):
    src = str(tmp_path / "src.jsonl")
    objs = [_obj(f"gaia:{i}") for i in range(2_000)]
    write_catalog(objs, src)
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        n, _ = db.import_iter(iter_jsonl(src), batch_size=500)
        assert n == 2_000
        assert db.stats().row_count == 2_000


def test_import_iter_dedupes_within_a_batch(tmp_path):
    """Two identical uids in the same batch must only land once."""
    src = str(tmp_path / "src.jsonl")
    objs = [_obj("gaia:dupe"), _obj("gaia:dupe")]
    write_catalog(objs, src)
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        db.import_iter(iter_jsonl(src))
        assert db.stats().row_count == 1


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def test_fetch_object_round_trips_columns(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        original = _obj(
            "gaia:42", name="Sirius", apparent_magnitude=-1.46,
            redshift=None, distance_parsec=2.64,
        )
        db.insert_objects([original])
        out = db.fetch_object("gaia:42")
        assert out is not None
        assert out.uid == "gaia:42"
        assert out.name == "Sirius"
        assert out.apparent_magnitude == pytest.approx(-1.46)
        assert out.distance_parsec == pytest.approx(2.64)


def test_fetch_object_returns_none_for_unknown_uid(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        assert db.fetch_object("nope") is None


def test_fetch_objects_handles_chunked_lookups(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        db.insert_objects([_obj(f"g:{i}") for i in range(700)])
        uids = [f"g:{i}" for i in range(700)]
        out = db.fetch_objects(uids)
        assert len(out) == 700


def test_fetch_object_with_metadata_attaches_blob(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        db.insert_objects([
            _obj("gaia:1", metadata_json='{"k":"v"}')
        ])
        obj = db.fetch_object_with_metadata("gaia:1")
        assert obj is not None
        assert json.loads(obj.metadata_json)["k"] == "v"


# ---------------------------------------------------------------------------
# Stats / sniffing
# ---------------------------------------------------------------------------


def test_stats_returns_distinct_sources_and_types(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        db.insert_objects([
            _obj("a", catalog_source="Gaia DR3", object_type="star"),
            _obj("b", catalog_source="SDSS", object_type="galaxy"),
            _obj("c", catalog_source="DESI", object_type="quasar"),
        ])
        st = db.stats()
        assert set(st.sources) == {"Gaia DR3", "SDSS", "DESI"}
        assert set(st.object_types) == {"star", "galaxy", "quasar"}


def test_stats_lists_indexed_columns(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        st = db.stats()
        assert "idx_objects_radec" in st.indexed_columns
        assert "idx_objects_x" in st.indexed_columns
        assert "idx_objects_source" in st.indexed_columns


def test_is_unav_db_is_true_for_freshly_written_db(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
    assert is_unav_db(db_path) is True


def test_is_unav_db_is_false_for_empty_path():
    assert is_unav_db("/nonexistent/path") is False


def test_open_db_context_manager_releases_handle(tmp_path):
    db_path = str(tmp_path / "u.db")
    with open_db(db_path) as db:
        db.apply_schema()
    # The context should have committed + closed; reopening
    # should observe the schema.
    assert is_unav_db(db_path) is True


def test_delete_uid_removes_object_and_metadata(tmp_path):
    db_path = str(tmp_path / "u.db")
    with DBManager(db_path) as db:
        db.apply_schema()
        db.insert_objects([_obj("gaia:1", metadata_json='{"k":"v"}')])
        ok = db.delete_uid("gaia:1")
        assert ok is True
        assert db.fetch_object("gaia:1") is None
        # FK cascade must have wiped the metadata row.
        assert db.fetch_metadata("gaia:1") is None
