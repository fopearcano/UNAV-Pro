# UNAV Pro — Data Provenance

How v3.2 captures + surfaces the story behind every
catalog row.

For the milestone overview see
[`V3_2_DATA_INTEGRITY.md`](V3_2_DATA_INTEGRITY.md).

---

## 1. The provenance record

Every row UNAV ingests can carry a `ProvenanceRecord`:

```python
@dataclass
class ProvenanceRecord:
    catalog_source: str
    connector: str
    connector_version: str
    normalisation_version: str
    fetched_at_iso: str
    query_parameters: dict
    original_field_names: dict
    coordinate_system: str       # ICRS / Galactic / Ecliptic / ...
    units: dict                  # {category: unit-string}
    known_limitations: list[str]
    schema_version: int          # v3.2 ships 1
```

Records are stored inside `CatalogObject.metadata_json`
under the key `"provenance"`. The schema version isolates
future changes; loaders fail-closed on newer versions.

## 2. Attaching provenance

Connectors call `build_record(...)` and `attach_provenance(...)`:

```python
from data.provenance import (
    build_record, attach_provenance,
    COORDINATE_SYSTEM_ICRS,
)

record = build_record(
    catalog_source="Gaia DR3",
    connector="gaia_connector",
    connector_version="0.3.0",
    normalisation_version="0.3.0",
    query_parameters={
        "ra_min": 56.0, "ra_max": 60.0,
        "dec_min": 23.0, "dec_max": 25.0,
        "row_cap": 5000,
    },
    original_field_names={
        "uid": "source_id",
        "ra_deg": "ra",
        "dec_deg": "dec",
        "parallax_mas": "parallax",
    },
    coordinate_system=COORDINATE_SYSTEM_ICRS,
    units={
        "ra": "deg", "dec": "deg",
        "parallax": "mas",
        "magnitude": "vega_mag",
        "epoch": "julian_date",
    },
    known_limitations=[
        "negative parallax rows yield no distance",
        "proper motions are J2016 reference",
    ],
)

for row in rows:
    attach_provenance(row, record)
```

The same record can be attached to many rows — connectors
typically build one and stamp every row in the batch.

## 3. Reading provenance

```python
from data.provenance import read_provenance

rec = read_provenance(obj)
if rec is not None and not rec.is_empty():
    print(rec.short_summary())
    # → "Gaia DR3 · via gaia_connector v0.3.0 · fetched 2026-…
```

`read_provenance` is **defensive**: malformed
`metadata_json`, missing keys, or broken schema all
return `None`. The inspector shows "(no provenance
recorded)" in that case rather than blowing up.

## 4. Aggregation: `summarise_provenance`

```python
summary = summarise_provenance(rows)
# ProvenanceSummary(
#     distinct_sources=["Gaia DR3", "JPL Horizons"],
#     distinct_connectors=["gaia_connector", "jpl_connector"],
#     distinct_coordinate_systems=["ICRS"],
#     earliest_fetched_iso="2026-01-01T...",
#     latest_fetched_iso="2026-05-10T...",
#     rows_with_provenance=4732,
#     rows_without_provenance=12,
#     aggregated_known_limitations=[...],
# )
```

The summary is **stable**: lists are sorted, so two runs
against the same data produce byte-identical output. The
dataset audit CLI embeds this; the export package's
`provenance_summary` field stores its dict form.

## 5. Coordinate-system tags

Canonical tags:

* `ICRS` (default for stars, galaxies)
* `Galactic` (for galactic-plane catalogs)
* `Ecliptic` (for ephemeris cuts)
* `Barycentric` (for solar-system bodies)

Any other string is allowed but the inspector tags it
`(custom)` so the artist knows it's not part of the
canonical set.

## 6. Units

`units` is a mapping `{category: unit-string}`. Categories
the v3.2 validator recognises:

| Category | Allowed units |
| --- | --- |
| `ra` / `dec` | `deg` |
| `parallax` | `mas` |
| `distance` | `pc`, `kpc`, `Mpc` |
| `magnitude` | `mag`, `vega_mag`, `AB_mag` |
| `epoch` | `julian_date`, `modified_julian_date`, `year` |
| `proper_motion` | `mas/yr`, `arcsec/yr` |
| `redshift` | `dimensionless`, `""` |
| `radial_velocity` | `km/s` |

A unit outside the allowed set is flagged
`unsupported_units` (warning, not error).

## 7. Known limitations

Free-form list of caveats. The inspector renders them
verbatim; the export package aggregates them across all
rows.

## 8. Tests

* `test_v32_provenance` covers round-trip,
  malformed-metadata defence, attach/read on
  catalog objects, the summary aggregator.
