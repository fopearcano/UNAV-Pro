# UNAV Pro — Safe Task Queue Model

Reference for `unav_pro/core/task_queue.py`. Why the queue
is single-threaded, how cooperative cancellation works, and
what the contract is between a runner and the queue.

---

## 1. Why no threads?

Cinema 4D's Python API is **not thread-safe**. The Maxon
documentation is explicit: scene mutation, undo, redraws,
and selection touches must happen on the main thread. UNAV
has honoured that since v0.1.

A multi-threaded queue inside Cinema 4D would deadlock at
best and corrupt scenes at worst. v3.0 therefore models
"async work" with **cooperative scheduling**: long-running
operations report progress between steps and yield control
to the queue, which lets the dialog's tick handler service
UI events between work units.

This is the same pattern Cinema 4D's own importers use.

## 2. Lifecycle

A task moves through five states:

```
pending → running → done
              ↘   → failed
              ↘   → cancelled
```

Once a task is in a terminal state (`done`, `failed`,
`cancelled`) the queue retains it for the diagnostics panel
("recent tasks") but won't run it again. `prune_terminal()`
drops them.

## 3. The runner contract

A runner is a `Callable[[Task], Any]`:

```python
def my_runner(task: Task) -> Any:
    for i, unit in enumerate(units):
        if task.is_cancelled():
            return None  # cooperative early-exit
        do_work(unit)
        task.report_progress((i + 1) / len(units),
                             f"step {i + 1}/{len(units)}")
    return final_result
```

Rules:

* The runner **must not** raise on cancellation; just
  return early. The queue inspects `task.is_cancelled()`
  after the runner returns and transitions to `cancelled`
  if set.
* The runner **may** raise on real errors. The queue
  catches the exception, records it in `task.error`, and
  transitions to `failed`. The exception is **not**
  re-raised — a buggy task must never crash the dialog.
* The runner **may** call `task.report_progress(fraction,
  message)` as often as it likes. The queue stores the
  latest reported value.
* The runner **may not** call `c4d.EventAdd()` or otherwise
  trigger Cinema 4D redraws on its own. The dispatcher
  (typically the dialog's `MessageData` tick) handles
  redraws after `run_next()` returns.

## 4. Convenience: `make_chunked_task`

The most common shape is "walk a list of units, run a step
function, report progress between steps." The
`make_chunked_task` builder bottles this:

```python
runner = make_chunked_task(
    kind="bake",
    label="Bake to timeline",
    units=list(frames),
    step=lambda f, task: bake_one_frame(f),
    final=lambda task: write_summary(),
)
queue.enqueue(runner, kind="bake", label="Bake to timeline")
```

The builder honours cancellation between steps and reports
fractional progress (1/N, 2/N, …, N/N) automatically.

## 5. Cancellation

The dialog flips `task.request_cancel()` when the artist
clicks "Cancel". The runner sees `task.is_cancelled()` go
True at its next poll point.

Three caveats:

* **Pending tasks cancel immediately.** No work has started;
  the queue transitions them straight to `cancelled`.
* **Running tasks cancel cooperatively.** If the runner
  ignores `is_cancelled()`, the cancel request has no
  effect until the runner returns of its own accord. By
  convention, runners check at every step boundary —
  `make_chunked_task` does this for you.
* **Terminal tasks ignore cancellation.** Once a task is
  done / failed / cancelled, `request_cancel` is a no-op.

## 6. Queue dispatch

The dialog drives the queue from a single point. Two
patterns:

* **Drain inline.** When the user clicks "Run all", the
  dialog calls `queue.run_all()`. Blocks the UI until the
  queue empties — appropriate for short workloads.
* **Drain in a tick.** A Cinema 4D `MessageData` plug-in
  ticks every redraw and calls `queue.run_next()`. The UI
  stays responsive between work units; the queue drains
  cooperatively as the user works.

v3.0 ships the queue and the `make_chunked_task` builder.
The dialog wiring (cancel button, tick `MessageData`) is
listed in [`ROADMAP.md`](ROADMAP.md) §2 as an upcoming
v3.x integration step.

## 7. Stats + diagnostics

`queue.stats` is a `QueueStats` snapshot:
`enqueued / started / completed / failed / cancelled`.

`render_task_queue_line(queue)` in `core/diagnostics.py`
produces a one-line summary the diagnostics panel renders.

## 8. Determinism + tests

Tasks IDs come from a process-local monotonic counter.
Tests reset it via `_reset_task_id_counter()` so test
ordering is deterministic.

The queue's `run_next` / `run_all` are synchronous; tests
verify lifecycle transitions, cancellation semantics, and
runner-error containment without any threading or sleeps.

## 9. What the queue is **not**

* Not preemptive. The runner runs until it returns.
* Not parallel. One task at a time, FIFO.
* Not persistent. Restarting Cinema 4D drops the queue.
* Not a network task pool. The plugin is offline-first;
  the queue is a local cooperative scheduler only.
