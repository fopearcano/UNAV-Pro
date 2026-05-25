# Data Fetch UI Workflow

A walkthrough of the most common loop: **fetch a region → (optionally
index) → register it as a dataset → use it in UNAV**. Everything below
happens from the **External Tools** window; the heavy work runs in your
external Python (see
[`TOOLS_PYTHON_ENVIRONMENT.md`](TOOLS_PYTHON_ENVIRONMENT.md)).

## 1. Pick a fetch tool

In the **Tool** dropdown, choose one of the Data Fetch tools:

| Tool | What it pulls |
| --- | --- |
| Fetch Gaia Region | Gaia DR3 stars in a cone (RA/Dec/radius) |
| Fetch SDSS Region | SDSS DR18 objects in a cone |
| Fetch DESI Region | DESI EDR objects in a cone |
| Fetch JPL Body | one solar-system body at an epoch |
| Fetch JPL Solar System | several bodies at an epoch |

The description line under the dropdown shows the runtime class and
dependency profile, e.g. `Fetch Gaia Region [fetch] (medium, network)`.

## 2. Fill in the form

Only the **minimal safe fields** are exposed — required ones are marked
with `*`:

- **RA / Dec (deg)** — the cone centre.
- **Radius (deg)** — keep this small. The default is `1.0°`.
- **Output path** — where the JSONL catalog is written.
- **Row limit** (optional) — pre-filled with a safe default (e.g.
  `5000` for Gaia). This caps the download size.
- **Build index dir** (optional) — if set, a chunked spatial index is
  built next to the catalog in one step.

Power-user CLI flags are intentionally *not* surfaced; run the script
directly if you need them (see
[`EXTERNAL_TOOLS_AUDIT.md`](EXTERNAL_TOOLS_AUDIT.md)).

## 3. Run

Click **Run Tool**. Because fetch tools hit the network, you'll get a
confirmation first:

> 'Fetch Gaia Region' downloads data over the network. It runs in the
> external Python process and won't freeze Cinema 4D. Continue?

The tool's stdout/stderr stream into the **Tool Output** panel as it
runs. Cinema 4D stays responsive — the work is in the child process.

When it finishes you'll see a summary line, e.g.
`fetch_gaia: done` plus the tool's own summary.

## 4. Register

If **Register dataset on success** is ticked (default), the produced
catalog is handed to the Dataset Manager automatically:

- the `--output` catalog is registered as a new dataset,
- if you set **Build index dir**, that index is attached to it.

You can also register manually later with **Register Output**.

From here it behaves like any registered dataset: enable it, load
active datasets, and it flows into the inspector, the route panel, and
sector streaming.

## 5. Index / DB later (optional)

If you didn't index during the fetch, switch to a **Processing** tool:

- **Build Spatial Index** — point `--input` at the catalog and
  `--output` at a new index directory. On success the index attaches to
  the matching registered dataset.
- **Import Catalog to DB** — import into a SQLite UNAV DB; the DB
  attaches to the matching dataset (or registers fresh).

## Safety reminders

- Start with a **small radius**. A 1° Gaia cone is already thousands of
  rows; widen gradually.
- The **row limit default** is your friend — raise it deliberately, not
  by accident.
- Fetchers use **public, anonymous** endpoints. No credentials are ever
  asked for or stored.
