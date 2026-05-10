"""UNAV Pro v3.3 presentation package.

Lecture / exhibition / cinematic-storytelling layer
on top of the v0.1 → v3.2 stack. Pure stdlib at
runtime; no Cinema 4D, no rendering, no IPC.

Modules:

* :mod:`presentation_sequence` — declarative shape
  (``PresentationSequence`` + ``PresentationStep``).
* :mod:`presentation_state` — runtime tracker
  (``PresentationState``).
* :mod:`annotations` — per-step annotation visibility
  helpers.
* :mod:`overlay_states` — per-step overlay / science
  flag merge helpers.
* :mod:`manager` — disk-backed CRUD store.
* :mod:`export` — Markdown summaries, presenter notes,
  package payloads.
"""

from __future__ import annotations

from .presentation_sequence import (
    DEFAULT_STEP_PAUSE_SECONDS,
    MAX_STEPS_PER_PRESENTATION,
    PRESENTATION_SCHEMA_VERSION,
    PresentationError,
    PresentationSequence,
    PresentationStep,
    ResolvedStep,
)
from .presentation_state import (
    PRESENTATION_FINISHED,
    PRESENTATION_IDLE,
    PRESENTATION_PAUSED,
    PRESENTATION_RUNNING,
    PRESENTATION_STATUSES,
    PresentationSnapshot,
    PresentationState,
)
from .annotations import (
    AnnotationDisplayState,
    StepAnnotationView,
    diff_annotation_views,
    resolve_annotation_view,
)
from .overlay_states import (
    FLAG_PREFIX,
    FlagDiff,
    apply_overlay_flags,
    apply_science_flags,
    diff_flags,
    resolved_layer_states,
)
from .manager import (
    PRESENTATIONS_DIRNAME,
    PRESENTATIONS_INDEX_FILENAME,
    PresentationManager,
    default_presentations_dir,
)
from .export import (
    PresentationPackagePayload,
    build_presentation_payload,
    render_presentation_markdown,
    render_presenter_notes,
    write_presentation_files,
)
from .chapters import (
    CHAPTER_SCHEMA_VERSION,
    MAX_CHAPTERS_PER_PRESENTATION,
    Chapter,
    ChapterError,
    ChapteredPresentation,
    chapters_from_step_groups,
)
from .exhibition_mode import (
    PROTECTED_OPERATIONS,
    VIEW_MODES,
    ExhibitionState,
    GuardDecision,
    ViewMode,
    guard_action,
    guarded_operations,
)
from .transitions import (
    TRANSITION_KINDS,
    StepProjection,
    TransitionFrame,
    TransitionKind,
    TransitionSequence,
    TransitionSpec,
    build_transition_sequence,
    project_resolved_step,
    sequence_transition,
)
from .audience_overlays import (
    AUDIENCE_HIDDEN_OVERLAY_FLAGS,
    AUDIENCE_HIDDEN_SCIENCE_FLAGS,
    AudienceOverlayFlags,
    HighlightInstruction,
    apply_audience_overlays,
    flags_for_state,
    highlight_for_state,
)
from .exhibition_export import (
    EXHIBITION_PACKAGE_SCHEMA_VERSION,
    ExhibitionPackagePayload,
    build_exhibition_package,
    render_chapter_summary,
    render_cue_sheet,
    write_exhibition_package,
)

__all__ = [
    # sequence
    "PresentationSequence", "PresentationStep", "ResolvedStep",
    "PresentationError",
    "PRESENTATION_SCHEMA_VERSION",
    "MAX_STEPS_PER_PRESENTATION", "DEFAULT_STEP_PAUSE_SECONDS",
    # state
    "PresentationState", "PresentationSnapshot",
    "PRESENTATION_IDLE", "PRESENTATION_RUNNING",
    "PRESENTATION_PAUSED", "PRESENTATION_FINISHED",
    "PRESENTATION_STATUSES",
    # annotations
    "AnnotationDisplayState", "StepAnnotationView",
    "resolve_annotation_view", "diff_annotation_views",
    # overlay states
    "FLAG_PREFIX", "FlagDiff",
    "apply_overlay_flags", "apply_science_flags",
    "diff_flags", "resolved_layer_states",
    # manager
    "PresentationManager", "default_presentations_dir",
    "PRESENTATIONS_DIRNAME", "PRESENTATIONS_INDEX_FILENAME",
    # export
    "PresentationPackagePayload",
    "build_presentation_payload",
    "render_presentation_markdown",
    "render_presenter_notes",
    "write_presentation_files",
    # v3.8 chapters
    "Chapter", "ChapterError", "ChapteredPresentation",
    "CHAPTER_SCHEMA_VERSION", "MAX_CHAPTERS_PER_PRESENTATION",
    "chapters_from_step_groups",
    # v3.8 exhibition mode
    "ExhibitionState", "ViewMode", "VIEW_MODES",
    "PROTECTED_OPERATIONS",
    "GuardDecision", "guard_action", "guarded_operations",
    # v3.8 transitions
    "TransitionKind", "TRANSITION_KINDS",
    "TransitionSpec", "TransitionFrame", "TransitionSequence",
    "StepProjection", "project_resolved_step",
    "sequence_transition", "build_transition_sequence",
    # v3.8 audience overlays
    "AudienceOverlayFlags", "HighlightInstruction",
    "AUDIENCE_HIDDEN_OVERLAY_FLAGS",
    "AUDIENCE_HIDDEN_SCIENCE_FLAGS",
    "flags_for_state", "highlight_for_state",
    "apply_audience_overlays",
    # v3.8 exhibition export
    "EXHIBITION_PACKAGE_SCHEMA_VERSION",
    "ExhibitionPackagePayload",
    "build_exhibition_package",
    "render_chapter_summary",
    "render_cue_sheet",
    "write_exhibition_package",
]
