# UNAV Pro v2.0 — Procedural Authoring Tools

UNAV's v2.0 milestone adds **procedural overlays** —
navigation aids the artist can drop into the C4D scene
without polluting the real catalog data: coordinate grids,
galactic / ecliptic planes, distance rings, the navigator's
sector cone, route corridors, waypoint labels.

This is **not a render engine**. v2.0 is authoring +
navigation support: visual references the artist sees in the
viewport, evaluates against the live datasets, and uses to
plan cinematics. None of the overlays participate in the
visible-sector pipeline; they cannot interfere with rendering
or with dataset objects.

For the per-feature deep dives:

* [`OVERLAYS_SYSTEM.md`](OVERLAYS_SYSTEM.md) — the seven
  overlay kinds, their math, and the C4D builder contract.
* [`DATASET_DERIVED_HELPERS.md`](DATASET_DERIVED_HELPERS.md)
  — bounding sphere, source distribution, density-heatmap +
  redshift-shell placeholders.

---

## 1. What v2.0 actually delivers

| Surface | Change |
|---------|--------|
| `procedural/overlays.py` | New module: pure-Python overlay computation. ``OverlaySettings`` dataclass + per-overlay builders + ``build_overlay_bundle`` aggregator. |
| `procedural/dataset_helpers.py` | New module: ``BoundingSphere``, ``SourceDistribution``, ``DensityHeatmap`` (placeholder), ``RedshiftShells`` (placeholder). |
| `c4d_objects/overlays_builder.py` | New module: c4d-bound applier that materialises a bundle under ``UNAV_Overlays``. Idempotent — re-build replaces in place; no scene-object duplication. |
| `core/project_state.py` | New ``overlays`` dict on ``ProjectState`` — overlay visibility + sizing round-trips through the project state sidecar. |
| `ui/main_dialog.py` | New **Overlays** tab with seven show/hide checkboxes, a radius scrubber, and **Build / Refresh** + **Clear Overlays** transports. |
| Tests | Four new test files (``test_v20_*``) covering settings serialization, geometry correctness, builder naming, route corridor calculation, and bounding-sphere math. |
| Docs | This file + two deep-dives. |

**No rendering features. No external renderer integration.
No IPC / sockets.** The visible-sector pipeline, the v1.4
mission system, the v1.7 stability layer, and the v1.8
timeline baker are all unchanged.

---

## 2. The seven overlay kinds

```python
from procedural import OverlaySettings, build_overlay_bundle

settings = OverlaySettings(
    show_grid=True,
    show_galactic_plane=True,
    show_ecliptic_plane=True,
    show_distance_rings=True,
    show_sector_cone=True,
    show_route_corridor=True,
    show_waypoint_labels=True,
    radius_pc=100.0,
    distance_ring_radii_pc=[10.0, 25.0, 50.0, 100.0],
)

bundle = build_overlay_bundle(
    settings,
    sector_origin_pc=(0, 0, 0),
    sector_forward=(1, 0, 0),
    sector_cone_half_angle_deg=30.0,
    route_waypoints=[(0, 0, 0), (10, 0, 0), (10, 10, 0)],
    waypoint_labels=[("A", (0, 0, 0)), ("B", (10, 0, 0))],
)
```

The seven kinds:

| Kind | What it draws | Math |
|------|---------------|------|
| ``grid`` | Flat XY coordinate grid, one polyline per line. | Linear span over ``[-grid_extent_pc, +grid_extent_pc]`` at ``grid_step_pc`` intervals. |
| ``galactic_plane`` | Great circle perpendicular to the galactic pole. | Pole at ICRS (192.8595°, 27.1283°). |
| ``ecliptic_plane`` | Great circle tilted ~23.44° about ICRS +X. | IAU J2000 obliquity (23.4392911°). |
| ``distance_rings`` | Concentric circles in the XY plane, one per radius in ``distance_ring_radii_pc``. | Closed-form circles. |
| ``sector_cone`` | Wireframe cone marking the navigator's view frustum. | Far + (optional) near disc + 4 cardinal edge lines. |
| ``route_corridor`` | Centre line + two parallel offset lines along a mission's waypoints. | Locally-perpendicular plane at each waypoint; offset by ``corridor_width_pc``. |
| ``waypoint_labels`` | Label anchors floating ``label_height_pc`` above each waypoint. | Position offset along world +Z. |

Every kind is independent — toggle one without affecting the
others.

---

## 3. The OverlaySettings dataclass

```python
@dataclass
class OverlaySettings:
    show_grid: bool = False
    show_galactic_plane: bool = False
    show_ecliptic_plane: bool = False
    show_distance_rings: bool = False
    show_sector_cone: bool = False
    show_route_corridor: bool = False
    show_waypoint_labels: bool = False
    radius_pc: float = 100.0
    segment_count: int = 64
    grid_step_pc: float = 25.0
    grid_extent_pc: float = 100.0
    distance_ring_radii_pc: List[float] = [10, 25, 50, 100]
    corridor_width_pc: float = 1.0
    label_height_pc: float = 1.5
    opacity: float = 1.0
```

* Validated on construction (``radius_pc > 0``, ``opacity ∈ [0, 1]``,
  segment count clamped to ``[4, 1024]``, ring count capped
  at ``MAX_RING_COUNT``).
* Round-trips through ``to_dict`` / ``from_dict`` losslessly.
* ``from_dict`` is fail-closed: a malformed payload returns
  defaults rather than raising (matches the v1.7 persistence
  contract).

---

## 4. The builder contract

`apply_overlay_bundle(bundle, doc=None)` materialises a
bundle under a single ``UNAV_Overlays`` null:

```
UNAV_Overlays/
  UNAV_Overlay_grid/
    x=-100 (grid#0)
    x=-50  (grid#1)
    ...
  UNAV_Overlay_galactic_plane/
    galactic plane (galactic_plane#0)
  UNAV_Overlay_distance_rings/
    10 pc (distance_rings#0)
    25 pc (distance_rings#1)
    ...
  UNAV_Overlay_waypoint_labels/
    A
    B
```

**Idempotent.** Each rebuild removes the per-kind containers
under ``UNAV_Overlays`` before re-inserting; the root null
itself stays in place so the artist's parent transformations
survive.

**Decoupled.** The overlays root is a sibling of the v0.1
``UNAV_Starfield`` root. The visible-sector pipeline never
walks under ``UNAV_Overlays`` and the overlay builder never
touches ``UNAV_Starfield``.

**Empty-bundle path.** Calling ``apply_overlay_bundle`` with
an empty bundle removes the entire ``UNAV_Overlays`` subtree
— a simple way to clear all overlays in one call. The
dialog's **Clear Overlays** button uses this.

---

## 5. Persistence

`OverlaySettings.to_dict()` emits a plain dict that
``ProjectState.overlays`` carries through the per-scene
sidecar:

```
~/.unav_pro/projects/<scene>.json
```

The dialog's **Save UNAV State** writes the current overlay
flags + radius + ring radii alongside the v0.x navigator,
route, datasets, and visual encoding. **Load UNAV State**
restores them.

A v1.x project state without the new ``overlays`` key loads
cleanly — the field defaults to an empty dict, the
``OverlaySettings`` constructed from it is the all-defaults
instance.

---

## 6. The dialog flow

1. Open the **Overlays** tab.
2. Tick the overlay kinds you want.
3. (Optional) Set the **Radius (pc)** scrubber.
4. Click **Build / Refresh**.

The builder reads the current navigator pose for the sector
cone and the active route waypoints for the corridor + labels.
Re-clicking Build reuses the existing scene tree (no
duplicates). Clicking **Clear Overlays** drops the entire
``UNAV_Overlays`` subtree.

The visible-sector pipeline is untouched throughout. Building
an overlay does *not* trigger a sector sync; clearing
overlays does *not* affect any catalog scene object.

---

## 7. Acceptance criteria

* [x] Artist can enable / disable navigation overlays via
  the Overlays tab.
* [x] Overlays are generated deterministically — same
  settings → byte-identical geometry.
* [x] Overlays do not duplicate on repeated sync; the
  builder is idempotent.
* [x] Overlays do not pollute dataset objects; ``UNAV_Overlays``
  and ``UNAV_Starfield`` are siblings.
* [x] Overlay settings persist via project state.
* [x] No rendering engine assumptions; no IPC / sockets.

---

## 8. What v2.0 explicitly does **not** do

| Out of scope                                    | Why                                                      |
|-------------------------------------------------|----------------------------------------------------------|
| Physical rendering / shading                     | The v2.0 contract is geometry only.                      |
| Density heatmap (real estimator)                | v2.0 ships a placeholder; the v2.x estimator drops in.   |
| Redshift shells (real cosmology)                | v2.0 ships the v0.5 Hubble proxy; v2.x can plug a real cosmology engine. |
| Time-varying overlays                           | Static at build time. The dialog rebuilds on demand.     |
| Per-overlay opacity at the C4D level            | The ``opacity`` field is stored but advisory; v2.x can wire it through display tags. |
| Animation of overlays                           | Out of scope; overlays are static scene objects.         |
| Renderer integration (RelativityRender etc.)    | Explicitly excluded.                                     |
| IPC / sockets                                   | Explicitly excluded.                                     |
