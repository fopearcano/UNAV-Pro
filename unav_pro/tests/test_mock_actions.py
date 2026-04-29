"""Tests for action handlers. Runs without Cinema 4D — handlers that
require c4d should report the limitation cleanly rather than raise."""

from __future__ import annotations

from core import mock_actions


def test_load_dataset_default_loads_bundled_sample():
    out = mock_actions.load_dataset()
    assert "Load Dataset" in out
    # The bundled sample contains 100 objects.
    assert "100" in out


def test_load_dataset_missing_path_reports_cleanly():
    out = mock_actions.load_dataset("/path/that/does/not/exist.jsonl")
    assert "Load Dataset" in out
    assert "not found" in out


def test_create_navigation_null():
    out = mock_actions.create_navigation_null()
    assert "Create Navigation Null" in out


def test_generate_point_cloud_without_c4d_reports_cleanly():
    # Outside Cinema 4D the handler must not raise; it should say so.
    out = mock_actions.generate_point_cloud()
    assert "Generate Point Cloud" in out
    assert "Cinema 4D not available" in out


def test_clear_scene_without_c4d_reports_cleanly():
    out = mock_actions.clear_scene()
    assert "Clear Scene" in out
    assert "Cinema 4D not available" in out
