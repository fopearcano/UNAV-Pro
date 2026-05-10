"""v3.0 task-queue tests.

Covers ``core/task_queue.py``:

* Task lifecycle (pending → running → done / failed /
  cancelled).
* Cooperative cancellation (pending vs running).
* Progress reporting clamps + message handling.
* Runner-error containment (failed tasks don't propagate).
* ``make_chunked_task`` helper builds a runner that walks
  units, reports progress, and honours cancellation.
* Queue stats accumulate correctly.
"""

from __future__ import annotations

import pytest

from core.task_queue import (
    GLOBAL_TASK_QUEUE,
    TERMINAL_STATUSES,
    Task,
    TaskQueue,
    TaskStatus,
    _reset_task_id_counter,
    make_chunked_task,
)


@pytest.fixture(autouse=True)
def _reset_ids():
    _reset_task_id_counter()


# ---------------------------------------------------------------------------
# Task lifecycle
# ---------------------------------------------------------------------------


def test_new_task_is_pending():
    t = Task(runner=lambda task: None)
    assert t.status is TaskStatus.PENDING
    assert t.is_terminal() is False


def test_task_runs_to_done():
    queue = TaskQueue()
    t = queue.enqueue(lambda task: 42, kind="test")
    queue.run_next()
    assert t.status is TaskStatus.DONE
    assert t.result == 42
    assert t.progress == 1.0


def test_task_runs_to_failed_on_exception():
    queue = TaskQueue()

    def boom(task):
        raise ValueError("oops")

    t = queue.enqueue(boom, kind="boom")
    queue.run_next()
    assert t.status is TaskStatus.FAILED
    assert t.error is not None
    assert "oops" in t.error


def test_task_runs_to_cancelled_when_pending():
    queue = TaskQueue()
    t = queue.enqueue(lambda task: 1, kind="will-cancel")
    cancelled = queue.request_cancel(t.id)
    assert cancelled is True
    assert t.status is TaskStatus.CANCELLED


def test_running_task_honours_cancellation_cooperatively():
    queue = TaskQueue()

    def runner(task):
        # Self-cancel inside the runner; queue should pick
        # this up after the runner returns.
        task.request_cancel()
        return None

    t = queue.enqueue(runner, kind="self-cancel")
    queue.run_next()
    assert t.status is TaskStatus.CANCELLED


def test_terminal_task_ignores_cancel():
    queue = TaskQueue()
    t = queue.enqueue(lambda task: 1, kind="done")
    queue.run_next()
    assert t.status is TaskStatus.DONE
    cancelled = queue.request_cancel(t.id)
    assert cancelled is False


# ---------------------------------------------------------------------------
# Progress reporting
# ---------------------------------------------------------------------------


def test_report_progress_clamps_to_unit_interval():
    t = Task()
    t.report_progress(2.5)
    assert t.progress == 1.0
    t.report_progress(-0.5)
    assert t.progress == 0.0


def test_report_progress_message_optional():
    t = Task()
    t.report_progress(0.5, "halfway")
    assert t.message == "halfway"
    # Empty message must NOT clobber the previous value.
    t.report_progress(0.6)
    assert t.message == "halfway"


def test_report_progress_handles_non_numeric():
    t = Task()
    t.report_progress("nope")  # type: ignore[arg-type]
    assert t.progress == 0.0


# ---------------------------------------------------------------------------
# Queue mechanics
# ---------------------------------------------------------------------------


def test_run_next_returns_none_when_empty():
    queue = TaskQueue()
    assert queue.run_next() is None


def test_run_all_drains_in_fifo_order():
    queue = TaskQueue()
    order = []
    queue.enqueue(lambda task: order.append(1), kind="a")
    queue.enqueue(lambda task: order.append(2), kind="b")
    queue.enqueue(lambda task: order.append(3), kind="c")
    n = queue.run_all()
    assert n == 3
    assert order == [1, 2, 3]


def test_cancel_all_pending_drops_only_pending():
    queue = TaskQueue()
    queue.enqueue(lambda task: 1, kind="a")
    queue.enqueue(lambda task: 2, kind="b")
    n = queue.cancel_all_pending()
    assert n == 2
    assert all(t.status is TaskStatus.CANCELLED for t in queue.snapshot())


def test_prune_terminal_drops_done_failed_cancelled():
    queue = TaskQueue()
    a = queue.enqueue(lambda task: 1, kind="ok")
    b = queue.enqueue(lambda task: 1 / 0, kind="boom")
    c = queue.enqueue(lambda task: 1, kind="will-cancel")
    queue.request_cancel(c.id)
    queue.run_all()
    n = queue.prune_terminal()
    assert n == 3
    assert len(queue) == 0


def test_snapshot_is_a_copy():
    queue = TaskQueue()
    queue.enqueue(lambda task: 1, kind="a")
    snap = queue.snapshot()
    snap.clear()
    assert len(queue) == 1


def test_queue_stats_accumulate():
    queue = TaskQueue()
    queue.enqueue(lambda task: 1, kind="a")
    queue.enqueue(lambda task: 1 / 0, kind="boom")
    queue.enqueue(lambda task: 1, kind="c")
    queue.cancel_all_pending()
    # Re-run after cancelling: nothing left to run.
    queue.run_all()
    assert queue.stats.enqueued == 3
    assert queue.stats.cancelled == 3


def test_queue_finds_by_id():
    queue = TaskQueue()
    t = queue.enqueue(lambda task: 1, kind="x")
    assert queue.find(t.id) is t
    assert queue.find(99999) is None


def test_queue_rejects_non_callable_runner():
    queue = TaskQueue()
    with pytest.raises(TypeError):
        queue.enqueue("not a callable", kind="bad")  # type: ignore[arg-type]


def test_queue_history_capacity_is_validated():
    with pytest.raises(ValueError):
        TaskQueue(history_capacity=0)


# ---------------------------------------------------------------------------
# make_chunked_task
# ---------------------------------------------------------------------------


def test_chunked_task_walks_units_in_order():
    seen = []
    runner = make_chunked_task(
        kind="walk", label="walking",
        units=["a", "b", "c"],
        step=lambda u, task: seen.append(u),
    )
    queue = TaskQueue()
    t = queue.enqueue(runner, kind="walk")
    queue.run_next()
    assert seen == ["a", "b", "c"]
    assert t.status is TaskStatus.DONE


def test_chunked_task_reports_progress_between_steps():
    progress: list = []

    def step(u, task):
        progress.append(task.progress)

    runner = make_chunked_task(
        kind="walk", label="walking",
        units=[1, 2, 3, 4],
        step=step,
    )
    queue = TaskQueue()
    t = queue.enqueue(runner, kind="walk")
    queue.run_next()
    # The progress list captures the value *before* each
    # step's progress update, so the first entry is 0 and
    # the last is 0.75 (3 of 4 done at the moment step #4
    # runs). After the final step the progress is 1.0.
    assert progress[0] == 0.0
    assert t.progress == 1.0


def test_chunked_task_short_circuits_on_cancel():
    seen = []
    cancel_at = 2

    def step(u, task):
        seen.append(u)
        if len(seen) == cancel_at:
            task.request_cancel()

    runner = make_chunked_task(
        kind="walk", label="walking",
        units=[1, 2, 3, 4, 5],
        step=step,
    )
    queue = TaskQueue()
    queue.enqueue(runner, kind="walk")
    queue.run_next()
    # Step 1 runs, step 2 runs (cancels inside),
    # step 3 sees is_cancelled() True and exits.
    assert len(seen) == cancel_at


def test_chunked_task_handles_empty_units():
    runner = make_chunked_task(
        kind="walk", label="walking", units=[], step=lambda u, t: None,
    )
    queue = TaskQueue()
    t = queue.enqueue(runner, kind="walk")
    queue.run_next()
    assert t.status is TaskStatus.DONE


def test_chunked_task_runs_final_callback():
    runner = make_chunked_task(
        kind="walk", label="walking",
        units=[1, 2, 3],
        step=lambda u, t: None,
        final=lambda task: "done!",
    )
    queue = TaskQueue()
    t = queue.enqueue(runner, kind="walk")
    queue.run_next()
    assert t.result == "done!"


# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------


def test_global_task_queue_is_a_queue():
    assert isinstance(GLOBAL_TASK_QUEUE, TaskQueue)


def test_terminal_statuses_set_is_correct():
    assert TaskStatus.DONE in TERMINAL_STATUSES
    assert TaskStatus.FAILED in TERMINAL_STATUSES
    assert TaskStatus.CANCELLED in TERMINAL_STATUSES
    assert TaskStatus.PENDING not in TERMINAL_STATUSES
    assert TaskStatus.RUNNING not in TERMINAL_STATUSES
