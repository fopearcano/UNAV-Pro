# UNAV Pro — Educational Workflows

Patterns for using v3.3 presentations in lectures,
exhibitions, and cinematic demonstrations.

For the milestone overview see
[`V3_3_PRESENTATION_MODE.md`](V3_3_PRESENTATION_MODE.md).

---

## 1. The lecture workflow

Goal: an instructor walks a class through twelve solar-
system bodies, pausing at each to read a paragraph of
narration.

1. **Build a mission** in the v1.4 mission panel —
   twelve waypoints, one per body.
2. **Open the v3.3 presentation panel** → *New
   Presentation*. Set the `mission_ref` to the
   mission's id.
3. **Add one step per waypoint.** Set
   `waypoint_ref` to each waypoint label (or
   `mission.waypoints[i].uid`).
4. **Write narration** in each step's `narration`
   field. The narration is what's read aloud; it
   appears in the markdown summary.
5. **Add presenter notes** (`presenter_notes`) for
   anything off-script the instructor wants on hand.
6. **Set `pause_seconds`** per step — typically 30 s
   for a paragraph of narration.
7. **Save.** The dialog stamps `updated_at_iso`.
8. **Run the talk.** *Start Presentation* loads the
   sequence; *Next Step* / *Previous Step* drive
   playback. The dialog renders the narration; the
   presenter notes pop into a side panel.

Recommended overlays per step: `show_distance_rings`
on for outer-system stops; `show_ecliptic_plane` on
for the inner planets.

## 2. The exhibition workflow

Goal: a museum kiosk loops a presentation
indefinitely, showing six waypoints with no presenter.

1. Build a presentation as above with **no
   `presenter_notes`** (no one's reading them).
2. Set `pause_seconds` long enough that the audience
   can absorb each step (typically 15 – 30 s).
3. **Loop manually.** v3.3 doesn't ship a
   built-in loop; the kiosk sets up an external
   timer that calls *Next Step* on a schedule and
   *Start Presentation* when the sequence finishes.
4. **Use locked navigation.**
   `state.lock_navigation(...)` keeps audience-
   uncontrollable views stable across steps.

## 3. The cinematic workflow

Goal: bake a presentation to the timeline so the C4D
renderer can make a video.

1. Author the presentation as above.
2. Use the v1.4 mission's *Bake to Timeline* button
   on the linked mission. This produces the camera
   keyframes; the presentation runs the **scene
   state** (overlays, annotations) underneath.
3. The artist can choose to export the v3.3
   presentation alongside the bake — the markdown
   summary becomes shot-list documentation.

The presentation layer does **not** render anything.
The C4D renderer (Standard, Redshift, Octane, Arnold)
draws the scene the presentation populates.

## 4. Hybrid: instructor + recording

Goal: an instructor delivers a lecture once; a
recording plays back the same sequence verbatim.

* Author once. The `presentation_id` survives across
  sessions.
* Run for the lecture. The instructor uses the
  panel's *Next Step* button.
* For the recording, drive *Next Step* programmatically
  from a Cinema 4D `MessageData` plug-in or the v3.0
  task queue. Same sequence; same pauses; same
  presenter notes off-screen.

## 5. Anti-patterns

* **Don't put time-critical narration in
  `narration`.** It's a prose field; the dialog renders
  it but doesn't time it. Use a teleprompter outside
  UNAV.
* **Don't conflate v3.3 with v1.4 missions.** A
  mission *is* the camera path. A presentation is
  the **lecture script** that drives a mission. They
  serialise to different files; reuse missions across
  presentations.
* **Don't build a 200-step presentation.** The cap is
  `MAX_STEPS_PER_PRESENTATION = 200` (matching
  `MAX_WAYPOINTS_PER_MISSION`). Past that, factor the
  talk into multiple presentations.

## 6. Cross-reference

* [`V1_4_GUIDED_VOYAGES.md`](V1_4_GUIDED_VOYAGES.md) —
  the underlying mission system.
* [`V1_9_ADVANCED_VOYAGE_TOOLS.md`](V1_9_ADVANCED_VOYAGE_TOOLS.md)
  — voyage templates the artist starts from.
* [`PRESENTER_NOTES.md`](PRESENTER_NOTES.md) — the
  notes layer + export pipelines.
* [`V3_1_PROJECT_WORKSPACES.md`](V3_1_PROJECT_WORKSPACES.md)
  — workspace integration.
