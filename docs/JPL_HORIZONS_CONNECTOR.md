# UNAV Pro — JPL Horizons Connector

Static-point connector for solar-system bodies, spacecraft, and small
bodies using NASA/JPL's public Horizons web API. Fetches one body at
one epoch and writes a UNAV-format JSONL catalog with a single row.

Companion to:

  * `UNAV_PRO_DATA_PIPELINE.md` §5 (solar-system handling)
  * `GAIA_CONNECTOR.md` (the same adapter pattern, different source)

---

## 1. Scope

  * **One body per call.** No batch / vectorized requests; spacecraft
    constellations and asteroid surveys go through repeated CLI
    invocations or a future per-source bulk path.
  * **One epoch per call.** Static point at the requested time. Live
    animation, time-axis playback, and SPK-kernel ephemerides are
    explicit non-goals for this MVP — see
    `UNAV_PRO_DATA_PIPELINE.md` §5.
  * **Heliocentric ICRF (J2000) Cartesian.** The connector requests
    `EPHEM_TYPE='VECTORS'` with `CENTER='@10'` and
    `REF_PLANE='FRAME'`. Heliocentric is the natural frame for solar-
    system rendering — distances are physically meaningful, the frame
    is stable across bodies, and the resulting (X, Y, Z) maps
    directly onto the schema's Cartesian columns after a units
    conversion.
  * **No credentials.** The Horizons web API is public; UNAV
    identifies itself with a User-Agent string and otherwise issues
    a vanilla HTTPS GET.
  * **No heavy dependencies.** Stdlib only — `urllib`, `json`, `re`,
    `math`, `dataclasses`. No `astroquery`, no `astropy`.

Object types supported by the CLI (`--object-type`):

| Type         | Typical body             |
|--------------|--------------------------|
| `planet`     | Mercury, Venus, Mars …   |
| `moon`       | Europa, Phobos, Charon … |
| `asteroid`   | Ceres, Apophis, Vesta …  |
| `comet`      | Halley, NEOWISE …        |
| `spacecraft` | Voyager 1, JWST, Juno …  |

The schema's full `OBJECT_TYPES` list is broader; the CLI restricts
to these five because they are the meaningful Horizons categories.

---

## 2. CLI

`tools/fetch_jpl_body.py` is the canonical entry point. It bootstraps
the plugin's `unav_pro/` directory onto `sys.path` and runs without
Cinema 4D installed.

```bash
python tools/fetch_jpl_body.py \
    --body "Mars" --epoch "2026-01-01" \
    --output data/jpl_mars.jsonl
```

| Flag             | Default      | Notes                                                                 |
|------------------|--------------|-----------------------------------------------------------------------|
| `--body`         | required     | Body designation. Names, NAIF IDs, or any string Horizons resolves.   |
| `--epoch`        | required     | ISO date `YYYY-MM-DD`, or anything Horizons accepts (JD, calendar).   |
| `--output`       | required     | Output JSONL path; parents are created.                               |
| `--center`       | `@10` (Sun)  | Horizons observer designation. `@0` = SSB, `500@399` = Earth.         |
| `--object-type`  | `planet`     | One of `planet`, `moon`, `asteroid`, `comet`, `spacecraft`.           |
| `--quiet`        | off          | Suppress the summary line.                                            |

Exit codes:

  * **0** — success (one row written).
  * **2** — invalid argument (empty body / epoch, unknown object
    type, etc.).
  * **3** — Horizons archive failure (network, HTTP, ambiguous body,
    no match, malformed response). The error text always includes
    enough context to know whether to retry or refine the body name.

Multiple-match handling: Horizons sometimes responds with a list of
candidates instead of an ephemeris (e.g. ``Mars`` matches both
``Mars Barycenter`` (4) and ``Mars`` (499)). The connector detects
that response, raises `JPLHorizonsError`, and the CLI prints the
candidate excerpt so the operator knows to re-run with a NAIF ID
or a more specific name.

---

## 3. UNAV mapping

Implemented in `parse_response` in
`unav_pro/data/connectors/jpl_horizons_connector.py`.

| UNAV field          | Source                                                        |
|---------------------|---------------------------------------------------------------|
| `uid`               | `jpl_horizons:<slug(body)>@<slug(epoch)>` (filesystem-safe).  |
| `catalog_source`    | `jpl_horizons`.                                               |
| `object_type`       | From the caller (`--object-type`).                            |
| `name` / `common_name` | The body designation as supplied.                          |
| `ra_deg` / `dec_deg`   | Derived from the heliocentric ICRF (X, Y, Z) vector.       |
| `distance_parsec`   | `sqrt(X² + Y² + Z²)` × AU→pc.                                 |
| `metadata_json`     | Raw vector + epoch + center + ref plane + Horizons signature. |

The schema's `compute_derived_fields` is what then populates
`cartesian_*` and `c4d_*` from the spherical fields at index / load
time, exactly as for any other catalog row. The connector itself
intentionally only emits the spherical representation; doing so keeps
solar-system bodies on the same code path as Gaia rows for every
downstream consumer.

`metadata_json` always includes:

```json
{
  "body": "Mars",
  "epoch": "2026-01-01",
  "center": "@10",
  "ref_plane": "ICRF",
  "out_units": "AU-D",
  "vector_au": {"X": 1.5, "Y": 0.0, "Z": 0.0},
  "vx_au_per_d": ...,
  "vy_au_per_d": ...,
  "vz_au_per_d": ...,
  "lt": ...,
  "rg": ...,
  "horizons_signature": {"source": "...", "version": "..."}
}
```

The state vector and light-time / range entries are recorded
verbatim so a future inspector or animation system can drive
interpolation without re-querying Horizons.

---

## 4. Coordinate frame

  * **Reference plane:** `FRAME` → ICRF / J2000 axes. Not the
    ecliptic; not body-mean-of-date. This matches the rest of UNAV's
    canonical ICRS Cartesian convention so heliocentric positions
    can be combined with Gaia stars in a single scene without
    reprojection.
  * **Units:** `AU-D` (astronomical units / day). Distances are
    converted to parsec inside the connector using
    ``1 AU = π / 648 000 pc`` (IAU 2012/2015 definition); the
    constant is exposed as ``AU_TO_PC`` for downstream consumers.
  * **Origin:** the requested observer center (default `@10` = Sun).
    If the caller wants a geocentric apparent position they pass
    `--center 500@399`; the schema's spherical fields reflect that
    choice unchanged.

The connector always returns positions in **the requested center's
frame**. There is no implicit conversion to barycentric; the operator
is expected to know which frame they asked for, and it is recorded
in `metadata_json["center"]`.

---

## 5. Failure modes

| Situation                          | Behavior                                              |
|------------------------------------|-------------------------------------------------------|
| Empty `body` / `epoch`             | `ValueError` at `JPLBodyQuery` construction; CLI exits 2. |
| Network down / HTTP error          | `JPLHorizonsError`; CLI exits 3.                      |
| Response is not JSON               | `JPLHorizonsError("not valid JSON")`; CLI exits 3.    |
| Ambiguous body designation         | `JPLHorizonsError("…ambiguous; refine the name…")`; the message includes a candidate excerpt. |
| `No matches found`                 | `JPLHorizonsError("…no body matching…")`.             |
| `$$SOE` / `$$EOE` block missing    | `JPLHorizonsError("…did not contain a \$\$SOE/\$\$EOE block")`. |
| `X` / `Y` / `Z` label missing      | `JPLHorizonsError("…missing 'X'…")` with block excerpt. |

The connector does **not** retry on transient archive errors. Adding
exponential-backoff retries is a small, local change to
`_http_fetch`; deferred until we have rate-limit data.

---

## 6. Testing

`unav_pro/tests/test_jpl_horizons_connector.py` covers the connector
with **no network access** — every test injects a `fetch_fn` that
returns a hand-crafted JSON payload with a synthetic Horizons text
block.

  * `JPLBodyQuery` validation — empty body/epoch, unknown object
    type, each documented type accepted, default object type.
  * `effective_stop` defaulting and override.
  * Request params — quoted strings, format/center/ref-plane/units.
  * `fetch_response` — round-trip with injected fetcher, invalid
    JSON, fetcher exception propagation.
  * `parse_response` vector geometry — on-axis, +Z pole, 45° in the
    XY plane, negative-Y wraps RA to positive.
  * `parse_response` metadata — vectors, light-time, range, signature
    preserved in `metadata_json`.
  * `parse_response` UID — filesystem-safe slugging of body and
    epoch (`Voyager 1` → `Voyager_1`).
  * Error paths — no `result` key, missing SOE/EOE block, missing
    XYZ label, multiple-match excerpt, no-match.
  * `fetch_and_normalize` end-to-end with a mocked payload returns a
    `CatalogObject` with positive distance.

Integration tests against the live Horizons archive are out of scope
for the unit-test suite; they belong in a separate `tools/qa/` script
run on demand.

---

## 7. Roadmap

  * **Time-series.** A future `fetch_trajectory(query, samples)`
    will return one `CatalogObject` per sample (or a single object
    with an animated position track) for the `time axis` slider
    described in `UNAV_PRO_ARCHITECTURE.md` §3.6. Live animation in
    the C4D viewport is deliberately deferred until the static path
    is exercised.
  * **SPK kernels.** Per the production plan, large solar-system
    asset packs will be backed by SPK files instead of one-shot
    Horizons queries. The connector signature stays the same; the
    fetcher backend swaps.
  * **Quality flags.** Horizons returns light-time and target-error
    info that we currently log but don't surface as schema fields.
    Adding them is a one-commit change.
  * **Multiple-match disambiguation.** Today the connector raises;
    the CLI could instead print the candidate list and offer to
    pick one. Deferred until artist feedback arrives.

The connector is intentionally minimal. It exists to validate the
solar-system code path end-to-end before the more complex pieces
(time axis, kernels, animated TP / matrix render) come online.
