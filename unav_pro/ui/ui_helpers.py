"""Shared UI helpers for a consistent UNAV Pro dialog experience.

This module has two halves:

* A **pure** half — string formatting for status labels, warning
  boxes, section titles, separators, and log lines. These have no
  Cinema 4D dependency and are unit-tested directly.
* A **c4d-bound** half — thin widget builders (`add_section_title`,
  `add_status_label`, `add_button_row`, `add_path_selector`,
  `add_compact_separator`, `add_warning_box`) that the dialogs call to
  lay out a section consistently. These are gated behind
  ``_C4D_AVAILABLE`` and raise outside the host.

The goal is one source of truth for *how a status reads* and *how a
section looks*, so every panel (Home / Dataset / Navigator / … ) feels
like part of the same plugin.

Status convention
-----------------

Cinema 4D's Python ``GeDialog`` has no reliable cross-platform way to
colour or icon individual ``AddStaticText`` widgets, so UNAV uses
**text prefixes** instead — readable, copy-pasteable, and identical on
every host:

    [OK]       healthy / done
    [WARN]     attention, non-fatal
    [ERROR]    failed
    [MISSING]  expected thing is absent
    [DISABLED] present but turned off
    [...]      in progress / unknown

Stdlib-only in the pure half.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, List, Optional, Sequence, Tuple

try:
    import c4d  # type: ignore
    from c4d import storage  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    storage = None  # type: ignore
    _C4D_AVAILABLE = False


# ---------------------------------------------------------------------------
# Status vocabulary (pure)
# ---------------------------------------------------------------------------


class Status(str, Enum):
    """Canonical status tokens shared by every panel."""

    OK = "OK"
    WARN = "WARN"
    ERROR = "ERROR"
    MISSING = "MISSING"
    DISABLED = "DISABLED"
    INFO = "INFO"
    PENDING = "PENDING"


#: Text prefix rendered for each status. Kept short + bracketed so it
#: aligns in a monospace panel and survives a clipboard round-trip.
_STATUS_PREFIX = {
    Status.OK: "[OK]",
    Status.WARN: "[WARN]",
    Status.ERROR: "[ERROR]",
    Status.MISSING: "[MISSING]",
    Status.DISABLED: "[DISABLED]",
    Status.INFO: "[INFO]",
    Status.PENDING: "[...]",
}


def _coerce_status(status) -> Status:
    if isinstance(status, Status):
        return status
    token = str(status or "").strip().upper()
    # Accept a few friendly aliases.
    if token in ("WARNING",):
        return Status.WARN
    try:
        return Status(token)
    except ValueError:
        return Status.INFO


def status_prefix(status) -> str:
    """Return the bracketed prefix for ``status`` (case-insensitive,
    accepts a ``Status`` or a string)."""
    return _STATUS_PREFIX[_coerce_status(status)]


def format_status_label(status, message: str) -> str:
    """``"[OK] message"`` — the standard one-line status string.

    Whitespace-only messages collapse to just the prefix so a caller
    can render a bare badge."""
    prefix = status_prefix(status)
    msg = (message or "").strip()
    return f"{prefix} {msg}" if msg else prefix


def format_section_title(title: str) -> str:
    """Normalise a section heading: trimmed, title-cased only at the
    edges we control (we don't force casing — artists name things)."""
    return (title or "").strip()


def compact_separator(width: int = 48, char: str = "-") -> str:
    """A short horizontal rule for monospace panels."""
    width = max(1, min(int(width), 200))
    return (char or "-")[0] * width


def format_warning_box(
    message: str,
    *,
    status=Status.WARN,
    width: int = 60,
) -> str:
    """A boxed multi-line warning suitable for a read-only text widget.

    ::

        [WARN] ----------------------------------------
        Heads up: the catalog file is missing.
        ------------------------------------------------
    """
    rule = compact_separator(width)
    head = f"{status_prefix(status)} {rule}"
    body = (message or "").strip() or "(no detail)"
    return "\n".join([head, body, rule])


def normalize_button_label(label: str) -> str:
    """Consistent button-label casing/spacing.

    Rules (deliberately light — we don't fight existing names):
      * trim surrounding whitespace,
      * collapse internal runs of spaces,
      * keep a trailing ``…`` (used for "opens a picker/dialog")
        but strip a stray trailing ``...`` → ``…``.
    """
    text = " ".join((label or "").split())
    if text.endswith("..."):
        text = text[:-3].rstrip() + "…"
    return text


def append_log_line(buffer, message: str, *, level: str = "INFO",
                    timestamp: Optional[str] = None) -> int:
    """Append one entry to a :class:`core.log_format.LogBuffer`.

    Thin pass-through so every panel logs through the same
    newline-safe path. Returns the number of physical lines added.
    """
    return buffer.append(message, level=level, timestamp=timestamp)


# ---------------------------------------------------------------------------
# c4d-bound widget builders
# ---------------------------------------------------------------------------


if _C4D_AVAILABLE:

    def add_section_title(dialog, title: str, *, id_: int = 0) -> None:
        """A bold-ish section heading row inside the current group."""
        dialog.AddStaticText(
            id_, c4d.BFH_SCALEFIT, name=format_section_title(title),
        )

    def add_status_label(dialog, widget_id: int, status, message: str) -> None:
        """Set a static-text widget to a standard status string. The
        widget must already exist (created in CreateLayout)."""
        dialog.SetString(widget_id, format_status_label(status, message))

    def add_warning_box(dialog, widget_id: int, message: str, *,
                        status=Status.WARN) -> None:
        """Render a boxed warning into an existing multi-line widget."""
        dialog.SetString(widget_id, format_warning_box(message, status=status))

    def add_compact_separator(dialog, *, id_: int = 0) -> None:
        dialog.AddStaticText(id_, c4d.BFH_SCALEFIT, name=compact_separator())

    def add_button_row(dialog, buttons: Sequence[Tuple[int, str]], *,
                       group_id: int = 0) -> None:
        """Lay out a horizontal row of buttons.

        ``buttons`` is a sequence of ``(widget_id, label)``. Labels are
        normalised through :func:`normalize_button_label`."""
        cols = max(1, len(buttons))
        dialog.GroupBegin(group_id, c4d.BFH_SCALEFIT, cols=cols, rows=1)
        for wid, label in buttons:
            dialog.AddButton(
                wid, c4d.BFH_SCALEFIT, name=normalize_button_label(label),
            )
        dialog.GroupEnd()

    def add_path_selector(dialog, *, label: str, edit_id: int,
                         button_id: int, label_id: int = 0) -> None:
        """A ``[label] [edit field] [Browse…]`` row."""
        dialog.GroupBegin(0, c4d.BFH_SCALEFIT, cols=3, rows=1)
        dialog.AddStaticText(label_id, c4d.BFH_LEFT, name=label)
        dialog.AddEditText(edit_id, c4d.BFH_SCALEFIT)
        dialog.AddButton(button_id, c4d.BFH_RIGHT,
                        name=normalize_button_label("Browse…"))
        dialog.GroupEnd()

    def pick_path(*, title: str = "Choose", save: bool = False) -> str:
        """Open a file picker and return the chosen path (or "")."""
        flags = c4d.FILESELECTTYPE_ANYTHING
        mode = c4d.FILESELECT_SAVE if save else c4d.FILESELECT_LOAD
        result = storage.LoadDialog(type=flags, title=title, flags=mode)
        return result or ""

else:  # pragma: no cover — non-C4D import path

    def _needs_c4d(*_args, **_kwargs):
        raise RuntimeError(
            "ui_helpers widget builders require Cinema 4D; the pure "
            "formatters (status_prefix, format_status_label, …) work "
            "everywhere."
        )

    add_section_title = _needs_c4d  # type: ignore
    add_status_label = _needs_c4d  # type: ignore
    add_warning_box = _needs_c4d  # type: ignore
    add_compact_separator = _needs_c4d  # type: ignore
    add_button_row = _needs_c4d  # type: ignore
    add_path_selector = _needs_c4d  # type: ignore
    pick_path = _needs_c4d  # type: ignore
