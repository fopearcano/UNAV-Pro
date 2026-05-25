"""External Tools panel — launch the heavy preprocessing tools from
inside the plugin while they run in a **separate external Python**.

The plugin itself stays lightweight: nothing here imports numpy /
astroquery / pandas. This panel only *describes* the tools (via the
``tools`` package registry), validates the external interpreter the
user points it at, and shells out via ``tools.tool_runner``.

Sections, top to bottom, mirror the task spec:

  * **Python Environment** — pick / detect / validate the external
    interpreter; the choice persists in the UNAV config.
  * **Data Fetch** — Gaia / JPL / SDSS / DESI cone + body fetchers.
  * **Processing** — spatial index, DB import, dataset audit.
  * **Export** — visible-sector binary export.

As with the other UNAV dialogs the pure-CPython controller lives in
this module (``ToolsPanelController``) so the whole pipeline —
environment resolution, command construction, run, dataset
registration — is unit-tested without booting Cinema 4D. The
c4d-bound dialog is a thin shell over the controller.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Tuple

try:
    import c4d  # type: ignore
    from c4d import gui, storage  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    gui = None  # type: ignore
    storage = None  # type: ignore
    _C4D_AVAILABLE = False

from core.config import UnavConfig, load_config, save_config
from core.logging_util import get_logger
from tools import (
    PythonEnvStatus,
    REGISTRY,
    ToolSpec,
    detect_default_python,
    get_tool,
    resolve_external_python,
    tools_in_category,
    validate_python,
)
from tools.tool_registry import (
    CATEGORY_EXPORT,
    CATEGORY_FETCH,
    CATEGORY_PROCESSING,
    TOOL_CATEGORIES,
)
from tools.tool_runner import (
    ToolRunRequest,
    ToolRunResult,
    run_tool,
    should_warn_before_run,
    warning_text_for,
)

_log = get_logger("ui.tools_panel")


# ---------------------------------------------------------------------------
# Repo-root location
# ---------------------------------------------------------------------------


def default_repo_root() -> str:
    """Absolute path to the repository root (the directory that
    contains the top-level ``tools/`` scripts).

    Layout: ``<repo>/unav_pro/ui/tools_panel.py`` → the repo root is
    three directories up. The external tool scripts live at
    ``<repo>/tools/*.py``.
    """
    here = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


# ---------------------------------------------------------------------------
# Section grouping
# ---------------------------------------------------------------------------


#: Human labels for the three tool sections, in display order.
SECTION_LABELS: Tuple[Tuple[str, str], ...] = (
    (CATEGORY_FETCH, "Data Fetch"),
    (CATEGORY_PROCESSING, "Processing"),
    (CATEGORY_EXPORT, "Export"),
)


# ---------------------------------------------------------------------------
# Controller (pure CPython, fully testable)
# ---------------------------------------------------------------------------


class ToolsPanelController:
    """Drives the External Tools panel without any c4d dependency.

    Owns the resolved external-Python choice + the repo root, and
    exposes the verbs the dialog wires to buttons: resolve / validate
    / persist the interpreter, build a tool form, run a tool, and fold
    a successful result into the Dataset Manager.
    """

    def __init__(
        self,
        config: Optional[UnavConfig] = None,
        *,
        repo_root: Optional[str] = None,
        config_path: Optional[str] = None,
    ):
        self.config = config if config is not None else load_config()
        self.config_path = config_path
        self.repo_root = repo_root or default_repo_root()

    # ----------------------------------------------------- python env
    def resolve_python(self) -> Optional[str]:
        """Best current guess at the external interpreter: the
        configured path if usable, else an auto-detected system
        Python."""
        return resolve_external_python(
            configured_path=self.config.external_python_path,
        )

    def detect_python(self) -> Optional[str]:
        """Auto-detect a system Python ≥ 3.10, ignoring the
        configured value. Used by the *Detect* button."""
        return detect_default_python()

    def validate_python(
        self,
        executable: Optional[str] = None,
        *,
        runner=None,
    ) -> PythonEnvStatus:
        """Validate ``executable`` (or the resolved one) by running
        ``--version``. Never raises."""
        exe = executable if executable is not None else self.resolve_python()
        return validate_python(exe, runner=runner)

    def set_python_path(self, path: Optional[str]) -> PythonEnvStatus:
        """Persist the user's interpreter choice into the UNAV config
        and return its validation status. An empty / ``None`` path
        clears the override (back to auto-detect)."""
        cleaned = (path or "").strip() or None
        self.config.external_python_path = cleaned
        try:
            save_config(self.config, self.config_path)
        except Exception:  # noqa: BLE001 — preferences aren't worth crashing
            _log.exception("Could not persist external_python_path")
        return self.validate_python(self.resolve_python())

    # --------------------------------------------------------- tools
    def sections(self) -> List[Tuple[str, str, List[ToolSpec]]]:
        """Return ``(category, label, [ToolSpec])`` for each section in
        display order."""
        out: List[Tuple[str, str, List[ToolSpec]]] = []
        for category, label in SECTION_LABELS:
            out.append((category, label, tools_in_category(category)))
        return out

    def tool(self, tool_id: str) -> Optional[ToolSpec]:
        return get_tool(tool_id)

    def needs_warning(self, tool_id: str) -> bool:
        spec = get_tool(tool_id)
        return bool(spec) and should_warn_before_run(spec)

    def warning_text(self, tool_id: str) -> str:
        spec = get_tool(tool_id)
        return warning_text_for(spec) if spec else ""

    # ----------------------------------------------------------- run
    def build_request(
        self,
        tool_id: str,
        values: Dict[str, object],
        *,
        timeout: Optional[float] = None,
    ) -> ToolRunRequest:
        """Assemble a :class:`ToolRunRequest`. Raises ``ValueError``
        for an unknown tool or unresolved interpreter so the dialog
        can show a clean message."""
        spec = get_tool(tool_id)
        if spec is None:
            raise ValueError(f"unknown tool: {tool_id}")
        python_exe = self.resolve_python()
        if not python_exe:
            raise ValueError(
                "no external Python configured — set one in the Python "
                "Environment section first"
            )
        return ToolRunRequest(
            spec=spec,
            python_executable=python_exe,
            values=dict(values or {}),
            repo_root=self.repo_root,
            timeout=timeout,
        )

    def run(
        self,
        tool_id: str,
        values: Dict[str, object],
        *,
        timeout: Optional[float] = None,
        runner=None,
        log: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> ToolRunResult:
        """Run a tool end-to-end. Construction errors map to a failed
        ``ToolRunResult`` so the caller has a single result type to
        handle."""
        try:
            request = self.build_request(tool_id, values, timeout=timeout)
        except ValueError as exc:
            return ToolRunResult(
                tool_id=tool_id, command=[], ok=False,
                failure_kind="runtime_error", error=str(exc),
            )
        return run_tool(
            request, runner=runner, log=log, cancel_check=cancel_check,
        )

    # ----------------------------------------- dataset-manager bridge
    def register_result(
        self,
        tool_id: str,
        result: ToolRunResult,
        values: Dict[str, object],
        *,
        controller=None,
    ) -> str:
        """Fold a successful run into the dataset registry via the
        Dataset Manager controller. ``controller`` is injectable for
        tests; in production a fresh one is built (it loads the
        on-disk registry)."""
        spec = get_tool(tool_id)
        if spec is None:
            return "Register: unknown tool."
        if controller is None:
            from ui.dataset_manager import DatasetManagerController
            controller = DatasetManagerController()
        return controller.register_tool_output(spec, result, values)


# ---------------------------------------------------------------------------
# C4D dialog
# ---------------------------------------------------------------------------


if _C4D_AVAILABLE:

    # Widget IDs ----------------------------------------------------------
    _ID_GROUP_ENV = 100
    _ID_EDIT_PYPATH = 101
    _ID_BTN_BROWSE = 102
    _ID_BTN_DETECT = 103
    _ID_BTN_VALIDATE = 104
    _ID_BTN_SAVE_ENV = 105
    _ID_TXT_ENV_STATUS = 106

    _ID_GROUP_SELECT = 200
    _ID_COMBO_TOOL = 201
    _ID_TXT_TOOL_DESC = 202
    _COMBO_BASE = 1_000_100

    _ID_GROUP_FORM = 300
    #: Fixed pool of dynamic input rows. No registered tool exposes
    #: more than this many inputs (see tool_registry).
    _FORM_ROWS = 10
    _FORM_LABEL_BASE = 3000
    _FORM_EDIT_BASE = 3100

    _ID_GROUP_ACTIONS = 400
    _ID_BTN_RUN = 401
    _ID_BTN_REGISTER = 402
    _ID_CHK_AUTO_REGISTER = 403

    _ID_GROUP_LOG = 500
    _ID_LOG = 501

    class UnavToolsDialog(gui.GeDialog):
        """Stand-alone External Tools window."""

        TITLE = "UNAV Pro — External Tools"
        controller: Optional[ToolsPanelController] = None

        def __init__(self) -> None:
            super().__init__()
            # Flat list of (ToolSpec) in combo order + their inputs, so
            # the Command handler can map a selection back to a spec.
            self._tool_order: List[ToolSpec] = []
            self._current_inputs: List = []  # ToolInput for the open form
            self._last_result: Optional[ToolRunResult] = None
            self._last_values: Dict[str, object] = {}
            self._last_tool_id: str = ""
            from core.log_format import LogBuffer
            self._log_buffer = LogBuffer()

        # ----------------------------------------------------- layout
        def CreateLayout(self) -> bool:
            self.SetTitle(self.TITLE)

            # --- Python Environment ---------------------------------
            self.GroupBegin(
                _ID_GROUP_ENV, c4d.BFH_SCALEFIT, cols=2, rows=1,
                title="Python Environment",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddStaticText(0, c4d.BFH_LEFT, name="External Python")
            self.AddEditText(_ID_EDIT_PYPATH, c4d.BFH_SCALEFIT)
            self.AddStaticText(0, c4d.BFH_LEFT, name="")
            self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=4, rows=1)
            self.AddButton(_ID_BTN_BROWSE, c4d.BFH_SCALEFIT, name="Browse…")
            self.AddButton(_ID_BTN_DETECT, c4d.BFH_SCALEFIT, name="Detect")
            self.AddButton(_ID_BTN_VALIDATE, c4d.BFH_SCALEFIT, name="Validate")
            self.AddButton(_ID_BTN_SAVE_ENV, c4d.BFH_SCALEFIT, name="Save")
            self.GroupEnd()
            self.AddStaticText(0, c4d.BFH_LEFT, name="Status")
            self.AddStaticText(_ID_TXT_ENV_STATUS, c4d.BFH_SCALEFIT, name="—")
            self.GroupEnd()

            # --- Tool selector --------------------------------------
            self.GroupBegin(
                _ID_GROUP_SELECT, c4d.BFH_SCALEFIT, cols=2, rows=1,
                title="Tool",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddStaticText(0, c4d.BFH_LEFT, name="Tool")
            self.AddComboBox(_ID_COMBO_TOOL, c4d.BFH_SCALEFIT)
            self.GroupEnd()
            self.AddMultiLineEditText(
                _ID_TXT_TOOL_DESC, c4d.BFH_SCALEFIT, inith=44,
                style=c4d.DR_MULTILINE_READONLY,
            )

            # --- Dynamic form ---------------------------------------
            self.GroupBegin(
                _ID_GROUP_FORM, c4d.BFH_SCALEFIT, cols=2, rows=1,
                title="Inputs",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            for i in range(_FORM_ROWS):
                self.AddStaticText(_FORM_LABEL_BASE + i, c4d.BFH_LEFT, name="")
                self.AddEditText(_FORM_EDIT_BASE + i, c4d.BFH_SCALEFIT)
            self.GroupEnd()

            # --- Actions --------------------------------------------
            self.GroupBegin(
                _ID_GROUP_ACTIONS, c4d.BFH_SCALEFIT, cols=3, rows=1,
                title="Run",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddButton(_ID_BTN_RUN, c4d.BFH_SCALEFIT, name="Run Tool")
            self.AddCheckbox(
                _ID_CHK_AUTO_REGISTER, c4d.BFH_LEFT, initw=0, inith=0,
                name="Register dataset on success",
            )
            self.AddButton(_ID_BTN_REGISTER, c4d.BFH_SCALEFIT, name="Register Output")
            self.GroupEnd()

            # --- Log ------------------------------------------------
            self.GroupBegin(
                _ID_GROUP_LOG, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                cols=1, rows=1, title="Tool Output",
            )
            self.GroupBorderSpace(8, 8, 8, 8)
            self.AddMultiLineEditText(
                _ID_LOG, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, inith=160,
                style=c4d.DR_MULTILINE_READONLY | c4d.DR_MULTILINE_MONOSPACED,
            )
            self.GroupEnd()
            return True

        def InitValues(self) -> bool:
            if self.controller is None:
                self.controller = ToolsPanelController()
            self._populate_tool_combo()
            self._refresh_env_status()
            resolved = self.controller.resolve_python() or ""
            self.SetString(_ID_EDIT_PYPATH, resolved)
            self.SetBool(_ID_CHK_AUTO_REGISTER, True)
            if self._tool_order:
                self._select_tool(0)
            return True

        # --------------------------------------------------- helpers
        def _populate_tool_combo(self) -> None:
            self.FreeChildren(_ID_COMBO_TOOL)
            self._tool_order = []
            idx = 0
            for _cat, label, specs in self.controller.sections():
                for spec in specs:
                    self.AddChild(
                        _ID_COMBO_TOOL, _COMBO_BASE + idx,
                        f"[{label}] {spec.display_name}",
                    )
                    self._tool_order.append(spec)
                    idx += 1
            if self._tool_order:
                self.SetInt32(_ID_COMBO_TOOL, _COMBO_BASE)

        def _selected_spec(self) -> Optional[ToolSpec]:
            try:
                pos = int(self.GetInt32(_ID_COMBO_TOOL)) - _COMBO_BASE
            except Exception:
                return None
            if 0 <= pos < len(self._tool_order):
                return self._tool_order[pos]
            return None

        def _select_tool(self, pos: int) -> None:
            if not (0 <= pos < len(self._tool_order)):
                return
            spec = self._tool_order[pos]
            self.SetInt32(_ID_COMBO_TOOL, _COMBO_BASE + pos)
            self.SetString(
                _ID_TXT_TOOL_DESC,
                f"{spec.description}\n{spec.short_summary()}",
            )
            self._render_form(spec)

        def _render_form(self, spec: ToolSpec) -> None:
            self._current_inputs = list(spec.all_inputs())
            for i in range(_FORM_ROWS):
                if i < len(self._current_inputs):
                    inp = self._current_inputs[i]
                    star = " *" if inp.required else ""
                    self.SetString(_FORM_LABEL_BASE + i, inp.label + star)
                    self.HideElement(_FORM_LABEL_BASE + i, False)
                    self.HideElement(_FORM_EDIT_BASE + i, False)
                    default = "" if inp.default is None else str(inp.default)
                    self.SetString(_FORM_EDIT_BASE + i, default)
                    self.Enable(_FORM_EDIT_BASE + i, True)
                else:
                    self.SetString(_FORM_LABEL_BASE + i, "")
                    self.SetString(_FORM_EDIT_BASE + i, "")
                    self.HideElement(_FORM_LABEL_BASE + i, True)
                    self.HideElement(_FORM_EDIT_BASE + i, True)
            self.LayoutChanged(_ID_GROUP_FORM)

        def _collect_values(self) -> Dict[str, object]:
            values: Dict[str, object] = {}
            for i, inp in enumerate(self._current_inputs):
                if i >= _FORM_ROWS:
                    break
                raw = self.GetString(_FORM_EDIT_BASE + i) or ""
                values[inp.flag] = raw.strip()
            return values

        def _refresh_env_status(self) -> None:
            status = self.controller.validate_python()
            self.SetString(_ID_TXT_ENV_STATUS, status.short_summary())

        def _append_log(self, line: str) -> None:
            self._log_buffer.append(line)
            self.SetString(_ID_LOG, self._log_buffer.render())

        # --------------------------------------------------- commands
        def Command(self, mid: int, msg) -> bool:
            try:
                if self.controller is None:
                    return True
                if mid == _ID_COMBO_TOOL:
                    spec = self._selected_spec()
                    if spec is not None:
                        self.SetString(
                            _ID_TXT_TOOL_DESC,
                            f"{spec.description}\n{spec.short_summary()}",
                        )
                        self._render_form(spec)
                elif mid == _ID_BTN_BROWSE:
                    picked = storage.LoadDialog(
                        type=c4d.FILESELECTTYPE_ANYTHING,
                        title="Pick external Python interpreter",
                    )
                    if picked:
                        self.SetString(_ID_EDIT_PYPATH, picked)
                elif mid == _ID_BTN_DETECT:
                    found = self.controller.detect_python() or ""
                    self.SetString(_ID_EDIT_PYPATH, found)
                    if not found:
                        self.SetString(
                            _ID_TXT_ENV_STATUS,
                            "Python: no system interpreter found",
                        )
                elif mid == _ID_BTN_VALIDATE:
                    path = (self.GetString(_ID_EDIT_PYPATH) or "").strip()
                    status = self.controller.validate_python(path or None)
                    self.SetString(_ID_TXT_ENV_STATUS, status.short_summary())
                elif mid == _ID_BTN_SAVE_ENV:
                    path = (self.GetString(_ID_EDIT_PYPATH) or "").strip()
                    status = self.controller.set_python_path(path or None)
                    self.SetString(_ID_TXT_ENV_STATUS, status.short_summary())
                elif mid == _ID_BTN_RUN:
                    self._do_run()
                elif mid == _ID_BTN_REGISTER:
                    self._do_register()
            except Exception as exc:  # noqa: BLE001 — UI boundary
                _log.exception("UnavToolsDialog command %s failed", mid)
                self._append_log(f"ERROR: {exc!r}")
            return True

        def _do_run(self) -> None:
            spec = self._selected_spec()
            if spec is None:
                self._append_log("No tool selected.")
                return
            # Warn before a long / networked run.
            if should_warn_before_run(spec):
                if not gui.QuestionDialog(warning_text_for(spec)):
                    self._append_log(f"{spec.tool_id}: cancelled by user.")
                    return
            values = self._collect_values()
            self._append_log(f"Running {spec.display_name}…")
            result = self.controller.run(
                spec.tool_id, values, log=self._append_log,
            )
            self._last_result = result
            self._last_values = values
            self._last_tool_id = spec.tool_id
            self._append_log(result.short_summary())
            if result.ok and self.GetBool(_ID_CHK_AUTO_REGISTER):
                self._do_register()

        def _do_register(self) -> None:
            if self._last_result is None or not self._last_result.ok:
                self._append_log("Register: run a tool successfully first.")
                return
            msg = self.controller.register_result(
                self._last_tool_id, self._last_result, self._last_values,
            )
            self._append_log(msg)

else:  # pragma: no cover — non-C4D import path

    class UnavToolsDialog:  # type: ignore[no-redef]
        TITLE = "UNAV Pro — External Tools"
        controller = None

        def __init__(self, *_args, **_kwargs):
            raise RuntimeError(
                "UnavToolsDialog can only be instantiated inside Cinema 4D."
            )
