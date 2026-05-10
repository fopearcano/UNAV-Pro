# UNAV Pro v2.5 — Docs, Onboarding & Workflow Polish

Release date: 2026-05-10
Codename: *Docs, Onboarding & Workflow Polish*

v2.5 is the documentation, onboarding, and workflow-polish
release. No new systems, no rendering, no IPC. The plugin's
runtime surface is byte-for-byte the same as v2.4; v2.5
adds the artist-facing reference material that makes the
v0.1 → v2.4 feature set learnable in an afternoon.

---

## Highlights

* **Four new artist-facing docs.**
  * [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) — the
    canonical 12-section workflow reference.
  * [`docs/ARTIST_QUICKSTART.md`](docs/ARTIST_QUICKSTART.md)
    — install → first cinematic in twelve numbered steps.
  * [`docs/TD_GUIDE.md`](docs/TD_GUIDE.md) — the technical-
    director / data-pipeline view: schemas, performance
    limits, lifecycle, scene-sync model.
  * [`docs/ROADMAP.md`](docs/ROADMAP.md) — implemented /
    planned / optional / explicitly out-of-scope. Restates
    the rendering / IPC / RelativityRender boundary.
* **QA checklist gains an end-to-end manual install test.**
  See [`docs/QA_CHECKLIST.md`](docs/QA_CHECKLIST.md) §5.
  The release engineer follows eight numbered steps that
  prove the published zip works on a fresh Cinema 4D.
* **Workflow presets** (`unav_pro/core/workflow_presets.py`).
  A thin, artist-friendly wrapper over the v1.9 voyage
  templates with cinematic-ready defaults and recommended
  overlays per preset. Five presets:
  *Solar System Flythrough*, *Stellar Neighbourhood*,
  *Hubble Flow Voyage*, *Blank Voyage*,
  *Selection Flythrough*. The wrapper is transparent —
  every preset still resolves to a v1.9 template builder.

## What didn't change

* No new runtime systems — every UI surface is unchanged.
* No new on-disk schemas — Mission JSON, Route JSON,
  Camera Path JSON, Export Manifest, DB schema, binary
  format are all unchanged from v2.4.
* No new dependencies — runtime is still stdlib-only.
* No rendering, no IPC, no RelativityRender bridge.

## Migration

* No migration step. v2.4 saves load cleanly in v2.5.
* `PLUGIN_VERSION` bumped from `2.4.0` → `2.5.0`.
* The packaging script's `REQUIRED_FILES` allowlist now
  includes the four new docs and the v2.5 release notes;
  the build pipeline picks them up automatically.

## Testing

* Full suite passes (1700+ tests).
* New v2.5 tests cover the workflow presets + doc-sanity
  surface.

## Known limitations (carried over from v2.4)

See [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).
Highlights: per-document time-navigator state,
substring-only name search, `Auto Sync` is a placeholder,
redshift→distance is a coarse Hubble-law proxy.

## Boundary, restated

UNAV Pro v2.5 is an **astronomical navigation + voyage /
camera-animation tool for Cinema 4D**. The plugin populates
the C4D scene with real catalog data, lets the artist plan
camera movement through it, bakes the result to the
timeline, and exports DCC-agnostic JSON. Rendering, IPC,
real-time scientific simulation, online services, and
render-engine bridges are explicitly out of scope. See
[`docs/ROADMAP.md`](docs/ROADMAP.md) §4 and §5.

If a future milestone changes this boundary, it will:
update `docs/ROADMAP.md` first, document the new identity
in `docs/USER_MANUAL.md`, and ship in a major-version
release (v3.x) with a migration path for v2.x state.
