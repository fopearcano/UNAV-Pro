"""Catalog source connectors.

Each module here is a concrete adapter onto an external astrophysical
archive (Gaia, SDSS, DESI, ...). All connectors are *out-of-process*
preprocessing tools: they import only the standard library plus the
plugin's local schema/IO, and they never need Cinema 4D running.

See ``docs/UNAV_PRO_DATA_PIPELINE.md`` for the wider pipeline
contract; see each connector's docstring for the source-specific
column mapping.
"""
