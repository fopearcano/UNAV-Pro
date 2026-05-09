# UNAV Pro v2.2 — Animation & Timeline Integration

UNAV's v2.2 milestone polishes the v1.4 voyage stack +
v1.8 timeline baker into a workable animation-authoring
pipeline inside Cinema 4D.

This is **not a render engine**. v2.2 is animation
*authoring*: keyframing, timeline markers, and animated
navigation state. The visible-sector pipeline, the v2.0
overlays, the v2.1 science layers, and the v1.x voyage
tools are all unchanged.

For the deep dives:

* [`ANIMATED_UNAV_STATE.md`](ANIMATED_UNAV_STATE.md) — the
  pure-Python frame-aware evaluator at the heart of v2.2.
* [`TIMELINE_MARKERS.md`](TIMELINE_MARKERS.md) — the four
  marker kinds (waypoint / epoch / sync / science), their
  on-disk naming, and the C4D applier's idempotency
  contract.
* [`SYNC_MARKERS_WORKFLOW.md`](SYNC_MARKERS_WORKFLOW.md) —
  why visible-sector refresh is *marker-based*, not
  per-frame, and how the artist schedules the markers.

---

## 1. What v2.2 actually delivers

| Surface | Change |
|---------|--------|
| `animation/animated_state.py` | New module: `AnimatedSample` + `AnimatedTimeline` + `evaluate_animated_state` (per-frame state oracle) + `evaluate_at_frame` / `evaluate_at_seconds` (single-frame pure reads). |
| `c4d_objects/timeline_markers.py` | New module: `MarkerRecord` + `MarkerBundle` + `build_marker_bundle` (pure-Python) + `apply_markers` / `clear_markers` (c4d-bound, idempotent via `UNAV:` prefix scrub). |
| `c4d_objects/timeline_keys.py` | Extended with `bake_mission_to_timeline`: keyframes + markers in one transactional pass. FOV passthrough already in v1.8. |
| `voyage/playback.py` | `Playback.evaluate_at_frame` / `evaluate_at_seconds` — pure-read, side-effect-free pose lookup at a Cinema 4D frame. |
| `ui/main_dialog.py` | Missions tab gains **Clear UNAV Keyframes**, **Add Timeline Markers**, **Clear Timeline Markers**, **Preview at Frame**, **Sync Visible Sector at Frame** buttons + an **FOV (deg)** field + a **Preview frame** scrubber. |
| Tests | Three new test files (``test_v22_*``): animated-state evaluator, timeline-marker builder, playback frame reads + bake. 52 new tests; **1592 Python tests pass.** |
| Docs | This file + three deep dives. |

**No new features beyond animation polish.** No rendering,
no IPC, no external renderer bridge. Every v1.x + v2.x
surface is unchanged.

---

## 2. Animated UNAV state

`evaluate_animated_state(mission, path, frame_range, config)`
turns a mission + its built camera path into one row per
frame:

```python
@dataclass
class AnimatedSample:
    frame: int
    progress: float
    seconds: float
    navigator_position: Vec3
    camera_position: Vec3
    camera_orientation_quat: Quaternion
    rotation_hpb: Tuple[float, float, float]
    fov_rad: Optional[float]
    epoch_jd: Optional[float]
    waypoint_index: int
    is_sync_marker: bool
```

The output ``AnimatedTimeline`` carries:

* `samples` — one per frame.
* `keyframes` — v1.8 ``KeyframeRecord`` rows the existing
  applier consumes.
* `waypoint_arrival_frames` — frames where each waypoint
  anchor lands.
* `sync_marker_frames` — frames where the visible sector
  should be re-streamed.
* `epoch_change_frames` — frames at which the path's
  per-waypoint epoch changes (waypoint-granularity, *not*
  the linearly-interpolated epoch curve).

Determinism: same inputs → byte-identical output. See
[`ANIMATED_UNAV_STATE.md`](ANIMATED_UNAV_STATE.md) for the
full contract.

---

## 3. Timeline markers

`build_marker_bundle(timeline, ...)` turns the timeline's
arrival / sync / epoch / science frames into a
``MarkerBundle`` of stable-named marker records. The c4d-
bound `apply_markers` drops them onto the document timeline
via `c4d.documents.AddMarker`; on rebuild every previous
UNAV-managed marker (those whose name starts with `UNAV:`)
is removed first.

The four kinds:

| kind        | One per                                     |
|-------------|----------------------------------------------|
| `waypoint`  | ``timeline.waypoint_arrival_frames`` entry. |
| `epoch`     | ``timeline.epoch_change_frames`` entry.     |
| `sync`      | ``timeline.sync_marker_frames`` entry.      |
| `science`   | (caller-supplied) science-layer refresh frame. |

Markers placed by the artist or by other plugins are *not*
touched — only names that start with `UNAV:`.

See [`TIMELINE_MARKERS.md`](TIMELINE_MARKERS.md).

---

## 4. The bake one-shot

`bake_mission_to_timeline(mission, path, ...)` is the
v2.2 high-level baker:

```python
timeline, keys_written, markers_written = bake_mission_to_timeline(
    mission, path,
    frame_range=BakeRange(start_frame=0, end_frame=240, fps=30),
    config=AnimatedStateConfig(fov_rad=math.radians(50)),
    navigator=nav, camera=cam,
)
```

In one transactional pass it:

* evaluates the animated state,
* writes camera/navigator keyframes (via the v1.8 applier),
* drops UNAV timeline markers (waypoint / epoch / sync /
  science).

The visible-sector pipeline is **never** triggered by this
function — markers are *requests* the dialog / SceneHook
honours separately.

See [`SYNC_MARKERS_WORKFLOW.md`](SYNC_MARKERS_WORKFLOW.md)
for the marker-based sync model + the per-frame regeneration
prohibition.

---

## 5. Pure-read previews

`Playback.evaluate_at_frame(frame, frame_range)` returns the
camera sample at a Cinema 4D frame **without** moving the
playback cursor, **without** firing apply, **without**
firing sync. The dialog's "Preview at Frame" button uses it;
the v2.2 contract is that pure reads never have side
effects.

`evaluate_at_seconds(seconds, frame_range)` is the
seconds-precision wrapper.

The standalone ``animation.evaluate_at_frame`` /
``evaluate_at_seconds`` mirror the same shape but consume
the mission + path directly (skipping the Playback engine
entirely). Tests use both.

---

## 6. UI flow

The Missions tab gains five new buttons + two new fields
sandwiched between the v1.8 bake row and the v1.9
template / analytics row:

```
[Clear UNAV Keyframes] [Add Timeline Markers] [Clear Timeline Markers]  FOV (deg)
FOV ▢   Preview frame ▢
[Preview at Frame] [Sync Visible Sector at Frame]
```

* **Clear UNAV Keyframes.** Placeholder — the v1.8 baker
  doesn't carry the per-track DescID dispatch needed for a
  surgical removal. The artist uses Cinema 4D's built-in
  "Delete Animation" on the navigator + camera tracks.
* **Add Timeline Markers.** Drops UNAV-tagged markers
  without doing a full keyframe bake. Useful when the
  artist wants to refresh markers after editing a mission.
* **Clear Timeline Markers.** Removes every `UNAV:`-named
  marker from the document. Markers placed by the artist
  or by other plugins are untouched.
* **FOV (deg).** Populates the constant FOV the bake +
  preview use. ``0`` means "leave FOV unset" (v2.2 doesn't
  animate FOV across the path).
* **Preview frame.** The frame the next two buttons
  operate on.
* **Preview at Frame.** Pure-read pose log to the dialog log.
* **Sync Visible Sector at Frame.** Logs a request that
  the visible-sector refresh should fire at this frame.
  v2.2 ships the request; the actual sync trigger lives
  with the v1.7 sector pipeline.

---

## 7. Acceptance criteria

* [x] Artist can bake mission motion to the C4D timeline
  (camera + navigator keyframes via the v1.8 applier).
* [x] Waypoint / epoch / sync markers appear on the
  timeline with stable, identifiable names.
* [x] Artist can preview mission state at any frame
  without committing.
* [x] Visible-sector refresh is marker-based — the bake
  never fires the sync pipeline; the markers carry the
  schedule for the dialog or a future SceneHook to honour.
* [x] Science-layer refresh frames can be scheduled via
  ``science_layer_frames`` on ``build_marker_bundle``.
* [x] No render-engine assumptions; no external renderer
  bridge; no IPC.
* [x] The bake is deterministic and idempotent — same
  inputs produce byte-identical output, and re-running
  replaces UNAV-managed markers in place.

---

## 8. What v2.2 explicitly does **not** do

| Out of scope                                  | Why                                                  |
|-----------------------------------------------|-------------------------------------------------------|
| FOV animation across the path                | v2.2 carries one constant FOV; per-frame FOV is a v2.x knob. |
| Per-frame visible-sector regeneration         | Markers + dialog-driven sync only; per-frame would melt the DB. |
| Real-time SceneHook playback                  | Hook lands in v1.x; v2.2 is dialog-driven.           |
| Easing-curve catalogue                        | Linear timing per segment (v1.8 contract).           |
| RelativityRender / external integration       | Explicitly excluded.                                 |
| IPC / sockets                                 | Explicitly excluded.                                 |
