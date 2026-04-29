# UNAV Pro v0.2 — Acceptance Tests

Manual + automated tests that prove the v0.2 sector-streaming
contract. Each item lists the assertion it certifies and where the
evidence lives (an automated test, a manual scene check, or both).

For the conceptual workflow these tests verify, see
[`V0_2_SECTOR_STREAMING_WORKFLOW.md`](V0_2_SECTOR_STREAMING_WORKFLOW.md).

---

## A. Automated tests (run without Cinema 4D)

```
cd unav_pro
python -m pytest tests/ -q
```

All **573 tests** pass. The v0.2-specific subset:

| Test                                                             | What it proves                                                                 |
|------------------------------------------------------------------|--------------------------------------------------------------------------------|
| `test_sector_streaming.test_indexed_dataset_uses_index_and_excludes_far` | An indexed dataset is queried via the spatial index; far-clipped cells are not loaded. |
| `test_sector_streaming.test_indexed_dataset_namespaces_uids`     | Streamed uids are prefixed `<entry.name>:`.                                    |
| `test_sector_streaming.test_indexed_dataset_respects_navigator_cap` | The navigator's `max_visible_objects` truncates the streamed result.        |
| `test_sector_streaming.test_indexed_dataset_dropped_index_dir_falls_back_to_catalog` | A stale `index_path` correctly falls back to the unindexed path.   |
| `test_sector_streaming.test_indexed_dataset_query_failure_surfaces_error` | A `query_index` exception surfaces as `DatasetStreamResult.error`; no scene mutation. |
| `test_sector_streaming.test_unindexed_dataset_falls_back_to_full_load` | Unindexed catalog uses `load_catalog` + filter; small catalog → no warning. |
| `test_sector_streaming.test_unindexed_large_dataset_emits_warning` | Above the size threshold, an explicit warning recommends Build Index.        |
| `test_sector_streaming.test_unindexed_huge_dataset_refuses_outright` | Above the hard ceiling, the streamer refuses outright; the scene is untouched. |
| `test_sector_streaming.test_unindexed_dataset_namespaces_uids`   | Fallback path also namespaces uids.                                            |
| `test_sector_streaming.test_unindexed_dataset_missing_file_records_error` | Missing file becomes a `DatasetStreamResult.error`.                          |
| `test_sector_streaming.test_multi_dataset_merges_namespaced_results` | Multiple enabled entries combine into a single namespaced merged list.       |
| `test_sector_streaming.test_multi_dataset_skips_disabled_entries` | Disabled entries do not appear in `per_dataset`.                               |
| `test_sector_streaming.test_multi_dataset_global_cap_truncates_after_merge` | Navigator's cap is enforced on the *post-merge* total.                  |
| `test_sector_streaming.test_multi_dataset_no_enabled_yields_empty` | Registry without enabled entries returns an empty result, no error.           |
| `test_sector_streaming.test_multi_dataset_short_summary_includes_warnings` | `StreamResult.short_summary` mentions warning counts when relevant.       |
| `test_sector_streaming.test_workflow_step_*` (×5)                | The five workflow-step branches map to the right hint.                         |
| `test_spatial_index.*` (20 tests)                                | Index build, manifest round-trip, and `query_index` correctness.               |
| `test_scene_sync.*` (21 tests)                                   | `compute_diff` add/keep/remove correctness — **no duplication on resync**.     |
| `test_metadata_lookup.*` and `test_metadata_panel.*` (42 tests)  | uid → CatalogObject lookup; marker-only fallback; clipboard JSON.              |
| `test_safety.*` (34 tests)                                       | Hard cap, navigator gate, advisory warnings, override semantics.               |

---

## B. Manual acceptance — Cinema 4D 2023+

Reproduce on a clean install. Each scenario lists the
expected status-log fragment.

### 1. Cold start, bundled sample

1. Open the dialog (Extensions → Universal Navigator Pro).
2. Workflow strip reads either *Step 1/5* or *Step 2/5* depending
   on whether the bundled sample auto-registered.
3. Click **Create Navigation Null**. Workflow strip moves to
   *Step 4/5*.
4. Click **Sync Visible Sector**.
5. Expected log:
   `+N added, =0 kept, -0 removed; stream: N visible (of N candidates)`
   or, if the bundled sample is unindexed:
   `+N added, …; stream: N visible (of 100 candidates) | warn: …`
   (size warning fires only above the threshold; the bundled
   sample is well under it).
6. Workflow strip moves to *Step 5/5*.

### 2. Real Gaia region — fetch + index + stream

1. From a terminal:
   ```
   python tools/fetch_gaia_region.py \
       --ra 56.75 --dec 24.12 --radius-deg 1.0 \
       --limit 5000 --output data/gaia_pleiades.jsonl
   python tools/build_spatial_index.py \
       --input data/gaia_pleiades.jsonl \
       --output cache/gaia_pleiades --chunk-size 5000
   ```
2. In C4D, open the **Dataset Manager…** and **Add Dataset**
   `data/gaia_pleiades.jsonl`. Set its **Index Path** to
   `cache/gaia_pleiades` (Build Index inside the dialog also
   works).
3. Disable the bundled sample. **Load Active Datasets**.
4. Position the navigator at the scene origin.
5. Click **Sync Visible Sector**.
6. Expected log fragment:
   `stream: <kept> visible (of <candidates> candidates)` —
   the *candidate count* should be substantially less than the
   total catalog size, proving sector streaming.
7. The Diagnostics dialog reports the active lookup's row count
   matching `<kept>`, not the full catalog.

### 3. Diff-and-update non-duplication

1. Open the Object Manager. Select one of the generated UNAV
   point objects. Tag it with a custom name.
2. Drag the navigator a small amount.
3. Click **Sync Visible Sector**. Log shows `=N kept` for some
   N; the previously-tagged object is still in the scene with
   its custom name intact.
4. Drag the navigator far enough that the object falls outside
   the cone. Sync again. Log shows `-1 removed` for that uid;
   no duplicates.

### 4. Metadata externalization

1. Inspect any generated UNAV object. Confirm the panel shows
   full astrometry / photometry — proving the metadata reaches
   the Inspector.
2. Open the C4D `BaseContainer` of that object via the Attribute
   Manager → User Data → marker container. Confirm only
   minimal fields are stored: uid, source, type, name, RA, Dec,
   distance. **No `metadata_json` blob.** (`embed_full_metadata_in_marker`
   stays off by default.)
3. Save the scene. Reopen on a machine **without** the dataset
   registered. The Inspector now falls back to "marker only"
   rendering — but the scene still loads, and the per-object
   uid + source is intact.

### 5. Save / Load state round-trip

1. Configure the navigator + active dataset + visual encoding.
2. Click **Save UNAV State**. Confirm log lists both the scene
   container and the sidecar path.
3. Save the C4D scene. Close C4D.
4. Reopen C4D, open the saved `.c4d`. Open the dialog. Click
   **Load UNAV State**.
5. Workflow strip + Diagnostics confirm the restored navigator
   parameters, the enabled dataset list, and the visual
   encoding.

### 6. Safety enforcement — refuse universe materialization

1. Disable all enabled datasets *except* one large unindexed
   dataset (synthetic million-row catalog OK).
2. Click **Sync Visible Sector**.
3. Expected log: `warn: dataset '<name>' has <N> rows and is not
   indexed; loading the whole file. Build Index in the Dataset
   Manager for sector-streaming I/O.`
4. Build the index. Re-sync. The candidate-count drops
   dramatically; the warning disappears.

### 7. Safety enforcement — hard ceiling

1. Edit the dataset's stats (or use a synthetic 6 M-row catalog)
   so the registry reports a row count above the hard ceiling.
2. Click **Sync Visible Sector**.
3. Expected log: `err: <name>: refused to full-load <N> rows
   above the <ceiling> ceiling — build the spatial index first`
4. The scene's `UNAV_VisibleSector` is unchanged.

### 8. CLI tools — work outside Cinema 4D

```
python tools/fetch_gaia_region.py --help
python tools/fetch_jpl_body.py --help
python tools/fetch_sdss_region.py --help
python tools/fetch_desi_region.py --help
python tools/build_spatial_index.py --help
```

All five succeed on a clean Python 3.9+ install with no Cinema
4D, no `astroquery`, no `astropy`, no credentials.

### 9. Tests — run without Cinema 4D

```
cd unav_pro
python -m pytest tests/ -q
```

Expected: 573 passed; 0 failures; 0 errors.

---

## C. Pre-tag audit checklist

Before tagging the v0.2 milestone:

- [ ] All 573 tests green.
- [ ] No huge committed files (largest data file ≤ 100 KB).
- [ ] No credentials, API keys, or auth tokens in source or
      fixtures.
- [ ] No hardcoded user-machine paths in plugin code or tests.
- [ ] `LIMITATIONS.md` updated to reflect what the streaming
      path solved and what remains.
- [ ] `CHANGELOG.md` carries a `[0.2.0]` entry.
- [ ] `RELEASE_NOTES_v0.2.md` (when cut) documents the streaming
      contract and acceptance status table.
- [ ] `TODO_v0.2.md` items either completed or carried forward
      into `TODO_v0.3.md`.
