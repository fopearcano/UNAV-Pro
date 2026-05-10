# UNAV Pro — Data Validation Reports

The v3.2 dataset audit machinery. How it works, what it
catches, and how the audit CLI uses it.

For the milestone overview see
[`V3_2_DATA_INTEGRITY.md`](V3_2_DATA_INTEGRITY.md).

---

## 1. The probes

Each probe is a small pure function over one row,
returning zero or more `ValidationIssue` records.

| Code | Severity | Trigger |
| --- | --- | --- |
| `missing_coordinates` | error | `ra_deg` / `dec_deg` missing or non-finite |
| `invalid_parallax` | warn | parallax ≤ 0 or > 10 000 mas |
| `missing_epoch` | warn | proper-motion set but no epoch in metadata |
| `invalid_redshift` | error / warn | z < 0 (error) or z > 15 (warn) |
| `duplicate_uid` | error | uid appears twice |
| `malformed_metadata_json` | error | `metadata_json` is not valid JSON object |
| `suspicious_distance` | warn / error | distance < 0 (error) or > 14.5 Gpc (warn) |
| `unsupported_units` | warn | provenance unit not in allowed set |
| `no_provenance` | info | row has no provenance record |

Severity is the v3.2 stable triplet:

* **info** — observation, no action needed.
* **warn** — likely caveat; check carefully.
* **error** — almost certainly wrong; fix the source.

## 2. The report

```python
@dataclass
class ValidationReport:
    counts: ValidationCounts
    issues: list[ValidationIssue]
    provenance: ProvenanceSummary | None
    notes: list[str]
```

`counts` is the aggregate the dialog renders;
`issues` is the full per-row finding list;
`provenance` is the v3.2 summary (omittable).

## 3. Running the validator

```python
from data.validation_report import validate_objects

report = validate_objects(rows)
if report.has_issues():
    print(report.short_summary())
    print(report.render_markdown())
```

`include_no_provenance_probe=False` skips the
info-level "no provenance" issue (the dialog
typically wants this on, the test suite typically
wants it off).

`include_provenance_summary=False` skips the
summary aggregation when you only need the per-row
findings.

## 4. The audit CLI

```bash
python tools/audit_dataset.py \
    --input data/catalogs/gaia_sample.jsonl \
    --output reports/gaia_sample_audit.md \
    --json-output reports/gaia_sample_audit.json
```

Flags:

* `--input / -i` (required) — JSONL catalog path.
* `--output / -o` — Markdown report path. Default:
  `<input>.audit.md`.
* `--json-output` — Optional JSON sidecar with the
  full report.
* `--include-no-provenance` — Emit the info-level
  "no provenance" issues. Off by default.
* `--max-rows N` — Stop after N rows; useful for
  spot checks.
* `--quiet` — Suppress stdout output.

Exit code: `0` on success or warnings-only; `1` on
any error-severity issue; `2` on missing input.

## 5. The Markdown report

Five sections:

1. **Header** — short summary (`audit ok` or
   `N issues across X/Y rows`).
2. **Provenance summary** — distinct sources,
   connectors, coordinate systems, fetch range,
   aggregated limitations.
3. **Counts** — totals + by-severity + by-code.
4. **Issues** — grouped by code; up to 50 per code
   shown verbatim; the rest collapsed.
5. **Notes** — free-form notes from the report
   (rare in v3.2; reserved for future probes).

## 6. The export-summary

```python
report.export_summary()
```

Compact dict suitable for embedding in an export
package's manifest. Counts only — no issue list, so
the manifest stays small.

## 7. Tests

* `test_v32_validation` covers each probe with
  positive + negative cases.
* `test_v32_audit_cli` exercises the CLI's pure
  helpers (argument parsing, streaming, exit
  codes) without spawning subprocesses.

## 8. Anti-patterns

* **Don't gate ingestion on the audit.** UNAV's
  v3.2 philosophy is "always show; never silently
  pass." Catalog rows that flunk a probe still
  load — the report just tells the artist what to
  be skeptical of.
* **Don't run the audit per-row inside a tight
  loop.** It walks the whole row sequence twice
  (once for issues, once for provenance summary).
  Run it once per dataset, not per visible-sector
  sync.
