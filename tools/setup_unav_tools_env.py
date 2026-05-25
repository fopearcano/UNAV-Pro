#!/usr/bin/env python3
"""Create the external Python environment for UNAV Pro's tools.

The heavy preprocessing tools (Gaia / JPL / SDSS / DESI fetch, spatial
index, DB import, audit, export) run in a Python interpreter that is
*separate* from Cinema 4D's embedded one. This helper bootstraps a
dedicated virtual environment for them and installs
``requirements-tools.txt`` into it.

Usage::

    # use the interpreter that's running this script
    python tools/setup_unav_tools_env.py

    # choose where the venv lives (default: <repo>/.venv-unav-tools)
    python tools/setup_unav_tools_env.py --venv ~/.unav_pro/tools-venv

    # just print the interpreter path of an existing venv
    python tools/setup_unav_tools_env.py --print-only

On success the **last line printed is the absolute path to the venv's
Python interpreter** — paste it into the plugin's *External Tools →
Python Environment* field (or it'll be auto-detected). The script is
stdlib-only and safe to run with any Python 3.10+.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import venv


MIN_PYTHON = (3, 10)
DEFAULT_VENV_DIRNAME = ".venv-unav-tools"


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def _venv_python(venv_dir: str) -> str:
    """Absolute path to the interpreter inside ``venv_dir``."""
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def _check_host_python() -> None:
    if sys.version_info[:2] < MIN_PYTHON:
        sys.stderr.write(
            f"ERROR: this helper needs Python >= {MIN_PYTHON[0]}."
            f"{MIN_PYTHON[1]}; you ran {sys.version.split()[0]}.\n"
        )
        raise SystemExit(2)


def create_venv(venv_dir: str) -> str:
    """Create a virtual environment at ``venv_dir`` (idempotent) and
    return the path to its interpreter."""
    py = _venv_python(venv_dir)
    if os.path.isfile(py):
        print(f"venv already exists: {venv_dir}")
        return py
    print(f"Creating venv at {venv_dir} …")
    builder = venv.EnvBuilder(with_pip=True, upgrade_deps=False)
    builder.create(venv_dir)
    if not os.path.isfile(py):
        sys.stderr.write(f"ERROR: venv creation did not yield {py}\n")
        raise SystemExit(1)
    return py


def install_requirements(py: str, requirements: str) -> None:
    """Install ``requirements`` into the venv at interpreter ``py``.

    The bundled requirements file is effectively empty (stdlib-only),
    so this is usually a fast no-op that simply ensures pip is current.
    """
    print("Upgrading pip …")
    subprocess.run(
        [py, "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
    )
    if os.path.isfile(requirements):
        print(f"Installing {requirements} …")
        subprocess.run(
            [py, "-m", "pip", "install", "-r", requirements],
            check=True,
        )
    else:
        print(f"(no requirements file at {requirements}; skipping)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap the external Python env for UNAV tools.",
    )
    parser.add_argument(
        "--venv",
        default=os.path.join(_repo_root(), DEFAULT_VENV_DIRNAME),
        help="Directory for the virtual environment.",
    )
    parser.add_argument(
        "--requirements",
        default=os.path.join(_repo_root(), "requirements-tools.txt"),
        help="Requirements file to install into the venv.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Don't create anything; just print the venv interpreter path.",
    )
    args = parser.parse_args(argv)

    venv_dir = os.path.abspath(os.path.expanduser(args.venv))

    if args.print_only:
        print(_venv_python(venv_dir))
        return 0

    _check_host_python()
    py = create_venv(venv_dir)
    install_requirements(py, os.path.abspath(os.path.expanduser(args.requirements)))

    print("\nDone. External tools Python interpreter:")
    # Final line: the interpreter path (machine-friendly).
    print(os.path.abspath(py))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
