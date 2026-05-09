# Sync-Markers Workflow

Why visible-sector refresh is *marker-based*, not per-frame
— and how the artist schedules the refresh markers.

For the milestone overview see
[`V2_2_ANIMATION_TIMELINE_INTEGRATION.md`](V2_2_ANIMATION_TIMELINE_INTEGRATION.md).
For the marker layer itself see
[`TIMELINE_MARKERS.md`](TIMELINE_MARKERS.md).

---

## 1. The problem

The visible-sector pipeline is the most expensive operation
UNAV runs. A typical sync against a million-row Gaia DR3
subset:

* runs the navigator's bbox SQL prefilter,
* runs the exact cone refine in Python,
* materialises up to `max_visible_objects` Cinema 4D nodes
  (or buffer slots for the Native Point Viewer),
* invalidates the visible-sector binary file (when the
  Native Viewer is loaded),
* fires `EventAdd` to refresh the viewport.

A bake that fires this pipeline every frame would melt the
DB and freeze the host. v2.2's design rule:

> The visible sector is *not* re-streamed every frame. It
> is re-streamed on **marker events** — specific frames the
> artist (or a default policy) declares as sync points.

---

## 2. Where the markers come from

`evaluate_animated_state(mission, path, frame_range, config)`
populates `timeline.sync_marker_frames` with a sorted,
deduplicated union of:

1. **Waypoint arrivals.** When `config.waypoint_arrival_markers
   = True` (the default), every waypoint anchor frame is
   automatically a sync point.
2. **Explicit list.** Whatever the artist passes via
   `config.sync_markers`.

Sync markers are *not* the same as the v1.4 sync cadence
(which runs every-N-steps during continuous playback). They
are explicit, named events the artist can see on the
timeline.

---

## 3. The default policy: "sync at every waypoint"

For a typical voyage — Mercury → Venus → Earth → Mars — the
default policy fires four sync markers (one per arrival).
That's enough to keep the visible sector roughly current as
the camera moves through the inner system, without the cost
of a per-frame refresh.

The artist can:

* **Add explicit sync markers** at frames where they want
  an extra refresh (e.g. mid-segment, when the camera is
  about to glance toward a different region).
* **Disable waypoint-arrival markers** by setting
  `waypoint_arrival_markers=False` and supplying a custom
  list — useful when the artist's mission is many short
  hops and a per-waypoint sync would over-trigger.

---

## 4. Capping + warnings

`evaluate_animated_state` emits a warning when
`len(sync_marker_frames) > 32`:

```
animated state: 47 sync markers scheduled — the visible-
sector pipeline will fire that many times during playback /
bake. Consider trimming.
```

The threshold is conservative: 32 syncs across a 240-frame
bake is one sync every ~7.5 frames, which already approaches
"sync every step" territory. The warning is informational
— UNAV doesn't refuse the bake.

The marker builder has its own cap
(`MAX_MARKERS_PER_BAKE = 4096`) across all kinds combined.

---

## 5. The bake never fires the sync pipeline

`bake_mission_to_timeline` is the v2.2 baker. It writes
keyframes + markers, full stop. The visible-sector
pipeline is **never** triggered by the bake. This is the
v2.2 acceptance criterion:

> visible-sector refresh is marker-based, not per-frame

The bake's markers are *requests* the dialog (or a future
SceneHook) honours separately:

* When the artist clicks **Sync Visible Sector at Frame**
  in the Animation panel, UNAV evaluates the mission state
  at that frame and fires one sync.
* When the v1.x SceneHook lands, it can auto-fire a sync
  whenever the Cinema 4D timeline cursor crosses a
  `UNAV:sync:*` marker.

Until the SceneHook ships, the markers are visual cues
only. The artist can step through the timeline manually +
click Sync at the marker frames.

---

## 6. The science-layer refresh hook

`build_marker_bundle` accepts an optional
`science_layer_frames=[…]` argument. The frames listed end
up as `UNAV:science:science refresh #N` markers on the
timeline.

v2.1 science layers don't animate; they're built once and
left in place. But a future v2.x might want to refresh
selected layers at specific frames (e.g. the
`solar_system_orbits` placeholder is rebuilt when the time
navigator's epoch changes). The hook is wired today so the
dialog can produce the markers; the runtime side lands when
the SceneHook does.

---

## 7. The artist workflow

Typical bake:

1. Open the Missions tab.
2. Build / edit the mission as usual.
3. Set the **Start frame** / **End frame** (or accept the
   defaults).
4. (Optional) Set **FOV (deg)**.
5. Click **Bake to Timeline**. UNAV writes camera +
   navigator keyframes and drops UNAV-tagged timeline
   markers.
6. Scrub the Cinema 4D timeline. At each `UNAV:waypoint:*`
   marker the artist sees the camera arrive at a stop. At
   each `UNAV:sync:*` marker, the artist (or a future
   SceneHook) refreshes the visible sector.
7. (Optional) Click **Add Timeline Markers** to refresh
   the markers without re-baking the keys (useful if the
   artist edited the mission's sync schedule).

To clear the markers without re-baking: **Clear Timeline
Markers**. This removes every `UNAV:`-prefixed marker; the
artist's own markers are untouched.

To clear the keyframes: today the artist uses Cinema 4D's
built-in "Delete Animation" on the navigator + camera
tracks. (The v2.2 **Clear UNAV Keyframes** button is a
placeholder; it logs guidance + does not remove tracks
itself. A future v2.x track-aware cleanup is reserved.)

---

## 8. Determinism

The sync schedule is deterministic:

* Same mission + same `BakeRange` + same
  `AnimatedStateConfig` → same `sync_marker_frames`.
* Same `sync_marker_frames` + same labels → same
  `MarkerBundle`.
* Same `MarkerBundle` applied to the same document → same
  set of `UNAV:`-named markers.

Tests in `test_v22_animated_state.py` and
`test_v22_timeline_markers.py` assert this end-to-end.

---

## 9. Caveats + future work

* **No partial refresh.** A sync marker triggers a *full*
  visible-sector rebuild — no incremental "just this
  source" or "just this region" path. v1.x optimisation
  work can change that without affecting the v2.2 marker
  layer.
* **No async sync.** The dialog runs the sync on the host
  thread; the marker is just a request. A future v2.x can
  add a background-thread sync, but the marker layer is
  thread-agnostic.
* **No marker colour.** v2.2 doesn't set the Cinema 4D
  marker colour field. A future v2.x can colour-code by
  kind (waypoint = blue, sync = green, etc.) — the data
  layer carries the kind already.
* **No round-trip.** Once a marker is on the timeline, the
  dialog cannot read it back into the mission JSON. The
  bake is one-way; re-running it from the mission is the
  source of truth.
