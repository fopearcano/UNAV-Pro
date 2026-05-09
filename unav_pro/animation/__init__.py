"""UNAV Pro v2.2 animation package.

Frame-aware mission state evaluator + Cinema 4D timeline
integration. See ``docs/V2_2_ANIMATION_TIMELINE_INTEGRATION.md``.
"""

from __future__ import annotations

from .animated_state import (
    AnimatedSample,
    AnimatedStateConfig,
    AnimatedTimeline,
    evaluate_animated_state,
    evaluate_at_frame,
    evaluate_at_seconds,
    frame_to_progress,
    frame_to_seconds,
    seconds_to_frame,
)

__all__ = [
    "AnimatedSample",
    "AnimatedStateConfig",
    "AnimatedTimeline",
    "evaluate_animated_state",
    "evaluate_at_frame",
    "evaluate_at_seconds",
    "frame_to_progress",
    "frame_to_seconds",
    "seconds_to_frame",
]
