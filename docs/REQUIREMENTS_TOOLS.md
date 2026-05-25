# External Tools Requirements

This explains `requirements-tools.txt` — the dependency list for the
**external** Python environment that runs UNAV Pro's preprocessing
tools. It is **not** for Cinema 4D's embedded interpreter.

## The short version

**The bundled tools have zero third-party dependencies.** Every tool
that ships with UNAV Pro runs on the Python 3.10+ standard library
alone:

- the data connectors (Gaia / JPL / SDSS / DESI) use `urllib` for HTTP,
- the index / DB / audit / export tools use `json`, `csv`, `sqlite3`,
  `struct`, etc.

So a clean Python 3.10+ is enough. `requirements-tools.txt` installs
nothing by default.

## Why the file exists anyway

Two reasons:

1. **Reproducible setup.** `tools/setup_unav_tools_env.py` installs this
   file into a fresh venv, so the setup path is the same whether or not
   there are extras.
2. **A place for your extensions.** If you write your own preprocessing
   tools that need scientific packages, this is where they go. The file
   ships with the common ones commented out:

   ```
   # requests>=2.31
   # numpy>=1.26
   # pandas>=2.1
   # astropy>=6.0
   # astroquery>=0.4.7
   ```

   Uncomment only what you actually need, then re-run the setup helper.
   They're commented so a default install stays small and **no large
   download happens unless you ask for it**.

## Installing

```sh
# create the venv and install requirements-tools.txt into it
python tools/setup_unav_tools_env.py
```

Or, into an interpreter you manage yourself:

```sh
/path/to/python -m pip install -r requirements-tools.txt
```

## What must NOT go here for C4D

Nothing about the C4D plugin runtime depends on this file. Do not try to
install these packages into Cinema 4D's embedded Python — the plugin is
deliberately stdlib-only inside the host, and the whole point of the
external environment is to keep heavy packages out of C4D.

## Version pins

The commented extras use lower-bound pins (`>=`) rather than exact pins
so they don't fight whatever else is in your environment. If you need
reproducible builds for a team, copy `requirements-tools.txt` to a
project-local file and pin exact versions there.
