# UNAV Pro — NOTICE

UNAV Pro is licensed under the **Apache License, Version 2.0**;
see [`LICENSE`](LICENSE) for the full text.

This NOTICE file is provided as required by Apache 2.0 §4(d) and
records:

* the copyright + attribution for UNAV Pro itself;
* the third-party data sources whose conventions UNAV reads;
* any bundled sample data and how it was generated.

Read [`docs/DATA_SOURCE_ATTRIBUTION.md`](docs/DATA_SOURCE_ATTRIBUTION.md)
for the per-source citation + license details. Read
[`docs/SCIENTIFIC_LIMITATIONS.md`](docs/SCIENTIFIC_LIMITATIONS.md)
for the canonical caveats UNAV embeds in every export package.

---

## 1. UNAV Pro

```
UNAV Pro — Cinema 4D Universal Navigator
Copyright 2026 UNAV Pro contributors
Licensed under the Apache License, Version 2.0
```

UNAV Pro is **not** affiliated with Maxon Computer GmbH, Cinema
4D, the Gaia mission, the SDSS / DESI collaborations, or
NASA / JPL. The plug-in reads the public data conventions those
projects publish; their respective licenses + attribution
requirements continue to apply when their data is used inside
UNAV.

## 2. Cinema 4D

UNAV Pro is a third-party plug-in for **Maxon Cinema 4D 2023+**.
Cinema 4D is a registered trademark of **Maxon Computer GmbH**;
UNAV Pro uses Cinema 4D's public Python API and ships no Maxon
code or assets.

## 3. Data sources (no data redistributed)

UNAV's connectors read public catalog data on demand. The plug-in
does **not** redistribute any third-party catalog data. The full
attribution + citation requirements for each source are tracked
in [`docs/DATA_SOURCE_ATTRIBUTION.md`](docs/DATA_SOURCE_ATTRIBUTION.md).
Summary:

* **Gaia DR3** — European Space Agency / Gaia Data Processing
  and Analysis Consortium. Use of Gaia data requires citation
  per the Gaia mission's data-release policy.
* **SDSS DR18** — Sloan Digital Sky Survey collaboration. Use
  of SDSS data requires the standard SDSS acknowledgement.
* **DESI EDR** — Dark Energy Spectroscopic Instrument
  collaboration. Use of DESI data requires the DESI EDR
  citation.
* **JPL Horizons** — NASA Jet Propulsion Laboratory.
  Solar-system body ephemerides are public data.

When you publish or distribute work made with UNAV that draws on
any of these sources, **you** are responsible for including the
appropriate citation. UNAV's `data/provenance.py` records the
source + connector version on every imported row so the
citation surfaces automatically in the export package's
manifest (v3.2 self-describing contract).

## 4. Bundled sample data

The release zip ships two tiny synthetic sample datasets:

* `samples/minimal_unav_demo/catalog.jsonl` — five rows of
  synthetic demo data, **not** sourced from any real catalog.
* `samples/internal_beta_demo/datasets/gaia_demo.jsonl` —
  five rows of synthetic Pleiades-region data **modelled
  after** Gaia DR3 conventions (RA, Dec, parallax in mas).
  The values are illustrative; **not** real Gaia
  measurements.
* `samples/internal_beta_demo/datasets/jpl_demo.jsonl` —
  three rows (Mercury, Earth, Mars) **modelled after** JPL
  Horizons conventions at a single demo epoch. The values
  are illustrative; **not** real JPL ephemerides.

Both demo datasets are **synthetic / illustrative**. They are
suitable for testing the plug-in workflow; they are **not**
suitable for science work. See
[`samples/internal_beta_demo/README.md`](samples/internal_beta_demo/README.md)
and [`samples/minimal_unav_demo/README.md`](samples/minimal_unav_demo/README.md).

## 5. Third-party Python code

UNAV Pro's runtime is **stdlib-only**. The plug-in does **not**
bundle, link, or import:

* `numpy`, `astropy`, `astroquery`, `pandas`, `scipy`,
  `matplotlib`,
* any external HTTP client other than `urllib`,
* any external rendering library,
* any C / C++ extension at runtime.

The offline preprocessing tools under `tools/` use `pytest`
during testing only.

## 6. Trademarks

* "Cinema 4D" is a trademark of Maxon Computer GmbH.
* "Gaia" is a mission name owned by the European Space Agency.
* "SDSS" is a trademark of the Sloan Digital Sky Survey
  collaboration.
* "DESI" is a trademark of the DESI collaboration.
* "JPL" and "NASA" are trademarks / agency identifiers of
  the United States government.

UNAV Pro uses these names only to describe data conventions
read by the plug-in's connectors. UNAV Pro is not endorsed by
any of these organisations.

## 7. Disclaimer

UNAV Pro is provided **as-is**, without warranty of any kind
(see Apache 2.0 §7 in [`LICENSE`](LICENSE)). UNAV Pro is a
**visualisation tool**, not a scientific instrument. Do not
cite UNAV measurements in publications; cite the upstream
catalog and use UNAV to communicate the results visually.

For the canonical out-of-scope list see
[`docs/ROADMAP.md`](docs/ROADMAP.md) §4.
