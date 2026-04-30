"""Smoke tests for the v1.0 benchmark CLI."""

from __future__ import annotations

import os

import pytest

from data.binary_export import FORMAT_VERSION_V2, read_visible_sector
from tools import benchmark_visible_sector_export as bench


def test_benchmark_writes_a_v2_file(tmp_path, capsys):
    out = tmp_path / "bench.unav"
    rc = bench.main([
        "--points", "100",
        "--output", str(out),
        "--version", "v2",
        "--no-roundtrip",
        "--seed", "42",
    ])
    assert rc == 0
    parsed = read_visible_sector(str(out))
    assert parsed.header.point_count == 100
    assert parsed.header.version == FORMAT_VERSION_V2


def test_benchmark_v1_round_trip(tmp_path):
    out = tmp_path / "bench_v1.unav"
    rc = bench.main([
        "--points", "50",
        "--output", str(out),
        "--version", "v1",
        "--seed", "0",
    ])
    assert rc == 0
    parsed = read_visible_sector(str(out))
    assert parsed.header.version == 1


def test_benchmark_camera_relative_marks_relative_flag(tmp_path):
    from data.binary_export import (
        RENDERER_FLAG_POINTS_RELATIVE_TO_SECTOR_ORIGIN,
    )
    out = tmp_path / "bench_rel.unav"
    rc = bench.main([
        "--points", "200",
        "--output", str(out),
        "--version", "v2",
        "--camera-relative",
    ])
    assert rc == 0
    parsed = read_visible_sector(str(out))
    assert parsed.header.v2_extras.renderer_flags & (
        RENDERER_FLAG_POINTS_RELATIVE_TO_SECTOR_ORIGIN
    )


def test_benchmark_rejects_zero_points(tmp_path, capsys):
    rc = bench.main([
        "--points", "0",
        "--output", str(tmp_path / "x.unav"),
    ])
    assert rc == 2


def test_benchmark_uses_tmp_when_no_output_specified(capsys):
    """Sanity: with no --output, the benchmark runs and cleans up
    its temp file. We can't observe the temp path; we just check
    the run is happy."""
    rc = bench.main([
        "--points", "100",
        "--no-roundtrip",
    ])
    assert rc == 0
