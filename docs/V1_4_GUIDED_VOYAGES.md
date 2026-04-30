# UNAV Pro v1.4 — Guided Voyages

UNAV's v1.4 milestone turns the plugin into a tool for
*structured interstellar journeys*. Before v1.4 the artist
could fly the navigator manually, drop bookmarks, and stitch a
linear route spline through them — but every click was a one-
shot operation. v1.4 introduces the **mission**: a named,
ordered sequence of waypoints (with optional epochs,
durations, camera orientations, and notes) that the artist
can save, reload, share, and *play back* through a
deterministic camera path.

Three new modules and one new tab:

| Surface                              | Where it lives                       |
|--------------------------------------|---------------------------------------|
| Mission + waypoint data model        | `voyage/mission.py`                   |
| Mission CRUD + per-user persistence  | `voyage/mission_manager.py`           |
| Cinematic camera path (Catmull-Rom)  | `voyage/camera_path.py`               |
| Deterministic playback engine        | `voyage/playback.py`                  |
| Dialog tab + transport controls      | `ui/mission_panel.py` + `main_dialog` |

Supporting docs:

* [`MISSION_FORMAT.md`](MISSION_FORMAT.md) — on-disk JSON
  layout, schema versioning, examples.
* [`CINEMATIC_CAMERA_PATHS.md`](CINEMATIC_CAMERA_PATHS.md) —
  how the camera path is built from a mission, the
  interpolation rules, the deterministic guarantees.
* [`PLAYBACK_SYSTEM.md`](PLAYBACK_SYSTEM.md) — the playback
  stepper, transport semantics, sync cadence and safety
  caps.

---

## 1. The mission concept

A mission is a saved sequence of stops. Each stop —
a ``MissionWaypoint`` — references one of:

| kind          | What it points at                                  |
|---------------|----------------------------------------------------|
| `object`      | A catalog uid (resolved via the active lookup).    |
| `coordinate`  | A free 3D point in C4D world units.                |
| `named`       | A label-only anchor (resolved by the dialog later).|
| `bookmark`    | A bookmark id from the v0.6 bookmarks list.        |

Optional per-waypoint fields:

* `epoch_jd` — the Julian Date the waypoint should be
  observed at; the playback path threads this through to the
  v1.2 Time Navigator so a mission can replay "Mars in 2026 →
  Mars in 2030".
* `orientation_quat` — `(w, x, y, z)` quaternion for the
  cinematic camera. `None` means "let the camera look at the
  next waypoint."
* `duration_seconds` — how long the playback dwells on / sweeps
  through this waypoint. Defaults to 4.0 s.
* `notes` — free-form text the dialog renders below the
  waypoint label.

The mission itself carries title, description, tags,
created/modified timestamps, and a stable hex `mission_id`
that the manager keys off (so renames / edits never break
references).

---

## 2. Persistence

Per-user missions live at::

    ~/.unav_pro/missions/
        index.json           # display order
        <mission_id>.json    # one file per mission

The split lets the dialog enumerate missions cheaply (just
parse the index) and lets the artist hand-edit a single
mission's JSON without disturbing the rest. Missing / corrupt
files log a warning and yield empty results — same convention
as the bookmarks layer.

`MissionManager.export_mission(mission_id, path)` and
`MissionManager.import_mission(path)` move a single mission
between machines. Imports get a fresh `mission_id` if the id
collides with one already in the user's library, so import is
always non-destructive.

---

## 3. The camera path

`camera_path.build_camera_path(mission, config)` is the
deterministic builder that turns a mission into an evaluable
``CameraPath``:

* **Position** — Catmull-Rom spline through the waypoint
  positions (endpoint-mirrored so the curve passes through
  the first / last waypoint exactly). Sampled in C4D world
  units.
* **Orientation** — slerp between per-waypoint quaternions.
  Waypoints without an explicit orientation get a synthesised
  "look toward the next waypoint" pose at build time.
* **Epoch** — linear lerp in JD. Waypoints without an
  explicit epoch inherit the previous waypoint's epoch.

Determinism: same inputs → byte-identical output. Tests
assert this end-to-end. There is no easing-curve catalogue
and no real-time keyframe engine in v1.4 — the path is a
parameterised table the playback module samples.

`camera_path.build_route_from_mission(mission)` converts a
mission into a v0.6 `core.route.Route` so the existing route-
spline rendering code (Build Route Spline) can show a
preview of the path before the artist hits Play.

---

## 4. The playback engine

`playback.Playback` is the **deterministic stepper** that
drives a built camera path:

```
play()           pause()           stop()
step_forward()   step_backward()
jump_to_waypoint(i)  jump_to_next_waypoint()  jump_to_previous_waypoint()
advance()        # called by an idle handler / SceneHook
set_speed(x)     # 0.1 .. 10.0
```

The engine is **not tied to wall-clock time**: the dialog
decides how often `advance()` fires (the configured
`steps_per_second × speed_multiplier` is reported via
`effective_step_interval_seconds` so a SceneHook can throttle
correctly). This is intentional — UNAV's v1.4 acceptance
criteria say "do not implement real-time interpolation tied
to frame rate."

### Sync cadence

The visible-sector pipeline is *not* re-streamed every step.
The `sync_callback` fires:

* On every transport jump (Play, Stop, Next/Prev, Jump-To).
* Every `sync_every_n_steps` ticks during continuous play
  (default 4).
* Whenever the cursor crosses a waypoint anchor.

When the per-step interval drops below
`MIN_INTERVAL_SECONDS_FOR_FULL_SYNC` (≈ 16 ms — i.e. the
artist scrubs faster than ~60 steps/s), the engine
automatically **stretches** the sync cadence so we don't
hammer the database during a fast scrub. The
`max_visible_objects` safety cap from the navigator is
forwarded into every sync call.

---

## 5. The Missions tab

The dialog gains a fourth tab next to Search / Bookmarks /
Navigation:

```
=== Missions (N) ===
  [0] Inner Solar System Tour (3 wp, 12.0s)  [solar-system, demo]
  ...

[New Mission]  [Delete]  [Import…]  [Export…]
Pick #  ▢  Title  ▢
Description ▢
=== <selected mission detail> ===
[Add Selected as Waypoint]  [Add Picked Bookmark]  [Remove Last]  [Preview as Route]
[◀◀ Prev] [◀ Step] [▶ Play] [❚❚ Pause] [◼ Stop] [Step ▶]
Speed × ▢   [Next Wp ▶▶]
(playback status)
```

The buttons map 1:1 to the transport methods on `Playback`.
The status line shows which step the cursor is on, the
effective interval per step, and whether playback is
PLAYING / PAUSED / FINISHED.

---

## 6. Integration with existing systems

* **Route system** — the "Preview as Route Spline" button
  rebuilds the live route from the mission and lets the
  v0.6 Build Route Spline path render it.
* **Bookmarks system** — bookmark-kind waypoints reference
  the v0.6 bookmark id. The "Add Picked Bookmark as Waypoint"
  button takes the current bookmark Pick and appends it.
* **Time Navigator (v1.2)** — when a mission carries epochs,
  the playback `apply` callback can update the v1.2
  TimeNavigatorState with the per-tick epoch. The dialog's
  default wiring leaves the Time Navigator alone unless the
  artist has explicitly enabled epoch sync.
* **Knowledge layer (v1.3)** — the Add Selected Object as
  Waypoint flow uses the same `inspect_active_selection`
  path as the v1.3 metadata inspector, so the cached
  catalog_source / object_type fields land on the waypoint
  for offline display.

---

## 7. Acceptance criteria

* [x] Artist can create, edit, delete, save, and reload
  missions without leaving Cinema 4D.
* [x] Waypoints can come from a real catalog selection, a
  bookmark, or a free coordinate.
* [x] Camera path moves smoothly between waypoints (Catmull-
  Rom; tests assert endpoints are exact).
* [x] Playback is deterministic — same step → same pose,
  every time.
* [x] Visible-sector updates fire on transport jumps and at a
  bounded cadence during play; `max_visible_objects` safety
  cap is honoured.
* [x] Missions persist to `~/.unav_pro/missions/` and reload
  on next launch.
* [x] Existing search / bookmark / navigation / route /
  knowledge surfaces are unaffected.

---

## 8. What v1.4 explicitly does **not** do

| Out of scope                                   | Why                                       |
|------------------------------------------------|-------------------------------------------|
| Real-time interpolation tied to frame rate     | v1.4 is integer-step + dialog-driven.     |
| Easing-curve catalogue (ease-in / ease-out)    | Out of scope; v1.4 uses linear timing per segment. |
| Per-frame Auto-Sync of the visible sector      | The SceneHook landing in v1.x will unlock this; the v1.4 stepper has the safe-cadence callback in place. |
| Audio / narration                              | Out of scope. The dialog's status line is the only feedback today. |
| Procedural waypoints (orbit-around, fly-by)    | Out of scope — the artist places every waypoint explicitly. |
| Branching / non-linear missions                | A mission is strictly an ordered list.    |
