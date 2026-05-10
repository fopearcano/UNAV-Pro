"""v3.5 first-run experience.

What the dialog shows the very first time a public-alpha
tester opens it:

* a friendly *welcome* message;
* a *next-step* recommendation depending on the current
  state (no workspace? load the bundled demo. Workspace
  loaded but no datasets? add one. Datasets loaded but
  no navigator? create one. Navigator but no visible
  sector? sync one.);
* a hint that the *Diagnostics → Run Health Check*
  button exists.

Pre-v3.5 the dialog had ad-hoc strings sprinkled across
panels. v3.5 gathers the policy here so:

* the messages are testable without a Cinema 4D host;
* the "next-step" recommendation is computed from a
  pure ``FirstRunState`` snapshot;
* the wording can be tuned in one place.

Pure stdlib; no Cinema 4D imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional


# ---------------------------------------------------------------------------
# State snapshot
# ---------------------------------------------------------------------------


class FirstRunStage(str, Enum):
    """Coarse stages the new tester can be in when the
    dialog opens. Pure data; the ``recommend_next_step``
    helper maps the stage onto a one-line recommendation."""

    NO_WORKSPACE = "no_workspace"
    NO_DATASETS = "no_datasets"
    NO_NAVIGATOR = "no_navigator"
    NO_VISIBLE_SECTOR = "no_visible_sector"
    READY = "ready"


FIRST_RUN_STAGES = tuple(FirstRunStage)


@dataclass
class FirstRunState:
    """Snapshot the dialog hands to ``recommend_next_step``.

    All fields are booleans / counts so the helper stays
    testable without booting Cinema 4D."""

    workspace_active: bool = False
    enabled_dataset_count: int = 0
    has_navigator: bool = False
    visible_sector_count: int = 0


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------


@dataclass
class FirstRunRecommendation:
    """One step's guidance: a stage tag, a short title,
    and a longer body the dialog renders into the status
    log + welcome panel."""

    stage: FirstRunStage
    title: str
    body: str
    button_label: str = ""

    def short_summary(self) -> str:
        return f"[{self.stage.value}] {self.title}"


def classify_state(state: FirstRunState) -> FirstRunStage:
    """Pure helper: map a state snapshot onto a stage."""
    if not state.workspace_active:
        return FirstRunStage.NO_WORKSPACE
    if state.enabled_dataset_count <= 0:
        return FirstRunStage.NO_DATASETS
    if not state.has_navigator:
        return FirstRunStage.NO_NAVIGATOR
    if state.visible_sector_count <= 0:
        return FirstRunStage.NO_VISIBLE_SECTOR
    return FirstRunStage.READY


def recommend_next_step(
    state: FirstRunState,
) -> FirstRunRecommendation:
    """Compose the recommendation for the current state.

    Returns a ``FirstRunRecommendation`` with title +
    body + suggested button label. The dialog renders
    the body verbatim into the *Welcome* panel.
    """
    stage = classify_state(state)
    if stage is FirstRunStage.NO_WORKSPACE:
        return FirstRunRecommendation(
            stage=stage,
            title="Open a workspace",
            body=(
                "Welcome to UNAV Pro!\n\n"
                "Start by opening the bundled internal-beta demo "
                "workspace via Project → Open Workspace…, then "
                "pick samples/internal_beta_demo/. The demo "
                "ships with five Gaia-style stars, three JPL "
                "bodies, a three-stop mission, and a "
                "presentation."
            ),
            button_label="Open Workspace…",
        )
    if stage is FirstRunStage.NO_DATASETS:
        return FirstRunRecommendation(
            stage=stage,
            title="Add a dataset",
            body=(
                "Workspace loaded. Open Dataset Manager → "
                "Add Dataset… and point at one of the bundled "
                "JSONL files (or your own catalog). Both demo "
                "files under datasets/ are safe to load."
            ),
            button_label="Open Dataset Manager…",
        )
    if stage is FirstRunStage.NO_NAVIGATOR:
        return FirstRunRecommendation(
            stage=stage,
            title="Create a navigator",
            body=(
                "Datasets are active. Click Navigator → Create "
                "Navigation Null to drop a UNAV_Navigator into "
                "the scene. Default cone settings produce a "
                "sensible visible sector for the demo data."
            ),
            button_label="Create Navigation Null",
        )
    if stage is FirstRunStage.NO_VISIBLE_SECTOR:
        return FirstRunRecommendation(
            stage=stage,
            title="Sync the visible sector",
            body=(
                "Navigator in place. Click Sync Visible Sector "
                "to materialise the catalog rows the navigator's "
                "cone selects. The status log shows "
                "+N added / =M kept / -K removed."
            ),
            button_label="Sync Visible Sector",
        )
    return FirstRunRecommendation(
        stage=FirstRunStage.READY,
        title="Ready",
        body=(
            "Workspace, datasets, navigator, and visible sector "
            "are all in place. Try Inspect Selected Object on "
            "any starfield child, or load the demo presentation "
            "via Presentation → Open Presentation…."
        ),
        button_label="",
    )


# ---------------------------------------------------------------------------
# Welcome banner
# ---------------------------------------------------------------------------


WELCOME_HEADER: str = "=== Welcome to UNAV Pro ==="

#: Sentence that appears under every "no data loaded yet"
#: state. Single source of truth so the wording is
#: identical in every panel.
EMPTY_STATE_HINT: str = (
    "No data loaded yet. Run Diagnostics → Run Health "
    "Check to confirm the install is healthy, or follow "
    "the next-step recommendation above."
)


def render_welcome_message(
    state: FirstRunState,
    *,
    plugin_version: str = "",
    plugin_codename: str = "",
) -> str:
    """Compose the full welcome banner the dialog shows
    on first open.

    The banner combines the version line, the
    recommendation body, and the empty-state hint.
    """
    rec = recommend_next_step(state)
    lines: List[str] = [WELCOME_HEADER, ""]
    if plugin_version:
        tag = (
            f"UNAV Pro v{plugin_version}"
            + (f" — {plugin_codename}" if plugin_codename else "")
        )
        lines.append(tag)
        lines.append("")
    lines.append(f"Next step: {rec.title}")
    lines.append("")
    lines.append(rec.body)
    if rec.button_label:
        lines.append("")
        lines.append(f"Suggested action: {rec.button_label}")
    lines.append("")
    if rec.stage is not FirstRunStage.READY:
        lines.append(EMPTY_STATE_HINT)
    return "\n".join(lines).rstrip() + "\n"


def render_empty_state(label: str) -> str:
    """Helper for *every* panel that wants a "no data
    loaded yet" placeholder. Pass a panel-specific
    ``label`` (e.g. ``"missions"``) and the helper
    returns a one-line message."""
    if not label:
        return EMPTY_STATE_HINT
    return f"No {label} loaded yet. {EMPTY_STATE_HINT}"


# ---------------------------------------------------------------------------
# Probe (defensive live-state read)
# ---------------------------------------------------------------------------


def probe_first_run_state() -> FirstRunState:
    """Construct a ``FirstRunState`` from the live
    state-manager facade. Defensive: every probe is
    wrapped so a missing subsystem produces a
    conservative ``False`` / ``0`` rather than raising.
    """
    state = FirstRunState()
    try:
        from core.state_manager import current_workspace
        state.workspace_active = current_workspace() is not None
    except Exception:  # noqa: BLE001
        pass
    try:
        from core.state_manager import get_dataset_registry
        registry = get_dataset_registry()
        entries = list(getattr(registry, "entries", ()) or ())
        state.enabled_dataset_count = sum(
            1 for e in entries if bool(getattr(e, "enabled", False))
        )
    except Exception:  # noqa: BLE001
        pass
    # has_navigator + visible_sector_count default to
    # False / 0 — the dialog overrides these from the
    # active C4D document when running inside the host.
    return state
