"""Render-mode tokens, defaults, and per-mode safety caps.

The v0.7 performance layer separates **how** a visible sector is
materialised in Cinema 4D from **what** is in it. Three render modes
are recognised:

* ``debug_objects`` — one ``c4d.Onull`` per visible row. The v0.1
  behaviour, kept for parity / debugging / per-object selection in the
  Object Manager. Heavy: each null is a real C4D object with its own
  marker BaseContainer, undo entry, and viewport draw call.
* ``instances`` — one shared template + one ``c4d.Oinstance`` per
  visible row. Lighter than debug objects: instances share the
  template's geometry and use less memory per node. Selection still
  works because each instance carries a minimal marker (``uid`` only).
* ``point_cloud`` — placeholder for future native / GPU drawing.
  No per-object C4D node is created; the visible-sector contents
  are recorded in an external uid map the metadata inspector can
  resolve via the search-based fallback. Marked **experimental** in
  the UI; safe to ship as a stub today, ready to swap in a real
  backend later.

This module is the policy half: pure-Python tokens, defaults, caps,
and a small ``RenderModePolicy`` dataclass. The C4D-bound backend
implementations live in
``unav_pro/c4d_objects/render_backend.py`` and
``unav_pro/c4d_objects/instance_builder.py``.

No c4d dependency. Fully unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

#: Render-mode tokens. The dialog's combo box uses
#: ``RENDER_MODE_LABELS`` for the UI strings.
RENDER_MODE_DEBUG_OBJECTS = "debug_objects"
RENDER_MODE_INSTANCES = "instances"
RENDER_MODE_POINT_CLOUD = "point_cloud"
RENDER_MODE_NATIVE_VIEWER = "native_viewer"

RENDER_MODES: Tuple[str, ...] = (
    RENDER_MODE_DEBUG_OBJECTS,
    RENDER_MODE_INSTANCES,
    RENDER_MODE_POINT_CLOUD,
    RENDER_MODE_NATIVE_VIEWER,
)

#: Default render mode. ``debug_objects`` keeps v0.1 behaviour for
#: anyone who upgrades — they have to opt into the lighter modes.
DEFAULT_RENDER_MODE = RENDER_MODE_DEBUG_OBJECTS

#: Human-readable labels for the UI dropdown, in display order.
RENDER_MODE_LABELS: Tuple[Tuple[str, str], ...] = (
    ("Debug Objects (one null per point)", RENDER_MODE_DEBUG_OBJECTS),
    ("Instances (shared template)", RENDER_MODE_INSTANCES),
    ("Point Cloud (experimental)", RENDER_MODE_POINT_CLOUD),
    ("Native Point Viewer (Experimental)", RENDER_MODE_NATIVE_VIEWER),
)


# ---------------------------------------------------------------------------
# Per-mode safety caps
# ---------------------------------------------------------------------------

#: Hard cap on visible-sector size per render mode. The debug-objects
#: cap is intentionally **lower** than the global v0.1 cap of 100k —
#: at debug-objects scale, 10k is already a heavy scene and most
#: machines start to lag past that. Instance and point-cloud modes
#: scale much higher.
DEFAULT_CAPS: Dict[str, int] = {
    RENDER_MODE_DEBUG_OBJECTS: 10_000,
    RENDER_MODE_INSTANCES: 200_000,
    RENDER_MODE_POINT_CLOUD: 1_000_000,
    # v0.9 native point viewer: configurable safety cap. The C++
    # plugin enforces the same limit on its side; the Python
    # exporter clips early so the file on disk is never bigger
    # than this many points.
    RENDER_MODE_NATIVE_VIEWER: 2_000_000,
}

#: Above this many visible objects in native-viewer mode the
#: dialog emits a soft warning. The exporter still proceeds; the
#: hard cap applies on top.
NATIVE_VIEWER_SOFT_WARNING = 500_000

#: Above this many visible objects in debug-objects mode the dialog
#: emits a soft warning. The user can still proceed; the cap above
#: is the hard limit.
DEBUG_OBJECTS_SOFT_WARNING = 5_000

#: Above this many visible objects in instances mode the dialog
#: emits a soft warning.
INSTANCES_SOFT_WARNING = 50_000


def cap_for_mode(mode: str) -> int:
    """Return the hard cap for ``mode`` (default if unknown)."""
    return DEFAULT_CAPS.get(mode, DEFAULT_CAPS[DEFAULT_RENDER_MODE])


def soft_warning_for_mode(mode: str) -> Optional[int]:
    """Return the soft-warning threshold for ``mode``, or ``None`` if
    that mode does not surface a warning."""
    if mode == RENDER_MODE_DEBUG_OBJECTS:
        return DEBUG_OBJECTS_SOFT_WARNING
    if mode == RENDER_MODE_INSTANCES:
        return INSTANCES_SOFT_WARNING
    if mode == RENDER_MODE_NATIVE_VIEWER:
        return NATIVE_VIEWER_SOFT_WARNING
    return None


def validate_mode(mode: Optional[str]) -> str:
    """Normalize ``mode`` to a known token. Unknown / falsy values
    fall back to ``DEFAULT_RENDER_MODE`` so a typo in saved state
    never breaks the dialog."""
    if not mode:
        return DEFAULT_RENDER_MODE
    return mode if mode in RENDER_MODES else DEFAULT_RENDER_MODE


# ---------------------------------------------------------------------------
# Bidirectional label ↔ token helpers (used by the dialog combo)
# ---------------------------------------------------------------------------


def render_mode_for_label(label: str) -> str:
    for lbl, token in RENDER_MODE_LABELS:
        if lbl == label:
            return token
    return DEFAULT_RENDER_MODE


def label_for_render_mode(token: str) -> str:
    for lbl, t in RENDER_MODE_LABELS:
        if t == token:
            return lbl
    return RENDER_MODE_LABELS[0][0]


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass
class RenderModePolicy:
    """All knobs that govern one render-mode pass.

    The dialog builds one of these per click, hands it to
    ``scene_sync.sync_visible_sector``, and the chosen backend
    consumes it.
    """

    mode: str = DEFAULT_RENDER_MODE
    #: Hard cap on visible-sector size for this mode. ``None`` defers
    #: to ``cap_for_mode(self.mode)``.
    max_visible: Optional[int] = None
    #: Whether to surface the soft warning when crossing the
    #: threshold. UI may want to silence it for batch jobs.
    surface_soft_warning: bool = True

    def __post_init__(self) -> None:
        self.mode = validate_mode(self.mode)
        if self.max_visible is not None and self.max_visible < 0:
            raise ValueError("max_visible must be >= 0 or None")

    @property
    def effective_cap(self) -> int:
        """The cap the backend should actually enforce, taking the
        explicit ``max_visible`` first, falling back to the per-mode
        default."""
        if self.max_visible is not None:
            return int(self.max_visible)
        return cap_for_mode(self.mode)

    def should_warn_for(self, visible_count: int) -> bool:
        """True iff ``visible_count`` crosses the soft-warning
        threshold for the current mode and warnings are enabled."""
        if not self.surface_soft_warning:
            return False
        threshold = soft_warning_for_mode(self.mode)
        return threshold is not None and visible_count > threshold


# ---------------------------------------------------------------------------
# Mode capability flags
# ---------------------------------------------------------------------------


@dataclass
class ModeCapabilities:
    """Static description of what a render mode can and cannot do.

    The UI keys off these to show / hide buttons (e.g. the Inspector
    is reachable from a click in debug+instances; in point-cloud it
    falls back to search-by-uid).
    """

    mode: str
    name: str
    description: str
    supports_per_object_selection: bool
    supports_per_instance_metadata: bool
    soft_warning: Optional[int]
    hard_cap: int

    def short_summary(self) -> str:
        sel = "yes" if self.supports_per_object_selection else "no"
        meta = "yes" if self.supports_per_instance_metadata else "no"
        return (
            f"{self.name}: cap={self.hard_cap}, "
            f"per-object selection={sel}, per-instance metadata={meta}"
        )


CAPABILITIES: Dict[str, ModeCapabilities] = {
    RENDER_MODE_DEBUG_OBJECTS: ModeCapabilities(
        mode=RENDER_MODE_DEBUG_OBJECTS,
        name="Debug Objects",
        description=(
            "One c4d.Onull per visible row. Heaviest mode; preserved for "
            "parity with v0.1 and for direct selection workflows."
        ),
        supports_per_object_selection=True,
        supports_per_instance_metadata=True,
        soft_warning=DEBUG_OBJECTS_SOFT_WARNING,
        hard_cap=DEFAULT_CAPS[RENDER_MODE_DEBUG_OBJECTS],
    ),
    RENDER_MODE_INSTANCES: ModeCapabilities(
        mode=RENDER_MODE_INSTANCES,
        name="Instances",
        description=(
            "One shared template null + one c4d.Oinstance per visible row. "
            "Lighter than debug objects; per-instance marker carries uid "
            "so the inspector still resolves selections."
        ),
        supports_per_object_selection=True,
        supports_per_instance_metadata=False,  # only uid, not full metadata
        soft_warning=INSTANCES_SOFT_WARNING,
        hard_cap=DEFAULT_CAPS[RENDER_MODE_INSTANCES],
    ),
    RENDER_MODE_POINT_CLOUD: ModeCapabilities(
        mode=RENDER_MODE_POINT_CLOUD,
        name="Point Cloud",
        description=(
            "Experimental placeholder for native/GPU drawing. No "
            "per-object C4D node is created; the inspector falls back to "
            "search-by-uid."
        ),
        supports_per_object_selection=False,
        supports_per_instance_metadata=False,
        soft_warning=None,
        hard_cap=DEFAULT_CAPS[RENDER_MODE_POINT_CLOUD],
    ),
    RENDER_MODE_NATIVE_VIEWER: ModeCapabilities(
        mode=RENDER_MODE_NATIVE_VIEWER,
        name="Native Point Viewer (Experimental)",
        description=(
            "v0.9 prototype: Python writes a binary visible-sector "
            "file; the native C++ plugin (when loaded) draws the "
            "points directly. No per-object C4D node is created; "
            "selection uses the native pick file with a search-based "
            "fallback when the native plugin is not available."
        ),
        supports_per_object_selection=False,
        supports_per_instance_metadata=False,
        soft_warning=NATIVE_VIEWER_SOFT_WARNING,
        hard_cap=DEFAULT_CAPS[RENDER_MODE_NATIVE_VIEWER],
    ),
}


def capabilities_for(mode: str) -> ModeCapabilities:
    return CAPABILITIES.get(validate_mode(mode), CAPABILITIES[DEFAULT_RENDER_MODE])
