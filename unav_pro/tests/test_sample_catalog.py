"""Tests for the synthetic sample-catalog generator."""

from __future__ import annotations

import os

from data import (
    generate_objects,
    load_catalog,
    validate_catalog,
    write_sample_catalog,
)


def test_generate_objects_count_default():
    objs = generate_objects()
    assert len(objs) == 100


def test_generate_objects_is_deterministic():
    a = generate_objects(seed=123)
    b = generate_objects(seed=123)
    assert [o.uid for o in a] == [o.uid for o in b]
    assert [o.ra_deg for o in a] == [o.ra_deg for o in b]


def test_generate_objects_mix_has_all_types():
    objs = generate_objects()
    types = {o.object_type for o in objs}
    assert {"star", "galaxy", "quasar", "nebula"}.issubset(types)


def test_generate_objects_all_valid():
    objs = generate_objects()
    summary = validate_catalog(objs)
    assert summary["invalid"] == 0, summary["issues"]


def test_write_sample_catalog_jsonl(tmp_path):
    out = tmp_path / "sample.jsonl"
    path = write_sample_catalog(str(out))
    assert os.path.exists(path)
    loaded = load_catalog(path)
    assert len(loaded) == 100
    assert all(o.cartesian_x is not None for o in loaded)


def test_write_sample_catalog_csv(tmp_path):
    out = tmp_path / "sample.csv"
    path = write_sample_catalog(str(out), fmt="csv")
    assert os.path.exists(path)
    loaded = load_catalog(path)
    assert len(loaded) == 100


def test_write_sample_catalog_custom_size(tmp_path):
    out = tmp_path / "small.jsonl"
    path = write_sample_catalog(str(out), n=20)
    loaded = load_catalog(path)
    assert len(loaded) == 20
