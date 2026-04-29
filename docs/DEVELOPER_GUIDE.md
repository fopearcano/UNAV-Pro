# Developer Guide

## Purpose

UNAV Pro is a Cinema 4D 2023+ plugin for astrophysical navigation,
visible-sector generation, and metadata-driven point fields. It
turns real or local catalog data into a viewport-friendly subset of
the universe — bounded by an in-scene navigator — and surfaces full
per-object metadata on demand.

## Architecture

The plugin is organized as discrete layers so each can evolve (and
later be replaced by native or GPU code) without dragging the
others along:

* **Cinema 4D plugin UI.** Dialogs, action buttons, status panels.
  Knows about `c4d.gui` / `c4d.documents` / `BaseContainer`. Talks
  to core via plain function calls and dataclasses.
* **Core navigation / filtering logic.** Camera-driven cone
  filters, distance gates, visible-sector diff/sync, route
  planning. Pure-Python; framework-agnostic.
* **Data normalization.** A single canonical object schema that
  every catalog flows into. Validation, coordinate conversion,
  derived rendering attributes.
* **Spatial index / cache.** Chunked on-disk index that lets
  queries load only the cells the navigator's cone touches —
  never the entire catalog.
* **Scene generation.** Builds a small, marker-tagged hierarchy in
  the C4D document (one parent for the visible sector, one for
  debug helpers). Each generated object carries a minimal
  identifier; the rest of the metadata stays in the external
  cache.
* **External catalog connectors.** One module per source (Gaia,
  SDSS, DESI, JPL Horizons, …). Each is a CLI-runnable
  preprocessor that fetches a region and writes a normalized
  local file.

## Data Flow

```
remote catalogs                (Gaia / SDSS / DESI / JPL Horizons / …)
       │
       ▼
external preprocessing tools   (per-source CLI, no C4D dependency)
       │
       ▼
normalized local files / cache (canonical schema; JSONL or similar)
       │
       ▼
spatial filtering              (cone + distance gate against navigator)
       │
       ▼
Cinema 4D generated visible    (UNAV objects under the starfield root)
sector
```

The plugin never opens a network socket at scene-load time. Data
fetch is offline and repeatable; the live workflow filters the
local cache.

## Cinema 4D Boundaries

* **C4D-specific imports stay isolated.** `import c4d` and any
  `from c4d ... import ...` belong inside try/except guards or
  inside C4D-only modules. They must never appear at module top
  level in code that the test suite or the offline CLIs need to
  import.
* **CLI tools and tests run without Cinema 4D.** A clean Python
  3.9+ install with no C4D, no proprietary scientific stack, and
  no credentials must be enough to run the offline preprocessors
  and the entire test suite.
* **Core logic stays mostly C4D-independent.** Pure data and
  algorithm modules accept plain Python objects; the C4D-bound
  glue layer adapts those into `BaseObject` / `BaseDocument`
  calls. Keep coordinate math, validation, filtering, indexing,
  and persistence in pure Python.

## Safety Rules

* **Never generate the full universe into the scene.** Without a
  cone filter, the build action must refuse rather than enumerate
  every catalog row into Cinema 4D.
* **Use visible-sector filtering.** Generation flows through the
  navigator's pose + cone parameters; only the surviving subset
  becomes scene objects.
* **Cap generated objects.** A hard ceiling on materialized
  objects per build. The user can raise it deliberately, but the
  default refuses heavy builds.
* **Keep full metadata external.** The catalog's full
  per-object record lives in the cache, indexed by uid; the
  plugin looks it up on demand.
* **Store only minimal identifiers on C4D objects.** Each
  generated object carries enough to identify itself (uid,
  source, type, basic position) and nothing more. The full record
  is not embedded into every scene node.

## Testing

* **Test core logic outside C4D.** Coordinate math, schema
  validation, filtering, indexing, persistence, and the various
  controllers should all be unit-tested without the host
  available.
* **Mock C4D APIs.** Where a code path must touch Cinema 4D, gate
  the import behind a try/except and provide a non-host fallback
  the tests can exercise. C4D-bound paths that cannot be
  meaningfully mocked are exercised manually inside the host.
* **Mock remote catalog responses.** Connector tests must inject
  a fetcher (or equivalent boundary) that returns a hand-written
  payload. No live HTTP traffic in the suite; no credentials
  anywhere in test fixtures.
* **Avoid huge data files in tests.** Sample inputs are small,
  deterministic, and built programmatically when possible. The
  suite must run quickly on a laptop with no special data setup.

## Adding a Connector

1. **Create the connector module.** One file per catalog source,
   parameterized by the cone (RA/Dec/radius) and a row cap.
2. **Normalize source data into the universal object schema.**
   Map source-specific columns onto the canonical fields; populate
   the optional fields (parallax, redshift, photometry, …) only
   when the source provides them.
3. **Preserve raw metadata.** Keep source-specific extras
   (quality flags, vector components, identifiers) in the row's
   free-form metadata blob so the inspector can surface them
   later.
4. **Add mocked tests.** Construct a small synthetic response,
   feed it through the connector via the boundary the test
   suite relies on, and assert the resulting normalized rows.
5. **Document limitations.** Note coordinate-frame choices,
   distance-derivation safety rules (e.g. SNR thresholds,
   redshift cuts), license / citation requirements, and known
   ambiguity / disambiguation behaviour.

## Release Checklist

* Tests pass.
* No credentials in source, fixtures, or commit history.
* No huge data files committed; sample data remains small and
  deterministic.
* No hardcoded local paths in plugin code or tests.
* Docs updated (per-feature and overview where applicable).
* Changelog updated.
* Sample data remains small.
