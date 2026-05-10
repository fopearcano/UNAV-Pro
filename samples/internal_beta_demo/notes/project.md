# UNAV Internal Beta Demo — Project Notes

This workspace ships with the v3.4 internal beta to give
testers a known-good starting point.

## What's inside

- `datasets/gaia_demo.jsonl` — five tiny Gaia DR3 rows
  with v3.2 provenance stamped.
- `datasets/jpl_demo.jsonl` — three JPL Horizons rows
  (Mercury, Earth, Mars) at a single epoch.
- `missions/demo_tour.json` — three-stop mission
  walking through the demo data.
- `routes/demo_route.json` — three-stop route variant.
- `presentations/demo_talk.json` — three-step
  presentation referencing the demo mission.
- `notes/project.md` — this file.

## Internal beta caveats

- The data is **synthetic / illustrative** — not
  suitable for science work.
- Distances are coarse approximations.
- Provenance records are filled out for parity with
  the v3.2 self-describing contract; the
  `query_parameters` are placeholder.

See [`docs/V3_4_INTERNAL_BETA_CHECKLIST.md`](../../docs/V3_4_INTERNAL_BETA_CHECKLIST.md)
for the test-pass procedure.
