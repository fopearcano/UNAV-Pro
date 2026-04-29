# UNAV Pro — Roadmap to a C++ / GPU Version

What the Python prototype proved, where it stops scaling, and how
each bottleneck migrates to a native or GPU implementation behind
**the same** scene model, dialog surface, and on-disk formats. The
plugin's feature set does not change in this roadmap; the engine
underneath it does.

For per-feature limitations today see
[`LIMITATIONS.md`](LIMITATIONS.md). For the architectural rationale
that already shaped the codebase to allow this migration see
[`UNAV_PRO_ARCHITECTURE.md`](UNAV_PRO_ARCHITECTURE.md) §5 and
[`UNAV_PRO_C4D_PLUGIN_STRATEGY.md`](UNAV_PRO_C4D_PLUGIN_STRATEGY.md) §4.

---

## 1. Why the Python prototype hits a ceiling

The plugin's hot paths are all bounded by three things, in this
order:

### 1.1 GIL-bound per-object allocation

Every catalog row that survives the filter becomes a
`c4d.BaseObject(c4d.Onull)` allocated through the Python API.
The C4D allocator is fast individually (low microseconds) but
serial: ten thousand allocations take seconds. A million takes
minutes if it doesn't OOM first.

* `core/spatial_filter.apply_filter` handles 1 M rows in the
  hundreds of milliseconds — it's not the limit.
* `c4d_objects/point_cloud_builder.build_point_object` is the
  limit. It's the *only* code path that has to touch the host
  for every row.

### 1.2 Per-object scene state

Every `BaseObject` carries:

* a `BaseContainer` for ID + display flags + the UNAV marker
  sub-container (~ 40 bytes minimum even with the minimal-marker
  policy);
* an entry in C4D's selection / undo / cache structures;
* a cell in the Object Manager's tree, redrawn on every refresh.

At ten thousand objects the Object Manager itself becomes the
bottleneck on selection and right-click. At a million the host
freezes.

### 1.3 Float32 viewport precision

C4D's viewport stack is float32. Stellar-scale scenes (parsec
distances, kpc fly-throughs) exhaust the precision long before
the object-count limit hits.

The mitigation is documented as the **floating origin** rule in
[`UNAV_PRO_ARCHITECTURE.md`](UNAV_PRO_ARCHITECTURE.md) §3.6, but
implementing scene rebasing while the viewport is moving is
itself non-trivial in pure Python — you have to sweep every
materialized object's `SetAbsPos` call on every rebase, which
hits the same per-object limit as construction.

---

## 2. The contract that survives migration

Every consumer of the visible sector sees three things, all of
which stay invariant across the C++ migration:

* **The hierarchy.**
  `UNAV_Starfield → UNAV_VisibleSector → point objects`,
  identified by the `BC_ID_UNAV_MARKER` container.
* **The marker contract.** uid + source + type + name + RA/Dec/
  distance, optionally + the metadata blob behind a safety
  flag. See [`POINT_CLOUD_GENERATION.md`](POINT_CLOUD_GENERATION.md)
  §1 and [`LARGE_DATA_SAFETY.md`](LARGE_DATA_SAFETY.md) §4.
* **The on-disk formats.**
  JSONL catalogs, `index.json` + chunk files,
  `~/.unav_pro/projects/<scene>.json` sidecars, the document's
  BaseContainer state slot.

Everything below the marker — how the objects are *drawn*, how
the catalog is *read*, how the cone is *filtered* — is allowed to
change.

---

## 3. The migration phases

### Phase A — numpy vectorization (no native code yet)

**Cost:** small. **Headroom:** ~10× on filter and 5× on chunk read.

| Replace                                | With                                                   |
|----------------------------------------|--------------------------------------------------------|
| `core/spatial_filter.apply_filter` Python loop | numpy array arithmetic on `(N, 3)` position arrays. |
| `data/catalog_io._load_jsonl` line-by-line parse | `pyarrow.json` reader. |
| `core/spatial_index.build_index` bucketing loop | `numpy.floor_divide` for cell indices. |

This phase keeps the plugin stdlib-only at *runtime* and adds
numpy + pyarrow as preprocessing dependencies for the offline
CLIs only. The plugin code path doesn't change. Useful for
artists who run on the C4D-bundled interpreter and don't want
to install scientific stacks into it.

This phase **does not solve** the GIL-bound per-object allocator,
which is the headline limit. It only widens the on-disk and
in-memory pipes feeding it.

### Phase B — `MatrixObject` instance grid

**Cost:** medium. **Headroom:** 100 k → ~ 200 k objects.

Replace the per-row `Onull` materializer with a single
`c4d.MatrixObject` (`Omgmatrix`) carrying an array of
`c4d.Matrix` instances. One `BaseObject`, N matrices. The Object
Manager sees one node; the viewport draws the matrices in a
single C4D call.

Trade-off: per-instance metadata cannot live on a per-instance
`BaseContainer`. The marker payload moves to a side-car: a
parallel UNAV array stored on the parent's marker container,
indexed by the matrix slot. Selection becomes "select an index"
rather than "select a `BaseObject`"; the metadata inspector
grows a hit-test path that maps a clicked matrix back to a uid.

The diff-and-update workflow ([`SCENE_SYNC_WORKFLOW.md`](SCENE_SYNC_WORKFLOW.md))
becomes "rewrite the matrix array" rather than "remove and add
nodes." Faster, but loses C4D's free undo per object.

### Phase C — C++ ObjectData + ViewportDraw

**Cost:** large (one Maxon SDK module). **Headroom:** ~ 200 k → 2 M.

The headline migration. Replace the Python materializer with a
C++ ObjectData plugin that:

* exposes a single `UnavStarfield` scene-object type;
* stores a packed point buffer
  (`uid[u64], xyz[f32×3], color[u32], size[f16], flags[u16]`)
  in C++ memory;
* draws the buffer via a `ViewportDraw` (or a Maxon SDK
  `BaseDraw` callback) issuing a single GL/Metal/Vulkan call
  per redraw;
* implements `Read` / `Write` so the buffer survives `.c4d`
  save/load through Maxon's serializer.

The Python dialog stays. Generation flows from
`mock_actions.generate_point_cloud` into an
`EngineClient.set_buffer(uids, positions, colors, sizes)`
function that passes a numpy array directly into the C++ buffer
via `pybind11` or Maxon's data-transfer hooks.

The marker container moves up to the `UnavStarfield` parent
(one container holding the per-instance side-car), exactly the
shape the matrix-grid phase already established.

This phase is what scales the plugin to a navigator-bounded
million-point scene. The on-disk formats and the dialog do not
change.

### Phase D — GPU compute for the filter

**Cost:** medium *given* phase C is in place. **Headroom:**
makes per-frame re-sync feasible.

Once the cone filter and the AABB-vs-cone gate are in C++,
porting them to a GPU compute kernel (CUDA / Metal /
Vulkan compute) is straightforward:

* Upload the catalog's `(N, 3)` positions to a GPU buffer once.
* Per query: dispatch a kernel that writes a `[N]` boolean
  mask and a packed survivor count.
* Read back the mask + the surviving positions.

For animation-quality re-sync (60 fps as the navigator drags),
this is the only path. The cone-vs-cell prefilter the spatial
index already provides means the GPU never sees more than the
candidate cells' rows; the GPU's job is exact rejection on a
working set of ~ 100 k–1 M.

### Phase E — Real-time sector streaming

**Cost:** medium *given* phase D is in place. **Headroom:**
infinite-catalog (cache-bound) navigation.

Per-frame re-sync without re-reading anything from disk. Cache
the loaded chunks in C++; use the navigator's velocity to
prefetch the cells the cone is about to enter; LRU-evict the
ones it's leaving.

This is what turns *Auto Sync* (currently a placeholder
checkbox — see [`LIMITATIONS.md`](LIMITATIONS.md) §2) into
a real feature. The user drags the navigator; the visible
sector follows at framerate.

### Phase F — Future binary cache

**Cost:** small. **Headroom:** halves disk footprint and parses
~10× faster.

The on-disk JSONL chunks the spatial index produces today are
text and parser-bound. A binary chunk format (the same
struct-of-arrays layout as the in-engine point buffer) is
mmap-friendly, columnar, and indexed by row.

`core.spatial_index.SpatialIndex` already abstracts the chunk
backend; swapping JSONL for the binary format is a `chunk_io`
module replacement. The plugin's `query_index` signature
doesn't change.

This phase is in [`SPATIAL_INDEXING_AND_CHUNKING.md`](SPATIAL_INDEXING_AND_CHUNKING.md)
§8 as one of the migration backends. Combined with phase A
(numpy / pyarrow on the read path) it gives the offline pipeline
a 10× write-and-read speedup without any C++.

### Phase G — Future render-pass parity

**Cost:** depends on the renderer.

The C++ point buffer of phases C–E is *editor-visible*; final-
frame renderers (Standard, Physical, Redshift, Octane, Cycles)
each need their own integration:

* **Standard / Physical.** Native consumer of `MatrixObject`
  instance arrays — phase B already gets you there.
* **Redshift / Octane / Cycles.** Each has an SDK for instance
  procedurals. The `UnavStarfield` ObjectData of phase C exposes
  a uniform "give me back instance matrices for the buffer"
  callback that the per-renderer plugins can hook into.

This phase is per-renderer and is the longest tail of the
roadmap. The current workaround (Mograph Cloner per-object,
or alembic export) is acceptable until the matrix-grid phase
ships.

---

## 4. Migration order

The phases are independent; the **recommended** order is the
one that buys the most user-visible improvement per unit of
work:

1. **Phase A (numpy/pyarrow ingest).** A weekend's work.
2. **Phase B (MatrixObject grid).** Two-week-ish project.
3. **Phase C (C++ ObjectData).** Multi-month, but unlocks every
   subsequent phase.
4. **Phase F (binary cache).** Plugs in at any time after A.
5. **Phase D (GPU filter)** + **Phase E (streaming).** Sequential
   on top of C.
6. **Phase G (renderer integrations).** As needed per project.

Skipping C means the plugin caps at ~200 k objects forever.
Skipping D means *Auto Sync* never ships at framerate.

---

## 5. What does *not* change

Spelling out the contract again so the migration cannot
accidentally break it:

* **Buttons + dialog layout.** Same actions, same logs, same
  status strip.
* **Hierarchy.** `UNAV_Navigator`, `UNAV_Starfield`,
  `UNAV_VisibleSector`, `UNAV_Debug`, `UNAV_Route`. The
  ObjectData's name is `UNAV_Starfield` or `UNAV_VisibleSector`,
  not "UnavGpuPointCloud".
* **Marker container.** `BC_ID_UNAV_MARKER` carrying uid +
  source + type + name + RA/Dec/distance. C++ writes the same
  container; *Clear Scene* identifies UNAV objects by it
  regardless of who made them.
* **On-disk formats.** JSONL → optional binary, but the JSONL
  reader survives as a fallback path (the schema doesn't
  change).
* **Project state file.** `~/.unav_pro/projects/<scene>.json`
  has a `schema_version`; bumping it is allowed but the
  current shape is forward-compatible.
* **CLI tools.** `tools/fetch_*.py` and
  `tools/build_spatial_index.py` keep their argparse
  signatures; native acceleration is opt-in and replaces only
  the implementation.
* **Tests.** The 500+ pure-CPython tests stay green during the
  migration. Native code adds parallel tests; it does not
  delete the Python ones.

The Python implementation remains the **reference**: every C++
behaviour must agree with the Python tests on the small inputs
those tests use.

---

## 6. Failure modes during migration

When phase C lands, the plugin must:

* Detect at startup whether the C++ engine library is present
  (cross-platform `find_library` / `os.path.isfile`).
* Fall back to the Python implementation if not. The plugin
  must remain usable on a machine without the native code.
* Surface the active engine in the **Diagnostics** dialog
  (`Engine: native v1.0.0` or `Engine: python (fallback)`).

This is the same pattern numpy uses for its BLAS dispatch and
the same one Maxon's own Cycles integration follows for GPU
fallbacks. The user never sees a hard requirement on the
native binary.

---

## 7. The closing argument

The Python prototype is a deliberate floor, not a ceiling. Every
piece — the schema, the spatial index, the cone filter, the
scene-sync diff, the marker contract, the safety system — was
designed knowing it would be replaced. The replacements are
constrained by the contracts in §5; everything else is open.

If the plugin reaches a million-point scene without losing the
diff-and-update workflow, the navigator-bounded safety system,
or the metadata inspector's "click-anywhere-and-the-data-shows-
up" behaviour, the migration succeeded.
