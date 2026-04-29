"""Tests for core.config. Pure CPython, no Cinema 4D."""

from __future__ import annotations

import json
import os

import pytest

from core import config as cfg
from core.config import (
    CONFIG_FILENAME,
    CONFIG_SCHEMA_VERSION,
    DEFAULT_LOG_LEVEL,
    UnavConfig,
    default_config_path,
    load_config,
    reset_config,
    save_config,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_unav_config_defaults_valid():
    c = UnavConfig()
    assert c.schema_version == CONFIG_SCHEMA_VERSION
    assert c.cache_root.endswith(".unav_pro/cache")
    assert c.default_scale_mode == "pc"
    assert c.log_level == DEFAULT_LOG_LEVEL
    assert c.auto_load_state is False
    assert c.last_state_path is None


def test_default_config_path_is_per_user():
    p = default_config_path()
    assert p.endswith(CONFIG_FILENAME)
    assert ".unav_pro" in p


# ---------------------------------------------------------------------------
# Save / load round trip
# ---------------------------------------------------------------------------


def test_save_load_round_trip(tmp_path):
    p = str(tmp_path / "config.json")
    c = UnavConfig(
        cache_root="/data/cache",
        default_scale_mode="kpc",
        log_level="DEBUG",
        auto_load_state=True,
        last_state_path="/projects/scene_state.json",
        last_catalog_path="/data/sample.jsonl",
    )
    saved = save_config(c, p)
    assert saved == p
    raw = json.loads(open(p).read())
    assert raw["schema_version"] == CONFIG_SCHEMA_VERSION
    out = load_config(p)
    assert out == c


def test_save_creates_parent_dirs(tmp_path):
    nested = str(tmp_path / "deep" / "deeper" / "config.json")
    save_config(UnavConfig(), nested)
    assert os.path.isfile(nested)


def test_save_handles_unwritable_dir_quietly(monkeypatch, tmp_path):
    def fail_makedirs(*_a, **_kw):
        raise OSError("read-only fs")

    monkeypatch.setattr(cfg.os, "makedirs", fail_makedirs)
    out = save_config(UnavConfig(), str(tmp_path / "nope" / "c.json"))
    assert out is None  # logged + reported, not raised


# ---------------------------------------------------------------------------
# Missing / corrupt fallback
# ---------------------------------------------------------------------------


def test_load_missing_returns_defaults(tmp_path):
    out = load_config(str(tmp_path / "no_such_file.json"))
    assert out == UnavConfig()


def test_load_corrupt_returns_defaults(tmp_path):
    p = str(tmp_path / "corrupt.json")
    with open(p, "w") as fh:
        fh.write("{not valid json")
    out = load_config(p)
    assert out == UnavConfig()


def test_load_unknown_keys_dropped(tmp_path):
    p = str(tmp_path / "config.json")
    with open(p, "w") as fh:
        json.dump(
            {
                "default_scale_mode": "pc",
                "warp_drive": True,
                "subspace_anchor": [1, 2, 3],
            },
            fh,
        )
    out = load_config(p)
    assert out.default_scale_mode == "pc"
    # Unknown keys are silently ignored — they don't make it onto the
    # dataclass.
    assert not hasattr(out, "warp_drive")


def test_invalid_scale_mode_falls_back(tmp_path):
    p = str(tmp_path / "config.json")
    save_config(UnavConfig(), p)
    # Hand-edit to break it.
    with open(p, "r+") as fh:
        d = json.load(fh)
        d["default_scale_mode"] = "warp"
        fh.seek(0)
        fh.truncate()
        json.dump(d, fh)
    out = load_config(p)
    assert out.default_scale_mode == "pc"


def test_invalid_log_level_falls_back(tmp_path):
    p = str(tmp_path / "config.json")
    save_config(UnavConfig(log_level="LOUD"), p)
    out = load_config(p)
    assert out.log_level == DEFAULT_LOG_LEVEL


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


def test_reset_rewrites_with_defaults(tmp_path):
    p = str(tmp_path / "config.json")
    save_config(
        UnavConfig(default_scale_mode="kpc", auto_load_state=True), p,
    )
    fresh = reset_config(p)
    assert fresh == UnavConfig()
    # File now contains the defaults.
    assert load_config(p) == UnavConfig()


def test_reset_with_delete_file_removes_it(tmp_path):
    p = str(tmp_path / "config.json")
    save_config(UnavConfig(), p)
    assert os.path.isfile(p)
    fresh = reset_config(p, delete_file=True)
    assert fresh == UnavConfig()
    assert not os.path.isfile(p)


def test_reset_delete_when_file_absent_is_noop(tmp_path):
    p = str(tmp_path / "absent.json")
    fresh = reset_config(p, delete_file=True)
    assert fresh == UnavConfig()
    assert not os.path.isfile(p)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def test_to_json_round_trip():
    c = UnavConfig(default_scale_mode="ly")
    out = UnavConfig.from_json(c.to_json())
    assert out == c


def test_from_json_handles_garbage():
    out = UnavConfig.from_json("{not valid")
    assert out == UnavConfig()


def test_from_json_handles_empty_string():
    out = UnavConfig.from_json("")
    assert out == UnavConfig()
