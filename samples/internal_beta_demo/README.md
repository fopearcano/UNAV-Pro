# UNAV Internal Beta Demo Workspace

A self-contained v3.1 workspace bundled with every v3.4
internal beta release. Use it to run through the
[`V3_4_INTERNAL_BETA_CHECKLIST.md`](../../docs/V3_4_INTERNAL_BETA_CHECKLIST.md)
without needing any external catalog data.

## Layout

```
internal_beta_demo/
├── project_manifest.json
├── datasets/
│   ├── gaia_demo.jsonl
│   └── jpl_demo.jsonl
├── missions/
│   └── demo_tour.json
├── routes/
│   └── demo_route.json
├── presentations/
│   └── demo_talk.json
└── notes/
    └── project.md
```

## Usage

1. Open Cinema 4D.
2. `Extensions → Universal Navigator Pro`.
3. `Project → Open Workspace…` → select this
   directory.
4. The dialog populates the dataset, mission, route,
   and presentation lists.
5. Walk through the
   [`V3_4_INTERNAL_BETA_CHECKLIST.md`](../../docs/V3_4_INTERNAL_BETA_CHECKLIST.md)
   end-to-end.

## What this demo does NOT do

- It does not test rendering. UNAV is not a renderer.
- It does not test against real Gaia / JPL endpoints.
  The data is synthetic and illustrative; do not cite
  measurements from this dataset.
- It does not test multi-million-row catalogs. For
  that, build an indexed dataset via the v0.x CLI
  tools.

## Files are tiny

Every file in this workspace is under 16 KB. The full
demo is well under 100 KB. The packaging script
includes the entire tree in every release zip.
