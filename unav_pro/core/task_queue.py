"""v3.0 lightweight task queue.

A pure-Python, **single-threaded** queue of plug-in operations.
The dialog hands long-running operations (build index, sync
huge sector, bake a long timeline) to the queue; the queue
walks them step-by-step on the main thread inside a Cinema 4D
``MessageData`` tick or under explicit ``queue.run_next()``
calls.

Why no threads? Cinema 4D's Python API is **not thread-safe**.
The Maxon docs are explicit: scene mutation, undo, redraws,
and selection touches must happen on the main thread. UNAV's
v0.1 → v2.5 baseline has always honoured that. v3.0 keeps
that contract and adds *cooperative* yielding instead of
*preemptive* threading.

What the queue gives you:

* A first-class ``Task`` record with status, progress, and a
  cancellation flag. The c4d-bound caller renders it in the
  status panel.
* Cooperative cancellation: the runner checks
  ``task.is_cancelled()`` between steps. Long c4d-bound
  operations call ``task.report_progress(...)`` and yield.
* Snapshotting: ``queue.snapshot()`` returns a stable view
  of all tasks the dialog can render without touching the
  internal list (so UI ticks and queue runs don't race).
* No threading, no asyncio, no signals. Just a list and a
  monotonic clock.

The queue is **opt-in**: existing v2.5 call sites continue
to drive operations directly. Long-running paths (e.g. a
multi-page sync or a frame-aware bake) wrap themselves as
``Task`` objects and run inside the queue.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any, Callable, Dict, Iterable, List, Optional, Sequence,
)

from core.logging_util import get_logger

_log = get_logger("core.task_queue")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TaskStatus(str, Enum):
    """Lifecycle states a task moves through.

    Inheriting from ``str`` so dataclass equality + JSON dump
    just work (the dialog stores recent task summaries in the
    project sidecar for the diagnostics panel)."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset(
    [TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED],
)


# ---------------------------------------------------------------------------
# Task record
# ---------------------------------------------------------------------------


_TASK_ID_COUNTER: int = 0


def _next_task_id() -> int:
    """Process-local monotonic counter. The queue uses these
    as a stable display ID; not for cross-session persistence."""
    global _TASK_ID_COUNTER
    _TASK_ID_COUNTER += 1
    return _TASK_ID_COUNTER


def _reset_task_id_counter() -> None:
    """Test helper. Resets the counter so test ordering is
    deterministic."""
    global _TASK_ID_COUNTER
    _TASK_ID_COUNTER = 0


@dataclass
class Task:
    """One queued operation.

    The runner is the long-running step body — it receives the
    ``Task`` itself so it can report progress + check
    cancellation. The runner returns the operation's *result*
    (any value) on success; raising stores the exception and
    moves the task to ``FAILED``.

    The runner is permitted to call ``task.report_progress``
    repeatedly; the queue uses the latest reported value when
    the dialog asks for the snapshot.
    """

    id: int = field(default_factory=_next_task_id)
    kind: str = "task"
    label: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    message: str = ""
    runner: Optional[Callable[["Task"], Any]] = None
    result: Any = None
    error: Optional[str] = None
    enqueued_at: float = field(default_factory=time.monotonic)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    _cancel_requested: bool = False

    # ---------------------------------------------------- predicates
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def is_cancelled(self) -> bool:
        """Runners poll this between steps. ``True`` once the
        dialog has called ``request_cancel`` (or the task's
        own kill switch flipped). Runners that respect this
        return early; the queue then transitions the task to
        ``CANCELLED`` if the runner exits cleanly."""
        return bool(self._cancel_requested)

    # ---------------------------------------------------- mutation
    def request_cancel(self) -> None:
        """Mark cancellation requested. Idempotent. Has no
        effect on terminal tasks."""
        if self.is_terminal():
            return
        self._cancel_requested = True

    def report_progress(
        self, fraction: float, message: str = "",
    ) -> None:
        """Long-running runners call this between work units.

        ``fraction`` clamps to [0, 1]. Empty ``message``
        leaves the existing ``message`` text untouched so the
        dialog can keep a one-shot status line stable across
        many progress updates.
        """
        try:
            f = float(fraction)
        except (TypeError, ValueError):
            f = 0.0
        if f < 0.0:
            f = 0.0
        elif f > 1.0:
            f = 1.0
        self.progress = f
        if message:
            self.message = str(message)

    # ---------------------------------------------------- timing
    @property
    def elapsed_seconds(self) -> float:
        """Wall time the task has been running (or ran). 0 for
        pending tasks, monotonic-now for running tasks, total
        elapsed for terminal tasks."""
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        return max(0.0, end - self.started_at)

    # ---------------------------------------------------- display
    def short_summary(self) -> str:
        """One-line text the dialog status panel renders."""
        bits = [f"#{self.id}", self.kind, self.status.value]
        if self.label:
            bits.append(f"'{self.label}'")
        if self.status is TaskStatus.RUNNING:
            bits.append(f"{int(round(self.progress * 100))}%")
        if self.message:
            bits.append(self.message)
        return " · ".join(bits)


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


@dataclass
class QueueStats:
    enqueued: int = 0
    started: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0


class TaskQueue:
    """FIFO queue of ``Task`` records.

    The queue is **single-threaded**. ``run_next()`` runs at
    most one task to completion (or cancellation) and returns;
    callers from a Cinema 4D ``MessageData`` tick can call it
    inside the message loop to drain the queue cooperatively.

    Tasks remain in the queue after they're done (so the
    dialog can render a "recent tasks" history). Use
    ``prune_terminal()`` to drop them.
    """

    def __init__(self, *, history_capacity: int = 64) -> None:
        if history_capacity <= 0:
            raise ValueError("history_capacity must be > 0")
        self._tasks: List[Task] = []
        self._history_capacity = int(history_capacity)
        self.stats = QueueStats()

    # ---------------------------------------------------- diagnostics
    @property
    def history_capacity(self) -> int:
        return self._history_capacity

    def __len__(self) -> int:
        return len(self._tasks)

    def snapshot(self) -> List[Task]:
        """Return a *shallow* copy of the queue. Safe for the
        UI to iterate while the queue is being mutated by a
        runner."""
        return list(self._tasks)

    def pending(self) -> List[Task]:
        return [t for t in self._tasks if t.status is TaskStatus.PENDING]

    def running(self) -> List[Task]:
        return [t for t in self._tasks if t.status is TaskStatus.RUNNING]

    def terminal(self) -> List[Task]:
        return [t for t in self._tasks if t.is_terminal()]

    def find(self, task_id: int) -> Optional[Task]:
        for t in self._tasks:
            if t.id == task_id:
                return t
        return None

    # ---------------------------------------------------- enqueue
    def enqueue(
        self,
        runner: Callable[[Task], Any],
        *,
        kind: str = "task",
        label: str = "",
    ) -> Task:
        """Append a fresh task at the tail of the queue. The
        task is returned so the caller can store its ID and
        observe progress."""
        if not callable(runner):
            raise TypeError("runner must be callable")
        task = Task(
            kind=str(kind or "task"),
            label=str(label or ""),
            runner=runner,
        )
        self._tasks.append(task)
        self.stats.enqueued += 1
        # Trim history when overflowing; only drop terminal
        # tasks from the head — never drop pending or running
        # work.
        self._trim_history()
        return task

    # ---------------------------------------------------- cancel
    def request_cancel(self, task_id: int) -> bool:
        """Forward a cancellation request to a task. Returns
        True iff the task was found and was non-terminal."""
        task = self.find(task_id)
        if task is None or task.is_terminal():
            return False
        task.request_cancel()
        # Pending tasks haven't started → mark cancelled now.
        if task.status is TaskStatus.PENDING:
            task.status = TaskStatus.CANCELLED
            task.finished_at = time.monotonic()
            self.stats.cancelled += 1
        return True

    def cancel_all_pending(self) -> int:
        """Drop every pending task. Returns the count
        cancelled. Used when the user hits 'Reset queue' or
        switches documents."""
        n = 0
        for task in self._tasks:
            if task.status is TaskStatus.PENDING:
                task.request_cancel()
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.monotonic()
                self.stats.cancelled += 1
                n += 1
        return n

    # ---------------------------------------------------- run
    def run_next(self) -> Optional[Task]:
        """Run the next pending task to completion (or
        cancellation). Returns the task that ran, or ``None``
        if no pending tasks remain.

        The runner is invoked synchronously. If it raises, the
        task transitions to ``FAILED`` and the exception is
        recorded in ``task.error``; the exception is **not**
        re-raised — the queue must not crash the dialog if a
        single task explodes.
        """
        task = self._first_pending()
        if task is None:
            return None
        return self._execute(task)

    def run_all(self, *, max_iterations: int = 1024) -> int:
        """Drain the queue. Returns the count of tasks that
        ran. ``max_iterations`` is a guard against runners that
        somehow re-enqueue themselves; the v3.0 baseline never
        does, but the cap keeps the queue safe under future
        misuse.
        """
        n = 0
        while n < max_iterations:
            task = self.run_next()
            if task is None:
                break
            n += 1
        return n

    # ---------------------------------------------------- maintenance
    def prune_terminal(self) -> int:
        """Drop every terminal task. Returns the count
        removed."""
        before = len(self._tasks)
        self._tasks = [t for t in self._tasks if not t.is_terminal()]
        return before - len(self._tasks)

    # ---------------------------------------------------- internals
    def _first_pending(self) -> Optional[Task]:
        for t in self._tasks:
            if t.status is TaskStatus.PENDING:
                return t
        return None

    def _execute(self, task: Task) -> Task:
        # Cooperative cancel before we even start.
        if task.is_cancelled():
            task.status = TaskStatus.CANCELLED
            task.finished_at = time.monotonic()
            self.stats.cancelled += 1
            return task
        task.status = TaskStatus.RUNNING
        task.started_at = time.monotonic()
        self.stats.started += 1
        try:
            assert task.runner is not None
            result = task.runner(task)
        except Exception as exc:  # noqa: BLE001 — task boundary
            task.error = repr(exc)
            task.status = TaskStatus.FAILED
            task.finished_at = time.monotonic()
            self.stats.failed += 1
            _log.exception("Task %s failed: %s", task.short_summary(), exc)
            return task
        task.finished_at = time.monotonic()
        if task.is_cancelled():
            task.status = TaskStatus.CANCELLED
            self.stats.cancelled += 1
            return task
        task.result = result
        task.status = TaskStatus.DONE
        task.progress = 1.0
        self.stats.completed += 1
        return task

    def _trim_history(self) -> None:
        """Drop the oldest *terminal* tasks from the head when
        the total task count exceeds the history capacity.
        Pending and running tasks are never dropped."""
        if len(self._tasks) <= self._history_capacity:
            return
        # Walk forward, dropping terminal tasks until under
        # capacity. Stop the moment we hit a non-terminal task
        # so order is preserved.
        kept: List[Task] = []
        dropped = 0
        target = max(0, len(self._tasks) - self._history_capacity)
        for t in self._tasks:
            if dropped < target and t.is_terminal():
                dropped += 1
                continue
            kept.append(t)
        self._tasks = kept


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------


#: Global queue the dialog wires its long-running operations
#: into. Tests usually construct a local queue.
GLOBAL_TASK_QUEUE = TaskQueue()


# ---------------------------------------------------------------------------
# Convenience builders
# ---------------------------------------------------------------------------


def make_chunked_task(
    *,
    kind: str,
    label: str,
    units: Sequence[Any],
    step: Callable[[Any, Task], None],
    final: Optional[Callable[[Task], Any]] = None,
) -> Callable[[Task], Any]:
    """Return a runner that walks ``units`` one step at a time,
    reporting progress between steps and honouring cancellation.

    Useful for paged scene-sync: pass the list of pages as
    ``units`` and a per-page builder as ``step``. The runner
    returns whatever ``final`` returns (or ``None``).

    Example::

        def step(page, task):
            apply_page_to_scene(page)

        runner = make_chunked_task(
            kind="sync_paged",
            label="Sync visible sector (paged)",
            units=list(pages),
            step=step,
        )
        queue.enqueue(runner, kind="sync_paged", label="…")
    """

    units_list = list(units)
    n = len(units_list)

    def _runner(task: Task) -> Any:
        if n == 0:
            task.report_progress(1.0, f"{label} (empty)")
            return None
        for i, unit in enumerate(units_list):
            if task.is_cancelled():
                return None
            step(unit, task)
            task.report_progress(
                (i + 1) / n,
                f"{label}: {i + 1}/{n}",
            )
        if final is not None:
            return final(task)
        return None

    _runner.__name__ = f"chunked_runner[{kind}]"
    return _runner
