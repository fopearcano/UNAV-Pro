# UNAV Pro — Navigation Null System

How UNAV Pro represents the user's "where am I and where am I looking"
inside the C4D scene, and how the rest of the plugin reads that state.
Companion to `UNAV_PRO_ARCHITECTURE.md` §3.6 (camera / null navigation
controller) and `POINT_CLOUD_GENERATION.md`.

---

## 1. Hierarchy

The navigation system is a small three-object hierarchy parented at
the scene root:

```
UNAV_Navigator        (Onull)              <- pose + filter parameters
  ├── UNAV_Camera     (Ocamera)            <- viewport / render camera
  └── UNAV_ViewRay    (SplineObject)       <- visual forward indicator
```

All three carry a `BC_ID_UNAV_MARKER` sub-container so the plugin
recognizes them across save/load cycles. The marker `kind` values are:

| Object             | Marker kind          |
|--------------------|----------------------|
| `UNAV_Navigator`   | `navigator`          |
| `UNAV_Camera`      | `navigator_camera`   |
| `UNAV_ViewRay`     | `navigator_ray`      |

Implementation: `unav_pro/c4d_objects/navigation_null.py`.

---

## 2. Convention

The navigator's **forward** direction is its local **−Z** axis,
matching Cinema 4D's camera convention (a fresh camera looks down −Z).

Consequences:

  * The view ray is a 2-knot linear spline from `(0, 0, 0)` to
    `(0, 0, -100)` C4D units.
  * The child camera has identity local transform; rotating or
    translating the navigator moves the camera in lockstep.
  * `get_navigation_forward_vector()` returns `-mg.v3` (negated z-axis
    of the global matrix), normalized.

When the filter system lands, "what's in front of the navigator" means
"what falls inside the cone of half-angle `cone_angle_deg` around
`-mg.v3` from the navigator's world-space origin."

---

## 3. User data on `UNAV_Navigator`

The navigator null carries the eight `NavigationParams` fields as real
C4D user data, so artists edit them in the Attribute Manager just like
any C4D parameter:

| Short name                  | Type   | Default        | Purpose                                         |
|-----------------------------|--------|----------------|-------------------------------------------------|
| `max_distance_parsec`       | REAL   | 1000.0         | Cull objects farther than this from origin       |
| `field_of_view_deg`         | REAL   | 60.0           | Camera FOV used by frustum filter                |
| `cone_angle_deg`            | REAL   | 30.0           | Half-angle of the selection / filter cone        |
| `near_clip_parsec`          | REAL   | 0.1            | Filter near-plane in pc                          |
| `far_clip_parsec`           | REAL   | 10000.0        | Filter far-plane in pc (must exceed near)        |
| `selected_catalog_sources`  | STRING | `unav_sample`  | Comma-separated list of source names to include  |
| `max_visible_objects`       | LONG   | 100000         | Hard cap on returned points per query            |
| `c4d_scale`                 | STRING | `pc`           | One of `au`, `ly`, `pc`, `kpc`, `mpc`            |

The same payload is mirrored into the marker's `metadata_json` slot as
JSON, giving us a stable serialization that survives even if the
user-data layout is later refactored.

`NavigationParams.clamped()` is the gate at the C4D boundary — any
out-of-range or wrong-typed value the user types in the Attribute
Manager is replaced with a safe default before the filter sees it,
rather than rejected. The original value remains visible in the user
data for the artist to fix.

---

## 4. Public accessors

Implemented in `c4d_objects/navigation_null.py`. All three accept
either a `navigator` object directly or a `doc` to look it up; both
default to the active document.

```python
get_navigation_origin(navigator=None, doc=None) -> c4d.Vector
get_navigation_forward_vector(navigator=None, doc=None) -> c4d.Vector
get_navigation_filter_params(navigator=None, doc=None) -> NavigationParams
```

Behavior:

  * **`get_navigation_origin`** returns `nav.GetMg().off` — the
    world-space translation of the navigator. This is the cone apex
    used by future ray/cone filters.
  * **`get_navigation_forward_vector`** returns the negated, normalized
    z-axis of the navigator's global matrix. If the matrix is
    degenerate (zero-length axis), returns `(0, 0, -1)` instead of
    raising.
  * **`get_navigation_filter_params`** reads the eight user-data slots,
    falls back to the marker JSON for any missing slot, and returns a
    `clamped()` `NavigationParams`. It never raises for malformed
    values; it logs and clamps.

All three raise `RuntimeError` if there is no navigator in the active
scene — the caller is expected to surface that as a friendly status
message rather than as a stack trace.

---

## 5. UI integration

The dialog's **Create Navigation Null** button is wired through
`core/mock_actions.create_navigation_null` to
`c4d_objects.navigation_null.ensure_navigator`:

  * If the navigator already exists, it is **selected** in the Object
    Manager and the dialog reports
    `'UNAV_Navigator' already exists; selected it`.
  * If it does not exist, the hierarchy is created inside an undo
    block and the dialog reports
    `created 'UNAV_Navigator' with child 'UNAV_Camera' and 'UNAV_ViewRay'`.

`ensure_navigator` is idempotent and undo-friendly: clicking the
button repeatedly never produces duplicate navigators.

---

## 6. Filtering — not yet implemented

This phase intentionally stops at the navigator hierarchy and the
parameter accessors. The actual cone / frustum / distance filtering
that consumes `get_navigation_origin`, `get_navigation_forward_vector`,
and `get_navigation_filter_params` lands in a later phase.

When that lands, it will read those three values once per query, run
the filter against the catalog, and update either:

  * the visible subset of `UNAV_Starfield` children (visualization
    mode), or
  * a baked filtered dataset (`.unavbake`), per
    `UNAV_PRO_ARCHITECTURE.md` §3.7.

The contract above is what that filter will rely on, so any change
here is a breaking change to the rest of the plugin.

---

## 7. Save / load round-trip

Because every navigator object carries its marker container, opening a
saved `.c4d` file:

  * `find_navigator(doc)` re-locates the null by marker.
  * The eight user-data slots persist as standard C4D user data.
  * The marker's JSON copy of the same parameters acts as a fallback
    so missing or corrupted user data does not lose the artist's
    settings.

Re-creating a navigator after a save/load is unnecessary; the existing
hierarchy continues to drive the filter accessors as before.

---

## 8. Future extensions

Tracked as design intent, not promises:

  * **Travel modes.** *Free fly* / *null follow* / *goto target* —
    `UNAV_PRO_ARCHITECTURE.md` §3.6. The travel mode will be a new
    user-data slot and will not change the accessor surface.
  * **Multiple navigators.** A scene may want a "render camera" and a
    separate "filter camera" eventually. The accessors already accept
    a `navigator` argument so callers can target either.
  * **Animated cones.** Because cone parameters are user data on a
    standard null, they animate via standard C4D keyframes for free
    once the filter system reads them per-frame.
