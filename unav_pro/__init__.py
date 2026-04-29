"""UNAV Pro — Cinema 4D plugin package.

This package is loaded by Cinema 4D 2023+ via ``unav_plugin.pyp``. The
``.pyp`` entry point inserts this directory into ``sys.path`` so the
sub-packages (``core``, ``ui``, ``data``, ``c4d_objects``) are importable
as top-level modules from inside C4D's Python host.
"""

__version__ = "0.1.0"
__author__ = "UNAV Pro contributors"
__plugin_name__ = "Universal Navigator Pro"

# Minimum Cinema 4D API version we support. C4D 2023 reports 26000 from
# c4d.GetC4DVersion(); C4D 2024 reports 2024xxx. The version_check module
# accepts both schemes.
MIN_C4D_VERSION = 26000
