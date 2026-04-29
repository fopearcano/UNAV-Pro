# UNAV Pro — Large-Data Safety

How UNAV Pro stops the user from accidentally crashing Cinema 4D
with a million-object generation, a 5 GB `.c4d` file, or a runaway
metadata blob baked into every null. Five guardrails, one
override, one minimal-marker policy, and one always-visible status
strip in the dialog.

Companion to:

  * `RAY_CONE_FILTERING.md` — the filter that *normally* keeps the
    visible set small.
  * `SCENE_SYNC_WORKFLOW.md` — the diff-and-update workflow whose
    `max_visible` cap also flows through here.
  * `SPATIAL_INDEXING_AND_CHUNKING.md` — the on-disk index that
    means the catalog never lives in RAM at full size.

---

## 1. The five guardrails

Implementation: `unav_pro/core/safety.py`. Each guardrail is a
separate `evaluate_*` function returning a `SafetyDecision`.

| Guardrail                       | Threshold default       | Effect on default                   |
|---------------------------------|-------------------------|-------------------------------------|
| `max_generated_objects` (cap)   | 100 000                 | **Blocks** any build past this size unless the override is on. |
| `warning_threshold`             | 10 000                  | Build succeeds; logs a warning and surfaces it in the action's status. |
| `dataset_size_warning`          | 1 000 000 rows           | Advisory when registering a dataset; never blocks (loading metadata is cheap, only materializing it is dangerous). |
| `max_scene_object_count`        | 200 000 objects         | Advisory based on the active C4D scene's existing object count; warns the user before they pile UNAV nulls on top. |
| `max_c4d_file_size_warning_bytes` | 200 MB                | Advisory after a save; suggests baking + clearing the starfield, or turning off `embed_full_metadata_in_marker`. |

Each evaluator returns a `SafetyDecision` with:

```
allowed   : bool          # gate
level     : "ok"|"warn"|"blocked"
requested : int           # what the caller asked for
effective : int           # what they'll actually get (0 if blocked)
messages  : list[str]     # human-readable reasons
```

`SafetyDecision.short_summary()` produces the one-liner the dialog
status log shows:

> `WARN (effective 12000/12000); 12000 objects is above the warning threshold (10000); the build will succeed but viewport responsiveness may degrade.`

> `BLOCKED (5000000 requested); Generation blocked: 5000000 objects exceeds the hard cap of 100000. Reduce the filter (...) or enable Allow Full Catalog to override.`

---

## 2. Visible-sector-only mode (the default)

`SafetyLimits.visible_sector_only = True` is the out-of-the-box
mode. It enforces one rule: **without a `UNAV_Navigator` in the
scene, generation is blocked**, regardless of size. The block
message tells the user exactly what to do:

> Generation blocked: visible-sector-only mode requires a
> UNAV_Navigator in the scene. Create one with 'Create Navigation
> Null', or enable Allow Full Catalog in the Safety panel to
> override.

This is the headline safety: the navigator's filter is the only
thing that bounds the working set on a real catalog. Without it,
"generate" means "the entire catalog reaches C4D" — which is a
crash, not a feature.

---

## 3. The override

`SafetyLimits.allow_full_catalog = True` flips both the navigator
gate **and** the hard cap off. It is loud about doing so:

  * `mode_label()` returns `"FULL CATALOG OVERRIDE (cap and
    navigator gate disabled)"`.
  * Every decision under the override carries a top-level message:
    `"Override active: full-catalog generation enabled —
    navigator gate and hard cap bypassed."`
  * The warning threshold still triggers a `level=warn` decision so
    the user is never silently dumped into a million-object build.

The override is per-session; it's persisted into config along with
the rest of `SafetyLimits` so the user's choice survives reload,
but the dialog status strip makes the active mode obvious every
time.

---

## 4. Minimal-marker policy

A separate but related rule lives in
`c4d_objects/point_cloud_builder.marker_for_object`:

```python
def marker_for_object(obj, kind="point", include_full_metadata=False):
    ...
```

`include_full_metadata=False` (the default) **omits** the schema's
full `metadata_json` blob from every UNAV null. The marker still
carries:

  * `uid` — the lookup key.
  * `catalog_source`, `object_type`, `name`.
  * `ra_deg`, `dec_deg`, `distance_pc`.

That is enough for `find_starfield`, `clear_starfield`, the
metadata inspector's marker-only fallback, and the route panel's
"Add Selected" path. The full record (parallax, redshift, raw
catalog blob, magnitudes, …) lives in the external
`MetadataLookup`; the inspector pulls it from there on demand.

Switching `include_full_metadata=True` (via
`SafetyLimits.embed_full_metadata_in_marker`) trades file size for
self-containment — a saved `.c4d` then carries every catalog row's
metadata blob and can be opened on a machine with no catalog. A
five-line note in the file-size advisory points at that toggle as
the first thing to turn off when scenes get heavy.

This policy was tightened on the safety pass: the previous default
embedded the blob unconditionally. Existing tests for the marker
have been updated to reflect the new default + the opt-in path.

---

## 5. Wiring in `mock_actions.generate_point_cloud`

The action runs the safety gate after the filter and before the
build:

```
load_catalog            -> objects
_filter_for_active_navigator(objects)  -> filtered, frag, used_filter
                       ↓
evaluate_generate(len(filtered), limits, has_navigator=...)
                       ↓
  level == "blocked"   →  return "safety: BLOCKED ..." (no scene mutation)
  level == "warn"      →  proceed; warning prepended to the status suffix
  level == "ok"        →  proceed
                       ↓
build_starfield(doc, filtered, encoding=encoding,
                include_full_metadata=limits.embed_full_metadata_in_marker)
```

The status the dialog shows always tells the user:

  * how many objects survived the filter,
  * what the safety gate said,
  * how many got materialized.

A **blocked** decision means the scene is *not touched* — no
partial builds, no half-rendered starfields.

---

## 6. UI — the always-visible Safety strip

The main dialog grows a **Safety** group above the Visible Sector
group. Three controls, one status line:

| Control                       | Widget                | Behaviour                                                                |
|-------------------------------|-----------------------|--------------------------------------------------------------------------|
| Status line                   | `AddStaticText`       | Renders `Mode: <mode_label> — Generated N / cap M`. Re-rendered after every refresh. |
| Max generated objects         | `AddEditNumberArrows` | The cap. Default 100 000; clamped to `[0, 10 000 000]`.                  |
| Allow Full Catalog            | `AddCheckbox`         | The override. Toggling refreshes the status line so the new mode shows. |
| Refresh                       | `AddButton`           | Re-counts the current `UNAV_VisibleSector` children and re-renders.      |

`UnavMainDialog._read_safety_limits()` snapshots the controls into
a `SafetyLimits` whenever **Generate Point Cloud** is clicked;
out-of-range values silently fall back to defaults rather than
refuse the build.

The status line is also refreshed on every dialog `InitValues`, so
opening the panel always shows the current state.

---

## 7. Robustness rules

The safety layer follows the standing plugin invariants
(`PLUGIN_STRUCTURE.md` §9):

  1. **Pure CPython, no c4d, no numpy.** Every evaluator is unit-
     testable without a host.
  2. **`SafetyLimits` validates at construction.** Negative caps
     raise `ValueError`; an inverted (`warning > cap`) pair is
     silently re-clamped to the cap so a UI typo doesn't trap the
     user.
  3. **Decisions carry their own messages.** The dialog never
     formats the reason itself; whatever the evaluator says is
     what the user sees.
  4. **Override is loud, not silent.** Every decision under
     `allow_full_catalog` carries an "Override active" message; the
     status-strip mode label changes to `FULL CATALOG OVERRIDE` in
     all-caps.
  5. **Block means no mutation.** When the evaluator returns
     `level=blocked`, `mock_actions.generate_point_cloud` returns
     before calling `build_starfield`. The scene is not touched.
  6. **Minimal markers by default.** The catalog blob is never
     embedded into every null without explicit opt-in.

---

## 8. Test coverage

`unav_pro/tests/test_safety.py` covers (34 tests):

  * **`SafetyLimits` dataclass.** Defaults, negative-value
    rejection, warning-threshold clamping, dict round-trip,
    unknown-keys-dropped on `from_dict`, invalid-values-fall-back,
    every variant of `mode_label` (default / override / sector-
    aware).
  * **`SafetyDecision.short_summary`.** All three states (ok /
    warn / blocked) render with their messages.
  * **`evaluate_generate` cap enforcement.** Under-warning is ok,
    in the warning band is warn, above the cap is blocked, hits
    "Allow Full Catalog" hint in the block message, override
    allows above-cap with a warn, override below the warning
    threshold still emits the override note, at-cap-exactly is
    warn-not-block.
  * **Visible-sector mode.** No-navigator + default mode is
    blocked; flipping `visible_sector_only=False` allows it; zero
    objects always ok; negative requested clamped to zero.
  * **`evaluate_dataset_load`.** Below threshold ok, above warns
    (never blocks), custom thresholds respected.
  * **`evaluate_scene_state`.** Below ok, above warns.
  * **`evaluate_file_size`.** Below ok, above warns with MB-
    rendered message.
  * **`status_line`.** Includes mode label and cap; includes
    generated count when provided; surfaces the override warning.
  * **End-to-end spec tests.** "Full-catalog generation blocked
    by default" and "allowed only with explicit override".

`unav_pro/tests/test_point_cloud_builder.py` adds 2 tests for the
new marker default:

  * **Default omits `metadata_json`.** A round-trip through
    `marker_for_object(obj)` does not include the schema's blob.
  * **Opt-in includes it.** `include_full_metadata=True` puts the
    blob back in.

The c4d-bound paths in the dialog (the Safety strip widgets, the
status refresh) are exercised by loading the plugin in Cinema 4D
2023+; they are not part of the automated suite.

---

## 9. Future extensions

  * **Per-source cap.** A future `SafetyLimits` field can carry a
    per-catalog-source cap so a Gaia + DESI scene can keep the
    Gaia component small while letting DESI fill the rest of the
    budget.
  * **Hard rejection of unknown sources.** A "trusted sources"
    allowlist that forces the user to register catalogs explicitly
    in the dataset manager before they can be generated.
  * **Live file-size estimate.** Show the projected `.c4d` size in
    the safety strip *before* the user clicks save, computed from
    the materialised count + the marker payload size.
  * **Auto-trim on save.** When the file-size advisory triggers,
    offer to bake the visible sector into a baked subset (see the
    `.unavbake` format in `UNAV_PRO_ARCHITECTURE.md` §3.9) and
    clear the live UNAV objects before save.

The MVP shipped here is intentionally five evaluators, one
override, and one minimal-marker rule. Every future extension fits
behind the same `SafetyLimits` / `SafetyDecision` interface.
