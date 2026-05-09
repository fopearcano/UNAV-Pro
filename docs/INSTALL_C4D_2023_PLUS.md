# Installing UNAV Pro in Cinema 4D 2023+

This guide covers installing the UNAV Pro Python plugin into Cinema 4D
2023, 2024, and 2025 on Windows and macOS. The plugin is delivered as
the ``unav_pro/`` directory in this repository — there is no compiled
binary to build for the Python prototype.

> **Status (v2.4):** Production. The plugin registers
> ``Extensions → Universal Navigator Pro`` with a full
> dialog (search / bookmarks / navigation / missions /
> overlays). For the five-minute install + smoke-test
> walkthrough, see [`QUICK_START.md`](QUICK_START.md).
> For diagnosis when something goes wrong, see
> [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

---

## 1. Requirements

- **Cinema 4D 2023 or newer** (R26 / 2024 / 2025).
  The plugin checks ``c4d.GetC4DVersion()`` at startup and refuses to
  register if the host reports an API version below ``26000``. The
  refusal is logged; Cinema 4D itself will start normally.
- **No external Python packages are required for the MVP.** Future
  phases will introduce `numpy`, `pyarrow`, `astropy`, `healpy`. Those
  must be installed into the Python interpreter that Cinema 4D ships
  with — see §5.
- **Operating systems:** Windows 10/11, macOS 12+ (Apple Silicon and
  Intel), Linux (where C4D is supported).

---

## 2. Locate the C4D plugins directory

Cinema 4D scans several directories at startup. Choose **one**:

### Per-user (recommended for development)

| OS       | Path                                                                 |
|----------|----------------------------------------------------------------------|
| Windows  | `%APPDATA%\Maxon\Maxon Cinema 4D <version>_<id>\plugins\`             |
| macOS    | `~/Library/Preferences/Maxon/Maxon Cinema 4D <version>_<id>/plugins/` |
| Linux    | `~/.config/Maxon/Maxon Cinema 4D <version>_<id>/plugins/`             |

Replace `<version>_<id>` with the actual folder Cinema 4D created on
first launch (example: `Maxon Cinema 4D 2024_F1B2C3D4`).

### System-wide

The application install directory's ``plugins/`` subfolder. On
Windows this is typically
``C:\Program Files\Maxon Cinema 4D <version>\plugins\``. Writing here
requires administrator privileges and is not recommended during
development.

You can also confirm the active plugin search paths from inside C4D:

```
Edit → Preferences → Files → Plugins
```

---

## 3. Install the plugin

### Option A — copy

1. Close Cinema 4D.
2. Copy the entire ``unav_pro/`` directory from this repository into
   the plugins directory chosen in §2.
3. Verify that the resulting structure is:

   ```
   <plugins_dir>/
     unav_pro/
       unav_plugin.pyp
       __init__.py
       core/
       ui/
       data/
       c4d_objects/
       docs/
       tests/
   ```

4. Start Cinema 4D.

### Option B — symlink (development)

A symlink lets you edit the plugin in place and reload it without
copying.

**macOS / Linux:**

```bash
ln -s /absolute/path/to/UNAV-Pro/unav_pro \
      "<plugins_dir>/unav_pro"
```

**Windows (PowerShell, as Administrator):**

```powershell
New-Item -ItemType SymbolicLink `
  -Path "<plugins_dir>\unav_pro" `
  -Target "C:\absolute\path\to\UNAV-Pro\unav_pro"
```

Reload the plugin from C4D with **Extensions → Reload Python Plugins**
after editing.

---

## 4. Verify the install

1. Launch Cinema 4D.
2. Open the menu: **Extensions → Universal Navigator Pro**.
   - If the menu entry appears: registration succeeded.
   - If it is missing: see §6.
3. Click the menu entry. The UNAV Pro dialog opens with four buttons
   (Load Dataset / Create Navigation Null / Generate Point Cloud /
   Clear Scene) and a status log. Each button appends a mock status
   line to the log.

You can also confirm registration from the **Script Manager** /
**Python Console** inside C4D:

```python
import c4d
print(c4d.gui.SearchPluginMenuResource())  # menus contain UNAV Pro
```

---

## 5. Adding Python dependencies later

When the data layer goes live, dependencies must be installed into the
Python interpreter that Cinema 4D ships with — **not** the system
Python. The interpreter lives inside the C4D install directory. As an
example for C4D 2024 on macOS:

```
/Applications/Maxon Cinema 4D 2024/resource/modules/python/libs/python311.macos.framework/Versions/Current/bin/python3
```

Run that interpreter with `-m pip install <package>`. Until the data
layer lands, no dependency installs are necessary.

---

## 6. Troubleshooting

### The menu entry doesn't appear

- Check the C4D Python Console (**Extensions → Console**) for lines
  prefixed with ``[UNAV Pro]`` or logger lines from ``unav_pro.*``.
- Open the persistent log file:
  - Windows: ``%TEMP%\unav_pro\unav_pro.log``
  - macOS / Linux: ``$TMPDIR/unav_pro/unav_pro.log`` (typically
    ``/tmp/unav_pro/unav_pro.log``).
- Confirm the directory is named exactly ``unav_pro`` (lowercase) and
  contains ``unav_plugin.pyp`` at its root.

### "Unsupported host" log line

Your Cinema 4D version reports an API number below ``26000`` (older
than C4D 2023). Upgrade C4D or run on a supported host.

### Import errors at startup

The plugin's ``.pyp`` adds ``unav_pro/`` to ``sys.path``. If another
plugin already exposes top-level modules named ``core``, ``ui``,
``data``, or ``c4d_objects``, names will collide. Rename the
conflicting plugin or sandbox the imports — file an issue with the
log file attached.

### Read-only filesystem

The logger silently falls back to console-only logging if it cannot
create ``<temp>/unav_pro/``. Functionality is unaffected; the only
visible change is the absence of a persistent log file.

---

## 7. Uninstall

Close Cinema 4D and delete the ``unav_pro`` directory from your
plugins folder. No registry entries, daemons, or shared system files
are touched.
