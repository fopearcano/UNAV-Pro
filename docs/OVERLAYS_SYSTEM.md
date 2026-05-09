# Overlays System

The seven v2.0 overlay kinds, their math, and the C4D
builder's idempotency contract.

For the milestone summary see
[`V2_0_PROCEDURAL_AUTHORING_TOOLS.md`](V2_0_PROCEDURAL_AUTHORING_TOOLS.md).
For dataset-derived overlays (bounding sphere etc.) see
[`DATASET_DERIVED_HELPERS.md`](DATASET_DERIVED_HELPERS.md).

---

## 1. The overlay set

Each kind has a stable string identifier the C4D builder
keys off. The identifiers (``KIND_*`` constants in
``procedural/overlays.py``) are the on-disk values; renaming
them would break every saved scene state.

```
KIND_GRID            = "grid"
KIND_GALACTIC_PLANE  = "galactic_plane"
KIND_ECLIPTIC_PLANE  = "ecliptic_plane"
KIND_DISTANCE_RINGS  = "distance_rings"
KIND_SECTOR_CONE     = "sector_cone"
KIND_ROUTE_CORRIDOR  = "route_corridor"
KIND_WAYPOINT_LABELS = "waypoint_labels"
```

---

## 2. Coordinate grid

A flat XY grid at z=0. One polyline per grid line so the
artist (or the builder) can style each line independently.

* `grid_extent_pc` — half-width of the grid square (default
  100 pc).
* `grid_step_pc` — line spacing (default 25 pc).

Coordinates are emitted as
``[-extent, -extent + step, …, +extent]`` — always including
both endpoints so the grid is visually closed.

Lines parallel to Y come first, then lines parallel to X.
Each polyline carries a label like ``x=-50`` so the artist
can find specific lines in the OM.

---

## 3. Galactic plane

The great circle perpendicular to the galactic pole, sampled
in ICRS Cartesian parsec.

* Pole at ICRS (192.8595°, 27.1283°) — Liu et al. 2011 /
  Hipparcos.
* In-plane reference direction toward the galactic centre
  (266.4051°, -28.9362°) so the basis is well-defined.

`segment_count` (default 64) controls the smoothness of the
circle. The polyline is closed.

---

## 4. Ecliptic plane

The great circle tilted by the obliquity (~23.44°) about
ICRS +X.

* Obliquity at J2000: 23.4392911° (IAU 2000A).
* Implemented as a great-circle build with the ecliptic
  pole at RA=270°, Dec=90°-obliquity.

UNAV uses the simple constant tilt rather than the full IAU
2006 polynomial — the visualisation difference across a few
centuries is sub-pixel. A future v2.x can plug in a higher-
fidelity precession model behind the same builder.

---

## 5. Distance rings

Concentric circles in the XY plane at the radii listed in
``distance_ring_radii_pc``. Default ladder:
``[10, 25, 50, 100]`` parsec.

* Each ring is a separate polyline, labelled with its radius
  (``"25 pc"``).
* Rings are deduplicated and sorted on construction; up to
  ``MAX_RING_COUNT`` (64) entries are honoured.
* Negative or zero radii are dropped silently.

When an artist wants distance rings centred on a body other
than the origin, the dialog can offset the ``UNAV_Overlays``
root null in the OM — overlays inherit the root's transform.

---

## 6. Sector cone

A wireframe cone marking the navigator's view frustum.

Inputs (passed by the dialog at build time):

* `sector_origin_pc` — apex position.
* `sector_forward` — apex-to-base direction (any non-zero
  vector; the builder normalises).
* `sector_cone_half_angle_deg` — half-angle of the cone
  (validated to ``(0, 180)``).
* `sector_near_pc` (default 0) — optional near-disc distance.
* `sector_far_pc` (default ``settings.radius_pc``) — far-disc
  distance.

Output: one far disc + (optionally) one near disc + four
cardinal edge lines. Each is its own polyline so the C4D
builder can place them in the same per-kind container under
``UNAV_Overlay_sector_cone``.

The cone is *purely visual* — UNAV's actual frustum-culling
math (``core/spatial_filter.py``) is unchanged.

---

## 7. Route corridor

A centre-line spline through the supplied waypoints plus two
parallel offset lines at ``corridor_width_pc`` to either
side.

For each waypoint, a tangent is computed from the surrounding
waypoints (forward difference at the endpoints, central
difference in the middle). The "side" vector is the
perpendicular to that tangent in the plane defined by world
+Z (or +Y, when the tangent is too close to +Z to use the
cross product safely).

The two edges are mirror images across the centre line. The
specific sign of "left" vs "right" is implementation-defined
and doesn't matter for the corridor's visual function.

A two-or-more-waypoint input produces three polylines
(centre + left + right). Less than two waypoints → empty
result. ``corridor_width_pc=0`` → centre line only.

---

## 8. Waypoint labels

Each label is an `OverlayLabel` with `text` and `position`.
The position is offset by `label_height_pc` along world +Z
so the label floats above its anchor waypoint.

The C4D builder materialises each label as a `c4d.Onull`
whose name carries the label text. A future v2.x can swap in
a text-spline / extruded-mesh implementation; the data
contract is unchanged.

Empty / whitespace-only labels are filtered.

---

## 9. The bundle

`build_overlay_bundle(settings, **inputs)` is the top-level
entry. It walks the settings flags and dispatches to the
per-kind builders, returning one ``OverlayBundle``:

```python
@dataclass
class OverlayBundle:
    polylines: List[OverlayPolyline]
    labels: List[OverlayLabel]
```

The C4D builder consumes this bundle. Bundles are
serialisable in spirit (every field is plain Python) but
v2.0 doesn't ship a JSON round-trip — the bundle is a
build-time artefact, not a persistence unit.

---

## 10. Idempotency contract

`apply_overlay_bundle(bundle)` materialises the bundle under
``UNAV_Overlays``. The contract:

1. Find or create the root ``UNAV_Overlays`` null.
2. Remove every existing per-kind container
   (``UNAV_Overlay_*``) under the root.
3. Group ``bundle.polylines`` by ``kind``. For each kind:
   * Create a fresh ``UNAV_Overlay_<kind>`` container.
   * Insert one ``c4d.SplineObject`` per polyline.
4. Group ``bundle.labels`` under ``UNAV_Overlay_waypoint_labels``.
5. Fire ``c4d.EventAdd``.

Re-running the build with the same bundle produces the same
scene tree — no duplicates, no orphans. The root null itself
is preserved across rebuilds so the artist's parent
transformations survive.

An empty bundle (no flag on, no inputs) drops the entire
``UNAV_Overlays`` subtree.

---

## 11. Decoupling from the visible-sector pipeline

The overlay system is designed to never interfere with the
catalog data:

* **Sibling parents.** ``UNAV_Overlays`` and the v0.1
  ``UNAV_Starfield`` are siblings under the document root.
  Neither walks under the other.
* **No marker container.** Overlay objects do *not* carry
  the v0.1 ``UNAV_marker`` BaseContainer — the visible-sector
  pipeline ignores them by construction.
* **No sync.** Building or clearing overlays never triggers
  a visible-sector sync. The two pipelines are entirely
  independent.

This is what lets v2.0 add overlays without bumping the
``compute_diff`` contract or the binary export.

---

## 12. Determinism

Every overlay builder is a pure function:

* Closed-form trigonometry (no random sampling).
* Settings-only inputs.
* No external state.

Same settings → byte-identical bundle. Tests
(``test_v20_overlays.py::test_overlay_bundle_is_deterministic``)
assert this end-to-end.

---

## 13. Adding a new overlay kind

1. Add a `KIND_<NAME>` string constant in
   `procedural/overlays.py`. Append it to ``OVERLAY_KINDS``.
2. Add the corresponding ``show_<name>`` flag on
   ``OverlaySettings``.
3. Implement the builder function (signature: takes
   ``settings`` plus optional inputs; returns
   ``List[OverlayPolyline]`` or a single polyline).
4. Wire it into ``build_overlay_bundle``.
5. Add a test in ``test_v20_overlays.py``.
6. Document the kind in this file under §1.

The C4D builder picks up the new kind automatically — the
container-name helper (``container_name_for_kind``) keys
off the kind string.
