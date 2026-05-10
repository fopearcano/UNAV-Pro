# UNAV Pro v3.2 — Data Integrity & Provenance

Release date: 2026-05-10
Codename: *Data Integrity & Provenance*

v3.2 is the **production validation and scientific data
integrity** milestone. The goal: make UNAV trustworthy
when handling real astronomical data, coordinates,
epochs, metadata, and exports.

This is **not** rendering. **Not** new authoring surfaces.
The v3.1 runtime surface is preserved byte-identical;
v3.2 adds a layer of scaffolding underneath that makes
every catalog row, every inspector view, and every
export package self-describing.

---

## Highlights

* **Data provenance system.** New
  `unav_pro/data/provenance.py` defines
  `ProvenanceRecord` (catalog source, query
  parameters, fetch timestamp, connector + version,
  normalisation version, original field names,
  coordinate system, units, known limitations).
  Connectors stamp records into
  `metadata_json["provenance"]`; the inspector reads
  them back; the audit CLI summarises them.
* **Validation reports.** New
  `unav_pro/data/validation_report.py` provides a
  `validate_objects(...)` walker that runs eight
  probes per row (missing coordinates, invalid
  parallax, missing epoch, invalid redshift,
  duplicate uid, malformed metadata, suspicious
  distance, unsupported units) plus a "no
  provenance" info-level probe. Reports render as
  Markdown and / or JSON.
* **Dataset audit CLI.** New
  `tools/audit_dataset.py` runs the validator
  against a JSONL catalog and emits a Markdown
  report plus an optional JSON sidecar. Exit codes:
  `0` clean / warnings only, `1` errors,
  `2` missing input.
* **Metadata inspector upgrade.** New
  `unav_pro/knowledge/provenance_view.py` produces
  the inspector block showing the row's
  provenance (catalog source / connector / units /
  coordinate system / known limitations) plus the
  per-row validation findings.
* **Export package integration.**
  `PackageManifest` gains four self-describing
  fields: `provenance_summary`, `audit_summary`,
  `coordinate_conventions`, `known_limitations`.
  The on-disk `manifest.json` becomes a
  scientifically self-describing artefact a
  consumer can read without UNAV.

## What's new in detail

### Modules

* `unav_pro/data/provenance.py` (new) —
  `ProvenanceRecord`, `ProvenanceSummary`,
  `attach_provenance`, `read_provenance`,
  `summarise_provenance`, `build_record`.
* `unav_pro/data/validation_report.py` (new) —
  `ValidationIssue`, `ValidationCounts`,
  `ValidationReport`, `validate_objects`. Stable
  issue codes (`CODE_*`); severity bands
  (`info` / `warn` / `error`). Markdown +
  JSON renderers; compact `export_summary()`
  for embedding in package manifests.
* `unav_pro/knowledge/provenance_view.py` (new) —
  `InspectorProvenanceView`,
  `build_provenance_view(obj)`.
* `tools/audit_dataset.py` (new) — CLI runner.

### Module extensions

* `unav_pro/data/__init__.py` — re-exports the v3.2
  API.
* `unav_pro/export/export_package.py::PackageManifest`
  — gains `provenance_summary`,
  `audit_summary`, `coordinate_conventions`,
  `known_limitations`. Round-trip tests cover the
  full v3.2 shape; legacy v3.1 / v2.3 manifests load
  without any of these fields.

### Documentation

* `docs/V3_2_DATA_INTEGRITY.md` — milestone overview.
* `docs/DATA_PROVENANCE.md` — provenance record
  shape + connector usage.
* `docs/DATA_VALIDATION_REPORTS.md` — validation
  probes + report shape + audit CLI.
* `docs/SCIENTIFIC_LIMITATIONS.md` — the canonical
  list of caveats UNAV embeds in every package.

### Release engineering

* `PLUGIN_VERSION` 3.1.0 → 3.2.0; codename *Data
  Integrity & Provenance*.
* `RELEASE_NOTES_v3.2.md` (this file).
* CHANGELOG entry.
* Packaging script ships the four new docs +
  RELEASE_NOTES_v3.2.md; `REQUIRED_FILES` updated.

## What didn't change

* No new on-disk schemas for v0.x → v3.1 surfaces.
  Mission JSON, Route JSON, Camera Path JSON, DB
  schema, binary format are byte-identical to v3.1.
  The new `provenance` key under `metadata_json` is
  additive and ignored by older readers.
* No new runtime dependencies. Stdlib-only at
  runtime.
* No rendering, no IPC, no RelativityRender bridge.
* No threading. The v3.0 task queue is still
  cooperative single-threaded.
* No replacement of core architecture. v0.1 → v3.1
  authoring surfaces continue to work unmodified.

## Migration

* **Drop-in v3.1 upgrade.** v3.1 saves load cleanly
  in v3.2. No format change. Catalog rows missing
  `metadata_json["provenance"]` simply look like "no
  provenance" to the inspector.
* The new manifest fields are **opt-in**: a v3.1
  exporter that doesn't populate them produces the
  same `manifest.json` shape as before.
* Connectors that don't yet stamp provenance keep
  working; the audit CLI flags them with the
  info-level `no_provenance` finding (off by
  default).

## Acceptance

* [x] Datasets can be audited (`validate_objects` API
  + `tools/audit_dataset.py` CLI).
* [x] Provenance is visible (inspector renders the
  v3.2 block for every row that carries a record).
* [x] Warnings are clear (stable issue codes;
  severity-banded; Markdown grouped by code).
* [x] Exports are scientifically self-describing
  (manifest carries provenance + audit + coords +
  limitations).
* [x] Invalid data does not silently pass (audit CLI
  exits non-zero on errors; inspector surfaces
  per-row findings).
* [x] No renderer assumptions, no IPC.

## Testing

* Full suite passes: **2125 tests** (2032 v3.1
  baseline + 93 new v3.2 tests).
* New v3.2 test files:
  * `test_v32_provenance` — round-trip,
    malformed-metadata defence, attach/read,
    summary aggregator.
  * `test_v32_validation` — every probe with
    positive + negative cases, severity tiers,
    duplicate-uid detection, report rendering.
  * `test_v32_audit_cli` — CLI argument parser,
    end-to-end runs, exit codes.
  * `test_v32_export_integration` — manifest
    round-trip, end-to-end build with v3.2
    fields, on-disk JSON shape.
  * `test_v32_inspector_view` — inspector view
    rendering across with/without-provenance and
    finding-severity scenarios.

## Boundary, restated

UNAV Pro v3.2 is an **astronomical navigation + voyage /
camera-animation tool for Cinema 4D**, scaled for very
large catalogs (v3.0), organised for production projects
(v3.1), and trustworthy on real data (v3.2). Rendering,
IPC, real-time scientific simulation, online services,
and render-engine bridges remain explicitly out of
scope.

For the long-form view of the boundary see
[`docs/ROADMAP.md`](docs/ROADMAP.md) §4–§5.
