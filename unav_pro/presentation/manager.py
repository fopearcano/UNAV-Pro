"""v3.3 presentation storage manager.

In-memory + on-disk store for ``PresentationSequence``
documents. Mirrors the v1.4 ``MissionManager`` shape so
the dialog code can drive presentations the same way it
already drives missions:

::

    pm = PresentationManager(directory="…/presentations/")
    pres = PresentationSequence(title="My Talk")
    pm.create(pres)
    pm.list_all()
    pm.load(pres.presentation_id)

Atomic writes (temp + rename); refuses duplicate ids;
fail-closed on disk corruption.

Pure stdlib + JSON-serialisable. No Cinema 4D imports.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Iterable, List, Optional

from .presentation_sequence import (
    PresentationError,
    PresentationSequence,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


PRESENTATIONS_DIRNAME: str = "presentations"
PRESENTATIONS_INDEX_FILENAME: str = "presentations_index.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def default_presentations_dir() -> str:
    """Per-user presentations directory. Lives next to
    ``config.json``."""
    from core.config import default_config_dir
    return os.path.join(default_config_dir(), PRESENTATIONS_DIRNAME)


def _index_path(presentations_dir: str) -> str:
    return os.path.join(presentations_dir, PRESENTATIONS_INDEX_FILENAME)


def _presentation_path(presentations_dir: str, pres_id: str) -> str:
    return os.path.join(presentations_dir, f"{pres_id}.json")


def _safe_write(path: str, body: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
        if not body.endswith("\n"):
            fh.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class PresentationManager:
    """Disk-backed CRUD store for presentations.

    Concurrency: single-threaded; the v3.3 dialog drives
    one writer at a time. If two C4D sessions write at
    once, last-writer-wins (same convention as the v1.4
    MissionManager).
    """

    def __init__(self, presentations_dir: Optional[str] = None) -> None:
        self._dir: str = presentations_dir or default_presentations_dir()
        self._presentations: Dict[str, PresentationSequence] = {}
        self._order: List[str] = []
        self.reload()

    # ---------------------------------------------------- properties
    @property
    def presentations_dir(self) -> str:
        return self._dir

    def __len__(self) -> int:
        return len(self._order)

    def __contains__(self, pres_id: str) -> bool:
        return pres_id in self._presentations

    # ---------------------------------------------------- introspection
    def list_all(self) -> List[PresentationSequence]:
        """Return presentations in display order."""
        return [
            self._presentations[pid] for pid in self._order
            if pid in self._presentations
        ]

    def list_ids(self) -> List[str]:
        return [pid for pid in self._order if pid in self._presentations]

    def get(self, pres_id: str) -> Optional[PresentationSequence]:
        return self._presentations.get(pres_id)

    # ---------------------------------------------------- CRUD
    def create(
        self, presentation: PresentationSequence,
    ) -> PresentationSequence:
        if presentation.presentation_id in self._presentations:
            raise PresentationError(
                f"presentation_id '{presentation.presentation_id}' "
                "already exists",
            )
        errs = presentation.validate()
        if errs:
            raise PresentationError(
                "presentation failed validation:\n  - "
                + "\n  - ".join(errs)
            )
        self._presentations[presentation.presentation_id] = presentation
        self._order.append(presentation.presentation_id)
        self._save_presentation(presentation)
        self._save_index()
        return presentation

    def update(
        self, presentation: PresentationSequence,
    ) -> PresentationSequence:
        if presentation.presentation_id not in self._presentations:
            raise KeyError(
                f"unknown presentation_id "
                f"'{presentation.presentation_id}'",
            )
        errs = presentation.validate()
        if errs:
            raise PresentationError(
                "presentation failed validation:\n  - "
                + "\n  - ".join(errs)
            )
        presentation.touch()
        self._presentations[presentation.presentation_id] = presentation
        self._save_presentation(presentation)
        self._save_index()
        return presentation

    def delete(self, pres_id: str) -> bool:
        if pres_id not in self._presentations:
            return False
        del self._presentations[pres_id]
        if pres_id in self._order:
            self._order.remove(pres_id)
        path = _presentation_path(self._dir, pres_id)
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
        self._save_index()
        return True

    # ---------------------------------------------------- I/O
    def reload(self) -> None:
        """Re-read the index + every presentation from disk.
        Defensive: missing files clear the in-memory store
        rather than raising."""
        self._presentations = {}
        self._order = []
        if not os.path.isdir(self._dir):
            return
        index_path = _index_path(self._dir)
        order: List[str] = []
        if os.path.isfile(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    order = [
                        str(x) for x in (data.get("order") or [])
                    ]
            except (OSError, json.JSONDecodeError):
                order = []
        # Load every JSON file that exists, even if not in
        # the order list — corruption-resistant.
        try:
            files = sorted(os.listdir(self._dir))
        except OSError:
            files = []
        loaded: Dict[str, PresentationSequence] = {}
        for fname in files:
            if not fname.endswith(".json"):
                continue
            if fname == PRESENTATIONS_INDEX_FILENAME:
                continue
            path = os.path.join(self._dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    pres = PresentationSequence.from_json(fh.read())
            except (OSError, PresentationError):
                continue
            loaded[pres.presentation_id] = pres
        # Apply the index order; tail any unknown files at
        # the end alphabetically.
        final_order: List[str] = []
        for pid in order:
            if pid in loaded and pid not in final_order:
                final_order.append(pid)
        for pid in sorted(loaded):
            if pid not in final_order:
                final_order.append(pid)
        self._presentations = loaded
        self._order = final_order

    def _save_presentation(
        self, presentation: PresentationSequence,
    ) -> None:
        path = _presentation_path(
            self._dir, presentation.presentation_id,
        )
        _safe_write(path, presentation.to_json())

    def _save_index(self) -> None:
        index = {"order": list(self._order)}
        _safe_write(
            _index_path(self._dir),
            json.dumps(index, indent=2, ensure_ascii=False),
        )

    # ---------------------------------------------------- ordering
    def reorder(self, pres_id: str, new_index: int) -> bool:
        if pres_id not in self._presentations:
            return False
        if pres_id not in self._order:
            return False
        new_index = max(0, min(len(self._order) - 1, int(new_index)))
        cur = self._order.index(pres_id)
        if cur == new_index:
            return False
        self._order.pop(cur)
        self._order.insert(new_index, pres_id)
        self._save_index()
        return True
