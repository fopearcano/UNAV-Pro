# UNAV Pro — Guided Tour Chapters

Reference for `unav_pro/presentation/chapters.py`.

For the milestone overview see
[`V3_8_EXHIBITION_WORKFLOWS.md`](V3_8_EXHIBITION_WORKFLOWS.md).

---

## 1. The chapter shape

```python
@dataclass
class Chapter:
    chapter_id: str               # immutable, auto-uuid by default
    title: str
    narration: str                # spoken aloud
    presenter_notes: str          # off-script
    step_ids: List[str]           # references to v3.3 PresentationStep ids
    estimated_duration_seconds: float
    overlay_flags: Dict[str, bool]
    science_flags: Dict[str, bool]
    highlighted_annotation_indices: List[int]
    tags: List[str]
```

A chapter never embeds steps directly — it
references them by id. The v3.3
`PresentationSequence` stays the single source of
truth for step content; the chapter layer is a
*narrative wrapper* on top.

## 2. ChapteredPresentation

```python
@dataclass
class ChapteredPresentation:
    presentation_id: str          # references v3.3 PresentationManager row
    title: str
    description: str
    chapters: List[Chapter]
    schema_version: int           # v3.8 ships 1
    created_at_iso: str
    updated_at_iso: str
```

Top-level document. Stable JSON I/O. Validation
catches duplicate chapter ids + over-cap chapter
counts (`MAX_CHAPTERS_PER_PRESENTATION = 64`).

## 3. Building from groups

```python
from presentation import chapters_from_step_groups

chaptered = chapters_from_step_groups(
    presentation_id="voyager-tour",
    title="Voyager Tour",
    groups=[
        ("Intro", ["step-a", "step-b"]),
        ("Saturn", ["step-c", "step-d", "step-e"]),
        ("Outro", ["step-f"]),
    ],
    durations=[60.0, 240.0, 30.0],
)
```

The dialog's *Auto-Group Steps* button calls this
helper after the presenter assigns chapter
boundaries.

## 4. Coverage check

```python
sequence_step_ids = [s.step_id for s in mission_sequence.steps]
report = chaptered.coverage_against_sequence(
    step_ids=sequence_step_ids,
)
print(report["covered"])      # step ids referenced by some chapter
print(report["uncovered"])    # step ids no chapter references
print(report["unknown"])      # chapter step ids not in the sequence
print(report["fully_covered"])
```

The coverage check is purely advisory — the
runtime layer doesn't refuse to run when chapters
don't cover every step. Use the report to spot
typos + steps you forgot to put into a chapter.

## 5. Reordering

```python
chaptered.move_chapter("ch-saturn", new_index=0)
```

`chapter_id` is immutable, so external state
(presenter notes, marker bindings) survives
reorder.

## 6. Step-id reverse map

```python
mapping = chaptered.step_id_to_chapter()
# → {"step-a": "ch-intro", "step-b": "ch-intro", ...}
```

The runtime state uses this to know which chapter
the current step belongs to.

## 7. Determinism

Same chapters + same step lists + same flags ⇒
identical JSON output, byte for byte. Tests
assert this directly.

## 8. Tests

* `test_v38_chapters` — round-trip,
  validation, sequence coverage, step-id reverse
  map, reorder.
