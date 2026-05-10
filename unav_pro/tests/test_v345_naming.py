"""v3.45 naming-policy tests."""

from __future__ import annotations

import pytest

from c4d_objects.naming import (
    MARKER_KIND_EPOCH,
    MARKER_KIND_PRESENTATION,
    MARKER_KIND_SCIENCE,
    MARKER_KIND_SYNC,
    MARKER_KIND_WAYPOINT,
    MARKER_KINDS,
    SCENE_OBJECT_PREFIX,
    TIMELINE_TOKEN_PREFIX,
    TRACK_SUFFIX_CAMERA_PSR,
    TRACK_SUFFIX_NAV_CONE,
    DisplayLabel,
    annotation_object_name,
    baked_track_name,
    display_label_for_visible,
    is_baked_track_name,
    is_unav_owned_name,
    marker_token,
    mission_preview_name,
    overlay_object_name,
    parse_marker_token,
    safe_token,
    science_layer_object_name,
    visible_sector_child_name,
    waypoint_null_name,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_prefix_constants():
    assert SCENE_OBJECT_PREFIX == "UNAV_"
    assert TIMELINE_TOKEN_PREFIX == "UNAV:"


def test_marker_kinds_complete():
    expected = {
        MARKER_KIND_WAYPOINT, MARKER_KIND_EPOCH,
        MARKER_KIND_SYNC, MARKER_KIND_SCIENCE,
        MARKER_KIND_PRESENTATION,
    }
    assert expected == set(MARKER_KINDS)


# ---------------------------------------------------------------------------
# safe_token
# ---------------------------------------------------------------------------


def test_safe_token_strips_unsafe_chars():
    assert safe_token("Saturn / Cassini Division") == "Saturn_Cassini_Division"


def test_safe_token_handles_empty():
    assert safe_token("") == "_"


def test_safe_token_caps_length():
    assert len(safe_token("a" * 200, max_len=50)) == 50


def test_safe_token_strips_dots_and_underscores():
    assert safe_token("___abc___") == "abc"


def test_safe_token_deterministic():
    assert safe_token("Mission: 42") == safe_token("Mission: 42")


# ---------------------------------------------------------------------------
# Scene object names
# ---------------------------------------------------------------------------


def test_visible_sector_child_name_uses_uid():
    name = visible_sector_child_name("gaia:5853498713160606720")
    assert name.startswith(SCENE_OBJECT_PREFIX)
    assert "gaia" in name


def test_visible_sector_child_name_uses_label_when_present():
    name = visible_sector_child_name("gaia:1", label="Proxima Centauri")
    assert "Proxima_Centauri" in name


def test_visible_sector_child_name_deterministic():
    a = visible_sector_child_name("gaia:1", label="Sun")
    b = visible_sector_child_name("gaia:1", label="Sun")
    assert a == b


def test_overlay_object_name():
    name = overlay_object_name("grid")
    assert name == "UNAV_Overlay_grid"


def test_science_layer_object_name():
    name = science_layer_object_name("distance_shells")
    assert name == "UNAV_Science_distance_shells"


def test_mission_preview_name_is_unique_per_mission():
    a = mission_preview_name("voyager")
    b = mission_preview_name("saturn")
    assert a != b


def test_waypoint_null_name_format():
    name = waypoint_null_name("voyager", 3, label="Saturn")
    assert "WP003" in name
    assert "Saturn" in name


def test_waypoint_null_name_falls_back_when_no_label():
    name = waypoint_null_name("voyager", 7)
    assert "WP007" in name


def test_annotation_object_name_format():
    name = annotation_object_name(2, "Welcome")
    assert "Annotation_002_Welcome" in name


# ---------------------------------------------------------------------------
# Marker tokens
# ---------------------------------------------------------------------------


def test_marker_token_basic_form():
    assert marker_token("waypoint") == "UNAV:waypoint"


def test_marker_token_with_payload():
    assert marker_token("epoch", "J2026") == "UNAV:epoch:J2026"


def test_marker_token_payload_sanitised():
    assert marker_token("waypoint", "Saturn / Cassini") == "UNAV:waypoint:Saturn_Cassini"


def test_marker_token_rejects_unknown_kind():
    with pytest.raises(ValueError):
        marker_token("not_a_kind")


def test_parse_marker_token_round_trip():
    token = marker_token("waypoint", "saturn")
    parsed = parse_marker_token(token)
    assert parsed == ("waypoint", "saturn")


def test_parse_marker_token_returns_none_for_foreign():
    assert parse_marker_token("MyMarker") is None
    assert parse_marker_token("UNAV:not_a_kind") is None


def test_parse_marker_token_no_payload():
    parsed = parse_marker_token("UNAV:epoch")
    assert parsed == ("epoch", "")


def test_parse_marker_token_handles_non_string():
    assert parse_marker_token(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# UNAV ownership check
# ---------------------------------------------------------------------------


def test_is_unav_owned_name_scene():
    assert is_unav_owned_name("UNAV_Overlay_grid")


def test_is_unav_owned_name_timeline():
    assert is_unav_owned_name("UNAV:waypoint:saturn")


def test_is_unav_owned_name_foreign():
    assert not is_unav_owned_name("Camera")
    assert not is_unav_owned_name("MyArtistNull")


def test_is_unav_owned_name_handles_non_string():
    assert not is_unav_owned_name(None)  # type: ignore[arg-type]
    assert not is_unav_owned_name(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Bake track names
# ---------------------------------------------------------------------------


def test_baked_track_name_format():
    name = baked_track_name(target="camera", suffix=TRACK_SUFFIX_CAMERA_PSR)
    assert name == "UNAV:Bake:camera:PSR"


def test_baked_track_name_navigator():
    name = baked_track_name(target="navigator", suffix=TRACK_SUFFIX_NAV_CONE)
    assert name == "UNAV:Bake:navigator:Cone"


def test_baked_track_name_deterministic():
    a = baked_track_name(target="camera", suffix="PSR")
    b = baked_track_name(target="camera", suffix="PSR")
    assert a == b


def test_is_baked_track_name_recognises_own():
    assert is_baked_track_name("UNAV:Bake:camera:PSR")


def test_is_baked_track_name_rejects_other():
    assert not is_baked_track_name("UNAV:waypoint:foo")
    assert not is_baked_track_name("Custom Track")


# ---------------------------------------------------------------------------
# Display label
# ---------------------------------------------------------------------------


def test_display_label_render_with_annotation():
    lbl = DisplayLabel(name="UNAV_Object_x", annotation="(Gaia DR3)")
    assert "(Gaia DR3)" in lbl.render()
    assert "UNAV_Object_x" in lbl.render()


def test_display_label_render_without_annotation():
    lbl = DisplayLabel(name="UNAV_Object_x")
    assert lbl.render() == "UNAV_Object_x"


def test_display_label_for_visible_with_common_name():
    lbl = display_label_for_visible(
        uid="gaia:1", common_name="Sun", catalog_source="Gaia DR3",
    )
    assert "Sun" in lbl.name
    assert "Gaia DR3" in lbl.annotation


def test_display_label_for_visible_no_source():
    lbl = display_label_for_visible(uid="gaia:1")
    assert lbl.annotation == ""
