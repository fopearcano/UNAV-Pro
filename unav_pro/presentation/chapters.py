"""v3.8 guided-tour chapters.

A *chapter* is a named span of v3.3 presentation
steps the artist groups into a coherent narrative
beat: an intro, an "approach Saturn", an outro.
Chapters can carry their own:

* title + presenter narration;
* presenter-only notes;
* highlighted overlay / science layer flags that
  apply across the whole chapter (in addition to
  the per-step flags);
* annotation indices to emphasise across the chapter;
* an estimated duration the dialog renders into
  the cue sheet.

A ``ChapteredPresentation`` wraps a v3.3
``PresentationSequence`` with an ordered list of
``Chapter`` records. Pure stdlib + JSON-
serialisable; no Cinema 4D imports.

Schema policy
-------------

* ``schema_version`` bumps when the on-disk shape
  changes incompatibly. v3.8 ships ``v=1``.
* Loaders accept missing fields (defaulted) but
  reject unknown ``schema_version`` fail-closed.
* Chapters are addressed by zero-based index.
  Every chapter carries an immutable
  ``chapter_id`` so external state survives
  reorder.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


CHAPTER_SCHEMA_VERSION: int = 1

#: Hard cap on chapters per presentation. The v3.3
#: presentation cap is 200 steps; chapters are
#: typically 5–20 per show.
MAX_CHAPTERS_PER_PRESENTATION: int = 64


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ChapterError(ValueError):
    """Raised on chapter schema / I/O failures."""


# ---------------------------------------------------------------------------
# Chapter
# ---------------------------------------------------------------------------


def _new_chapter_id() -> str:
    return f"ch-{uuid.uuid4().hex[:12]}"


@dataclass
class Chapter:
    """One chapter in a guided tour.

    ``step_ids`` references v3.3 ``PresentationStep``
    ids. The chapter spans those steps in order; the
    runtime state advances through them inside the
    chapter.

    ``overlay_flags`` / ``science_flags`` are merged
    on top of each step's per-step flags during the
    chapter, so a chapter can keep "distance rings"
    visible across every one of its steps without
    repeating itself.
    """

    chapter_id: str = field(default_factory=_new_chapter_id)
    title: str = ""
    narration: str = ""
    presenter_notes: str = ""
    step_ids: List[str] = field(default_factory=list)
    estimated_duration_seconds: float = 0.0
    overlay_flags: Dict[str, bool] = field(default_factory=dict)
    science_flags: Dict[str, bool] = field(default_factory=dict)
    highlighted_annotation_indices: List[int] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.estimated_duration_seconds < 0:
            raise ChapterError(
                "estimated_duration_seconds must be >= 0"
            )
        if self.tags:
            self.tags = [
                str(t).strip().lower() for t in self.tags
                if str(t).strip()
            ]

    # ---------------------------------------------------- (de)ser
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "title": self.title,
            "narration": self.narration,
            "presenter_notes": self.presenter_notes,
            "step_ids": list(self.step_ids),
            "estimated_duration_seconds": float(
                self.estimated_duration_seconds,
            ),
            "overlay_flags": dict(self.overlay_flags),
            "science_flags": dict(self.science_flags),
            "highlighted_annotation_indices": list(
                self.highlighted_annotation_indices,
            ),
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "Chapter":
        if not isinstance(d, dict):
            raise ChapterError("chapter payload is not an object")
        return cls(
            chapter_id=str(d.get("chapter_id") or _new_chapter_id()),
            title=str(d.get("title") or ""),
            narration=str(d.get("narration") or ""),
            presenter_notes=str(d.get("presenter_notes") or ""),
            step_ids=[str(s) for s in (d.get("step_ids") or [])],
            estimated_duration_seconds=float(
                d.get("estimated_duration_seconds", 0.0) or 0.0,
            ),
            overlay_flags={
                str(k): bool(v)
                for k, v in (d.get("overlay_flags") or {}).items()
            },
            science_flags={
                str(k): bool(v)
                for k, v in (d.get("science_flags") or {}).items()
            },
            highlighted_annotation_indices=[
                int(i) for i in (
                    d.get("highlighted_annotation_indices") or []
                )
            ],
            tags=[str(t) for t in (d.get("tags") or [])],
        )

    # ---------------------------------------------------- helpers
    def step_count(self) -> int:
        return len(self.step_ids)

    def is_empty(self) -> bool:
        return not self.step_ids

    def short_summary(self) -> str:
        bits = []
        if self.title:
            bits.append(self.title)
        bits.append(f"{self.step_count()} step(s)")
        if self.estimated_duration_seconds:
            bits.append(f"~{self.estimated_duration_seconds:.0f}s")
        return " · ".join(bits)


# ---------------------------------------------------------------------------
# ChapteredPresentation
# ---------------------------------------------------------------------------


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class ChapteredPresentation:
    """Top-level wrapper bundling a v3.3
    ``PresentationSequence`` reference (by id) with
    an ordered list of chapters.

    The presentation itself isn't embedded — the
    ``presentation_id`` references a row in the v3.3
    ``PresentationManager`` store. This keeps the
    chapter document small + portable.
    """

    presentation_id: str = ""
    title: str = "Untitled Tour"
    description: str = ""
    chapters: List[Chapter] = field(default_factory=list)
    schema_version: int = CHAPTER_SCHEMA_VERSION
    created_at_iso: str = ""
    updated_at_iso: str = ""

    # ---------------------------------------------------- size
    def __len__(self) -> int:
        return len(self.chapters)

    def chapter_count(self) -> int:
        return len(self.chapters)

    # ---------------------------------------------------- timestamps
    def touch(self) -> None:
        self.updated_at_iso = _utc_iso()

    # ---------------------------------------------------- (de)ser
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "presentation_id": self.presentation_id,
            "title": self.title,
            "description": self.description,
            "chapters": [c.to_dict() for c in self.chapters],
            "created_at_iso": self.created_at_iso,
            "updated_at_iso": self.updated_at_iso,
        }

    @classmethod
    def from_dict(
        cls, d: Optional[Dict[str, Any]],
    ) -> "ChapteredPresentation":
        if not isinstance(d, dict):
            raise ChapterError(
                "chaptered-presentation payload is not an object"
            )
        version = d.get("schema_version", CHAPTER_SCHEMA_VERSION)
        try:
            version_i = int(version)
        except (TypeError, ValueError) as exc:
            raise ChapterError(
                f"chapter schema_version not an integer: {version!r}",
            ) from exc
        if version_i > CHAPTER_SCHEMA_VERSION:
            raise ChapterError(
                f"chapter schema_version {version_i} is newer "
                f"than this build understands "
                f"({CHAPTER_SCHEMA_VERSION})."
            )
        chapters_in = d.get("chapters") or []
        if not isinstance(chapters_in, list):
            raise ChapterError("chapters must be a list")
        return cls(
            schema_version=version_i,
            presentation_id=str(d.get("presentation_id") or ""),
            title=str(d.get("title") or "Untitled Tour"),
            description=str(d.get("description") or ""),
            chapters=[
                Chapter.from_dict(c) for c in chapters_in
                if isinstance(c, dict)
            ],
            created_at_iso=str(d.get("created_at_iso") or ""),
            updated_at_iso=str(d.get("updated_at_iso") or ""),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(), indent=indent, ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, text: str) -> "ChapteredPresentation":
        try:
            d = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ChapterError(
                f"chapter JSON parse failed: {exc}",
            ) from exc
        return cls.from_dict(d)

    # ---------------------------------------------------- mutation
    def add_chapter(self, chapter: Chapter) -> Chapter:
        if len(self.chapters) >= MAX_CHAPTERS_PER_PRESENTATION:
            raise ChapterError(
                f"chapter cap exceeded "
                f"({MAX_CHAPTERS_PER_PRESENTATION})"
            )
        if any(c.chapter_id == chapter.chapter_id for c in self.chapters):
            raise ChapterError(
                f"duplicate chapter_id: {chapter.chapter_id}"
            )
        self.chapters.append(chapter)
        return chapter

    def remove_chapter(self, chapter_id: str) -> bool:
        before = len(self.chapters)
        self.chapters = [
            c for c in self.chapters if c.chapter_id != chapter_id
        ]
        return len(self.chapters) != before

    def find_chapter(self, chapter_id: str) -> Optional[Chapter]:
        for c in self.chapters:
            if c.chapter_id == chapter_id:
                return c
        return None

    def find_chapter_index(self, chapter_id: str) -> int:
        for i, c in enumerate(self.chapters):
            if c.chapter_id == chapter_id:
                return i
        return -1

    def move_chapter(
        self, chapter_id: str, new_index: int,
    ) -> bool:
        idx = self.find_chapter_index(chapter_id)
        if idx < 0:
            return False
        new_index = max(0, min(len(self.chapters) - 1, int(new_index)))
        if idx == new_index:
            return False
        chapter = self.chapters.pop(idx)
        self.chapters.insert(new_index, chapter)
        return True

    # ---------------------------------------------------- validation
    def validate(self) -> List[str]:
        errs: List[str] = []
        if self.schema_version != CHAPTER_SCHEMA_VERSION:
            errs.append(
                f"schema_version is {self.schema_version}; this build "
                f"writes {CHAPTER_SCHEMA_VERSION}."
            )
        seen: set = set()
        for i, chapter in enumerate(self.chapters):
            if not chapter.chapter_id:
                errs.append(f"chapter #{i}: chapter_id is empty")
                continue
            if chapter.chapter_id in seen:
                errs.append(
                    f"chapter #{i}: duplicate chapter_id "
                    f"'{chapter.chapter_id}'"
                )
            seen.add(chapter.chapter_id)
        if len(self.chapters) > MAX_CHAPTERS_PER_PRESENTATION:
            errs.append(
                f"chapter count {len(self.chapters)} exceeds cap "
                f"({MAX_CHAPTERS_PER_PRESENTATION})"
            )
        return errs

    # ---------------------------------------------------- summary
    def total_estimated_duration_seconds(self) -> float:
        return sum(c.estimated_duration_seconds for c in self.chapters)

    def step_id_to_chapter(self) -> Dict[str, str]:
        """Reverse map: ``{step_id: chapter_id}``. The
        runtime state uses this to know which chapter
        the current step belongs to. Steps that aren't
        referenced by any chapter map to ``""``."""
        out: Dict[str, str] = {}
        for chapter in self.chapters:
            for step_id in chapter.step_ids:
                if step_id and step_id not in out:
                    out[step_id] = chapter.chapter_id
        return out

    def chapter_for_step(self, step_id: str) -> Optional[Chapter]:
        """Return the first chapter that includes
        ``step_id``, or ``None``."""
        for chapter in self.chapters:
            if step_id in chapter.step_ids:
                return chapter
        return None

    # ---------------------------------------------------- coverage
    def coverage_against_sequence(
        self, *, step_ids: Sequence[str],
    ) -> Dict[str, Any]:
        """Compare the chapters' ``step_ids`` against
        the sequence's actual step ids and report:

        * ``covered`` — step ids present in some
          chapter.
        * ``uncovered`` — step ids that no chapter
          references (orphans).
        * ``unknown`` — step ids the chapters
          reference that aren't in the sequence
          (typo / stale).
        """
        sequence_set = set(step_ids)
        chapter_ids: List[str] = []
        for c in self.chapters:
            for s in c.step_ids:
                if s:
                    chapter_ids.append(s)
        chapter_set = set(chapter_ids)
        covered = sorted(sequence_set & chapter_set)
        uncovered = sorted(sequence_set - chapter_set)
        unknown = sorted(chapter_set - sequence_set)
        return {
            "covered": covered,
            "uncovered": uncovered,
            "unknown": unknown,
            "fully_covered": not uncovered,
        }


# ---------------------------------------------------------------------------
# Composition helper
# ---------------------------------------------------------------------------


def chapters_from_step_groups(
    *,
    presentation_id: str,
    title: str = "Tour",
    groups: Sequence[Tuple[str, Sequence[str]]],
    durations: Optional[Sequence[float]] = None,
) -> ChapteredPresentation:
    """Convenience builder: hand in a list of
    ``(chapter_title, [step_id, ...])`` tuples and
    optionally a parallel list of estimated durations,
    return a fully-populated ``ChapteredPresentation``.

    Used by the dialog's *Auto-Group Steps* button to
    seed chapters from a v3.3 sequence.
    """
    out = ChapteredPresentation(
        presentation_id=presentation_id,
        title=title,
    )
    durations = list(durations) if durations is not None else []
    for i, (chapter_title, step_ids) in enumerate(groups):
        chapter = Chapter(
            title=chapter_title,
            step_ids=[str(s) for s in step_ids],
            estimated_duration_seconds=(
                float(durations[i]) if i < len(durations) else 0.0
            ),
        )
        out.add_chapter(chapter)
    return out
