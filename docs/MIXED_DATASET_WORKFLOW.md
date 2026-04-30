# Mixed Dataset Workflow — Gaia + JPL + SDSS + DESI in One C4D Scene

How to assemble a Cinema 4D scene that mixes a Gaia DR3 regional
star catalog (v0.3), a JPL Horizons solar-system snapshot (v0.4),
and SDSS / DESI extragalactic catalogs (v0.5). All four feed the
same visible-sector pipeline and the same metadata inspector —
the contract makes sure their uids, catalog-source labels, and
`object_type` tags stay disjoint, so the visual encoder can
render them differently and the inspector can pull any record
without ambiguity.

For background see
[`V0_3_GAIA_DR3_WORKFLOW.md`](V0_3_GAIA_DR3_WORKFLOW.md),
[`V0_4_JPL_HORIZONS_WORKFLOW.md`](V0_4_JPL_HORIZONS_WORKFLOW.md),
[`V0_5_SDSS_DESI_WORKFLOW.md`](V0_5_SDSS_DESI_WORKFLOW.md),
[`SOLAR_SYSTEM_COORDINATES_AND_EPOCHS.md`](SOLAR_SYSTEM_COORDINATES_AND_EPOCHS.md),
[`REDSHIFT_DISTANCE_LIMITATIONS.md`](REDSHIFT_DISTANCE_LIMITATIONS.md),
[`EXTRAGALACTIC_VISUAL_ENCODING.md`](EXTRAGALACTIC_VISUAL_ENCODING.md),
[`DATASET_MANAGER.md`](DATASET_MANAGER.md), and
[`VISUAL_ENCODING.md`](VISUAL_ENCODING.md).

---

## 1. Why mixing works

Two contracts make Gaia + JPL + SDSS + DESI coexistence safe:

1. **Disjoint uid prefixes.** Each connector emits a different
   prefix:
   * Gaia: `gaia:{source_id}`
   * JPL Horizons: `jpl:{body}:{epoch}`
   * SDSS: `sdss:{specObjID or objID}`
   * DESI: `desi:{targetid}`

   The four prefix namespaces never overlap, so the metadata
   lookup never has to disambiguate a collision inside a single
   dataset.
2. **Per-dataset registry namespace.** The Dataset Manager wraps
   every uid as `<dataset_name>:<original_uid>` when it merges
   active datasets into the metadata lookup. So even if two
   different JSONLs both reused a connector uid, the registry
   namespace prevents collision across datasets.

The same two contracts apply to `catalog_source` and
`object_type`:

* `catalog_source` is one of `"Gaia DR3"` / `"Gaia DR2"` /
  `"JPL Horizons"` / `"SDSS"` / `"DESI"`. The visual encoder's
  *catalog source* mode renders each source with its own colour
  (see [`EXTRAGALACTIC_VISUAL_ENCODING.md`](EXTRAGALACTIC_VISUAL_ENCODING.md)
  for the palette).
* `object_type` is `"star"` for Gaia, one of
  `"planet" / "moon" / "asteroid" / "comet" / "spacecraft"` for
  JPL, and `"galaxy" / "quasar" / "star" / "unknown"` for SDSS
  and DESI. The visual encoder's *object type* mode and *redshift*
  mode distinguish them at sight.

---

## 2. Recommended end-to-end workflow

```
1. Pick a sky region for stars and an epoch for the solar system.

2. Fetch + index Gaia (offline, no Cinema 4D required):

       python tools/fetch_gaia_region.py \
           --ra 56.75 --dec 24.12 --radius-deg 1.0 \
           --limit 5000 \
           --output data/catalogs/gaia_pleiades_sample.jsonl \
           --build-index cache/gaia_pleiades

3. Fetch + index JPL solar system at the chosen epoch:

       python tools/fetch_jpl_solar_system.py \
           --epoch "2026-01-01T00:00:00" \
           --bodies "Mercury,Venus,Earth,Mars,Jupiter,Saturn,Uranus,Neptune,Pluto,Moon=moon" \
           --center "500@10" \
           --output data/catalogs/jpl_solar_system_2026.jsonl \
           --build-index cache/jpl_solar_system_2026

4. In Cinema 4D, open Universal Navigator Pro.

5. Open Dataset Manager, Add Dataset for each JSONL:
     - data/catalogs/gaia_pleiades_sample.jsonl  → cache/gaia_pleiades
     - data/catalogs/jpl_solar_system_2026.jsonl → cache/jpl_solar_system_2026

6. Disable the bundled sample. Click Load Active Datasets.
   The status log reports both row counts and the merged
   bounding radius.

7. Click Create Navigation Null. Position and rotate it.

8. Click Sync Visible Sector. The streaming layer queries
   each dataset's index independently; only the cells the
   navigator's cone touches are loaded.

9. Open the Visual Encoding panel:
     - Color Mode    → catalog source (Gaia vs JPL)
                       or object type (star vs planet/moon/…)
     - Size Mode     → object type (planets large, moons small)
                       or magnitude (Gaia stars by brightness)

10. Click any object → Inspect Selected Object:
      - A Gaia star shows G-mag, BP-RP, parallax, distance, RA/Dec.
      - A JPL body shows epoch, observer center, vector_au /
        vector_pc, distance_au, distance_km.
```

---

## 3. Scale guidance

Stars and solar-system bodies live on **wildly different
distance scales**. Gaia neighbors are on the order of 1–500 pc;
the entire solar system fits inside ~5e-4 pc. In a single C4D
scene that means the planets sit essentially at the navigator's
origin while Gaia stars are far away.

Two practical patterns:

1. **Wide-cone, large clip range** — set the navigator's
   `near_clip_parsec` to `0.0` and `far_clip_parsec` to
   `50–500`. Gaia stars dominate visually; the planets are a
   tight cluster at the origin and you may want to zoom the C4D
   viewport to inspect them.
2. **Solar-system focus** — set `near_clip_parsec` to `0.0` and
   `far_clip_parsec` to `1e-3` (≈ 200 AU) so only the JPL bodies
   pass the cone. Useful when staging a navigator pose around
   the Sun.

Both patterns rely on the safety guardrails from v0.1: the
visible-sector-only mode refuses to build without a navigator,
and the 100 000-row hard cap and minimal-marker policy keep the
scene healthy regardless of how the catalogs are mixed.

---

## 4. Visual encoding in mixed scenes

The encoder's *catalog source* mode is the cleanest mixed-scene
default — every Gaia source gets one colour and every JPL body
gets another, regardless of body type. *Object type* mode is
finer-grained: it renders `star`, `planet`, `moon`, `asteroid`,
`comet`, and `spacecraft` distinctly.

The encoder has self-healing fallbacks: if a row is missing the
field a mode needs (e.g. `magnitude` is undefined for JPL
bodies), the encoder falls back to a uniform default for that
row instead of erroring. See
[`VISUAL_ENCODING.md`](VISUAL_ENCODING.md) for the per-mode
fallback table.

---

## 5. Metadata inspector in mixed scenes

The inspector pulls by uid, and the registry's namespace prefix
disambiguates the source dataset. So selecting any UNAV node and
clicking *Inspect Selected Object* reaches the right record
regardless of which JSONL it came from.

For a JPL body the **identity** section shows the body name and
the `JPL Horizons` source label; the **astrometry** section
shows RA/Dec/distance derived from the heliocentric vector; the
raw JSON section shows the full `metadata_json` blob with
`epoch`, `center`, `vector_au`, `vector_pc`, `distance_au`,
`distance_km`, and Horizons signature.

For a Gaia star the same panel shows G-mag, BP-RP, parallax with
its error, and the raw Gaia row.

The user does not have to know which dataset an object came
from to inspect it. The full record-by-uid lookup is
[`METADATA_INSPECTOR.md`](METADATA_INSPECTOR.md).

---

## 6. Scene sync, persistence, and route planning

All three v0.1+v0.2+v0.3 contracts continue to apply unchanged:

* **Sync Visible Sector** diffs the materialized set against the
  new filter result across **both** datasets and only adds /
  removes the delta. JPL bodies that fall out of the cone are
  removed; Gaia stars that newly enter are added.
* **Save UNAV State** writes the navigator + route + active
  datasets (Gaia and JPL together) + visual encoding into the
  C4D document and the sidecar JSON. Reopening the `.c4d`
  reloads both datasets.
* **Route planner** waypoints can mix Gaia stars and JPL bodies.
  The route spline draws a linear path through whatever set of
  objects the artist picks, regardless of origin.

---

## 7. What mixed scenes still don't do

* **No crossmatch.** UNAV does not reconcile a JPL body and a
  hypothetical Gaia row that happen to describe the same
  physical object — they remain two separate inspector entries.
* **No multi-epoch animation.** A mixed scene captures one
  Gaia subset at one query time and one JPL snapshot at one
  epoch. Re-fetch at a different epoch via the CLI to compare.
* **No automatic frame mismatch detection.** Both connectors
  emit ICRF (J2000) by contract, so frames already line up; if
  a future connector emits a different frame, the artist will
  see misregistered objects rather than a friendly error.
