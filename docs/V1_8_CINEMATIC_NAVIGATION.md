# UNAV Pro v1.8 — Cinematic Navigation Polish

UNAV's v1.8 milestone polishes the v1.4 voyage system into a
practical animation-authoring tool inside Cinema 4D.

This is **not a rendering release**. v1.8 adds nothing about
shaders, materials, or third-party renderers. It is camera
movement, route animation, mission playback, and Cinema 4D
timeline integration. The visible-sector pipeline is
deliberately untouched: catalog ingest, DB queries, render
backends, and binary export are unchanged. v1.8's contract
is "the camera now moves nicely; everything else stays
exactly as v1.7 left it."

For the per-feature deep dives see:

* [`CAMERA_PATH_AUTHORING.md`](CAMERA_PATH_AUTHORING.md) —
  the v1.8 mission-waypoint additions (pause, look-at,
  roll) and the smooth/linear interpolation modes.
* [`TIMELINE_BAKING.md`](TIMELINE_BAKING.md) — how a
  mission gets baked into Cinema 4D keyframes, what the
  applier writes, and what it doesn't write.
* [`MISSION_PLAYBACK_POLISH.md`](MISSION_PLAYBACK_POLISH.md) —
  the new transport methods (`jump_to_start`, `jump_to_end`,
  `scrub_to_progress`, `evaluate_at_progress`) and the dialog's
  scrub-slider integration.

---

## 1. What v1.8 actually delivers

| Surface | Change |
|---------|--------|
| `voyage/mission.py::MissionWaypoint` | New optional fields: `pause_seconds`, `look_at_uid`, `look_at_position`, `roll_deg`. All default to no-op so v1.4 missions round-trip byte-identical. |
| `voyage/camera_path.py` | New `INTERP_SMOOTH` / `INTERP_LINEAR` constants on `CameraPathConfig`. Camera path now carries per-waypoint `pause_durations` + `rolls_deg`. New `tessellate_path()` and `build_preview_spline_data()` helpers for the C4D preview spline. |
| `voyage/playback.py` | New transports: `jump_to_start`, `jump_to_end`, `scrub_to_progress(p)`, `evaluate_at_progress(p)`. New `progress` property. `evaluate_at_progress` is **side-effect-free** — used by the dialog scrub slider for live-preview without committing. |
| `c4d_objects/timeline_keys.py` | New module: pure-Python keyframe generator (`generate_keyframes`) + Cinema 4D applier (`apply_keyframes`). Tested without c4d. |
| `c4d_objects/path_preview.py` | New module: drops a Cinema 4D `SplineObject` named `UNAV_Mission_Preview` into the active document; the dialog's "Clear Path Preview" button removes it. |
| `ui/main_dialog.py` | New buttons: **Preview Path**, **Clear Path Preview**, **Bake to Timeline**, **|◀ Start**, **End ▶|**. New widgets: **Interp** combo (smooth/linear), **Scrub** slider (0–1000 → progress 0..1), **Start frame** / **End frame** numeric inputs. |
| Tests | `test_v18_camera_path.py`, `test_v18_playback.py`, `test_v18_timeline_keys.py`, `test_v18_path_preview.py` covering interpolation modes, look-at, roll, pause durations, scrub, frame mapping, keyframe generation, missing-waypoint fallback. |
| Docs | This file + the three deep-dives (camera path, timeline baking, playback polish). |

**Not in v1.8:** new mission features (kinds), real-time
playback / SceneHook, easing-curve catalogue, audio /
narration, FOV animation, RelativityRender or any external
renderer integration, IPC / sockets, on-disk format bumps.

---

## 2. Camera-path additions at a glance

```python
from voyage import (
    Mission, MissionWaypoint, CameraPathConfig,
    build_camera_path, INTERP_LINEAR,
)

m = Mission(waypoints=[
    MissionWaypoint(
        kind="object", uid="jpl:Mars:2026",
        duration_seconds=3.0,
        pause_seconds=2.0,                      # dwell at Mars
        look_at_uid="jpl:Sun:2026",             # target the Sun
        roll_deg=15.0,                          # camera roll
    ),
    MissionWaypoint(
        kind="bookmark", bookmark_id="abc12345",
        duration_seconds=4.0,
    ),
])

path = build_camera_path(m, CameraPathConfig(
    interp_mode=INTERP_LINEAR,
    speed_multiplier=1.0,
    honour_pause_seconds=True,
    honour_look_at=True,
))
```

The `path` is the same `CameraPath` shape as v1.4; the v1.8
extensions are additive (`pause_durations`, `rolls_deg`,
`interp_mode`). The playback engine and the timeline-bake
applier consume the same path object.

---

## 3. Playback additions

```python
from voyage import make_playback

pb = make_playback(mission)
pb.scrub_to_progress(0.42)         # cursor at 42% of the path
pb.jump_to_start()                  # back to step 0
pb.jump_to_end()                    # snap to the last step

sample = pb.evaluate_at_progress(0.5)   # pure read; no cursor move
```

`evaluate_at_progress` is the workhorse of the dialog's scrub
slider: dragging the slider does not commit a transport
action; it just samples the path so the UI can preview the
pose. When the artist releases the slider, the dialog calls
`scrub_to_progress` (which moves the cursor + fires sync) on
the final value.

---

## 4. Timeline baking

```python
from c4d_objects.timeline_keys import (
    BakeRange, generate_keyframes, apply_keyframes,
)

records = generate_keyframes(
    path,
    BakeRange(start_frame=0, end_frame=480, fps=24),
)
written = apply_keyframes(records, navigator=nav, camera=cam)
```

The pure-Python `generate_keyframes` produces a list of
`KeyframeRecord` rows. The c4d-bound `apply_keyframes`
writes those records to the host's timeline as keyframes on
the navigator + camera objects. **Visible-sector generation
is not triggered** — the bake only touches navigation and
camera channels. See `TIMELINE_BAKING.md` §3 for the
contract.

---

## 5. Safety contract

* **Preview Path** does *not* sync the visible sector. It
  inserts a `SplineObject` and that's it.
* **Bake to Timeline** does *not* sync the visible sector.
  It writes keyframes and that's it.
* **Scrub slider** fires the sync callback on commit (when
  the artist releases the slider) — same cadence as a
  manual `Jump-To-Waypoint` click. It does *not* sync per
  scrub-pixel during the drag.
* **Real-time playback** is unchanged from v1.4: the engine
  is still cursor-step based, still frame-rate-independent,
  still requires the dialog (or a future SceneHook) to
  drive `advance()`.

The visible-sector pipeline retains every v1.7 safety:
`max_visible_objects` cap, atomic JSON writes, defensive
scene-walk, deterministic compute_diff.

---

## 6. Acceptance criteria

* [x] User can create a mission with v1.8 fields
  (pause / look-at / roll) via the dialog.
* [x] User can preview the path (Cinema 4D spline drops
  into the OM).
* [x] User can scrub through the mission with the slider;
  the camera follows in real time without committing.
* [x] User can bake the camera movement to the Cinema 4D
  timeline as keyframes.
* [x] No render-engine assumptions; no external renderer
  bridge; no socket / IPC.
* [x] Visible-sector generation remains decoupled from
  animation (no sector regen during preview / bake).
* [x] v1.4 missions round-trip through v1.8 byte-identical
  on disk.
* [x] All 1255+ pre-v1.8 tests still pass; new tests cover
  v1.8 surfaces.

---

## 7. What v1.8 explicitly does **not** do

| Out of scope                                      | Why                                      |
|---------------------------------------------------|------------------------------------------|
| Real-time per-frame playback                      | Tied to a SceneHook landing in v1.x.     |
| Easing-curve catalogue (ease-in / ease-out)       | Out of scope; v1.8 timing is per-segment linear (modulo the smooth / linear position interpolator). |
| Animated FOV                                      | The bake supports a constant FOV via `BakeRange.fov_rad`; per-frame FOV variation is not in v1.8. |
| Per-frame visible-sector update                   | Animation is decoupled from the catalog pipeline by design. |
| Audio / narration                                 | Out of scope.                             |
| RelativityRender / external renderer integration  | Explicitly excluded by the v1.8 task spec. |
| IPC / sockets                                     | Explicitly excluded.                      |
| Full mission-system rewrite                       | The v1.4 mission shape is unchanged; v1.8 extensions are additive. |
