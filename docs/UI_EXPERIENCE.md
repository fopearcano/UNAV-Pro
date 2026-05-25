# UNAV Pro — UI Experience Guide

How the UNAV Pro dialog is meant to feel, and the shared building blocks
that keep every panel consistent. For the tab order see
`UI_TAB_STRUCTURE.md`; for the end-to-end task flows see
`USER_WORKFLOW_MAP.md`.

## Principles

1. **Compact + resizable.** Default window 900×700, fits a 1366×768
   laptop. The body lives in a vertical `ScrollGroup`, so long panels
   scroll and the bottom controls are always reachable. The window is
   resizable in both directions.
2. **Workflow-ordered.** Tabs run in the order you use them
   (`tab_registry.TAB_ORDER`): Home → Dataset → Navigator → Search →
   Voyage → Animation → Overlays → Tools → Diagnostics → Settings.
3. **Readable status.** One status vocabulary everywhere, as text
   prefixes (Cinema 4D Python has no reliable per-widget colour/icon):
   `[OK]` `[WARN]` `[ERROR]` `[MISSING]` `[DISABLED]` `[INFO]` `[...]`.
4. **Guarded destruction.** Anything that throws away work asks first.
5. **External tools stay external.** The heavy preprocessing tools run
   in a separate Python interpreter and are labelled as such — they are
   never C4D-runtime dependencies.

## Shared helpers — `ui/ui_helpers.py`

Pure formatters (work everywhere, unit-tested):

| Helper | Returns |
| --- | --- |
| `status_prefix(status)` | `"[OK]"`, `"[WARN]"`, … (accepts `Status` or str) |
| `format_status_label(status, msg)` | `"[OK] ready"` |
| `format_section_title(title)` | trimmed heading |
| `compact_separator(width, char)` | a short rule, bounded 1–200 |
| `format_warning_box(msg)` | a 3-line boxed `[WARN]` block |
| `normalize_button_label(label)` | collapses spaces, `...` → `…` |
| `append_log_line(buffer, msg, level=…)` | append to a `LogBuffer` |

c4d widget builders (inside the host only):

`add_section_title` • `add_status_label` • `add_warning_box` •
`add_compact_separator` • `add_button_row` • `add_path_selector` •
`pick_path`

Use these instead of hand-rolling `AddStaticText` / `AddButton` rows so
spacing and naming match across panels.

### Example

```python
from ui.ui_helpers import Status, format_status_label, append_log_line

# status label text
self.SetString(_ID_DS_STATUS,
               format_status_label(Status.MISSING, "catalog file not found"))

# logging (newline-safe, one entry per line)
append_log_line(self._log_buffer, "Sync complete: 4823 objects", level="INFO")
self.SetString(_ID_LOG, self._log_buffer.render())
```

## Status colours / icons

If a future build gains reliable per-widget styling, map the same
`Status` tokens to colours (`OK`→green, `WARN`→amber, `ERROR`→red,
`MISSING`→grey, `DISABLED`→dim). Until then the text prefixes are the
contract — and they have the bonus of surviving copy-paste into a bug
report.

## Logs

Logging goes through `core.log_format.LogBuffer` (see
`docs/DIAGNOSTICS.md`): the buffer is maintained Python-side, rendered
to the widget on every append, so every entry stays on its own line and
the widget never collapses newlines. **Copy Logs** and **Clear Logs**
are available; Clear Logs confirms first.

## Destructive actions — `ui/confirmations.py`

```python
from ui.confirmations import confirm_destructive

if confirm_destructive("clear_scene"):
    ...                       # do it
else:
    self._append_log("Clear Scene: cancelled.")
```

Registered actions: `clear_scene`, `clear_generated_objects`,
`reset_workspace`, `reset_preferences`, `delete_mission`,
`delete_dataset`, `clear_route`, `clear_keyframes`,
`clear_cache_references`, `clear_log`. Unregistered ids still prompt
(generic message) so nothing slips through unguarded.

## Home dashboard — `ui/home_dashboard.py`

`build_dashboard_text(DashboardState)` renders the at-a-glance block:

```
[OK] UNAV Pro v3.9.0 — Integrated External Tools
------------------------------------------------
[OK] Workspace: /proj/ws
[OK] Datasets: 2 enabled of 3 registered
[OK] Navigator: UNAV Navigator
[OK] Visible sector: 4823 objects
[INFO] Mission: none active
[OK] Health: 6/6 ok
```

Unknown values render as `[MISSING]` / `[...]` rather than blanking, so
the dashboard is useful even before anything is loaded.

## Manual QA checklist

- [ ] Opens on a 1080p screen with room to spare.
- [ ] Opens on a smaller laptop-height screen without clipping bottom
      controls.
- [ ] Resize vertically — content reflows / scrolls.
- [ ] Switch every tab — no empty / broken tab.
- [ ] Scroll the long panels.
- [ ] Bottom action buttons reachable at the smallest size.
- [ ] Logs readable, one entry per line, Copy + Clear work.
- [ ] Each destructive button shows a confirm dialog.
