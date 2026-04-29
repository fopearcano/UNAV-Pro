"""Pytest configuration: make the plugin's sub-packages importable.

The plugin's ``.pyp`` entry point inserts the plugin root into
``sys.path`` so that ``from core import ...`` works inside C4D. Tests
follow the same convention so the modules under test see their imports
resolve identically.
"""

from __future__ import annotations

import os
import sys

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
