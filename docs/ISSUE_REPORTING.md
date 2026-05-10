# UNAV Pro — Issue Reporting

How to file a bug against the v3.5 public alpha.

For the canonical "what should I test" list see
[`PUBLIC_ALPHA_TESTING_GUIDE.md`](PUBLIC_ALPHA_TESTING_GUIDE.md).
For the v3.4 reset-tools recovery guide see
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) §11.

---

## 1. Before you file

Run through the v3.5 quick triage:

1. **Run the health check.**
   `Diagnostics → Run Health Check`. If a probe
   reports `[ERR]`, the bug may be that probe's
   subsystem.
2. **Check known limitations.** The
   [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md)
   list captures every "yes, we know" entry. If
   your symptom matches one, no need to file.
3. **Check the troubleshooting guide.**
   [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) covers
   the common install / startup / sync / metadata
   problems. The v3.4 reset tools recover most
   confused-state cases.
4. **Try a fresh workspace.** Some bugs only
   reproduce against a corrupted workspace; opening
   the bundled `samples/internal_beta_demo/` is the
   fastest fresh-state.

If after all four steps the bug is still there: file.

## 2. Build the issue report bundle

UNAV ships a one-click report builder. Open the
dialog and click:

> **Diagnostics → Create Issue Report**

The plug-in writes a Markdown file under
`~/.unav_pro/issue_reports/` with the timestamp in the
filename (e.g.
`issue_report_2026-05-10T1200Z.md`). The file
contains:

* UNAV Pro version + codename;
* Cinema 4D API + build version (when running
  inside the host);
* Python version + platform string + machine arch;
* the v3.1 workspace status (path, intact / not);
* the dataset-registry status (entry count + active
  count);
* the most recent `run_health_check()` rendering;
* the last 50 status-log lines (≤ 32 KB).

The bundle is **plain text**. It contains:

* No catalog row data.
* No mission JSONs.
* No scene file.
* No file paths outside your `.unav_pro/` config dir
  + the workspace root.

Read it before sending; redact anything you don't
want shared.

## 3. Filing the issue

UNAV Pro lives at the project's GitHub repository.
File an issue with:

* **Title** — one sentence describing the bug.
  *"Sync visible sector crashes when navigator's
  cone is wider than 90°"* not *"crash"*.
* **Body** — paste the issue-report bundle plus a
  short repro:
  1. What you did (steps).
  2. What you expected.
  3. What actually happened.
  4. Whether it reproduces consistently.
* **Labels** — pick one:
  * `bug` — something broken.
  * `regression` — worked in a previous release.
  * `feature-request` — a new feature (read the
    out-of-scope list first; rendering / IPC are
    permanent **no**s).
  * `docs` — documentation gap.

## 4. The seven-line repro template

If you don't know what to write:

```
Steps:
1. (your first step)
2. ...

Expected: (what you thought would happen)
Got:      (what actually happened)
Repro:    (every time / sometimes / once)
```

Followed by the issue-report bundle in a Markdown
fenced block.

## 5. What we don't want in the report

* The full status log if it's longer than what the
  v3.5 bundler trims to (the bundler caps at 50
  lines / 32 KB; that's enough).
* Your full `.c4d` scene file — the bundler doesn't
  include it; please don't attach it unless we ask.
* Your full catalog JSONL — same.
* Sensitive paths, credentials, or proprietary
  scene data. The v3.5 issue-report bundle never
  includes any of these by design.

## 6. Triage timing

The public alpha is **community-supported**. Triage
turn-around varies; please be patient. Critical
crashes rise to the top.

When the maintainers respond, they may ask for:

* a smaller repro (e.g. a synthetic dataset that
  triggers the bug);
* a screenshot of the C4D Object Manager state;
* the `manifest.json` of an export package (safe —
  contains no row data).

## 7. Severity

We use four severity buckets:

* **Critical** — Cinema 4D hangs / crashes; data
  loss. Top priority.
* **High** — feature unusable; significant
  workflow blocker.
* **Medium** — workflow friction; specific
  workarounds exist.
* **Low** — typo / wording / cosmetic.

Use your best judgement. A maintainer will adjust
if needed.

## 8. Privacy

UNAV Pro is **offline-first**. The plug-in opens no
sockets; the issue-report bundle is **not**
auto-uploaded. You are in control of what goes
where.

The bundler never reads:

* The active C4D scene's geometry.
* Catalog JSONLs.
* Mission / route / presentation JSONs (only their
  *count* via the workspace + manifest).
* Files outside `.unav_pro/` and the active
  workspace root.

If you spot a privacy regression in the bundler, that
is itself a release-blocker bug — please file
immediately.

## 9. Cross-reference

* [`PUBLIC_ALPHA_TESTING_GUIDE.md`](PUBLIC_ALPHA_TESTING_GUIDE.md)
  — the canonical "what to test" list.
* [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — the
  common-issues reference.
* [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) —
  the "yes, we know" list.
* [`ROADMAP.md`](ROADMAP.md) §4 — the canonical
  out-of-scope list.
* [`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md)
  — what UNAV is + isn't, scientifically.
