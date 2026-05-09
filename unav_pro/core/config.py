"""Plugin-wide preferences (the long-lived per-user settings).

This module is the simpler half of UNAV Pro's persistence story:
catalog cache root, default scale mode, log verbosity, the path to
the last loaded state file, etc. Everything here is per-user — it
follows the user across scenes — and lives in a single JSON file
under ``~/.unav_pro/config.json``.

For per-project state (route, active datasets, encoding) see
``unav_pro/core/project_state.py``.

No c4d dependency. Pure CPython.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Optional

from core.logging_util import get_logger
from data.schema import DEFAULT_SCALE_MODE, SCALE_MODES

_log = get_logger("core.config")

CONFIG_SCHEMA_VERSION = 1
CONFIG_FILENAME = "config.json"

DEFAULT_CACHE_ROOT = "~/.unav_pro/cache"
DEFAULT_LOG_LEVEL = "INFO"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class UnavConfig:
    """Per-user UNAV preferences.

    Defaults reproduce the plugin's out-of-the-box behaviour, so a
    fresh install with no config file behaves identically to a config
    file containing only the defaults.
    """

    schema_version: int = CONFIG_SCHEMA_VERSION
    cache_root: str = DEFAULT_CACHE_ROOT
    default_scale_mode: str = DEFAULT_SCALE_MODE
    log_level: str = DEFAULT_LOG_LEVEL

    #: Whether the dialog should try to auto-load the last saved
    #: project state when the active document changes. Default off
    #: until we have a stable scene-listener path; the user can opt
    #: in.
    auto_load_state: bool = False

    #: Where the dialog last saved a project state. Used to suggest
    #: a default Save UNAV State filename next time around.
    last_state_path: Optional[str] = None

    #: Last catalog the user picked from the file dialog. Used as
    #: the starting directory for "Add Dataset".
    last_catalog_path: Optional[str] = None

    # ---------------------------------------------------- (de)serialization
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "UnavConfig":
        d = d or {}
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in d.items() if k in known}
        out = cls(**clean)
        # Validate enums silently — fall back to defaults if the user
        # hand-edited config.json into an invalid state.
        if out.default_scale_mode not in SCALE_MODES:
            _log.warning(
                "Config: default_scale_mode=%r unknown; reverting to %r.",
                out.default_scale_mode, DEFAULT_SCALE_MODE,
            )
            out.default_scale_mode = DEFAULT_SCALE_MODE
        if out.log_level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            out.log_level = DEFAULT_LOG_LEVEL
        return out

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "UnavConfig":
        try:
            return cls.from_dict(json.loads(s or "{}"))
        except (TypeError, ValueError):
            return cls()


# ---------------------------------------------------------------------------
# Disk paths
# ---------------------------------------------------------------------------


def default_config_dir() -> str:
    """Per-user UNAV Pro directory. Created lazily by ``save_config``."""
    return os.path.expanduser("~/.unav_pro")


def default_config_path() -> str:
    return os.path.join(default_config_dir(), CONFIG_FILENAME)


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------


def load_config(path: Optional[str] = None) -> UnavConfig:
    """Load the per-user config. Missing or corrupt files yield the
    default config; this function never raises."""
    p = path or default_config_path()
    if not os.path.isfile(p):
        return UnavConfig()
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return UnavConfig.from_dict(json.load(fh))
    except (OSError, ValueError, TypeError) as exc:
        _log.warning("Could not read config %s: %s; using defaults.", p, exc)
        return UnavConfig()


def safe_write_json(path: str, payload: str) -> Optional[str]:
    """Atomic JSON write helper shared by the v1.7 persistence
    surfaces (config / bookmarks / project state / missions).

    Writes to a sibling ``.tmp`` file and renames into place, so a
    crash mid-write can never truncate an existing valid file.
    Returns ``path`` on success or ``None`` on failure (never
    raises). Logs at ``warning`` level on failure.
    """
    parent = os.path.dirname(os.path.abspath(path))
    tmp = path + ".tmp"
    try:
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except OSError as exc:
        _log.warning("Could not write %s: %s", path, exc)
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass
        return None
    return path


def save_config(
    config: UnavConfig, path: Optional[str] = None,
) -> Optional[str]:
    """Persist the config. Returns the path on success, ``None`` on
    failure. Failures are logged but not raised — preferences are not
    worth crashing the dialog over."""
    p = path or default_config_path()
    return safe_write_json(p, config.to_json())


def reset_config(
    path: Optional[str] = None, delete_file: bool = False,
) -> UnavConfig:
    """Replace the on-disk config with a fresh default. Returns the
    new ``UnavConfig`` so the caller can install it.

    With ``delete_file=True`` the file is removed instead of
    rewritten — useful when the user wants every UNAV Pro hint to
    truly disappear.
    """
    p = path or default_config_path()
    fresh = UnavConfig()
    if delete_file:
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError as exc:
            _log.warning("Could not delete config %s: %s", p, exc)
        return fresh
    save_config(fresh, p)
    return fresh
