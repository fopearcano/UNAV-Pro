"""Hard safety guardrails for UNAV Pro.

Cinema 4D scenes that try to materialize the universe crash on save,
freeze on selection, or silently produce 5 GB ``.c4d`` files. This
module is the gate that refuses to let that happen by accident.

Rules
-----

  * **Hard cap.** No build action emits more than
    ``SafetyLimits.max_generated_objects`` C4D nodes. The default is
    100 000 — well above what the Python prototype handles
    smoothly, but well below "freeze the host."
  * **Warning threshold.** Builds above
    ``SafetyLimits.warning_threshold`` (default 10 000) succeed but
    log a warning and surface it in the action's status line so
    the user knows they're in heavy territory.
  * **Visible-sector-only mode.** The default. Without a
    ``UNAV_Navigator`` in the scene, generation is **blocked** with
    a clear message explaining how to either create a navigator or
    flip the override.
  * **Override.** ``SafetyLimits.allow_full_catalog`` lets the user
    intentionally bypass the cap *and* the visible-sector
    requirement. Logged as a warning every time it triggers so the
    user is never surprised by the override staying on across
    sessions.
  * **Dataset / scene / file-size advisories.** Three additional
    evaluators warn the user *before* they hit the runtime
    consequences: registering a million-row catalog, a scene that
    already holds 200 k objects, or a ``.c4d`` larger than 200 MB.

Marker minimality
-----------------

A separate but related rule lives in
``c4d_objects/point_cloud_builder.marker_for_object``:
**the schema's full ``metadata_json`` blob is not embedded into
every UNAV null by default**. The marker carries uid + source +
type + name + core astrometry — enough to look the object up in
the external catalog. The inspector pulls the rest from the
``MetadataLookup`` and falls back to "marker only" rendering when
the catalog is not loaded. The opt-in ``include_full_metadata``
flag lets a user save a self-contained .c4d at the cost of a
larger save file; safety mode is "off" until they ask.

No c4d dependency. Pure CPython, fully unit-tested.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional

from core.logging_util import get_logger

_log = get_logger("core.safety")


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

#: Hard ceiling on emitted C4D objects per build. The Python prototype
#: handles this many nulls without falling over; well below the host-
#: freeze territory of millions.
DEFAULT_MAX_GENERATED_OBJECTS = 100_000

#: Above this many objects per build, succeed but warn loudly.
DEFAULT_WARNING_THRESHOLD = 10_000

#: Above this many *registered* rows in a single dataset, advise the
#: user to chunk / index / split before activating it for a build.
DEFAULT_DATASET_SIZE_WARNING = 1_000_000

#: Warn when the active C4D scene already contains this many objects
#: of any kind — likely the user has accumulated content elsewhere
#: and is approaching general C4D viewport limits.
DEFAULT_MAX_SCENE_OBJECT_COUNT = 200_000

#: 200 MB. Above this, a saved .c4d is risky to email / transfer /
#: open on the average machine.
DEFAULT_FILE_SIZE_WARNING_BYTES = 200 * 1024 * 1024


# ---------------------------------------------------------------------------
# Limits dataclass
# ---------------------------------------------------------------------------


@dataclass
class SafetyLimits:
    """User-editable safety policy. Survives across sessions via the
    persistence layer; defaults reproduce safe behaviour out of the
    box."""

    max_generated_objects: int = DEFAULT_MAX_GENERATED_OBJECTS
    warning_threshold: int = DEFAULT_WARNING_THRESHOLD
    dataset_size_warning: int = DEFAULT_DATASET_SIZE_WARNING
    max_scene_object_count: int = DEFAULT_MAX_SCENE_OBJECT_COUNT
    max_c4d_file_size_warning_bytes: int = DEFAULT_FILE_SIZE_WARNING_BYTES

    #: Default mode: refuse to build without a navigator (so the
    #: filter is what bounds the working set, not "the whole
    #: catalog"). Flip to False only when the user explicitly opts
    #: into materializing without a filter.
    visible_sector_only: bool = True

    #: Explicit override that bypasses the hard cap *and* the
    #: visible-sector requirement. Logged as a warning every time it
    #: triggers.
    allow_full_catalog: bool = False

    #: Whether to embed the schema's full ``metadata_json`` blob into
    #: every UNAV null's marker container. Default False keeps .c4d
    #: files small and respects the "minimal marker" rule.
    embed_full_metadata_in_marker: bool = False

    def __post_init__(self) -> None:
        if self.max_generated_objects < 0:
            raise ValueError("max_generated_objects must be >= 0")
        if self.warning_threshold < 0:
            raise ValueError("warning_threshold must be >= 0")
        if self.warning_threshold > self.max_generated_objects:
            # Re-clamp instead of raising so a small typo in the UI
            # doesn't trap the user.
            self.warning_threshold = self.max_generated_objects
        if self.dataset_size_warning < 0:
            raise ValueError("dataset_size_warning must be >= 0")
        if self.max_scene_object_count < 0:
            raise ValueError("max_scene_object_count must be >= 0")
        if self.max_c4d_file_size_warning_bytes < 0:
            raise ValueError("max_c4d_file_size_warning_bytes must be >= 0")

    # ----------------------------------------------------------- (de)ser
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "SafetyLimits":
        d = d or {}
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in d.items() if k in known}
        try:
            return cls(**clean)
        except (TypeError, ValueError) as exc:
            _log.warning(
                "SafetyLimits: invalid persisted values (%s); using defaults.",
                exc,
            )
            return cls()

    # ----------------------------------------------------------------- mode
    def mode_label(self) -> str:
        """Short string for the dialog: what mode is active right now?"""
        if self.allow_full_catalog:
            return "FULL CATALOG OVERRIDE (cap and navigator gate disabled)"
        if self.visible_sector_only:
            return "Visible-sector only (default)"
        return "Sector-aware (no navigator gate; cap still enforced)"


# ---------------------------------------------------------------------------
# Decision dataclass
# ---------------------------------------------------------------------------


LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_BLOCKED = "blocked"


@dataclass
class SafetyDecision:
    """Outcome of one safety check.

    * ``allowed`` is True for ``ok`` and ``warn`` levels, False for
      ``blocked``. The caller treats this as the gate.
    * ``effective`` is what the caller will *actually* materialize
      after any cap clamping; equal to ``requested`` when below the
      cap, equal to the cap when truncated, 0 when blocked.
    * ``messages`` are human-readable reasons; the dialog
      concatenates them into the status line.
    """

    allowed: bool = True
    level: str = LEVEL_OK
    requested: int = 0
    effective: int = 0
    messages: List[str] = field(default_factory=list)

    def short_summary(self) -> str:
        if self.level == LEVEL_BLOCKED:
            head = f"BLOCKED ({self.requested} requested)"
        elif self.level == LEVEL_WARN:
            head = f"WARN (effective {self.effective}/{self.requested})"
        else:
            head = f"ok ({self.effective})"
        if self.messages:
            return head + "; " + " | ".join(self.messages)
        return head


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------


def evaluate_generate(
    requested_count: int,
    limits: Optional[SafetyLimits] = None,
    has_navigator: bool = True,
) -> SafetyDecision:
    """Decide whether a generate / sync action of ``requested_count``
    objects should proceed.

    Logic:

      * ``allow_full_catalog`` → never blocks; warn if above the
        warning threshold; ``effective == requested``.
      * No navigator + ``visible_sector_only`` → blocked.
      * ``requested > max_generated_objects`` and not allowed →
        blocked.
      * ``requested >= warning_threshold`` → warn but allow.
      * Otherwise → ok.
    """
    limits = limits or SafetyLimits()
    requested = max(0, int(requested_count))
    decision = SafetyDecision(requested=requested, effective=requested)

    if limits.allow_full_catalog:
        decision.messages.append(
            "Override active: full-catalog generation enabled — "
            "navigator gate and hard cap bypassed."
        )
        if requested >= limits.warning_threshold:
            decision.level = LEVEL_WARN
            decision.messages.append(
                f"{requested} objects is above the warning threshold "
                f"({limits.warning_threshold}); expect a heavy build."
            )
        return decision

    # Navigator gate (visible-sector-only mode).
    if limits.visible_sector_only and not has_navigator:
        decision.allowed = False
        decision.level = LEVEL_BLOCKED
        decision.effective = 0
        decision.messages.append(
            "Generation blocked: visible-sector-only mode requires a "
            "UNAV_Navigator in the scene. Create one with "
            "'Create Navigation Null', or enable Allow Full Catalog "
            "in the Safety panel to override."
        )
        return decision

    # Hard cap.
    if requested > limits.max_generated_objects:
        decision.allowed = False
        decision.level = LEVEL_BLOCKED
        decision.effective = 0
        decision.messages.append(
            f"Generation blocked: {requested} objects exceeds the hard "
            f"cap of {limits.max_generated_objects}. Reduce the filter "
            "(tighter cone, smaller far-clip, lower max_visible_objects) "
            "or enable Allow Full Catalog to override."
        )
        return decision

    # Warning band.
    if requested >= limits.warning_threshold:
        decision.level = LEVEL_WARN
        decision.messages.append(
            f"{requested} objects is above the warning threshold "
            f"({limits.warning_threshold}); the build will succeed but "
            "viewport responsiveness may degrade."
        )

    return decision


def evaluate_dataset_load(
    object_count: int,
    limits: Optional[SafetyLimits] = None,
) -> SafetyDecision:
    """Advisory check when registering / activating a dataset.

    Never blocks (loading the catalog metadata is cheap; only
    materializing it is dangerous), but warns when the row count is
    above ``dataset_size_warning``."""
    limits = limits or SafetyLimits()
    requested = max(0, int(object_count))
    decision = SafetyDecision(requested=requested, effective=requested)
    if requested >= limits.dataset_size_warning:
        decision.level = LEVEL_WARN
        decision.messages.append(
            f"Dataset has {requested} rows — above the "
            f"{limits.dataset_size_warning} advisory threshold. Build "
            "the spatial index before generating from it; consider "
            "splitting into per-region tiles."
        )
    return decision


def evaluate_scene_state(
    current_scene_object_count: int,
    limits: Optional[SafetyLimits] = None,
) -> SafetyDecision:
    """Advisory check on the *existing* scene's object count.

    Above ``max_scene_object_count`` the user is approaching general
    C4D viewport limits regardless of UNAV — warn, don't block."""
    limits = limits or SafetyLimits()
    requested = max(0, int(current_scene_object_count))
    decision = SafetyDecision(requested=requested, effective=requested)
    if requested >= limits.max_scene_object_count:
        decision.level = LEVEL_WARN
        decision.messages.append(
            f"Scene already contains {requested} objects — at or above "
            f"the {limits.max_scene_object_count} advisory threshold. "
            "Adding more UNAV objects on top may stress the host."
        )
    return decision


def evaluate_file_size(
    bytes_on_disk: int,
    limits: Optional[SafetyLimits] = None,
) -> SafetyDecision:
    """Advisory on the saved .c4d file size."""
    limits = limits or SafetyLimits()
    requested = max(0, int(bytes_on_disk))
    decision = SafetyDecision(requested=requested, effective=requested)
    threshold = limits.max_c4d_file_size_warning_bytes
    if requested >= threshold:
        decision.level = LEVEL_WARN
        mb = requested / (1024 * 1024)
        thresh_mb = threshold / (1024 * 1024)
        decision.messages.append(
            f"Saved scene is {mb:.0f} MB — above the {thresh_mb:.0f} "
            "MB advisory threshold. Consider baking + clearing the "
            "starfield before saving, or removing per-object "
            "metadata via Embed Full Metadata = off."
        )
    return decision


# ---------------------------------------------------------------------------
# Helpers for the dialog
# ---------------------------------------------------------------------------


def status_line(
    limits: SafetyLimits,
    generated_now: Optional[int] = None,
) -> str:
    """One-liner for the dialog's safety strip."""
    parts = [f"Mode: {limits.mode_label()}"]
    if generated_now is not None:
        parts.append(
            f"Generated {generated_now} / cap {limits.max_generated_objects}"
        )
    else:
        parts.append(f"Cap {limits.max_generated_objects}")
    return " — ".join(parts)
