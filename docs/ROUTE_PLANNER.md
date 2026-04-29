# UNAV Pro — Route Planner

Visual route planning for the navigator: a list of waypoints, a
linear C4D spline drawn through them, totals in C4D units and (when
available) parsec, and a one-click "focus the navigator on this
waypoint" command.

This is **not** a propulsion model. There is no orbital mechanics,
no relativistic time dilation, no powered flight. The route planner
is a navigation aid for assembling fly-throughs and target lists in
the C4D viewport.

Companion to:

  * `NAVIGATION_NULL_SYSTEM.md` (the navigator the planner repositions).
  * `METADATA_INSPECTOR.md` (the lookup that turns selected uids into
    parsec coords).
  * `SCENE_SYNC_WORKFLOW.md` (the sister hierarchy under
    `UNAV_Starfield`; the route lives at the scene root, peer to it).

---

## 1. Pieces

| Module                                       | Responsibility                                                |
|----------------------------------------------|---------------------------------------------------------------|
| `unav_pro/core/route.py`                     | Pure data model. ``Waypoint`` / ``Route`` / ``ResolvedPosition`` / ``RouteSegment`` / ``RouteSummary``; resolvers; distance computation; multi-line summary renderer. |
| `unav_pro/ui/route_panel.py`                 | C4D-bound action layer. Reads the active selection, builds and removes the route spline, focuses the navigator. |
| `unav_pro/ui/main_dialog.py`                 | Adds the "Route Planner" group with a multi-line panel + four buttons; owns a single ``Route`` instance shared across button clicks. |

Pure data lives without c4d, so unit tests cover every distance and
serialization path. The c4d-bound code is c4d-guarded; outside the
host its functions raise a clean ``RuntimeError`` and the dialog
falls back to a friendly status message.

---

## 2. Waypoint kinds

`Waypoint.kind` is one of:

| Kind          | Required fields                                  | Resolved by                                                   |
|---------------|--------------------------------------------------|---------------------------------------------------------------|
| `object`      | `uid`. C4D coords cached when the user clicked **Add Selected Object**. | `make_lookup_resolver(MetadataLookup)` fills parsec coords from the schema. |
| `coordinate`  | `x_c4d`, `y_c4d`, `z_c4d`.                       | Pass-through. Useful for free-space points: scene origin, named anchors built from a C4D null. |
| `named`       | `label` only (everything else optional).         | Resolves to ``None`` unless coords are explicitly attached.   |

Each `Waypoint` also carries `catalog_source` and `object_type`
informationally; they survive in `metadata_json` round-trips and
appear in the panel's per-row labels.

`Waypoint.__post_init__` validates the kind / uid / position
invariants at construction time so a malformed waypoint can never
slip into a `Route`.

---

## 3. Resolution

```
PositionResolver = Callable[[Waypoint], Optional[ResolvedPosition]]
```

Two resolvers ship in `core.route`:

  * **`passthrough_resolver`** — returns whatever the waypoint
    already carries. Used for tests and for routes built from
    pure-coordinate waypoints.
  * **`make_lookup_resolver(lookup)`** — for object waypoints whose
    parsec coords are not cached, looks the uid up in a
    ``MetadataLookup`` and pulls ``cartesian_x/y/z`` off the
    resolved ``CatalogObject``. Falls back to whatever the waypoint
    already had if the lookup misses.

`ResolvedPosition` carries `x_c4d/y_c4d/z_c4d` and optionally
`x_pc/y_pc/z_pc`. The C4D coords are required (every drawable point
on the route lives at a real viewport position); the parsec coords
are advisory and only used to surface a parsec total when *every*
waypoint along the route has them.

---

## 4. Distance computation

`compute_route(route, resolver)` walks the waypoint list, asks the
resolver for each position, and produces a `RouteSummary`:

```
RouteSummary(
    waypoint_count        = len(route),
    resolved_count        = how many resolved successfully,
    segments              = [RouteSegment, ...],
    total_distance_c4d    = sum of segment c4d lengths,
    total_distance_pc     = sum of segment pc lengths, or None,
    incomplete_segments   = segments where one endpoint did not resolve,
    incomplete_pc_segments= segments where pc length was unavailable,
)
```

Per-segment distance is straight-line:

  * `distance_c4d = sqrt(dx² + dy² + dz²)` in C4D world units.
  * `distance_pc = sqrt(dx_pc² + dy_pc² + dz_pc²)` only when **both**
    endpoints carry parsec coords; otherwise `None`.

`total_distance_pc` is `None` if *any* segment in the route lacks a
parsec measurement — the parsec total is all-or-nothing because a
mixed total of "some pc + some unknown" is misleading.

Empty routes and single-waypoint routes return zero distance with
zero segments.

---

## 5. Pretty rendering

`render_summary(route, summary)` produces the multi-line text the
dialog drops into the route panel:

```
=== UNAV Route ===
Waypoints       : 3 (3 resolved)
Total (C4D)     : 5.83 units
Total (parsec)  : 6.12 pc

Waypoints:
  [0] Alpha One  (object)  — unav_sample, star
  [1] Earth      (named)
  [2] (12, 0, 0) (coordinate)
```

Distance formatting is unit-aware:

  * Sub-parsec distances render as AU (`123 AU`).
  * Above 1 kpc render as `kpc`; above 1 Mpc render as `Mpc`.

Empty routes render a friendly nudge instead of zeros.

---

## 6. UI integration

Implementation: `unav_pro/ui/main_dialog.py` (the buttons) +
`unav_pro/ui/route_panel.py` (the c4d-bound actions).

The dialog owns one `Route` instance per session, accessible across
every button click. Each button refreshes the panel text so the
artist always sees the current state.

| Button                                | Action                                                                                       |
|---------------------------------------|----------------------------------------------------------------------------------------------|
| **Add Selected Object as Waypoint**   | Reads `doc.GetActiveObject()`. UNAV-tagged → `Waypoint(kind="object")` with uid + coords; otherwise → `Waypoint(kind="coordinate")` from the object's name + world position. |
| **Clear Route**                       | Empties the live `Route` and removes the existing route spline if any.                       |
| **Build Route Spline**                | Resolves every waypoint, builds a 2+-knot `c4d.SplineObject` (linear), and inserts it under a fresh `UNAV_Route` null at the scene root. Replaces the prior spline so re-clicking is idempotent. |
| **Focus Navigator on Waypoint**       | Moves `UNAV_Navigator`'s global-matrix translation to the *last* waypoint's resolved position. Rotation is left untouched. Reports a friendly error if the navigator is missing or the waypoint has no resolvable position. |

All four actions wrap their effects in a `doc.StartUndo()/EndUndo()`
block so a single Ctrl-Z reverts every C4D mutation. The route data
itself is in-memory; closing the dialog drops the live route. (A
future change can persist it via `Route.to_json()` into a scene
container — see the roadmap.)

---

## 7. Hierarchy

The route lives at the scene root, peer to `UNAV_Starfield`:

```
UNAV_Route                 (null, marker kind = "route_root")
└── UNAV_RoutePath         (linear SplineObject, marker kind = "route_spline")
```

Both nulls carry the standard `BC_ID_UNAV_MARKER` container so
`clear_starfield` removes the route subtree the same way it removes
everything else UNAV ever made.

The route is intentionally **not** under `UNAV_Starfield` because it
should survive when the visible-sector starfield gets rebuilt by a
filter change. The artist's curated waypoints outlive any one
sector.

---

## 8. Robustness rules

The planner follows the standing plugin invariants
(`PLUGIN_STRUCTURE.md` §9):

  1. **No exception escapes the C4D boundary.** Every dialog handler
     for a route button is wrapped; per-button helpers report
     statuses as strings rather than raising.
  2. **Missing data produces messages, not crashes.** The four
     button paths each surface a clear status when the navigator
     is missing, the catalog lookup misses, the route is empty,
     fewer than two waypoints have resolvable positions, or the
     selection is non-UNAV.
  3. **No top-level c4d import in testable modules.** `core.route`
     is c4d-free; only `ui.route_panel` and the dialog touch the
     host.
  4. **Idempotent.** `Build Route Spline` replaces the prior spline
     rather than adding another. `Clear Route` is safe with an
     empty route.
  5. **Single undo step.** Each c4d-bound action is wrapped in
     `doc.StartUndo()/EndUndo()`.

---

## 9. Test coverage

`unav_pro/tests/test_route.py` covers (40 tests):

  * **Validation.** Unknown kind rejected; object waypoint requires
    uid; coordinate waypoint requires `x/y/z_c4d`; named waypoint
    allows no position.
  * **Display label.** Explicit label wins; falls back to uid for
    objects and to `<kind>` otherwise.
  * **Waypoint serialization.** `to_dict` drops `None` fields;
    object / coordinate round trip; unknown keys dropped on
    `from_dict`.
  * **Route container.** Starts empty; add / clear / remove_at /
    last / iteration semantics.
  * **Route serialization.** `schema_version` recorded;
    name + waypoints round-trip via dict and JSON; garbage / `None`
    inputs degrade to an empty route.
  * **Resolvers.** `passthrough_resolver` returns positions when
    present and `None` otherwise; `make_lookup_resolver` fills pc
    from the catalog, falls back when the lookup misses, and
    returns `None` for unresolvable named waypoints.
  * **`compute_route`.** Empty / single-waypoint routes; total
    c4d distance correctness across multiple segments; parsec
    total only when *every* segment has both endpoints in pc;
    parsec total falls back to `None` when even one segment is
    missing pc; unresolvable waypoints leave both surrounding
    segments incomplete; custom resolver overrides positions
    end-to-end.
  * **`render_summary`.** Empty-route friendly message; route name
    and counts surfaced; missing-pc total is called out;
    waypoints listed by index, label, and kind.

The c4d-bound paths in `ui/route_panel.py` (selection reading,
spline building, navigator focus) are exercised by loading the
plugin in Cinema 4D 2023+; they are not part of the automated
suite.

---

## 10. Future extensions

Tracked as design intent, not promises:

  * **Per-waypoint focus picker.** Today **Focus Navigator on
    Waypoint** focuses on the last added waypoint. A future combo
    box can pick any waypoint by index.
  * **Route persistence.** Save/restore the route as part of the
    `.c4d` file via a serialized JSON in the `UNAV_Route` null's
    marker container, using the existing `Route.to_json()` /
    `from_json()` round trip.
  * **Camera-friendly transitions.** Animate the navigator along
    the route spline (constant velocity, bezier ease) once the
    base path is robust.
  * **Cubic / Bezier splines.** Linear is correct for distance but
    not always pretty. Add a "spline kind" picker (linear / B-spline
    / cubic) without changing the data model.
  * **Waypoint reordering and removal in the panel.** Today the
    panel is read-only and the only mutation is `Clear Route`.
    Future versions add per-row Move-Up / Move-Down / Delete
    buttons.
  * **Parsec total under cosmology.** When any waypoint has a
    redshift but no pc coords (e.g. a DESI quasar at z=2.5), a
    cosmology-aware integrator can fill the pc field. Reuses the
    same hook discussed in `SDSS_CONNECTOR.md` §8.

The MVP shipped here is intentionally narrow: one list, four
buttons, one summary. Every future extension slots in behind the
same `Route` / `compute_route` / `render_summary` interface.
