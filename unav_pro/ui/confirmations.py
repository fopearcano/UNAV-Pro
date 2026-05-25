"""Confirmation prompts for destructive UI actions.

A single registry of the operations that throw away work or scene
state, plus the message the dialog should show before doing them. The
pure half (the registry + message builder) is unit-tested; the c4d half
(:func:`confirm_destructive`) calls ``gui.QuestionDialog`` and is gated
behind the host.

Why centralise: the same destructive action (e.g. *Clear Scene*) may be
reachable from more than one button/path, and the wording + the *which
actions need a prompt* decision should live in one place — not be
re-judged at each call site.

Stdlib-only in the pure half.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

try:
    import c4d  # type: ignore
    from c4d import gui  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    gui = None  # type: ignore
    _C4D_AVAILABLE = False


@dataclass(frozen=True)
class DestructiveAction:
    """One guarded action: a stable id, a short title, and the body of
    the confirmation prompt."""

    action_id: str
    title: str
    prompt: str


#: Every destructive action in the dialog that should confirm first.
DESTRUCTIVE_ACTIONS: Dict[str, DestructiveAction] = {
    a.action_id: a
    for a in (
        DestructiveAction(
            "clear_scene",
            "Clear Scene",
            "Remove all UNAV-generated objects from the active document? "
            "This cannot be undone from here.",
        ),
        DestructiveAction(
            "clear_generated_objects",
            "Clear Generated Objects",
            "Delete every object UNAV generated (point cloud, overlays, "
            "splines)? Your catalogs and datasets are not affected.",
        ),
        DestructiveAction(
            "reset_workspace",
            "Reset Workspace",
            "Reset the current workspace? Unsaved route / mission / note "
            "changes in this workspace will be lost.",
        ),
        DestructiveAction(
            "reset_preferences",
            "Reset Preferences",
            "Reset UNAV preferences to defaults? Your saved datasets and "
            "scene are not affected.",
        ),
        DestructiveAction(
            "delete_mission",
            "Delete Mission",
            "Delete the selected mission? Its waypoints and metadata will "
            "be removed.",
        ),
        DestructiveAction(
            "delete_dataset",
            "Remove Dataset",
            "Remove this dataset registration? The catalog file on disk is "
            "left untouched — only the registry entry is removed.",
        ),
        DestructiveAction(
            "clear_route",
            "Clear Route",
            "Clear the current route? All waypoints will be removed.",
        ),
        DestructiveAction(
            "clear_keyframes",
            "Clear UNAV Keyframes",
            "Remove all UNAV-authored keyframes from the camera/navigator? "
            "Other animation in the scene is left alone.",
        ),
        DestructiveAction(
            "clear_cache_references",
            "Clear Cache References",
            "Forget the cached index / chunk references? The cache files on "
            "disk remain; UNAV will rebuild references on next use.",
        ),
        DestructiveAction(
            "clear_log",
            "Clear Log",
            "Clear the status log? The current log text will be discarded.",
        ),
    )
}


def is_destructive(action_id: str) -> bool:
    return action_id in DESTRUCTIVE_ACTIONS


def get_action(action_id: str) -> Optional[DestructiveAction]:
    return DESTRUCTIVE_ACTIONS.get(action_id)


def confirmation_message(action_id: str) -> str:
    """The prompt body for ``action_id``. Falls back to a generic
    message for an unregistered id so a caller can still guard a new
    action without editing this file first."""
    action = DESTRUCTIVE_ACTIONS.get(action_id)
    if action is None:
        return "This action cannot be undone. Continue?"
    return action.prompt


def confirmation_title(action_id: str) -> str:
    action = DESTRUCTIVE_ACTIONS.get(action_id)
    return action.title if action else "Confirm"


if _C4D_AVAILABLE:

    def confirm_destructive(action_id: str) -> bool:
        """Show a yes/no confirmation for ``action_id``. Returns True
        when the user confirms. Unregistered ids still prompt (with the
        generic message) so nothing destructive slips through
        unguarded."""
        return bool(gui.QuestionDialog(confirmation_message(action_id)))

else:  # pragma: no cover — non-C4D import path

    def confirm_destructive(action_id: str) -> bool:
        raise RuntimeError(
            "confirm_destructive requires Cinema 4D; use "
            "confirmation_message()/is_destructive() in pure code."
        )
