# UNAV Pro — v3.2 Data Integrity & Provenance

The v3.2 milestone is about **production-grade data
integrity**. The goal: make UNAV trustworthy when handling
real astronomical data, coordinates, epochs, metadata, and
exports.

This is **not** rendering. **Not** new authoring surfaces.
The runtime feature surface is unchanged from v3.1; v3.2
adds the **provenance + validation layer** under which the
existing data pipeline operates.

For deep dives see:

* [`DATA_PROVENANCE.md`](DATA_PROVENANCE.md) — the
  v3.2 provenance record + how connectors stamp it.
* [`DATA_VALIDATION_REPORTS.md`](DATA_VALIDATION_REPORTS.md)
  — the validation rules + report shape + audit CLI.
* [`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md)
  — the documented caveats UNAV embeds in every
  package.

---

## 1. What changed at a glance

| Surface | v3.1 | v3.2 |
| --- | --- | --- |
| Catalog provenance | implicit (catalog_source string) | structured `ProvenanceRecord` in `metadata_json["provenance"]` |
| Dataset audit | none | `validate_objects(...)` + Markdown / JSON reports |
| Audit CLI | none | `tools/audit_dataset.py` |
| Metadata inspector | nine-section summary | + provenance section + validation findings |
| Export package manifest | coordinate convention + units | + provenance summary + audit summary + known limitations |

Every change is **additive**. v3.1 saves and exports
load cleanly in v3.2; the new fields are optional.

## 2. New modules

* `unav_pro/data/provenance.py` — `ProvenanceRecord`,
  `attach_provenance`, `read_provenance`,
  `summarise_provenance`.
* `unav_pro/data/validation_report.py` —
  `validate_objects` + `ValidationReport`,
  `ValidationIssue`, `ValidationCounts`. Probes:
  missing coordinates, invalid parallax, missing
  epoch, invalid redshift, duplicate uid, malformed
  metadata, suspicious distance, unsupported units.
* `unav_pro/knowledge/provenance_view.py` —
  `build_provenance_view(obj)` returns the inspector
  block for one row.
* `tools/audit_dataset.py` — CLI runner.

## 3. Module extensions

* `unav_pro/data/__init__.py` re-exports the v3.2 API.
* `unav_pro/export/export_package.py::PackageManifest`
  gains four self-describing fields:
  `provenance_summary`, `audit_summary`,
  `coordinate_conventions`, `known_limitations`.

## 4. Acceptance criteria

* [x] **Datasets can be audited.** Both via the
  `validate_objects(...)` API and via the
  `tools/audit_dataset.py` CLI.
* [x] **Provenance is visible.** Inspector renders
  the v3.2 provenance block for every row that
  carries one. Connectors that stamp records via
  `build_record(...)` get their data displayed
  immediately.
* [x] **Warnings are clear.** Each issue carries a
  stable `code`, a `severity` band (info / warn /
  error), and a human-readable `detail`. The
  Markdown renderer groups by code.
* [x] **Exports are scientifically self-describing.**
  Manifests embed the provenance summary, audit
  summary, coordinate conventions, and known
  limitations.
* [x] **Invalid data does not silently pass.** The
  audit CLI exits non-zero on errors. The inspector
  surfaces every per-row finding alongside the v1.3
  classification.
* [x] No renderer assumptions, no IPC.

## 5. What v3.2 is **not**

* Not a hard validator. The audit produces
  *reports*, not blocking errors. Catalog rows that
  flunk a probe still load; the report tells the
  artist what to be skeptical of.
* Not a fix-it tool. v3.2 surfaces problems but
  doesn't rewrite catalogs. Data hygiene happens
  upstream (in the connector or in the catalog
  vendor's pipeline).
* Not astropy. The probes are deliberately coarse —
  unit recognition is a small allowlist; redshift
  bounds are sanity checks, not cosmology.
  See [`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md)
  for the full list of caveats.

## 6. Testing

* Full suite passes: **2032 v3.1 baseline + new v3.2
  tests** covering provenance round-trip,
  validation probes, the audit CLI's pure helpers,
  and the export-package manifest round-trip.
