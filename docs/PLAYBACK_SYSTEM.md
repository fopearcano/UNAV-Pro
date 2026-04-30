# Playback System

The deterministic stepper that drives a v1.4 camera path. The
reference implementation is `unav_pro/voyage/playback.py`;
this document describes the transport semantics, the sync
cadence, and the safety contract.

---

## 1. The shape of the engine

```
Playback(path, config, apply, sync_callback)
    .play() / .pause() / .stop()
    .step_forward(n=1) / .step_backward(n=1)
    .jump_to_waypoint(i) / .jump_to_next_waypoint() / .jump_to_previous_waypoint()
    .advance()           # called by an idle handler / SceneHook
    .set_speed(x)        # 0.1 .. 10.0
```

The cursor is an integer step in `[0, total_steps]`.
`total_steps` is derived from `path.total_duration_seconds()
× config.steps_per_second`, with a floor of `waypoint_count - 1`
so even a brief mission has at least one step per segment.

Each transport call returns a `PlaybackTick` that the dialog
appends to its log. The same tick is also pushed to the
optional `apply` callback — this is the seam where the
dialog wires up "move the navigator + the camera + (if
enabled) the v1.2 Time Navigator state."

---

## 2. Why integer steps?

UNAV's v1.4 acceptance criteria are explicit:

> Do not implement real-time interpolation tied to frame
> rate.

The playback engine is therefore **not a clock-driven loop**.
It is a stepper the dialog drives manually:

* `play()` flips a flag.
* `advance()` moves the cursor by one step *if* the flag is
  set. The dialog (or a future SceneHook) calls `advance()`
  on whatever cadence makes sense — typically once per
  C4D idle event.
* `effective_step_interval_seconds` is the engine's
  recommendation for how often `advance()` should fire,
  computed from `steps_per_second` and `speed_multiplier`.
  Honouring this is the dialog's responsibility.

This design has three useful properties:

1. **Deterministic.** Same step number → same pose.
2. **Frame-rate-independent.** A 30 fps host and a 60 fps
   host produce the same playback (assuming both call
   `advance()` at the recommended interval).
3. **Pausable.** No timer to cancel; just stop calling
   `advance()`.

---

## 3. Transport semantics

### 3.1 Step transitions

`step_forward(n=1)` moves the cursor by `n` steps. Negative
`n` works (it mirrors `step_backward`). Out-of-range values
clamp to `[0, total_steps]` unless `config.loop = True`, in
which case they wrap modulo `total_steps`.

When the cursor reaches `total_steps` and `loop = False`,
`is_finished` becomes True and `is_playing` resets to False.
Subsequent `advance()` calls are no-ops; the dialog reports
this as "FINISHED" in the status line.

### 3.2 Waypoint jumps

The path's cumulative-normalised table maps each waypoint to
a step anchor::

    waypoint_step_anchors = [int(round(cum[i] × total_steps)) for i in ...]

`jump_to_waypoint(i)` snaps the cursor to anchor `i`.
`jump_to_next_waypoint()` and `jump_to_previous_waypoint()`
read the current cursor and dispatch accordingly. "Previous"
mid-segment rewinds to the *current* waypoint's anchor (a
common transport convention — like CD-player Previous
restarting the current track before jumping to the previous).

Every jump fires the sync callback unconditionally — when
the artist explicitly seeks, the visible sector should
reflect the new pose immediately.

### 3.3 Speed

`set_speed(x)` updates `speed_multiplier` mid-playback.
Clamped to `[0.1, 10.0]`. This does not change the total
step count — only the recommended `effective_step_interval`
that the dialog samples.

---

## 4. Sync callback cadence

The visible-sector pipeline is the most expensive thing in
UNAV. v1.4 keeps it in check via three rules.

### 4.1 Always sync on jumps

Any explicit transport jump (Play, Stop, Next, Prev,
Jump-To) sets `tick.trigger_sync = True`. The artist
expects the visible sector to update when they explicitly
seek.

### 4.2 Sync at fixed cadence during play

During continuous play, the engine fires the sync callback
every `sync_every_n_steps` ticks (default 4). With the
default `steps_per_second = 30` and `speed_multiplier =
1.0`, that's ~7.5 syncs/s — fast enough for the artist to
see the cone update, slow enough not to overload the DB.

### 4.3 Throttle on fast scrubs

When `effective_step_interval_seconds` drops below
`MIN_INTERVAL_SECONDS_FOR_FULL_SYNC` (≈ 16 ms — the artist
is scrubbing faster than the visible-sector pipeline can
keep up), the engine **stretches** the sync cadence
automatically. The rule is: at most one full re-sync per
simulated second during throttled play. Skipped ticks still
fire the `apply` callback (so the camera moves smoothly);
they just don't request a visible-sector rebuild.

### 4.4 Crossing a waypoint anchor

Every step that crosses a waypoint anchor fires a sync,
regardless of cadence. This way the artist always sees the
visible sector at the "named stops" even if the cadence is
otherwise throttled.

---

## 5. Safety

`PlaybackConfig.max_visible_objects` carries the navigator's
existing safety cap (default 100,000). The number is
threaded into the sync callback (the dialog passes it to
`stream_sector_for_active_datasets`) so a fast scrub can't
blow through the safety guard. The cap is not enforced
*inside* the playback engine — UNAV's broader safety layer
(`core/safety.py`) is the authoritative checkpoint; the
engine just forwards the number.

---

## 6. Determinism

The same sequence of transport calls on the same path
produces the same sequence of `PlaybackTick`s, byte-for-byte.
The tests (`test_playback_is_deterministic`) construct two
identical engines and step them in lockstep, asserting that
every sample matches.

This is the basis of the v1.4 acceptance criterion "playback
works deterministically." It also makes the v1.4 layer
testable without running Cinema 4D — every test in
`unav_pro/tests/test_voyage_*.py` runs against pure
Python.

---

## 7. What the playback engine is *not*

* **Not a media player.** No buffering, no audio, no codec.
* **Not real-time.** No `time.time()` calls, no event loop.
  The dialog drives the cadence.
* **Not multi-threaded.** Single thread, single cursor. Two
  dialogs cannot share a `Playback` instance.
* **Not bound to a specific renderer.** It produces a
  pose-per-step; the dialog routes the pose into the
  navigator null + the C4D camera. A future native viewer
  reads the same pose verbatim.
