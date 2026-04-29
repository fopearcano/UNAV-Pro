# UNAV Pro — Gaia Query Limits and Safety

The hard caps and advisory warnings the Gaia connector enforces.
These are deliberately conservative: the public ESA archive is a
shared resource, and a typo'd `--limit` can otherwise pull
millions of rows.

For the full Gaia workflow this is part of, see
[`V0_3_GAIA_DR3_WORKFLOW.md`](V0_3_GAIA_DR3_WORKFLOW.md). For the
generic catalog-vs-scene safety system, see
[`LARGE_DATA_SAFETY.md`](LARGE_DATA_SAFETY.md).

---

## 1. Hard caps (refused at construction)

`GaiaQuery.__post_init__` rejects out-of-range parameters with a
`ValueError`. The CLI translates that into exit code **2**.

| Parameter        | Hard limit                       | Where defined (in `gaia_connector.py`) |
|------------------|----------------------------------|----------------------------------------|
| `ra_deg`         | `[0, 360)`                       | constructor.                           |
| `dec_deg`        | `[-90, 90]`                      | constructor.                           |
| `radius_deg`     | `(0, 30]` — see `MAX_RADIUS_DEG` | constructor.                           |
| `limit`          | `(0, 100 000]` — see `MAX_ROW_LIMIT` | constructor.                       |
| `release`        | One of `gaia_dr3` / `gaia_dr2`   | `_RELEASE_TO_TABLE`.                   |

The radius ceiling exists because the brightest-first row cap
(`ORDER BY phot_g_mean_mag ASC`) is only meaningful within a
modest cone — beyond ~30° the result becomes "the brightest stars
in a quarter of the sky", which is not what the user usually
asks for.

The 100 000-row hard cap is also the upper bound the rest of the
plugin trusts. The chunked spatial index, the visible-sector
streaming layer, and the safety system all agree on it.

---

## 2. Soft warnings (printed on stderr; query proceeds)

These are advisory only — the CLI runs the query and writes the
output, but emits a warning so the operator knows they're in
heavy territory.

| Trigger                              | Threshold (in `gaia_connector.py`) | Message                                                                |
|--------------------------------------|------------------------------------|------------------------------------------------------------------------|
| `limit > SOFT_LIMIT_WARNING`         | 50 000                             | "limit=… is large… consider tightening --radius-deg or building a spatial index immediately afterwards." |
| `radius_deg > SOFT_RADIUS_WARNING_DEG` | 5°                               | "radius_deg=… is wide… for sky surveys, prefer multiple smaller cones or HEALPix tiling." |

`soft_warnings(query)` returns the messages as a `List[str]`. The
CLI prints each one on stderr; the
`fetch_normalize_and_write` helper carries them on
`FetchAndWriteReport.warnings` for programmatic callers.

---

## 3. Parallax-to-distance safety

`safe_parallax_to_distance(parallax_mas, parallax_error_mas, snr_min,
distance_pc_max)` returns `None` (no derived distance) for any of
these conditions:

* `parallax_mas` is missing or ≤ 0 (negative-parallax noise).
* `parallax_error_mas` is provided and `parallax / error <
  snr_min` (the SNR cut; default 5σ; CLI `--parallax-snr-min` /
  `--no-parallax-cut`).
* The implied distance exceeds `distance_pc_max` (default
  100 kpc); beyond that, naive `1000/parallax` inversion diverges
  significantly from cosmology-aware comoving distance and is
  misleading.

In every "no derived distance" case the row still flows through:
`parallax_mas` is preserved verbatim, `distance_parsec` is
`None`, and the schema's placeholder-sphere fallback applies at
compute-derived time so the rest of the pipeline stays
well-defined.

---

## 4. Network and HTTP failures

The connector wraps `urllib.request.urlopen` and translates every
failure into a `GaiaQueryError`:

| Source                                  | Behavior                                                              |
|-----------------------------------------|-----------------------------------------------------------------------|
| `URLError` (network down, DNS failure)  | `GaiaQueryError("Gaia TAP network error: …")`. CLI exits 3.           |
| `HTTPError` 4xx / 5xx                   | `GaiaQueryError` with status + first 300 chars of the body. CLI 3.    |
| 200 OK with non-CSV body                | `_parse_csv` returns an empty iterator. CLI prints `warning: query returned 0 usable rows`. Exit 0. |
| 200 OK with rows missing required cols  | Each affected row is logged and skipped at normalize time.            |

The connector does **not** retry on transient errors. Adding
exponential backoff is a small change to `_http_fetch` once we
have rate-limit data from real-world use; deferred by design so
HTTP 429 / 503 outages aren't masked.

---

## 5. Output-side safety

* **No `metadata_json` blob is embedded in C4D objects by
  default.** The full Gaia row stays in the catalog file; the
  inspector reads it from the lookup at view time. See
  `LARGE_DATA_SAFETY.md` §4 for the minimal-marker policy.
* **No huge catalog reaches Cinema 4D.** When the registered
  catalog is unindexed and above
  `dataset_size_warning` (1 000 000 rows by default), the
  streaming path emits an explicit warning recommending **Build
  Index**. Above `hard_full_load_ceiling` (5 000 000 rows) the
  streamer refuses outright and the scene is untouched. See
  `V0_2_SECTOR_STREAMING_WORKFLOW.md` §6 and `core/safety.py`.
* **Visible-sector-only mode is the C4D-side default.** The
  navigator's cone is what bounds the working set; without a
  navigator, generation is blocked.

---

## 6. Citation

Gaia data are released under the ESA license at
<https://www.cosmos.esa.int/web/gaia-users/archive/gaia-data-release-3-license>.
Recipients of UNAV Pro outputs derived from Gaia DR3 must cite
the Gaia mission per the archive's published guidance — UNAV Pro
preserves the source IDs and release tag in `metadata_json` so
attribution is straightforward.
