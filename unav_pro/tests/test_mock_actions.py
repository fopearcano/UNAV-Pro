"""Tests for mock action handlers. Runs without Cinema 4D."""

from __future__ import annotations

from core import mock_actions


def test_load_dataset_no_path():
    out = mock_actions.load_dataset()
    assert "Load Dataset" in out
    assert "mock" in out.lower()


def test_load_dataset_missing_path():
    out = mock_actions.load_dataset("/path/that/does/not/exist.parquet")
    assert "Load Dataset" in out
    assert "not found" in out


def test_create_navigation_null():
    out = mock_actions.create_navigation_null()
    assert "Create Navigation Null" in out


def test_generate_point_cloud_default():
    out = mock_actions.generate_point_cloud()
    assert "Generate Point Cloud" in out
    assert "10000" in out


def test_generate_point_cloud_invalid():
    out = mock_actions.generate_point_cloud(0)
    # Invalid input should be reported, not raised.
    assert "FAILED" in out


def test_clear_scene():
    out = mock_actions.clear_scene()
    assert "Clear Scene" in out
