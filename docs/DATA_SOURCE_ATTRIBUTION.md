# UNAV Pro — Data Source Attribution

UNAV Pro reads public astronomical catalog data. The
plug-in **does not redistribute** that data; it provides
connectors that fetch on demand and writes UNAV-format
JSONL rows from the response.

When you publish or distribute work that uses any of these
sources through UNAV, **you** are responsible for including
the citation each project requires. UNAV's v3.2
provenance system stamps every imported row with the
source + connector + fetch timestamp, and the v2.3
export-package manifest aggregates that into a
`provenance_summary` field — so the citation surfaces
in the artefact you ship.

For the legal + IP framing see [`NOTICE.md`](../NOTICE.md).
For the science caveats see
[`docs/SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md).

---

## 1. Gaia DR3 (European Space Agency)

**Source.** Gaia mission, Data Release 3 (Gaia DR3).
Operated by the European Space Agency (ESA) and the Gaia
Data Processing and Analysis Consortium (DPAC).

**UNAV connector.** `unav_pro/data/connectors/gaia_connector.py`
queries the Gaia ESA archive's TAP endpoint
(`gaiadr3.gaia_source`) with an ADQL cone-search.

**Citation requirement.** Per ESA's Gaia data release
policy, any publication using Gaia DR3 data must cite:

* Gaia Collaboration et al. (2023), *Gaia Data Release 3.
  Summary of the content and survey properties*.
* The original Gaia mission paper.

The ESA Gaia archive's website hosts the canonical citation
text + BibTeX entry; UNAV does not duplicate that here so
the citation never gets stale.

**License.** Gaia data is distributed under the standard
ESA / Gaia mission terms — free for scientific and
educational use, with attribution.

**Rate limits.** The TAP endpoint applies per-IP rate
limits. UNAV's `gaia_connector` defaults to a 1° / 5 000-
row cone, well below the limits. Heavier queries are the
artist's responsibility.

## 2. SDSS DR18 (Sloan Digital Sky Survey)

**Source.** Sloan Digital Sky Survey, Data Release 18
(SDSS DR18). Operated by the SDSS collaboration.

**UNAV connector.** `unav_pro/data/connectors/sdss_connector.py`
queries the SDSS DR18 SQL endpoint (CrossID-style cone
search).

**Citation requirement.** The SDSS collaboration publishes
a standard acknowledgement template
(`https://www.sdss.org/collaboration/citing-sdss/`).
Publications using SDSS data must include both:

* the SDSS DR18 reference paper, and
* the standard SDSS acknowledgement paragraph.

UNAV does not embed the paragraph (it changes between
data releases); link to the SDSS site in your publication
or export package's `notes`.

**License.** SDSS data is freely available under SDSS's
data policy, with attribution.

## 3. DESI EDR (Dark Energy Spectroscopic Instrument)

**Source.** DESI Early Data Release (EDR). Operated by the
DESI collaboration.

**UNAV connector.** `unav_pro/data/connectors/desi_connector.py`
queries DESI's public catalog endpoints.

**Citation requirement.** Publications using DESI EDR data
must cite the DESI EDR overview paper plus the DESI
collaboration's standard acknowledgement.

**License.** DESI EDR is publicly released under the
collaboration's data-release policy, with attribution.

## 4. JPL Horizons (NASA / Jet Propulsion Laboratory)

**Source.** JPL Horizons system. Operated by NASA's Jet
Propulsion Laboratory.

**UNAV connector.** `unav_pro/data/connectors/jpl_horizons_connector.py`
queries the JPL Horizons system's API for solar-system body
ephemerides at a given epoch.

**Citation requirement.** JPL Horizons output is U.S.
Government public data and does not require formal
citation in most contexts. For scientific use, follow JPL's
Horizons documentation for the recommended acknowledgement.

**License.** JPL Horizons output is in the public domain
(U.S. Government work).

## 5. Bundled sample data

UNAV ships two **synthetic** demo datasets in the release
zip. They are **not** real catalog data; they exist so
testers can exercise the workflow without a network round-
trip.

* `samples/minimal_unav_demo/catalog.jsonl` — five rows
  of generic demo data. Not modelled on any real catalog.
* `samples/internal_beta_demo/datasets/gaia_demo.jsonl` —
  five rows **modelled after** Gaia DR3 conventions (RA,
  Dec, parallax in mas, color index, vega magnitude). The
  numeric values are **illustrative**, not real Gaia
  measurements.
* `samples/internal_beta_demo/datasets/jpl_demo.jsonl` —
  three rows **modelled after** JPL Horizons solar-system
  body conventions at a single demo epoch. The numeric
  values are **illustrative**, not real JPL ephemerides.

Each demo file's `metadata_json` carries a v3.2
provenance record that names the source as
`"Gaia DR3 (demo)"` / `"JPL Horizons (demo)"` /
`"UNAV Demo"` so it can never be confused with real data
once it lands in an export package.

The total size of every bundled sample file is well under
**32 KB**.

## 6. Citation in your output

When you publish or distribute work made with UNAV that
draws on any of these sources, include the source's
required citation. UNAV's v2.3 export package manifest
makes this easy:

* The `provenance_summary` field lists every distinct
  source + connector that contributed to the package.
* The `known_limitations` field carries the caveats from
  the connector (e.g. *"negative parallax rows yield no
  distance"*).
* The `coordinate_conventions` field documents the
  coordinate system (`ICRS Cartesian parsec`).

Use those fields as the starting point for your formal
citation; the export package itself isn't a substitute
for a citation in your paper / video credits.

## 7. Updating attribution

If a data source's citation requirement changes:

1. Update the relevant section in this document.
2. If the connector still produces correct data,
   bump only the connector's `connector_version` in the
   provenance record.
3. If the data shape changed, treat it as a connector
   schema bump and follow the v3.2 provenance schema-
   version policy.

## 8. Removed / deprecated sources

None as of v3.5. Future deprecations land in
[`docs/KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) before
they're removed from this document.
