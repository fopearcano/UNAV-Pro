# UNAV Pro — Tab Structure (Information Architecture)

The dialog's tabs follow the **user's workflow**, top to bottom. The
order is defined once, as data, in `unav_pro/ui/tab_registry.py`
(`TAB_ORDER`) — tests assert it stays unique and in this sequence.

## Canonical order

| # | Tab | Key | For |
| --- | --- | --- | --- |
| 1 | Home | `home` | At-a-glance dashboard + the five most common actions |
| 2 | Dataset | `dataset` | Register, import, index, audit catalogs |
| 3 | Navigator | `navigator` | Navigator object, camera, view cone, epoch, sector sync |
| 4 | Search | `search` | Find objects, filter, act on results |
| 5 | Voyage | `voyage` | Bookmarks, route, mission builder, waypoints, analytics |
| 6 | Animation | `animation` | Path preview, timeline baking, markers, frame range |
| 7 | Overlays | `overlays` | Navigation overlays, science layers, presentation labels |
| 8 | Tools | `tools` | External Python preprocessing tools (run **outside** C4D) |
| 9 | Diagnostics | `diagnostics` | Health check, logs, issue report, reset tools |
| 10 | Settings | `settings` | Workspace + cache paths, default limits, external Python |

`Settings` is marked `advanced=True` (rare controls sit lower /
collapsed).

## Per-tab section layout

The intended sections for each tab. Advanced/rare controls go to the
bottom of their tab or behind a collapsible group.

### 1. Home
- Dashboard (read-only): version • workspace • datasets • navigator •
  visible sector • mission • health.
- Primary actions: **Create Navigator**, **Load / Register Dataset**,
  **Sync Visible Sector**, **Open Sample Demo**, **Run Health Check**.

### 2. Dataset
- Active datasets (list with `[OK]/[MISSING]/[DISABLED]` + `idx`/`db`).
- Register dataset.
- Import to DB.
- Build index.
- Audit dataset.
- Dataset warnings (boxed `[WARN]`).

### 3. Navigator
- Navigator object (create / select).
- Camera controls.
- View cone / filter.
- Current position.
- Current epoch.
- Visible-sector sync (Sync / Clear).

### 4. Search
- Basic search.
- Advanced filters (lower / collapsed).
- Results.
- Result actions: Focus • Bookmark • Add to Route • Inspect.

### 5. Voyage
- Current Route.
- Mission Builder.
- Waypoints.
- Analytics.

### 6. Animation
- Camera path preview.
- Timeline baking.
- Markers.
- Frame range.
- Actions: Preview Path • Bake Mission to Timeline • Clear UNAV
  Keyframes • Add Timeline Markers.

### 7. Overlays
- Navigation overlays.
- Science layers.
- Presentation labels.
- Compact checkboxes; one radius scrubber.

### 8. Tools
- Python environment.
- Fetch Gaia / JPL / SDSS / DESI.
- Import / Index / Audit.
- Tool log output.
- **Clearly marked as external Python tools** — not C4D-runtime
  dependencies.

### 9. Diagnostics
- Health Check.
- Logs (one entry per line, Copy, Clear).
- Issue Report.
- Reset tools.

### 10. Settings
- Workspace paths.
- Cache paths.
- Default limits.
- UI preferences.
- External Python executable.
- Safety limits.

## Current implementation state

- The **order and IA** are codified in `tab_registry.py` (this is the
  source of truth).
- The **live dialog** currently realises the IA as: a top control
  stack (Display / Safety / Visible Sector / Render / Time / Actions /
  Log / Route / Metadata) plus a reordered `TabGroup`
  (Navigator → Search → Bookmarks → Missions → Overlays), with
  Dataset / Diagnostics / External Tools as dedicated windows opened
  from the Actions grid.
- The physical consolidation into ten discrete tabs (driven by
  `tab_registry`) is a mechanical, in-host refactor — see the audit's
  "Deliberately deferred" note.

## Rules

- **Don't** re-decide tab order at a call site — read `TAB_ORDER`.
- **Don't** reuse a tab `widget_id`; `validate_tabs()` (and a test)
  guard uniqueness.
- New rare controls land at the bottom of their tab or in a collapsed
  group, never above the primary controls.
