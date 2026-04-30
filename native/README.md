# UNAV Pro — Native (C++) Skeleton

This folder is the v0.8 **feasibility skeleton** for the future
native Cinema 4D plugin that will draw very large point fields
through the C4D SDK. The sources here do **not** build into a
loaded plugin yet — they are placeholder declarations and stubs
that pin the shape of the eventual implementation, paired with the
v0.8 design docs in `../docs/`:

* [`../docs/V0_8_NATIVE_CPP_FEASIBILITY.md`](../docs/V0_8_NATIVE_CPP_FEASIBILITY.md)
* [`../docs/MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md`](../docs/MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md)
* [`../docs/NATIVE_VIEWPORT_DRAWING_RESEARCH.md`](../docs/NATIVE_VIEWPORT_DRAWING_RESEARCH.md)
* [`../docs/PYTHON_TO_CPP_MIGRATION_PLAN.md`](../docs/PYTHON_TO_CPP_MIGRATION_PLAN.md)
* [`../docs/BINARY_VISIBLE_SECTOR_FORMAT.md`](../docs/BINARY_VISIBLE_SECTOR_FORMAT.md)

The scope of v0.8 is deliberately a **spike**: lock the shape of
the C++ surface, document the SDK research, and ship a real
binary bridge from the Python prototype. Actual plugin building
lands in v0.9+.

---

## Layout

```
native/
├── README.md                  # this file
├── CMakeLists.txt             # build placeholder; not loaded today
├── include/
│   ├── unav_native_plugin.h   # plugin entry-point declarations
│   └── unav_point_buffer.h    # native point-buffer API (matches binary spec)
├── src/
│   ├── unav_native_plugin.cpp # plugin entry-point stubs
│   └── unav_point_buffer.cpp  # native point-buffer stubs
└── docs/                      # native-specific design notes
```

The headers and the binary format together form the migration
contract: when the real Maxon SDK build harness arrives in v0.9,
both sides plug into existing structures rather than negotiating
a new shape.

---

## Why this folder exists today

Three reasons:

1. **API lock-in.** The Python exporter
   (`unav_pro/data/binary_export.py`) and the C++ headers here
   declare *the same* per-point layout. If the Python side
   changes the layout, the C++ side won't compile against the
   stable spec — that's the safety we want.
2. **SDK research has a home.** Maxon's C4D SDK documentation
   evolves between releases (R20 → 2023 → 2024). Notes about
   which plugin types apply to UNAV Pro's needs live next to
   the placeholder source so they're still here when the real
   work starts.
3. **No accidental builds.** The skeleton is intentionally not
   wired into any CI / CMake target. A reader who clones this
   repo gets a Python plugin that runs today plus a C++ skeleton
   that documents tomorrow.

---

## When v0.9 arrives

The plan documented in
[`../docs/PYTHON_TO_CPP_MIGRATION_PLAN.md`](../docs/PYTHON_TO_CPP_MIGRATION_PLAN.md)
fills the placeholders one piece at a time:

1. CMake glue against the Maxon SDK install path.
2. `UnavPointBuffer::loadFromFile(...)` — implement against the
   binary format the Python exporter already produces.
3. `UnavStarfield` ObjectData class — wraps the buffer; exposes
   it via `BaseDraw` callbacks.
4. Selection bridge — depth-pick → `uid_hash` → Python uid via
   the metadata sidecar.
5. Diagnostics integration — surface "engine: native" in the
   v0.6 Diagnostics dialog.

Until then, the Python prototype is the production engine; the
C++ skeleton is the destination.

---

## Building (future)

When the build harness lands, the recommended toolchain is:

* CMake 3.20+
* C++17 compiler (MSVC 2022 / clang 14+ / gcc 11+)
* Cinema 4D SDK 2024.x (or the matching SDK for the target
  C4D 2023+ host).

The current `CMakeLists.txt` is a placeholder with notes for the
v0.9 implementer; running CMake on it today is intentionally a
no-op.
