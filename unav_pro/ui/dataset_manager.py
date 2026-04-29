"""Dataset Manager — separate dialog for catalog registration.

The main dialog grows enough buttons already; the dataset manager
gets its own ``GeDialog`` so the registry view, the per-entry
dropdown, and the per-row buttons have room without crowding the
main control panel.

Buttons:

  * **Add Dataset** — file-pick a JSONL/CSV catalog and register it.
  * **Remove Dataset** — drop the currently selected entry.
  * **Enable/Disable** — toggle the selected entry's ``enabled``.
  * **Build Index** — call ``core.spatial_index.build_index`` on the
    selected entry's catalog and remember the resulting cache path.
  * **Load Active Datasets** — merge every enabled entry into the
    plugin-wide ``MetadataLookup`` so the inspector and the route
    panel see all of them.

The registry is persisted across plugin reloads to
``~/.unav_pro/datasets.json`` (per-user). Failures to save / load /
scan are surfaced as status lines, never raised out of the dialog
event loop.
"""

from __future__ import annotations

from typing import Optional

try:
    import c4d  # type: ignore
    from c4d import gui, storage  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    gui = None  # type: ignore
    storage = None  # type: ignore
    _C4D_AVAILABLE = False

from core.dataset_registry import (
    DatasetRegistry,
    bootstrap_with_sample,
    default_registry_path,
    render_registry,
)
from core.logging_util import get_logger
from core.metadata_lookup import MetadataLookup, set_default_lookup

_log = get_logger("ui.dataset_manager")

# Widget IDs.
_ID_GROUP_TABLE = 100
_ID_PANEL = 101
_ID_GROUP_PICKER = 200
_ID_COMBO_DATASET = 201
_COMBO_BASE = 1_000_000  # combo item ids — well beyond UNAV widget ids
_ID_GROUP_BUTTONS = 300
_ID_BTN_ADD = 301
_ID_BTN_REMOVE = 302
_ID_BTN_TOGGLE = 303
_ID_BTN_INDEX = 304
_ID_BTN_LOAD = 305
_ID_BTN_REFRESH = 306
_ID_GROUP_LOG = 400
_ID_LOG = 401


# ---------------------------------------------------------------------------
# Top-level control class
# ---------------------------------------------------------------------------


class DatasetManagerController:
    """Orchestrates the dialog's view and the underlying registry.

    Stateless across host startup / shutdown except for the
    on-disk registry path. The dialog instantiates one of these and
    threads every button through it.
    """

    def __init__(
        self,
        registry: Optional[DatasetRegistry] = None,
        registry_path: Optional[str] = None,
    ):
        self.registry_path = registry_path or default_registry_path()
        if registry is not None:
            self.registry = registry
        else:
            self.registry = DatasetRegistry.load(self.registry_path)
            if len(self.registry) == 0:
                self.registry = bootstrap_with_sample()
                self._save_quiet()

    # --------------------------------------------------------------- save
    def _save_quiet(self) -> None:
        try:
            self.registry.save(self.registry_path)
        except OSError as exc:
            _log.warning(
                "Could not persist registry to %s: %s",
                self.registry_path, exc,
            )

    # ---------------------------------------------------------- table view
    def panel_text(self) -> str:
        """Multi-line text rendering of the registry for the dialog
        panel."""
        return render_registry(self.registry)

    # ------------------------------------------------------------ actions
    def add_dataset(self, path: str) -> str:
        """Register the catalog at ``path``. Scans on add for stats.
        Returns a status string; never raises."""
        if not path:
            return "Add Dataset: cancelled."
        try:
            entry = self.registry.add_path(path)
        except ValueError as exc:
            return f"Add Dataset: {exc}"
        self._save_quiet()
        suffix = ""
        if entry.notes:
            suffix = f" ({entry.notes})"
        return f"Add Dataset: '{entry.name}' registered{suffix}."

    def remove_dataset(self, name: str) -> str:
        """Drop ``name`` from the registry. Returns a status string."""
        if not name:
            return "Remove Dataset: nothing selected."
        removed = self.registry.remove(name)
        if removed is None:
            return f"Remove Dataset: '{name}' not found."
        self._save_quiet()
        return f"Remove Dataset: '{name}' removed."

    def toggle_enabled(self, name: str) -> str:
        """Flip the enabled flag on ``name``. Persists the change."""
        if not name:
            return "Toggle Enabled: nothing selected."
        entry = self.registry.find(name)
        if entry is None:
            return f"Toggle Enabled: '{name}' not found."
        entry.enabled = not entry.enabled
        self._save_quiet()
        state = "enabled" if entry.enabled else "disabled"
        return f"Toggle Enabled: '{name}' {state}."

    def refresh_stats(self, name: str) -> str:
        """Rescan the catalog file behind ``name`` and update stats."""
        if not name:
            return "Refresh: nothing selected."
        entry = self.registry.rescan(name)
        if entry is None:
            return f"Refresh: '{name}' not found."
        self._save_quiet()
        if entry.notes:
            return f"Refresh: '{name}' — {entry.notes}"
        if entry.stats is None:
            return f"Refresh: '{name}' — no stats."
        return (
            f"Refresh: '{name}' — {entry.stats.object_count} objects, "
            f"r ≤ {entry.stats.bounding_radius_pc:.3g} pc."
        )

    def build_index(self, name: str) -> str:
        """Build the chunked spatial index for ``name``'s catalog and
        record the resulting cache directory on the entry."""
        if not name:
            return "Build Index: nothing selected."
        entry = self.registry.find(name)
        if entry is None:
            return f"Build Index: '{name}' not found."
        if not entry.file_exists:
            return f"Build Index: catalog file is missing at {entry.path}."

        # Local imports keep the module loadable in environments
        # where the index/builder dependencies might not be set up.
        from core.spatial_index import build_index
        from data.catalog_io import CatalogIOError, load_catalog
        import os

        try:
            objects = load_catalog(entry.path)
        except CatalogIOError as exc:
            return f"Build Index: load failed: {exc}"
        if not objects:
            return f"Build Index: '{name}' is empty."

        out_dir = entry.path + ".index"
        try:
            index = build_index(objects, out_dir)
        except Exception as exc:  # noqa: BLE001 — boundary
            _log.exception("build_index failed")
            return f"Build Index: failed: {exc!r}"

        entry.index_path = os.path.abspath(out_dir)
        self._save_quiet()
        return (
            f"Build Index: '{name}' — {index.total_objects} objects "
            f"into {len(index.cells)} cells at {entry.index_path}."
        )

    def load_active(self) -> str:
        """Merge every enabled dataset into a fresh ``MetadataLookup``
        and install it as the process default."""
        merge = self.registry.merge_active()
        if merge.total_objects == 0 and not merge.errors:
            return "Load Active: no enabled datasets."
        lookup = MetadataLookup(merge.objects)
        set_default_lookup(lookup)
        msg = "Load Active: " + merge.short_summary()
        if merge.errors:
            for k, v in merge.errors.items():
                _log.warning("merge error for %s: %s", k, v)
            msg += " (see log for error detail)"
        return msg


# ---------------------------------------------------------------------------
# C4D dialog
# ---------------------------------------------------------------------------


if _C4D_AVAILABLE:

    class UnavDatasetDialog(gui.GeDialog):
        """Stand-alone window for the dataset manager.

        The main UNAV dialog opens this with ``Open(...)``; everything
        the user does here mutates the on-disk registry directly so
        closing the window does not lose work.
        """

        TITLE = "UNAV Pro — Dataset Manager"

        controller: Optional[DatasetManagerController] = None

        def CreateLayout(self) -> bool:
            self.SetTitle(self.TITLE)

            # Table view of registered datasets.
            self.GroupBegin(
                _ID_GROUP_TABLE, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                cols=1, rows=1, title="Registered datasets",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddMultiLineEditText(
                _ID_PANEL,
                c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                inith=240,
                style=c4d.DR_MULTILINE_READONLY | c4d.DR_MULTILINE_MONOSPACED,
            )
            self.GroupEnd()

            # Picker — combo of registered names.
            self.GroupBegin(
                _ID_GROUP_PICKER, c4d.BFH_SCALEFIT, cols=2, rows=1,
                title="Selection",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Active dataset")
            self.AddComboBox(_ID_COMBO_DATASET, c4d.BFH_SCALEFIT)
            self.GroupEnd()

            # Buttons.
            self.GroupBegin(
                _ID_GROUP_BUTTONS, c4d.BFH_SCALEFIT, cols=3, rows=2,
                title="Actions",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddButton(_ID_BTN_ADD, c4d.BFH_SCALEFIT, name="Add Dataset")
            self.AddButton(_ID_BTN_REMOVE, c4d.BFH_SCALEFIT, name="Remove Dataset")
            self.AddButton(_ID_BTN_TOGGLE, c4d.BFH_SCALEFIT, name="Enable/Disable")
            self.AddButton(_ID_BTN_INDEX, c4d.BFH_SCALEFIT, name="Build Index")
            self.AddButton(_ID_BTN_LOAD, c4d.BFH_SCALEFIT, name="Load Active Datasets")
            self.AddButton(_ID_BTN_REFRESH, c4d.BFH_SCALEFIT, name="Refresh Stats")
            self.GroupEnd()

            # Status log.
            self.GroupBegin(
                _ID_GROUP_LOG, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                cols=1, rows=1, title="Status",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddMultiLineEditText(
                _ID_LOG,
                c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                inith=80,
                style=c4d.DR_MULTILINE_READONLY | c4d.DR_MULTILINE_MONOSPACED,
            )
            self.GroupEnd()
            return True

        def InitValues(self) -> bool:
            if self.controller is None:
                self.controller = DatasetManagerController()
            self._refresh()
            return True

        # -------------------------------------------------------- refresh
        def _refresh(self) -> None:
            if self.controller is None:
                return
            self.SetString(_ID_PANEL, self.controller.panel_text())
            self._rebuild_combo()

        def _rebuild_combo(self) -> None:
            self.FreeChildren(_ID_COMBO_DATASET)
            for i, name in enumerate(self.controller.registry.names()):
                self.AddChild(_ID_COMBO_DATASET, _COMBO_BASE + i, name)
            if self.controller.registry.names():
                self.SetInt32(_ID_COMBO_DATASET, _COMBO_BASE)

        def _selected_name(self) -> Optional[str]:
            try:
                idx = int(self.GetInt32(_ID_COMBO_DATASET))
            except Exception:
                return None
            pos = max(0, idx - _COMBO_BASE)
            names = self.controller.registry.names()
            if not names:
                return None
            if pos >= len(names):
                pos = len(names) - 1
            return names[pos]

        def _append_log(self, line: str) -> None:
            current = self.GetString(_ID_LOG) or ""
            new_text = (current + line + "\n") if current else (line + "\n")
            self.SetString(_ID_LOG, new_text)

        # ------------------------------------------------------ commands
        def Command(self, mid: int, msg) -> bool:
            try:
                if self.controller is None:
                    return True
                if mid == _ID_BTN_ADD:
                    path = storage.LoadDialog(
                        type=c4d.FILESELECTTYPE_ANYTHING,
                        title="Pick UNAV catalog (JSONL or CSV)",
                    )
                    self._append_log(self.controller.add_dataset(path or ""))
                    self._refresh()
                elif mid == _ID_BTN_REMOVE:
                    name = self._selected_name()
                    self._append_log(self.controller.remove_dataset(name or ""))
                    self._refresh()
                elif mid == _ID_BTN_TOGGLE:
                    name = self._selected_name()
                    self._append_log(self.controller.toggle_enabled(name or ""))
                    self._refresh()
                elif mid == _ID_BTN_INDEX:
                    name = self._selected_name()
                    self._append_log(self.controller.build_index(name or ""))
                    self._refresh()
                elif mid == _ID_BTN_LOAD:
                    self._append_log(self.controller.load_active())
                elif mid == _ID_BTN_REFRESH:
                    name = self._selected_name()
                    self._append_log(self.controller.refresh_stats(name or ""))
                    self._refresh()
            except Exception as exc:  # noqa: BLE001 — UI boundary
                _log.exception("DatasetManagerDialog command %s failed", mid)
                self._append_log(f"ERROR: {exc!r}")
            return True

else:  # pragma: no cover — non-C4D import path

    class UnavDatasetDialog:  # type: ignore[no-redef]
        TITLE = "UNAV Pro — Dataset Manager"
        controller = None

        def __init__(self, *_args, **_kwargs):
            raise RuntimeError(
                "UnavDatasetDialog can only be instantiated inside Cinema 4D."
            )
