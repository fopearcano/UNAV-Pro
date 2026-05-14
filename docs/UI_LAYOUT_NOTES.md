# UNAV Pro — UI Layout Notes

How the dialog stays usable on laptop-class
screens, and what the fix that introduced the
vertical scroll wrapper changes.

---

## 1. The problem

The main `UnavMainDialog` (`unav_pro/ui/main_dialog.py`)
stacks roughly ten major sections vertically:

* Workflow hint
* Display (visual encoding)
* Safety
* Visible Sector (sync controls)
* Render Mode
* Native Point Viewer (experimental)
* Time Navigator
* Actions (the primary buttons grid)
* Status Log
* Route Planner
* Metadata Inspector
* Tab group (Search / Bookmarks / Navigation /
  Missions / Overlays)

Each section has its own `GroupBegin` /
`GroupBorderSpace(8, 8, 8, 8)` /
`GroupEnd`. The natural minimum height of the
dialog adds up to **well over 900 px** before
any tab content is considered. On a typical
laptop screen (≤ 768 px usable after menus +
taskbars), the bottom of the dialog falls below
the screen edge and the *Sync*, *Bake*, and
*Project* buttons are unreachable.

Before this fix the dialog also opened with a
`defaultw=420, defaulth=320` — well below the
*minimum* size the layout requires. C4D
silently enlarges the window to the layout's
minimum, which on a small screen pushes the
window past the screen edge with no scroll
recovery.

## 2. The fix

Three small changes:

1. **Wrap the dialog body in a vertical scroll
   group.** `CreateLayout` opens a single
   `ScrollGroupBegin(_ID_GROUP_SCROLL_ROOT,
   BFH_SCALEFIT | BFV_SCALEFIT,
   SCROLLGROUP_VERT | SCROLLGROUP_AUTOVERT)` /
   `GroupBegin(...)` immediately after
   `SetTitle`, and a matching pair of
   `GroupEnd` calls just before `return True`.
   The whole stack now lives inside a scroll
   viewport; when the window is shorter than the
   natural layout, a vertical scrollbar appears.
2. **Use a laptop-class default size.** The
   `Execute` method that opens the dialog now
   passes `defaultw=720, defaulth=640` instead
   of `420, 320`. 640 px is comfortable on a
   1366×768 screen with menus + taskbars, and
   the scroll group handles anything below
   that.
3. **Trim the diagnostics panel.** The
   `Diagnostics` dialog's multi-line edit was
   set to `inith=420`, forcing the dialog over
   500 px tall. Lowered to `inith=240` with
   `BFV_SCALEFIT` so it grows when there's
   room. Its `defaulth` dropped from 620 to
   520.

## 3. Why an outer scroll group + not per-panel
scroll groups

C4D's `TabGroupBegin` does **not** behave well
inside a vertical `ScrollGroupBegin` if each
tab also tries to scroll independently — the
inner viewports steal scroll events from the
outer one, and Maxon's Python GUI API doesn't
expose a clean way to chain them.

Wrapping every section (including the tab
group) in a single outer scroll group is the
lowest-risk option:

* Every control becomes reachable.
* The tabs continue to switch normally; the
  tab body grows / shrinks with the panel.
* The window remains resizable in both
  directions via the standard C4D resize
  grips.
* Existing widget IDs + Command routing are
  untouched.

## 4. What you should see now

* **Initial open** — window opens at 720 × 640.
* **Resize taller** — sections at the bottom
  become visible without a scrollbar.
* **Resize shorter** — a vertical scrollbar
  appears next to the body; the user scrolls
  to reach lower sections. Tabs still switch
  via the same row near the bottom of the
  scroll viewport.
* **Tab switch** — tab content fills whatever
  space remains under the tab row + above the
  bottom of the scroll viewport. Long tab
  content (e.g. the Missions tab) scrolls
  with the rest of the dialog.

## 5. Caveats

* `ScrollGroupBegin` requires Cinema 4D 2023+.
  Older hosts (the v3.x baseline already
  rejects them — `MIN_C4D_API = 26000` in
  `version.py`) wouldn't have hit this code
  path. The dialog also has a `try/except`
  around the wrapper so a Cinema 4D build that
  has temporarily lost the API constant
  degrades to the flat layout instead of
  refusing to load.
* If you add a new panel, place it **between
  the `_ID_GROUP_SCROLL_INNER` GroupBegin and
  the matching GroupEnd** so it inherits
  scrolling. No extra wiring; the existing
  flat-layout pattern (`GroupBegin` /
  `GroupBorderSpace` / `GroupEnd`) works
  unchanged.

## 6. Testing

Pure-Python unit tests can't drive Cinema 4D's
GUI. The v3.x test suite covers the *data* +
*logic* surfaces; the layout is verified
manually. The recommended manual matrix:

| Display | Expected |
| --- | --- |
| 1080p (1920×1080) | Dialog opens at 720×640, every section visible without scrolling after slight resize. |
| 1366×768 laptop | Dialog opens at 720×640, vertical scrollbar appears, all sections + tabs reachable. |
| 13″ MBA 1440×900 | Dialog opens at 720×640, no scrolling needed; resizing both directions works. |
| 1024×768 (rare) | Dialog opens at 720×640, scrollbar active from the start; bottom controls reachable. |

Steps:

1. Open Cinema 4D 2023+.
2. *Extensions → Universal Navigator Pro*.
3. Confirm the dialog opens without clipping.
4. Resize the window shorter than the content;
   confirm the vertical scrollbar appears + the
   user can reach every section.
5. Switch through every tab (Search /
   Bookmarks / Navigation / Missions /
   Overlays). Confirm tab content + bottom
   controls remain reachable.
6. Open *Diagnostics → Run Health Check* — the
   diagnostics dialog should open at 620×520,
   fully visible.

If any tab content is clipped or any control
is unreachable: file an issue with a
screenshot of the dialog + your screen
resolution.
