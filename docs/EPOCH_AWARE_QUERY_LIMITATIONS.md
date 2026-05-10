# UNAV Pro — Epoch-Aware Query Limitations

What the v3.7 query engine **does** (and **doesn't**)
do when the artist sets `epoch_jd` on an
`AdvancedQuery`.

For the wider milestone overview see
[`V3_7_ADVANCED_ASTRONOMICAL_QUERIES.md`](V3_7_ADVANCED_ASTRONOMICAL_QUERIES.md).
For the canonical scientific-limitations list see
[`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md).

---

## 1. What `epoch_jd` does in v3.7

When you set `epoch_jd` on an `AdvancedQuery`:

* The engine surfaces a **note** in the report's
  `notes` list confirming "epoch-aware evaluation
  requested."
* If `interpolate_ephemeris=False` (the default),
  the engine **also surfaces a warning**:
  *"epoch_jd set but interpolate_ephemeris=False;
  v3.7 query engine evaluates positions
  statically. Ephemeris rows will keep their
  stored coordinates."*
* The engine **does not** propagate proper motion
  in v3.7. It does **not** interpolate JPL
  ephemeris snapshots.

Translation: the v3.7 engine **respects** the
`epoch_jd` field as a query parameter (it shows
up in the report + every export) but **does not
propagate** positions in time.

## 2. Why the limitation

The v1.2 time navigator + the v1.2 temporal
resolver already do proper-motion + ephemeris
propagation — but they're **scene-side** (they
operate on `CatalogObject`s before the navigator
caches them). The v3.7 query engine sits one
layer above that: it filters whatever
`CatalogObject` rows you hand it.

If you want propagated positions:

1. Run the v1.2 resolver first (call
   `core.temporal_resolver.resolve_for_epoch`
   against your candidate rows).
2. Hand the resolved rows to `run_query`.

The two-step shape keeps the engine fast +
deterministic; the v1.2 resolver handles all the
science-y math.

## 3. What this means in practice

* **Stars** (Gaia rows) — proper motion **is
  not** applied. The engine evaluates the row's
  stored RA/Dec/cartesian. For sub-arcsecond
  precision over decades, run the v1.2 resolver
  first.
* **Solar-system bodies** (JPL rows) — the
  engine returns whatever ephemeris snapshot
  the dataset stored. The v3.7
  `solar_system_at_epoch` preset surfaces the
  set of bodies; their *positions* are the
  stored ones.
* **Galaxies / quasars** — distance-via-
  redshift is the v0.5 Hubble-law proxy; not
  cosmology-grade. The query engine inherits
  this caveat without amplifying it.

## 4. How the engine warns

The `AdvancedQuery.epoch_jd` slot drives the
engine's report:

```python
if query.epoch_jd is not None and not query.interpolate_ephemeris:
    report.warnings.append(
        "epoch_jd set but interpolate_ephemeris=False; "
        "v3.7 query engine evaluates positions statically. "
        "Ephemeris rows will keep their stored coordinates."
    )
if query.epoch_jd is not None and query.interpolate_ephemeris:
    report.notes.append(
        "epoch-aware evaluation requested; the v3.7 "
        "engine respects metadata_json['epoch_jd'] but "
        "does not propagate proper motion. See "
        "docs/EPOCH_AWARE_QUERY_LIMITATIONS.md."
    )
```

These messages show up in:

* The `QueryReport.warnings` / `notes` lists.
* The Markdown export's *Warnings* + *Notes*
  sections.
* The dialog's *Advanced Query* panel status log.

The artist can't miss them.

## 5. Future work

A future v3.x can plumb the v1.2 resolver
through `run_query(...)` automatically — flip
`interpolate_ephemeris=True` + the engine
calls the resolver before applying filters.
That's a v3.x feature; v3.7 documents the
limitation so the contract is clear.

## 6. Cross-references

* [`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md)
  — full canonical list.
* [`V1_2_TIME_NAVIGATION.md`](V1_2_TIME_NAVIGATION.md)
  — the time-navigator + resolver.
* [`V0_5_SDSS_DESI_WORKFLOW.md`](V0_5_SDSS_DESI_WORKFLOW.md)
  — redshift→distance proxy details.
* [`REDSHIFT_DISTANCE_LIMITATIONS.md`](REDSHIFT_DISTANCE_LIMITATIONS.md)
  — the v0.5 caveat in detail.
