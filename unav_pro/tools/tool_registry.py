"""v-integrated-external-tools tool registry.

Single source of truth describing every external
preprocessing tool the dialog's *External Tools*
panel can launch. The registry is **pure data** —
no subprocess, no Cinema 4D, no network. The runner
(``tool_runner``) reads a ``ToolSpec`` to build a
command line; the panel reads it to draw a form.

Each ``ToolSpec`` is deliberately conservative: it
exposes only the *minimal safe* inputs an artist
needs (RA / Dec / radius / limit / output), not
every obscure CLI flag. Advanced flags stay
available on the command line for power users.

Stdlib-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Runtime + dependency classes
# ---------------------------------------------------------------------------


#: Coarse runtime expectation. The dialog warns
#: before launching anything slower than ``short``.
RUNTIME_CLASSES: Tuple[str, ...] = ("short", "medium", "long")


class DependencyProfile(str, Enum):
    """How heavy the tool's dependencies are.

    ``STDLIB`` — runs on any Python 3.10+.
    ``NETWORK`` — needs outbound HTTP (the fetch
      tools). Still stdlib-code, but the network
      call is what makes it unsafe on the C4D main
      thread.
    ``HEAVY`` — reserved for future tools the user
      adds that need numpy / astropy etc. None of
      the bundled tools are HEAVY.
    """

    STDLIB = "stdlib"
    NETWORK = "network"
    HEAVY = "heavy"


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


CATEGORY_FETCH: str = "fetch"
CATEGORY_PROCESSING: str = "processing"
CATEGORY_EXPORT: str = "export"

TOOL_CATEGORIES: Tuple[str, ...] = (
    CATEGORY_FETCH, CATEGORY_PROCESSING, CATEGORY_EXPORT,
)


# ---------------------------------------------------------------------------
# Tool input
# ---------------------------------------------------------------------------


class InputKind(str, Enum):
    """The widget the panel renders for one input."""

    FLOAT = "float"
    INT = "int"
    STRING = "string"
    PATH = "path"
    BOOL = "bool"


@dataclass(frozen=True)
class ToolInput:
    """One CLI argument the panel exposes as a form
    field.

    ``flag`` is the literal CLI flag (e.g.
    ``"--ra"``). ``required`` inputs must be
    populated before the panel enables *Run*.
    ``default`` seeds the field. ``bool`` inputs
    map to a checkbox + emit the flag only when
    checked (store_true semantics).
    """

    flag: str
    label: str
    kind: InputKind
    required: bool = False
    default: Optional[object] = None
    help: str = ""

    def is_store_true(self) -> bool:
        return self.kind is InputKind.BOOL


# ---------------------------------------------------------------------------
# Tool spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    """Full description of one external tool."""

    tool_id: str
    display_name: str
    script_path: str                 # relative to repo root, e.g. "tools/fetch_gaia_region.py"
    description: str
    category: str
    required_inputs: Tuple[ToolInput, ...] = ()
    optional_inputs: Tuple[ToolInput, ...] = ()
    output_flags: Tuple[str, ...] = ()      # which input flags carry generated artefacts
    estimated_runtime_class: str = "medium"
    dependency_profile: DependencyProfile = DependencyProfile.STDLIB
    safe_to_run_inside_c4d: bool = False
    produces_dataset: bool = False          # output is a catalog the Dataset Manager can register
    produces_index: bool = False            # output is / can be a spatial index
    produces_db: bool = False               # output is a SQLite DB

    def all_inputs(self) -> Tuple[ToolInput, ...]:
        return tuple(self.required_inputs) + tuple(self.optional_inputs)

    def input_for_flag(self, flag: str) -> Optional[ToolInput]:
        for inp in self.all_inputs():
            if inp.flag == flag:
                return inp
        return None

    def short_summary(self) -> str:
        return (
            f"{self.display_name} [{self.category}] "
            f"({self.estimated_runtime_class}, "
            f"{self.dependency_profile.value})"
        )


# ---------------------------------------------------------------------------
# Shared input builders
# ---------------------------------------------------------------------------


def _ra() -> ToolInput:
    return ToolInput("--ra", "RA (deg)", InputKind.FLOAT, required=True,
                     help="Right ascension of the cone centre, degrees.")


def _dec() -> ToolInput:
    return ToolInput("--dec", "Dec (deg)", InputKind.FLOAT, required=True,
                     help="Declination of the cone centre, degrees.")


def _radius() -> ToolInput:
    return ToolInput("--radius-deg", "Radius (deg)", InputKind.FLOAT,
                     required=True, default=1.0,
                     help="Cone search radius, degrees. Keep small.")


def _limit(default: int = 5000) -> ToolInput:
    return ToolInput("--limit", "Row limit", InputKind.INT,
                     required=False, default=default,
                     help="Hard cap on rows fetched. Default keeps "
                          "downloads small.")


def _output(label: str = "Output path") -> ToolInput:
    return ToolInput("--output", label, InputKind.PATH, required=True,
                     help="Where to write the resulting JSONL catalog.")


def _build_index() -> ToolInput:
    return ToolInput("--build-index", "Build index dir", InputKind.PATH,
                     required=False,
                     help="Optional: also build a spatial index in this "
                          "directory.")


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


REGISTRY: Tuple[ToolSpec, ...] = (
    # ----- Data fetch ----------------------------------------------------
    ToolSpec(
        tool_id="fetch_gaia",
        display_name="Fetch Gaia Region",
        script_path="tools/fetch_gaia_region.py",
        description="Cone-search Gaia DR3 and write a UNAV JSONL catalog.",
        category=CATEGORY_FETCH,
        required_inputs=(_ra(), _dec(), _radius(), _output("Gaia catalog output")),
        optional_inputs=(_limit(5000), _build_index()),
        output_flags=("--output", "--build-index"),
        estimated_runtime_class="medium",
        dependency_profile=DependencyProfile.NETWORK,
        safe_to_run_inside_c4d=False,
        produces_dataset=True,
        produces_index=True,
    ),
    ToolSpec(
        tool_id="fetch_jpl_body",
        display_name="Fetch JPL Body",
        script_path="tools/fetch_jpl_body.py",
        description="Fetch one JPL Horizons solar-system body at an epoch.",
        category=CATEGORY_FETCH,
        required_inputs=(
            ToolInput("--body", "Body", InputKind.STRING, required=True,
                      help="Body name, e.g. Mars."),
            ToolInput("--epoch", "Epoch (ISO)", InputKind.STRING, required=True,
                      default="2026-01-01T00:00:00",
                      help="Epoch in ISO-8601, e.g. 2026-01-01T00:00:00."),
            _output("JPL body output"),
        ),
        optional_inputs=(
            ToolInput("--center", "Center", InputKind.STRING, required=False,
                      default="500@10",
                      help="JPL coordinate center; default heliocentric."),
            _build_index(),
        ),
        output_flags=("--output", "--build-index"),
        estimated_runtime_class="short",
        dependency_profile=DependencyProfile.NETWORK,
        safe_to_run_inside_c4d=False,
        produces_dataset=True,
    ),
    ToolSpec(
        tool_id="fetch_jpl_solar_system",
        display_name="Fetch JPL Solar System",
        script_path="tools/fetch_jpl_solar_system.py",
        description="Fetch multiple JPL Horizons bodies at an epoch.",
        category=CATEGORY_FETCH,
        required_inputs=(
            ToolInput("--epoch", "Epoch (ISO)", InputKind.STRING, required=True,
                      default="2026-01-01T00:00:00",
                      help="Epoch in ISO-8601."),
            _output("Solar-system output"),
        ),
        optional_inputs=(
            ToolInput("--bodies", "Bodies (CSV)", InputKind.STRING,
                      required=False,
                      default="Mercury,Venus,Earth,Mars,Jupiter,Saturn",
                      help="Comma-separated body names."),
            ToolInput("--center", "Center", InputKind.STRING, required=False,
                      default="500@10", help="JPL coordinate center."),
            _build_index(),
        ),
        output_flags=("--output", "--build-index"),
        estimated_runtime_class="medium",
        dependency_profile=DependencyProfile.NETWORK,
        safe_to_run_inside_c4d=False,
        produces_dataset=True,
    ),
    ToolSpec(
        tool_id="fetch_sdss",
        display_name="Fetch SDSS Region",
        script_path="tools/fetch_sdss_region.py",
        description="Cone-search SDSS DR18 and write a UNAV JSONL catalog.",
        category=CATEGORY_FETCH,
        required_inputs=(_ra(), _dec(), _radius(), _output("SDSS catalog output")),
        optional_inputs=(_limit(2000), _build_index()),
        output_flags=("--output", "--build-index"),
        estimated_runtime_class="medium",
        dependency_profile=DependencyProfile.NETWORK,
        safe_to_run_inside_c4d=False,
        produces_dataset=True,
    ),
    ToolSpec(
        tool_id="fetch_desi",
        display_name="Fetch DESI Region",
        script_path="tools/fetch_desi_region.py",
        description="Cone-search DESI EDR and write a UNAV JSONL catalog.",
        category=CATEGORY_FETCH,
        required_inputs=(_ra(), _dec(), _radius(), _output("DESI catalog output")),
        optional_inputs=(_limit(2000), _build_index()),
        output_flags=("--output", "--build-index"),
        estimated_runtime_class="medium",
        dependency_profile=DependencyProfile.NETWORK,
        safe_to_run_inside_c4d=False,
        produces_dataset=True,
    ),
    # ----- Processing ----------------------------------------------------
    ToolSpec(
        tool_id="build_index",
        display_name="Build Spatial Index",
        script_path="tools/build_spatial_index.py",
        description="Build a chunked spatial index from a JSONL/CSV catalog.",
        category=CATEGORY_PROCESSING,
        required_inputs=(
            ToolInput("--input", "Input catalog", InputKind.PATH, required=True,
                      help="JSONL or CSV catalog to index."),
            ToolInput("--output", "Index output dir", InputKind.PATH,
                      required=True,
                      help="Directory for index.json + chunks/."),
        ),
        optional_inputs=(
            ToolInput("--chunk-size", "Chunk size", InputKind.INT,
                      required=False,
                      help="Max rows per chunk file."),
        ),
        output_flags=("--output",),
        estimated_runtime_class="medium",
        dependency_profile=DependencyProfile.STDLIB,
        safe_to_run_inside_c4d=True,
        produces_index=True,
    ),
    ToolSpec(
        tool_id="import_db",
        display_name="Import Catalog to DB",
        script_path="tools/import_catalog_to_db.py",
        description="Import a JSONL/CSV catalog into a SQLite UNAV DB.",
        category=CATEGORY_PROCESSING,
        required_inputs=(
            ToolInput("--input", "Input catalog", InputKind.PATH, required=True,
                      help="JSONL or CSV catalog to import."),
            ToolInput("--db", "DB path", InputKind.PATH, required=True,
                      help="Target SQLite DB path."),
        ),
        optional_inputs=(
            ToolInput("--replace", "Replace existing", InputKind.BOOL,
                      required=False,
                      help="Drop + recreate the objects table first."),
        ),
        output_flags=("--db",),
        estimated_runtime_class="medium",
        dependency_profile=DependencyProfile.STDLIB,
        safe_to_run_inside_c4d=True,
        produces_db=True,
    ),
    ToolSpec(
        tool_id="audit_dataset",
        display_name="Audit Dataset",
        script_path="tools/audit_dataset.py",
        description="Run the v3.2 data-integrity audit on a catalog.",
        category=CATEGORY_PROCESSING,
        required_inputs=(
            ToolInput("--input", "Input catalog", InputKind.PATH, required=True,
                      help="JSONL catalog to audit."),
            ToolInput("--output", "Report output", InputKind.PATH, required=True,
                      help="Markdown report output path."),
        ),
        optional_inputs=(
            ToolInput("--json-output", "JSON sidecar", InputKind.PATH,
                      required=False,
                      help="Optional machine-readable JSON report."),
        ),
        output_flags=("--output", "--json-output"),
        estimated_runtime_class="short",
        dependency_profile=DependencyProfile.STDLIB,
        safe_to_run_inside_c4d=True,
    ),
    # ----- Export --------------------------------------------------------
    ToolSpec(
        tool_id="export_visible_sector_binary",
        display_name="Export Visible Sector Binary",
        script_path="tools/export_visible_sector_binary.py",
        description="Export a visible sector to the UNAV binary buffer format.",
        category=CATEGORY_EXPORT,
        required_inputs=(
            ToolInput("--input", "Input catalog", InputKind.PATH, required=True,
                      help="Catalog to filter + export."),
            ToolInput("--navigator-state", "Navigator state JSON",
                      InputKind.PATH, required=True,
                      help="Navigator pose + cone parameters JSON."),
            ToolInput("--output", "Binary output", InputKind.PATH, required=True,
                      help="Output .bin path."),
        ),
        optional_inputs=(
            ToolInput("--max-points", "Max points", InputKind.INT,
                      required=False,
                      help="Hard cap on exported points."),
        ),
        output_flags=("--output",),
        estimated_runtime_class="short",
        dependency_profile=DependencyProfile.STDLIB,
        safe_to_run_inside_c4d=True,
    ),
)


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def list_tools() -> List[ToolSpec]:
    """Return every registered tool in display order."""
    return list(REGISTRY)


def get_tool(tool_id: str) -> Optional[ToolSpec]:
    """Look up a tool by its stable ``tool_id``.
    Returns ``None`` for unknown ids so the panel
    can surface the failure cleanly."""
    if not tool_id:
        return None
    target = tool_id.strip().lower()
    for spec in REGISTRY:
        if spec.tool_id == target:
            return spec
    return None


def tools_in_category(category: str) -> List[ToolSpec]:
    """Return every tool whose ``category`` matches."""
    return [s for s in REGISTRY if s.category == category]
