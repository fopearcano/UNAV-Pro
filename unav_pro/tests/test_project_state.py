"""Tests for core.project_state. Pure CPython, no Cinema 4D."""

from __future__ import annotations

import json
import os
from dataclasses import asdict

import pytest

from core.config import UnavConfig
from core.dataset_registry import DatasetEntry, DatasetRegistry
from core.navigation_state import NavigationParams
from core.project_state import (
    PROJECT_SCHEMA_VERSION,
    ApplyReport,
    ProjectState,
    apply_project_state,
    gather_project_state,
    load_project_state,
    project_state_dir,
    save_project_state,
    sidecar_path_for,
)
from core.route import Route, Waypoint
from core.visual_encoding import VisualEncodingParams


# ---------------------------------------------------------------------------
# ProjectState dataclass
# ---------------------------------------------------------------------------


def test_default_project_state_is_empty():
    s = ProjectState()
    assert s.schema_version == PROJECT_SCHEMA_VERSION
    assert s.enabled_datasets == []
    assert s.navigator == {}
    assert s.route == {}
    assert s.visual_encoding == {}
    assert s.config is None
    assert s.notes == ""


def test_project_state_round_trip_dict():
    s = ProjectState(
        saved_at_iso="2026-01-01T00:00:00",
        enabled_datasets=["A", "B"],
        navigator={"c4d_scale": "kpc", "max_visible_objects": 1234},
        route={"name": "Tour", "waypoints": []},
        visual_encoding={"color_mode": "redshift", "size_scale": 2.0},
        config={"default_scale_mode": "pc"},
        notes="hello",
    )
    out = ProjectState.from_dict(s.to_dict())
    assert out == s


def test_project_state_round_trip_json():
    s = ProjectState(
        navigator={"c4d_scale": "ly"},
        route={"name": "x"},
    )
    out = ProjectState.from_json(s.to_json())
    assert out == s


def test_from_json_handles_garbage():
    out = ProjectState.from_json("{not json")
    assert out == ProjectState()


def test_from_dict_filters_unknown_keys():
    out = ProjectState.from_dict({"warp_drive": True, "navigator": {"c4d_scale": "pc"}})
    assert not hasattr(out, "warp_drive")
    assert out.navigator == {"c4d_scale": "pc"}


def test_from_dict_drops_falsy_dataset_names():
    out = ProjectState.from_dict({"enabled_datasets": ["A", "", None, "B"]})
    assert out.enabled_datasets == ["A", "B"]


# ---------------------------------------------------------------------------
# gather_project_state
# ---------------------------------------------------------------------------


def test_gather_collects_every_piece():
    nav = NavigationParams(c4d_scale="kpc", cone_angle_deg=45.0)
    route = Route(name="T")
    route.add(Waypoint(kind="named", label="Earth"))
    enc = VisualEncodingParams(color_mode="redshift", size_scale=2.0)
    cfg = UnavConfig(default_scale_mode="kpc")

    reg = DatasetRegistry()
    reg.entries.append(DatasetEntry(name="ds_on", path="/a", enabled=True))
    reg.entries.append(DatasetEntry(name="ds_off", path="/b", enabled=False))

    state = gather_project_state(
        registry=reg, navigator=nav, route=route, encoding=enc, config=cfg,
    )
    assert state.enabled_datasets == ["ds_on"]
    assert state.navigator["c4d_scale"] == "kpc"
    assert state.route["name"] == "T"
    assert state.visual_encoding["color_mode"] == "redshift"
    assert state.config["default_scale_mode"] == "kpc"
    assert state.saved_at_iso  # populated


def test_gather_with_missing_pieces_yields_empty_subdicts():
    state = gather_project_state()
    assert state.enabled_datasets == []
    assert state.navigator == {}
    assert state.route == {}
    assert state.visual_encoding == {}
    assert state.config is None


# ---------------------------------------------------------------------------
# apply_project_state — restoration
# ---------------------------------------------------------------------------


def test_apply_restores_navigator_route_encoding():
    state = ProjectState(
        navigator=NavigationParams(c4d_scale="kpc", cone_angle_deg=45.0).to_dict(),
        route=Route(name="X").to_dict(),
        visual_encoding=asdict(VisualEncodingParams(color_mode="redshift", size_scale=2.0)),
    )
    out = apply_project_state(state)
    assert out["navigator"].c4d_scale == "kpc"
    assert out["navigator"].cone_angle_deg == 45.0
    assert out["route"].name == "X"
    assert out["encoding"].color_mode == "redshift"
    assert out["encoding"].size_scale == 2.0
    rep: ApplyReport = out["report"]
    assert rep.navigator_restored
    assert rep.route_restored
    assert rep.encoding_restored


def test_apply_returns_defaults_when_state_empty():
    out = apply_project_state(ProjectState())
    assert out["navigator"] == NavigationParams()
    assert out["route"].name == "UNAV Route"
    assert out["encoding"] == VisualEncodingParams()
    rep: ApplyReport = out["report"]
    assert not rep.navigator_restored
    assert not rep.route_restored
    assert not rep.encoding_restored


def test_apply_aligns_registry_enabled_flags():
    reg = DatasetRegistry()
    reg.entries.append(DatasetEntry(name="A", path="/a", enabled=False))
    reg.entries.append(DatasetEntry(name="B", path="/b", enabled=True))
    reg.entries.append(DatasetEntry(name="C", path="/c", enabled=True))

    state = ProjectState(enabled_datasets=["A", "C"])
    out = apply_project_state(state, registry=reg)

    assert reg.find("A").enabled is True
    assert reg.find("B").enabled is False
    assert reg.find("C").enabled is True
    rep: ApplyReport = out["report"]
    assert "A" in rep.datasets_enabled
    assert "B" in rep.datasets_disabled


def test_apply_records_missing_dataset_names():
    reg = DatasetRegistry()
    reg.entries.append(DatasetEntry(name="A", path="/a"))
    state = ProjectState(enabled_datasets=["A", "ghost", "phantom"])
    out = apply_project_state(state, registry=reg)
    assert sorted(out["report"].datasets_missing) == ["ghost", "phantom"]


def test_apply_accepts_invalid_navigator_values_clamped():
    # Negative far_clip would normally fail validation; clamped()
    # repairs it on the way in.
    bad_nav = {
        "max_distance_parsec": -1.0,
        "far_clip_parsec": -10.0,
        "near_clip_parsec": 0.1,
        "field_of_view_deg": 200.0,
        "c4d_scale": "warp",
    }
    state = ProjectState(navigator=bad_nav)
    out = apply_project_state(state)
    nav = out["navigator"]
    assert nav.max_distance_parsec > 0
    assert nav.far_clip_parsec > nav.near_clip_parsec
    assert 0 < nav.field_of_view_deg < 180
    assert nav.c4d_scale == "pc"


def test_apply_invalid_visual_encoding_falls_back_to_defaults():
    state = ProjectState(visual_encoding={"color_mode": "warp_drive"})
    out = apply_project_state(state)
    assert out["encoding"] == VisualEncodingParams()
    assert not out["report"].encoding_restored


def test_apply_returns_config_when_present():
    state = ProjectState(config={"default_scale_mode": "kpc"})
    out = apply_project_state(state)
    assert out["config"].default_scale_mode == "kpc"


def test_apply_returns_no_config_when_absent():
    state = ProjectState()
    out = apply_project_state(state)
    assert out["config"] is None


# ---------------------------------------------------------------------------
# Round trip — gather + apply
# ---------------------------------------------------------------------------


def test_gather_then_apply_round_trips_live_state():
    nav = NavigationParams(c4d_scale="ly", cone_angle_deg=20.0)
    route = Route(name="Pleiades Tour")
    route.add(Waypoint(kind="object", uid="x:1", label="Alpha",
                       x_c4d=10.0, y_c4d=0.0, z_c4d=0.0))
    enc = VisualEncodingParams(color_mode="catalog_source", size_scale=1.5)

    state = gather_project_state(navigator=nav, route=route, encoding=enc)
    out = apply_project_state(state)

    assert out["navigator"].c4d_scale == "ly"
    assert out["route"].name == "Pleiades Tour"
    assert out["route"].waypoints[0].uid == "x:1"
    assert out["encoding"].color_mode == "catalog_source"
    assert out["encoding"].size_scale == 1.5


# ---------------------------------------------------------------------------
# save / load on disk
# ---------------------------------------------------------------------------


def test_save_load_round_trip(tmp_path):
    state = ProjectState(
        enabled_datasets=["A"],
        navigator=NavigationParams(c4d_scale="kpc").to_dict(),
        route=Route(name="X").to_dict(),
        visual_encoding=asdict(VisualEncodingParams(color_mode="redshift")),
        config=UnavConfig().to_dict(),
        notes="hello",
    )
    p = str(tmp_path / "state.json")
    saved = save_project_state(state, p)
    assert saved == p
    out = load_project_state(p)
    assert out == state


def test_save_creates_parent_dirs(tmp_path):
    nested = str(tmp_path / "a" / "b" / "state.json")
    save_project_state(ProjectState(), nested)
    assert os.path.isfile(nested)


def test_load_missing_returns_default(tmp_path):
    out = load_project_state(str(tmp_path / "nope.json"))
    assert out == ProjectState()


def test_load_corrupt_returns_default(tmp_path):
    p = str(tmp_path / "bad.json")
    with open(p, "w") as fh:
        fh.write("{not valid json")
    out = load_project_state(p)
    assert out == ProjectState()


def test_save_handles_unwritable_quietly(monkeypatch, tmp_path):
    import core.project_state as ps

    def fail_makedirs(*_a, **_kw):
        raise OSError("read-only fs")

    monkeypatch.setattr(ps.os, "makedirs", fail_makedirs)
    out = save_project_state(ProjectState(), str(tmp_path / "x" / "y.json"))
    assert out is None


# ---------------------------------------------------------------------------
# Sidecar paths
# ---------------------------------------------------------------------------


def test_project_state_dir_is_per_user():
    d = project_state_dir()
    assert d.endswith(".unav_pro/projects")


def test_sidecar_path_uses_scene_stem():
    p = sidecar_path_for("/projects/scene_alpha.c4d")
    assert p.endswith("scene_alpha.json")


def test_sidecar_path_handles_no_extension():
    p = sidecar_path_for("/projects/scene_alpha")
    assert p.endswith("scene_alpha.json")


def test_sidecar_path_for_untitled_scene():
    p = sidecar_path_for(None)
    assert p.endswith("_untitled.json")
    p = sidecar_path_for("")
    assert p.endswith("_untitled.json")


# ---------------------------------------------------------------------------
# ApplyReport.short_summary
# ---------------------------------------------------------------------------


def test_apply_report_summary_lists_restored_pieces():
    rep = ApplyReport(
        navigator_restored=True,
        route_restored=True,
        encoding_restored=False,
        datasets_enabled=["A"],
        datasets_missing=["ghost"],
    )
    text = rep.short_summary()
    assert "navigator" in text
    assert "route" in text
    assert "encoding" in text
    assert "1 dataset(s) enabled" in text
    assert "1 dataset(s) missing" in text
