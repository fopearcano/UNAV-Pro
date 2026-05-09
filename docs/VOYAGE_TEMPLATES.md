# Voyage Templates

The v1.9 ``voyage.templates`` module ships five ready-to-edit
mission templates. Templates are **builders**, not locked
presets — every template returns a fresh ``Mission`` the
artist is expected to rename, reorder, or extend.

---

## 1. The bundled templates

| Name | Builder | Waypoints | Best for |
|------|---------|-----------|----------|
| ``solar_system_tour`` | ``solar_system_tour()`` | 8 (Mercury → Neptune) | Solar-system fly-throughs at a chosen epoch. |
| ``nearest_stars_tour`` | ``nearest_stars_tour()`` | 7 (Sun + 6 nearby stars) | Local-neighbourhood cinematics; ships with cached parsec positions so it renders without a lookup. |
| ``redshift_tour`` | ``redshift_tour()`` | 5 (z = 0 → 3) | Hubble-flow demos. Distances are the v0.5 Hubble-law proxy and tagged ``approximate``. |
| ``empty_voyage`` | ``empty_voyage(title=…)`` | 0 | Build everything from scratch. |
| ``selected_objects_tour`` | ``selected_objects_tour(uids)`` | N (1 per uid) | Quick fly-through of a list of UIDs the dialog supplies (selected bookmarks / search results). |

---

## 2. Solar System Tour

```python
from voyage import solar_system_tour
m = solar_system_tour(
    epoch_iso="2026-01-01T00:00:00",
    epoch_jd=2461041.5,
    duration_seconds=4.0,
)
```

* Eight ``orbital``-kind waypoints: Mercury, Venus, Earth,
  Mars, Jupiter, Saturn, Uranus, Neptune.
* UIDs follow the v0.4 JPL Horizons convention
  (``jpl:<body>:<epoch_iso>``).
* Tags: mission-level ``solar-system``, ``template`` +
  per-waypoint ``solar-system``, ``planet``, ``template``.
* Default epoch is J2026-01-01 — the artist edits the epoch
  field per waypoint after creation, or re-runs the
  builder with a different ``epoch_iso``.

---

## 3. Nearest Stars Tour

```python
from voyage import nearest_stars_tour
m = nearest_stars_tour(duration_seconds=4.0)
```

* Sun (origin coordinate) + six closest stars: Proxima
  Centauri, Alpha Centauri A, Barnard's Star, Wolf 359,
  Lalande 21185, Sirius A.
* Cached parsec positions baked in so the path renders
  even without an active metadata lookup.
* UIDs are Gaia DR3 source IDs; the dialog re-resolves them
  via the active dataset registry when the lookup is loaded.
* Tags: ``star``, ``template``, ``nearby``.

---

## 4. Redshift / Extragalactic Tour

```python
from voyage import redshift_tour
m = redshift_tour(duration_seconds=4.0)
```

* Five extragalactic anchors at increasing redshift:
  M31 (z ≈ 0), Virgo (z ≈ 0.0036), 3C 273 (z ≈ 0.158),
  a placeholder distant galaxy (z ≈ 1.0), a placeholder
  high-z quasar (z ≈ 3.0).
* Distances are the v0.5 Hubble-law proxy. **Not suitable
  for cosmology** — the template is a teaching aid for the
  Hubble flow, not an astrometric reference.
* Mission tag: ``approximate`` (loud signal in route
  analytics so the artist sees the caveat).

---

## 5. Empty Voyage

```python
from voyage import empty_voyage
m = empty_voyage(
    title="My Mission",
    description="A blank slate.",
    tags=["custom"],
)
```

Zero waypoints, just the metadata scaffold. The dialog uses
this as the fallback when a richer template requires arguments
the dialog can't supply (e.g. ``selected_objects_tour`` with
no selection).

---

## 6. Selected Objects Tour

```python
from voyage import selected_objects_tour
m = selected_objects_tour(
    uids=["gaia:1", "gaia:2", "gaia:3"],
    title="Pleiades Tour",
    duration_seconds=3.0,
    catalog_source="Gaia DR3",
)
```

Builds a mission whose waypoints are the supplied UIDs in
order. Empty / whitespace UIDs are filtered. Useful when the
artist has selected multiple bookmarks or search results and
wants a quick fly-through without dropping each one in by
hand.

---

## 7. The registry

Every bundled template is reachable through the registry:

```python
from voyage import TEMPLATE_REGISTRY, get_template, list_templates

list_templates()        # → [TemplateDescriptor, ...]
get_template("solar_system_tour")  # → TemplateDescriptor

descriptor = get_template("nearest_stars_tour")
mission = descriptor.builder()
```

Each entry has a stable ``name`` (lookup key), a ``label``
(dialog display), a ``description`` (dialog tooltip), and a
``builder`` (the ``Mission``-returning callable).

---

## 8. Adding a new template

1. Add a builder function to ``voyage/templates.py``. The
   function must return a fresh ``Mission`` and must not
   raise (templates are idempotent constructors).
2. Append a ``TemplateDescriptor`` entry to
   ``TEMPLATE_REGISTRY``.
3. Add a focused test in
   ``unav_pro/tests/test_v19_templates.py`` asserting the
   waypoint count + the canonical tags / labels.
4. Document the template in this file under §1 + a new
   section.

The dialog picks up new entries automatically — the picker
reads ``list_templates()`` at layout time.

---

## 9. Determinism

Every bundled template is a pure function: same arguments →
byte-identical Mission. This matters for the v1.7
deterministic-state guarantees and for tests that assert the
template-built missions round-trip through JSON.

The ``solar_system_tour``'s default epoch is fixed at
J2026-01-01 in the source; later releases may bump it, but
the function will keep accepting an explicit ``epoch_iso``
override so existing scripts stay reproducible.
