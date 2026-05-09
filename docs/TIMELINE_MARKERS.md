# Timeline Markers

The v2.2 marker system. Lives in
`unav_pro/c4d_objects/timeline_markers.py`. The pure-Python
data layer (`MarkerRecord`, `build_marker_bundle`) is tested
without Cinema 4D; the c4d-bound applier (`apply_markers` /
`clear_markers`) drops + scrubs Cinema 4D timeline markers.

For the v2.2 milestone overview see
[`V2_2_ANIMATION_TIMELINE_INTEGRATION.md`](V2_2_ANIMATION_TIMELINE_INTEGRATION.md).

---

## 1. The four marker kinds

```
KIND_WAYPOINT  = "waypoint"   # one per waypoint anchor frame
KIND_EPOCH     = "epoch"      # one per epoch change frame
KIND_SYNC      = "sync"       # one per sync-marker frame
KIND_SCIENCE   = "science"    # one per (caller-supplied) refresh frame
```

Each marker carries a stable display name:

```
UNAV:<kind>:<label>
```

For example `UNAV:waypoint:Earth`, `UNAV:sync:sync #2`,
`UNAV:epoch:epoch change #1`. The artist can read the marker
in Cinema 4D's timeline + identify it by the prefix.

---

## 2. The build helper

```python
from c4d_objects.timeline_markers import build_marker_bundle

bundle = build_marker_bundle(
    timeline,
    waypoint_labels=["Mercury", "Venus", "Earth", "Mars"],
    sync_label="sync",
    science_layer_frames=[60, 120, 180],
)
```

* `timeline` — an ``AnimatedTimeline`` from
  ``evaluate_animated_state``.
* `waypoint_labels` — optional, paired with
  ``timeline.waypoint_arrival_frames`` in order. Extras
  fall back to ``waypoint #N``.
* `sync_label` — base label for the sync markers; v2.2
  defaults to "sync".
* `science_layer_frames` — caller-supplied frames at which
  a science-layer refresh should fire. v2.1 layers don't
  animate, but the dialog can wire its own refresh schedule
  via this hook.

The output ``MarkerBundle`` has a `records` list (every
``MarkerRecord`` to drop) and a `warnings` list (cap
overrun, etc.).

The helper caps the bundle at `MAX_MARKERS_PER_BAKE = 4096`
records — anything past that is dropped + a warning is
logged.

---

## 3. The C4D applier

```python
from c4d_objects.timeline_markers import apply_markers

written = apply_markers(bundle, doc=None, fps=None)
```

Returns the number of markers actually inserted.

Idempotency: every previously-managed UNAV marker (those
whose name starts with `UNAV:`) is removed first, then the
new bundle is dropped. A re-bake replaces in place; the
artist's hand-placed markers + other plugins' markers are
left untouched.

Outside Cinema 4D the applier is a no-op (returns 0).

`clear_markers(doc)` removes every `UNAV:`-prefixed marker
from the document; returns the count removed.

---

## 4. The C4D-side cleanup walk

`apply_markers` and `clear_markers` both call
``_clear_unav_markers`` to scrub previous UNAV markers. The
walk:

1. Get the document's first marker via
   ``c4d.documents.GetFirstMarker(doc)``.
2. Walk the linked list via ``GetNext()``.
3. For each marker, read the name. If it starts with
   ``UNAV_MARKER_PREFIX`` (the literal string `"UNAV:"`),
   add it to the removal list.
4. After the walk, remove each tagged marker via
   ``Remove()``.

The two-pass design (collect-then-remove) avoids the
classic mid-iteration mutation hazard.

The walk is defensive: every C4D call is wrapped in a
try/except so a corrupt marker can't break the whole
cleanup.

---

## 5. Coexistence with artist + other-plugin markers

By design the prefix `UNAV:` is the *only* signal the
cleanup walk uses. Markers placed by:

* the artist (e.g. via Cinema 4D's "Add Marker" command),
* other plugins (e.g. a render queue, a notes plugin),
* manual scripts the artist wrote,

are all left untouched on every UNAV bake / clear. The
trade-off: if the artist names a marker
`UNAV:my notes` by hand, the next UNAV bake will remove
it. The dialog logs every cleanup count so this is at
least visible.

---

## 6. Markers are *requests*, not actions

The v2.2 design rule: markers are *requests* the dialog or a
future SceneHook honours separately. The bake never
triggers a visible-sector sync; it just drops the markers
that say "fire a sync here." The dialog can:

* show the sync markers as visual cues,
* fire a sync when the artist clicks **Sync Visible Sector
  at Frame**,
* (in a future v1.x SceneHook) auto-fire syncs when the
  Cinema 4D timeline cursor crosses a sync-marker frame.

This keeps animation playback decoupled from data
generation. See
[`SYNC_MARKERS_WORKFLOW.md`](SYNC_MARKERS_WORKFLOW.md) for
the full reasoning.

---

## 7. The diagnostic renderer

`render_marker_summary(bundle)` produces a plain-text
summary the dialog drops into the log:

```
=== UNAV markers (12) ===
  waypoint  : 4
  sync      : 6
  epoch     : 2
```

Used after the marker pass + after the bake one-shot. Empty
bundles render `"No timeline markers to insert."`.

---

## 8. Determinism

The pure-Python builder is deterministic: same timeline +
same labels + same science frames → byte-identical bundle.
Tests
(``test_v22_timeline_markers.py::test_bundle_build_is_deterministic``)
assert this end-to-end.

The C4D applier is *write*-deterministic: the same bundle
applied to the same document produces the same set of
markers (modulo the artist's pre-existing non-UNAV markers).

---

## 9. Caveats

* **Cinema 4D's marker count is unbounded.** The cap is on
  *UNAV* markers only; the host's own marker pool can hold
  many more. v2.2's 4096 cap is a soft guard — past 4096
  the artist is doing something the dialog should refuse.
* **No per-marker colour.** Cinema 4D's marker API exposes
  a colour field; v2.2 doesn't set it. A future v2.x can
  colour-code markers by kind without changing the data
  layer.
* **No round-trip from C4D markers back to UNAV.** Once
  dropped, a marker is just a Cinema 4D scene object — the
  dialog can't re-derive the original timeline from the
  scene's marker set. The artist re-bakes from the
  mission JSON if they want a fresh marker set.
