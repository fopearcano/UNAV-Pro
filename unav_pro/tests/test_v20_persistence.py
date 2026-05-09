"""v2.0 overlay-settings persistence tests."""

from __future__ import annotations

import pytest

from core.project_state import ProjectState
from procedural import OverlaySettings


# ---------------------------------------------------------------------------
# ProjectState carries the overlays dict
# ---------------------------------------------------------------------------


def test_project_state_default_overlays_empty():
    ps = ProjectState()
    assert ps.overlays == {}


def test_project_state_round_trip_with_overlays():
    settings = OverlaySettings(
        show_grid=True,
        show_galactic_plane=True,
        radius_pc=42.0,
    )
    ps = ProjectState(overlays=settings.to_dict())
    rt = ProjectState.from_dict(ps.to_dict())
    assert "show_grid" in rt.overlays
    assert rt.overlays["show_grid"] is True
    assert rt.overlays["radius_pc"] == 42.0


def test_overlay_settings_round_trip_through_project_state():
    settings = OverlaySettings(
        show_grid=True, show_distance_rings=True,
        radius_pc=200.0, segment_count=128,
        distance_ring_radii_pc=[5.0, 10.0, 100.0],
    )
    ps = ProjectState(overlays=settings.to_dict())
    rt = ProjectState.from_dict(ps.to_dict())
    rebuilt = OverlaySettings.from_dict(rt.overlays)
    assert rebuilt.show_grid is True
    assert rebuilt.show_distance_rings is True
    assert rebuilt.radius_pc == 200.0
    assert rebuilt.segment_count == 128
    assert rebuilt.distance_ring_radii_pc == [5.0, 10.0, 100.0]


def test_project_state_handles_missing_overlays_key():
    """Loading a v1.x project state that doesn't carry the
    new ``overlays`` key must not raise."""
    legacy = {
        "schema_version": 1,
        "saved_at_iso": None,
        "navigator": {},
        "route": {},
        "visual_encoding": {},
        "config": None,
    }
    ps = ProjectState.from_dict(legacy)
    assert ps.overlays == {}


def test_overlay_settings_corrupt_dict_falls_through():
    """Bad payload at the OverlaySettings layer doesn't crash
    the project_state load path."""
    bad = {"radius_pc": -10.0}  # invalid — would raise in __post_init__
    settings = OverlaySettings.from_dict(bad)
    # Defaults instead of raising.
    assert settings.radius_pc > 0
