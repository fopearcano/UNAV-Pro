# External Tools — Python Environment

The preprocessing tools run in a Python interpreter that is **separate**
from Cinema 4D's embedded one. This page explains how to set one up and
point the plugin at it.

## TL;DR

1. Make sure you have **Python 3.10 or newer** installed on your
   machine (`python3 --version`).
2. (Recommended) Create a dedicated virtual environment:

   ```sh
   python tools/setup_unav_tools_env.py
   ```

   The **last line printed is the interpreter path** — copy it.
3. In **External Tools → Python Environment**, paste that path (or
   click **Detect**), click **Validate**, then **Save**.

That's it. The bundled tools need nothing beyond the standard library,
so a clean Python 3.10+ works out of the box.

## How the plugin finds a Python

Resolution order (`unav_pro/tools/python_env.py`):

1. **Configured path** — whatever you saved in the panel
   (`external_python_path` in `~/.unav_pro/config.json`), if the file
   still exists.
2. **Auto-detected default** — the first of `python3.13`, `python3.12`,
   …, `python3`, `python` found on `PATH` that is **not** Cinema 4D's
   embedded interpreter.

The detector deliberately skips any interpreter whose path looks like a
Cinema 4D install (contains `cinema 4d`, `maxon`, or `c4dpy`) so it
never accidentally picks the embedded Python you're trying to avoid.

## Validation

**Validate** runs `<python> --version` (bounded by a 10-second timeout
so it can never hang the dialog) and parses the result. You'll see one
of:

- `Python 3.12.1 @ /usr/bin/python3` — good to go.
- `Python 3.9.7 @ … — below the 3.10 minimum` — works to launch, but
  the tools target 3.10+; upgrade if a tool misbehaves.
- `Python: invalid (…)` — the path isn't a runnable interpreter.

Validation **never raises**: a missing file, a timeout, or a crash all
map to a clear status string.

## Using a virtual environment

`tools/setup_unav_tools_env.py`:

- creates a venv (default `<repo>/.venv-unav-tools`, override with
  `--venv`),
- upgrades pip,
- installs `requirements-tools.txt` (a no-op for the bundled tools —
  they're stdlib-only),
- prints the venv interpreter path as its final line.

```sh
# custom location
python tools/setup_unav_tools_env.py --venv ~/.unav_pro/tools-venv

# just print the path of an existing venv (creates nothing)
python tools/setup_unav_tools_env.py --print-only
```

## What is NOT installed into Cinema 4D

Nothing. The C4D plugin runtime stays stdlib-only. You never need to
`pip install` numpy / pandas / astroquery into Cinema 4D's embedded
Python — and you shouldn't. All third-party packages (if you add any
for your own extension tools) live in the external environment only.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| "no external Python configured" when you click Run | Set + Save a path in the Python Environment section. |
| Detect finds nothing | Install Python 3.10+ and ensure it's on `PATH`, or paste a full path with **Browse…**. |
| A fetch tool fails with `ModuleNotFoundError` | Your *own* extension tool needs a package — add it to `requirements-tools.txt` and re-run the setup helper. The bundled tools never need this. |
| Validation says "below the 3.10 minimum" | Point at a newer interpreter. |
