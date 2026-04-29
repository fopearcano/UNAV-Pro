"""Plugin ID registry.

Cinema 4D requires every registered plugin (CommandData, ObjectData,
TagData, etc.) to have a unique integer ID obtained from Maxon's
PluginCafe. The IDs below are *development placeholders* in the
1000001–1000010 range reserved by Maxon for local testing. They MUST
be replaced with officially registered IDs before any public release.

Reference: https://plugincafe.maxon.net/
"""

# --- Development placeholders -------------------------------------------------
# WARNING: replace before release.

PLUGIN_ID_MAIN_COMMAND = 1000001  # "Universal Navigator Pro" menu command
PLUGIN_ID_MAIN_DIALOG = 1000002   # Main dialog window

# Reserved for upcoming plugin classes (kept here so future code can refer
# to a single source of truth).
PLUGIN_ID_UNAV_UNIVERSE = 1000003   # ObjectData
PLUGIN_ID_UNAV_DATASET = 1000004    # ObjectData
PLUGIN_ID_UNAV_FILTER_CONE = 1000005  # TagData
PLUGIN_ID_UNAV_INSPECTOR = 1000006   # CommandData
PLUGIN_ID_UNAV_INGEST = 1000007      # CommandData
PLUGIN_ID_UNAV_PREFERENCES = 1000008  # PreferenceData


def all_ids():
    """Return every reserved ID; useful for collision checks in tests."""
    return [
        PLUGIN_ID_MAIN_COMMAND,
        PLUGIN_ID_MAIN_DIALOG,
        PLUGIN_ID_UNAV_UNIVERSE,
        PLUGIN_ID_UNAV_DATASET,
        PLUGIN_ID_UNAV_FILTER_CONE,
        PLUGIN_ID_UNAV_INSPECTOR,
        PLUGIN_ID_UNAV_INGEST,
        PLUGIN_ID_UNAV_PREFERENCES,
    ]
