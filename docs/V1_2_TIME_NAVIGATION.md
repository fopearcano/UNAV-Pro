# UNAV Pro v1.2 — Time Navigation

UNAV's v1.2 milestone teaches the plugin that astronomical
objects are not frozen. Stars drift across the sky every year;
planets orbit on day-by-day timescales; spacecraft traverse the
solar system in hours. Before v1.2 every position in UNAV was a
single snapshot — usually Gaia's J2016.0 reference epoch or a
"today"-ish JPL Horizons fetch. v1.2 makes the epoch a first-
class part of the data model: **every position carries the time
it is valid for**, and the user can step that time forward and
backward to watch the scene evolve.

This document is the v1.2 overview. The supporting docs cover
the building blocks:

* [`EPOCHS_AND_JULIAN_DATES.md`](EPOCHS_AND_JULIAN_DATES.md) —
  the time model itself (ISO ↔ JD, Jyear, named epochs).
* [`GAIA_PROPER_MOTION_LIMITATIONS.md`](GAIA_PROPER_MOTION_LIMITATIONS.md) —
  what the linear propagation does and does not approximate.
* [`JPL_TIME_SERIES_WORKFLOW.md`](JPL_TIME_SERIES_WORKFLOW.md) —
  fetching multi-epoch ephemerides into the DB.
* [`SOLAR_SYSTEM_COORDINATES_AND_EPOCHS.md`](SOLAR_SYSTEM_COORDINATES_AND_EPOCHS.md) —
  the v0.4 single-epoch baseline that v1.2 extends.

---

## 1. What v1.2 actually delivers

| Capability                        | Where it lives                                            |
|-----------------------------------|-----------------------------------------------------------|
| Epoch model + conversions         | `core/time_model.py`                                      |
| Gaia proper-motion propagation    | `core/proper_motion.py`                                   |
| Per-uid time-series state table   | `db/schema.sql` (`object_states`, schema v2)              |
| Epoch-aware position resolver     | `core/temporal_resolver.py`                               |
| Multi-epoch JPL fetch + DB sink   | `tools/fetch_jpl_solar_system.py` (`--start/--end/--step-days`, `--db`) |
| Visible-sector sync at an epoch   | `db/spatial_query.py`, `core/sector_streaming.py`         |
| Time Navigator dialog panel       | `ui/main_dialog.py`, `core/time_navigator.py`             |
| Binary export carries the epoch   | `data/binary_export.py` (format v3)                       |

---

## 2. The data model

### 2.1 The reference epoch on a `CatalogObject`

Each row in the catalog still carries a static
``(ra_deg, dec_deg, distance_parsec)`` triple plus optional
``proper_motion_ra`` / ``proper_motion_dec``. v1.2 adds **no
required columns** to ``CatalogObject`` — old datasets remain
valid. The implicit reference epoch for these static fields is
**J2016.0** for Gaia rows (``epoch=2016`` is what Gaia DR3
reports its astrometry at) and the row's import epoch for JPL
rows.

### 2.2 The new ``object_states`` table

When the temporal pose for an object is non-trivial, v1.2
records explicit state rows in the new ``object_states`` table.
Each row is one (uid, epoch_jd) pair plus a ``state_type``:

| state_type        | What it stores                                          | Used for                                  |
|-------------------|---------------------------------------------------------|-------------------------------------------|
| ``static``        | (just the FK; no extra fields)                          | Pinned overrides; rarely needed.          |
| ``proper_motion`` | ``pmra_masyr``, ``pmdec_masyr``, ``reference_epoch_jd`` | Gaia stars whose drift is non-negligible. |
| ``ephemeris``     | ``x``, ``y``, ``z`` (parsec), optional ``vx/vy/vz``      | JPL planets / moons / spacecraft.         |

Schema lives in
[`unav_pro/db/schema.sql`](../unav_pro/db/schema.sql); the
DBManager bumps ``schema_version`` from ``1`` to ``2``
transparently when an old DB is opened.

### 2.3 The temporal resolver

``core/temporal_resolver.resolve_for_epoch(...)`` is the central
"give me positions at epoch T" function. It splits the input
catalog into three buckets:

1. **Ephemeris-backed uids** — interpolate (or pick the nearest)
   ``x/y/z`` snapshot from the per-uid timeseries. Highest
   fidelity; takes priority over proper-motion.
2. **Proper-motion-backed uids** — apply linear ICRS great-
   circle propagation (cos(dec) factor; pole-singularity
   clamp) using the override store's pmra/pmdec rates and the
   row's own ra/dec.
3. **Static uids** — left unchanged.

The resolver also recomputes the cartesian xyz so downstream
sector / binary code sees a coherent (ra, dec, distance, x, y,
z) tuple.

---

## 3. The visible sector at an epoch

``db.spatial_query.query_cone(..., epoch=...)`` gained an
``epoch`` keyword. When it is supplied, the cone query first
fetches the ``object_states`` rows for the bbox candidates, then
runs the resolver to update positions before the exact cone
refine. This means a catalog row's bbox and final pass-through
both reflect the requested epoch — a star with high pmra crossing
the cone boundary will be picked up correctly even if its static
position was on the other side of the boundary.

``query_cone_for_navigator``, the dataset-aware streaming code
in ``core/sector_streaming.py``, and the ``mock_actions``
``sync_visible_sector_at_epoch`` handler all thread the same
``epoch`` argument through.

---

## 4. The Time Navigator dialog panel

The Time Navigator panel (right-hand side of the main dialog,
under the Native Viewer group) lets the artist:

* Type / paste an epoch (ISO datetime or a JD or a Jyear or a
  named-epoch string like ``J2016.0``) and click **Set**.
* Click **<** / **>** to step backward / forward by ``step_days``.
* Type a step size (days) into the numeric field.
* Toggle a **Play** flag (placeholder in v1.2; the per-frame
  sweeper lands with the v1.x SceneHook + Auto-Sync pipeline).
* Click **Sync at epoch** to re-stream the visible sector for
  every active dataset using the current epoch.

The panel reads / writes ``core.time_navigator.default_state()``
— a process-wide singleton. Every other code path that needs to
know "what epoch is the user currently looking at" reads the
same singleton.

---

## 5. Binary format v3

The visible-sector binary file (the bridge to the future C++
point renderer) gains a v3 layout. v3 appends 16 bytes to the v2
extra-header block:

```
float64 epoch_jd        Julian Date the file was rendered for
uint8   state_mode      0=static / 1=proper_motion / 2=ephemeris / 3=mixed
bytes   pad[7]          reserved
```

v1 and v2 readers fail closed on a v3 file (version mismatch);
v3 readers handle v1 / v2 / v3 correctly. The renderer can use
``epoch_jd`` to display the scene's "as-of" timestamp.

See [`BINARY_VISIBLE_SECTOR_FORMAT.md`](BINARY_VISIBLE_SECTOR_FORMAT.md)
for the complete byte-level layout.

---

## 6. Acceptance criteria

A v1.2 build must satisfy all of the following:

* [x] User can set an arbitrary epoch via the Time Navigator
  panel; the dialog status line reflects it.
* [x] JPL planets fetched as a multi-epoch time series move
  visibly between epochs in the C4D scene.
* [x] Gaia stars with non-zero pmra/pmdec are propagated when
  the visible sector is synced at a non-J2016 epoch.
* [x] Old static-only catalogs still work — every code path is
  no-op when ``epoch is None``.
* [x] Schema-v1 DBs auto-migrate to schema-v2 on first open.
* [x] Existing v1 / v2 binary files still parse against v1.2.

---

## 7. What v1.2 explicitly does **not** do

| Out of scope                                        | Why                                              |
|-----------------------------------------------------|--------------------------------------------------|
| Full N-body / orbital integration                   | Out of scope — v1.2 is *interpolation* + *linear drift*. |
| Light-time correction                               | The v0.4 connector already accepts ``2``-table state vectors with light-time, but UNAV does not back-propagate signals. |
| Relativistic time dilation                          | Out of scope until the timescale is heliocentric/barycentric and the artist needs sub-second precision. |
| Per-frame "play" sweep                              | The dialog has the toggle wired but the SceneHook is parked behind v1.x's Auto-Sync pipeline. |
| Per-uid covariance propagation                      | Gaia DR3 reports correlated errors on (ra, dec, parallax, pmra, pmdec); v1.2 propagates the *mean* only. See [`GAIA_PROPER_MOTION_LIMITATIONS.md`](GAIA_PROPER_MOTION_LIMITATIONS.md). |
