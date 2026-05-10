"""v3.3 per-step overlay + science-layer state.

Each presentation step carries an ``overlay_flags`` dict
and a ``science_flags`` dict mapping ``show_*`` field
name → bool. This module provides:

* ``apply_overlay_flags`` — fold a step's flags into
  a base settings dict (the v2.0 `OverlaySettings.to_dict()`
  / v2.1 `ScienceLayerSettings.to_dict()` shape) so the
  C4D builder can hand the merged dict to the existing
  builders without modification.
* ``diff_flags`` — what changed between two consecutive
  steps so the v3.0 partial-rebuild planners can skip
  unchanged groups.
* ``apply_step_flags_to_settings_dict`` — convenience
  variant for nested settings dicts.

Pure stdlib; no Cinema 4D, no astropy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set


# ---------------------------------------------------------------------------
# Allowed flag prefixes
# ---------------------------------------------------------------------------


#: Every flag tracked by v3.3 presentation steps starts
#: with ``show_``. Other keys in the step's flag dict are
#: ignored — the v3.3 layer never injects geometry knobs.
FLAG_PREFIX: str = "show_"


# ---------------------------------------------------------------------------
# Apply step flags
# ---------------------------------------------------------------------------


def apply_overlay_flags(
    base_settings: Optional[Dict[str, Any]],
    step_flags: Optional[Dict[str, bool]],
) -> Dict[str, Any]:
    """Return a fresh settings dict whose ``show_*`` keys
    are taken from ``step_flags`` when present and from
    ``base_settings`` otherwise.

    The merge is non-destructive: ``base_settings`` is
    never mutated. Geometry / radius / opacity fields ride
    through unchanged.
    """
    out: Dict[str, Any] = dict(base_settings or {})
    for k, v in (step_flags or {}).items():
        if not isinstance(k, str):
            continue
        if not k.startswith(FLAG_PREFIX):
            continue
        out[k] = bool(v)
    return out


def apply_science_flags(
    base_settings: Optional[Dict[str, Any]],
    step_flags: Optional[Dict[str, bool]],
) -> Dict[str, Any]:
    """Same shape as :func:`apply_overlay_flags`, kept as
    a separate helper so the v2.1 science-layer module's
    schema can drift independently of v2.0 overlays."""
    return apply_overlay_flags(base_settings, step_flags)


# ---------------------------------------------------------------------------
# Diff flags
# ---------------------------------------------------------------------------


@dataclass
class FlagDiff:
    """Per-flag transitions between two consecutive
    settings snapshots. Pure data."""

    enabled: List[str] = field(default_factory=list)
    disabled: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)

    def is_clean(self) -> bool:
        return not self.enabled and not self.disabled

    def short_summary(self) -> str:
        parts: List[str] = []
        if self.enabled:
            parts.append(f"enable {len(self.enabled)}")
        if self.disabled:
            parts.append(f"disable {len(self.disabled)}")
        return ", ".join(parts) if parts else "no changes"


def diff_flags(
    previous: Optional[Dict[str, Any]],
    current: Optional[Dict[str, Any]],
) -> FlagDiff:
    """Compare two settings dicts and report the
    ``show_*`` flag transitions between them.

    Both inputs are full settings dicts (not just the
    flag subset); only ``show_*`` keys participate in the
    diff. Geometry knob changes are *not* reported here —
    the v3.0 partial-rebuild planners cover those.
    """
    prev = previous or {}
    cur = current or {}
    keys: Set[str] = {
        k for k in set(prev) | set(cur)
        if isinstance(k, str) and k.startswith(FLAG_PREFIX)
    }
    diff = FlagDiff()
    for key in sorted(keys):
        p = bool(prev.get(key, False))
        c = bool(cur.get(key, False))
        if p == c:
            diff.unchanged.append(key)
            continue
        if c and not p:
            diff.enabled.append(key)
        else:
            diff.disabled.append(key)
    return diff


# ---------------------------------------------------------------------------
# Resolver helper
# ---------------------------------------------------------------------------


def resolved_layer_states(
    *,
    base_overlay_settings: Optional[Dict[str, Any]],
    base_science_settings: Optional[Dict[str, Any]],
    overlay_flags: Optional[Dict[str, bool]],
    science_flags: Optional[Dict[str, bool]],
) -> Dict[str, Dict[str, Any]]:
    """Convenience: produce both merged dicts in one
    call. The C4D builder consumes
    ``out["overlays"]`` and ``out["science_layers"]``
    directly."""
    return {
        "overlays": apply_overlay_flags(
            base_overlay_settings, overlay_flags,
        ),
        "science_layers": apply_science_flags(
            base_science_settings, science_flags,
        ),
    }
