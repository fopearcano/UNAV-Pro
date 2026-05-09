# Mission Playback Polish

The v1.8 polish to the v1.4 playback engine. Focus is
**transport ergonomics** for the dialog: the artist needs to
scrub, jump, and preview without the engine's cursor state
getting in the way.

---

## 1. New transports

| Method                              | Behaviour |
|-------------------------------------|-----------|
| `Playback.jump_to_start()`          | Move the cursor to step 0. Always fires a sync. Does not flip the play flag. |
| `Playback.jump_to_end()`            | Snap the cursor to `total_steps`. Flips `is_playing` to False (the run is over). Always fires a sync. |
| `Playback.scrub_to_progress(p)`     | Place the cursor at progress `p ∈ [0, 1]`. Clamps. Always fires a sync. Used by the dialog's scrub slider. |
| `Playback.evaluate_at_progress(p)`  | **Pure read.** Returns the `CameraSample` at progress `p` without moving the cursor, without firing the apply callback, and without firing the sync callback. Determinism: same input → same output. |
| `Playback.progress` (property)      | Read-only normalised cursor progress in `[0, 1]`. Used by the dialog to keep the slider synchronised with transport actions. |

The v1.4 transports (`play / pause / stop / step_forward /
step_backward / jump_to_waypoint / jump_to_next_waypoint /
jump_to_previous_waypoint / advance / set_speed`) are all
unchanged.

---

## 2. The scrub slider integration

Scrubbing is the v1.8 polish's centrepiece. The dialog's
scrub control is an integer slider in `[0, 1000]` that the
v1.8 wiring maps to `progress = slider / 1000.0`.

There are two distinct paths:

* **During drag.** The dialog reads the slider continuously
  and calls `Playback.evaluate_at_progress(p)` to *preview*
  the camera pose. This does not commit anything; the
  cursor stays where the artist last left it.
* **On commit.** When the slider sends a value-change event
  (release / discrete tick), the dialog calls
  `Playback.scrub_to_progress(p)`. *That* moves the cursor,
  fires apply, and fires sync.

In v1.8 the dialog wires the `Command(_ID_PLAYBACK_SCRUB)`
event to the commit path. Cinema 4D fires this on slider
release, which matches the design — preview-during-drag,
commit-on-release.

A future SceneHook could invoke `evaluate_at_progress` on
every viewport redraw while the slider is being held, but
v1.8 leaves that to the v1.x SceneHook landing.

---

## 3. Determinism

All five new transports are deterministic by construction:

* `jump_to_start` / `jump_to_end` set the cursor to
  fixed integer values.
* `scrub_to_progress` rounds `progress * total_steps` to
  the nearest integer with `int(round(...))`.
* `evaluate_at_progress` is a thin wrapper around
  `CameraPath.sample(p)`, which is itself pure.

The same sequence of transport calls on the same path
produces byte-identical `PlaybackTick`s, every time. The
v1.8 test suite asserts this.

---

## 4. Cold-start scrubbing

When the dialog's scrub slider receives an event but no
`Playback` engine has been built yet (the artist hasn't
clicked Play), the dialog auto-builds one from the active
mission with the current Speed × and Interp settings, then
calls `scrub_to_progress`. The dialog log records:

```
Mission: 1 waypoint(s) could not be resolved (no cached position).
tick step=420/840 wp=2 pos=(...) [sync]
```

so the artist sees both the build report and the resulting
tick.

This is the same convention the v1.4 Play button uses; v1.8
just plumbs it through the scrub path so dragging the
slider works without a prior Play click.

---

## 5. Safety contract during playback

* The visible-sector sync callback fires **only** on
  transport-triggered jumps and at the v1.4 cadence (every
  `sync_every_n_steps` ticks during play, plus on waypoint-
  anchor crossings). Scrub commits trigger one sync per
  release; they do not fire per-pixel during the drag.
* The `max_visible_objects` cap is forwarded into every
  sync (same as v1.4) — fast scrubs cannot blow through
  the safety guard.
* The bake operation does not trigger the sync callback at
  all (see [`TIMELINE_BAKING.md`](TIMELINE_BAKING.md) §6).
* Mode-switching the camera-path interpolator (`smooth` ↔
  `linear`) requires re-building the path. The dialog
  handles this implicitly: every transport / scrub action
  reads the current Interp dropdown and rebuilds the path
  if needed before driving the engine.

---

## 6. Status rendering

`render_playback_status(playback)` (in `ui/mission_panel.py`)
now reflects the v1.8 progress:

```
Playback: PAUSED  step 420/840  interval 33.3 ms
```

The dialog's status line updates after every transport
action. The progress slider also updates so the slider
position always matches the current cursor.

`evaluate_at_progress` does **not** update the slider — it's
a pure read; the dialog uses it for the live-preview during
the drag, but the slider's own widget value is the
authoritative artist intent.

---

## 7. What v1.8 playback does *not* add

| Out of scope                                    | Why                                                              |
|-------------------------------------------------|------------------------------------------------------------------|
| Real-time per-frame playback                    | Tied to a SceneHook landing in v1.x.                             |
| Audio scrubbing                                 | UNAV does not carry audio; out of scope.                         |
| Reverse playback (negative speed)               | The v1.4 cursor model is forward-only with explicit step-back transport. Reverse-play would need a sign-aware sync cadence; deferred. |
| Loop point bookmarking                          | The v1.4 `loop=True` mode is unchanged. Per-segment loops are not supported. |
| Two-finger / multi-touch scrubbing              | The dialog uses Cinema 4D's stock slider widget; gesture support is host-dependent. |
