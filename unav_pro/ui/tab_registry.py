"""Canonical tab information architecture for the UNAV Pro dialog.

This is the single source of truth for *which* tabs exist and *in what
order* they appear — the workflow-ordered IA the v3.9.x UI-experience
pass standardises on:

    Home → Dataset → Navigator → Search → Voyage → Animation →
    Overlays → Tools → Diagnostics → Settings

Keeping the order as **data** (not buried in ``CreateLayout``) means
tests can assert the order + uniqueness, docs can render the map, and a
future layout refactor builds the tab strip from this list instead of
re-deciding the order ad hoc.

Each ``TabDef`` carries a stable integer ``widget_id`` (used as the
Cinema 4D group id), a short ``key`` (used in docs / state), a
``title`` (shown on the tab), and a one-line ``summary`` of what the
tab is for. ``advanced=True`` marks tabs whose rarer controls should
sit lower / collapsed.

Stdlib-only; safe to import inside Cinema 4D.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


#: Base id for tab group widgets. Chosen well clear of the existing
#: main-dialog widget-id ranges (which top out in the 10,5xx band for
#: the legacy tab groups). The new IA tabs use 11_0xx.
_TAB_ID_BASE: int = 11_000


@dataclass(frozen=True)
class TabDef:
    """One tab in the dialog's information architecture."""

    key: str
    title: str
    summary: str
    widget_id: int
    advanced: bool = False


#: The canonical, workflow-ordered tab list. Order here *is* the order
#: in the dialog.
TAB_ORDER: Tuple[TabDef, ...] = (
    TabDef(
        key="home",
        title="Home",
        summary="At-a-glance dashboard + the five most common actions.",
        widget_id=_TAB_ID_BASE + 0,
    ),
    TabDef(
        key="dataset",
        title="Dataset",
        summary="Register, import, index, and audit catalogs.",
        widget_id=_TAB_ID_BASE + 1,
    ),
    TabDef(
        key="navigator",
        title="Navigator",
        summary="Navigator object, camera, view cone, epoch, sector sync.",
        widget_id=_TAB_ID_BASE + 2,
    ),
    TabDef(
        key="search",
        title="Search",
        summary="Find objects, filter, and act on results.",
        widget_id=_TAB_ID_BASE + 3,
    ),
    TabDef(
        key="voyage",
        title="Voyage",
        summary="Bookmarks, route, mission builder, waypoints, analytics.",
        widget_id=_TAB_ID_BASE + 4,
    ),
    TabDef(
        key="animation",
        title="Animation",
        summary="Path preview, timeline baking, markers, frame range.",
        widget_id=_TAB_ID_BASE + 5,
    ),
    TabDef(
        key="overlays",
        title="Overlays",
        summary="Navigation overlays, science layers, presentation labels.",
        widget_id=_TAB_ID_BASE + 6,
    ),
    TabDef(
        key="tools",
        title="Tools",
        summary="External Python preprocessing tools (run outside C4D).",
        widget_id=_TAB_ID_BASE + 7,
    ),
    TabDef(
        key="diagnostics",
        title="Diagnostics",
        summary="Health check, logs, issue report, reset tools.",
        widget_id=_TAB_ID_BASE + 8,
    ),
    TabDef(
        key="settings",
        title="Settings",
        summary="Workspace + cache paths, default limits, external Python.",
        widget_id=_TAB_ID_BASE + 9,
        advanced=True,
    ),
)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def ordered_tabs() -> List[TabDef]:
    """Tabs in display order."""
    return list(TAB_ORDER)


def tab_keys() -> List[str]:
    return [t.key for t in TAB_ORDER]


def tab_ids() -> List[int]:
    return [t.widget_id for t in TAB_ORDER]


def tab_titles() -> List[str]:
    return [t.title for t in TAB_ORDER]


def get_tab(key: str) -> TabDef:
    """Look up a tab by key. Raises ``KeyError`` for an unknown key so
    a typo fails loudly at build time."""
    for t in TAB_ORDER:
        if t.key == key:
            return t
    raise KeyError(f"unknown tab key: {key!r}")


def index_of(key: str) -> int:
    for i, t in enumerate(TAB_ORDER):
        if t.key == key:
            return i
    return -1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_tabs() -> Dict[str, object]:
    """Self-check the registry. Returns a report dict; ``ok`` is False
    if any invariant is violated. Used by tests + a future startup
    assert."""
    keys = tab_keys()
    ids = tab_ids()
    titles = tab_titles()
    dup_keys = sorted({k for k in keys if keys.count(k) > 1})
    dup_ids = sorted({i for i in ids if ids.count(i) > 1})
    dup_titles = sorted({t for t in titles if titles.count(t) > 1})
    blank = [t.key for t in TAB_ORDER if not t.title.strip() or not t.summary.strip()]
    return {
        "ok": not (dup_keys or dup_ids or dup_titles or blank),
        "count": len(TAB_ORDER),
        "duplicate_keys": dup_keys,
        "duplicate_ids": dup_ids,
        "duplicate_titles": dup_titles,
        "blank": blank,
    }
