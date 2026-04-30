# Object Classification Rules

The exact deterministic rule set
`unav_pro/knowledge/object_classifier.py` runs to assign one
of UNAV's nine canonical classes to a `CatalogObject`. There
is no machine learning here, no training data, and no
probability — just a small ordered cascade of rules.

The nine classes:

```
star, galaxy, quasar, planet, moon, asteroid, comet,
spacecraft, unknown
```

The schema's broader `OBJECT_TYPES` list also includes
`nebula`, `cluster`, and `exoplanet`, but the v1.3 classifier
collapses those to `unknown` because the connectors don't
reliably populate them yet. A future knowledge release can
refine.

---

## 1. Confidence tags

The classifier emits one of four confidence strings:

| Tag       | Meaning                                              |
|-----------|------------------------------------------------------|
| `high`    | Direct evidence from a known survey's authoritative tag (Gaia row → star, JPL planet → planet, SDSS spec_class, DESI spectype with `zwarn=0`). |
| `medium`  | Schema-level `object_type` says so, or DESI spectype with `zwarn` set. |
| `low`     | Only an indirect heuristic fired (spectral type → star; non-trivial redshift → galaxy). |
| `unknown` | Nothing discriminating in the row.                   |

These are **string tags, not probabilities**. v1.3 deliberately
doesn't fit a model — fields like "60% star, 40% white dwarf"
need a real classifier with calibrated probabilities, which is
out of scope.

---

## 2. The cascade (in order)

### 2.1 Source-specific rules

The classifier first looks at `obj.catalog_source` (lowercased,
prefix match):

#### Gaia (`gaia*`)

* If `object_type == "star"` or empty → `star` (high). Reason:
  "Gaia DR3 row (Gaia is a stellar catalog)".
* If `object_type` is a canonical class → trust it (medium).
* Otherwise → `unknown` (low).

Rationale: Gaia DR3 is essentially a stellar catalog. If the
upstream importer has tagged a row as something else, we trust
it but mark medium confidence.

#### JPL Horizons (`jpl*` / `horizons*`)

* If `object_type` is one of `planet` / `moon` / `asteroid` /
  `comet` / `spacecraft` → that class (high). Reason: "JPL
  Horizons '<type>' tag".
* Otherwise → `unknown` (low).

Rationale: the JPL connector accepts `--bodies "Mars=planet,Voyager 1=spacecraft"` and the user is in
charge of tagging — we trust their tagging completely.

#### SDSS (`sdss` or `sdss *`)

* If `metadata_json["spec_class"]` is `STAR` / `GALAXY` /
  `QSO` → that class (high). Reason: "SDSS spec_class='<x>'".
* Otherwise if schema `object_type` is canonical → that class
  (medium). Reason: "SDSS photometric type '<x>'".
* Otherwise → `unknown` (low).

Rationale: SDSS spectroscopic classification is high quality;
photometric class is a fallback.

#### DESI (`desi` or `desi *`)

* If `metadata_json["spectype"]` is `STAR` / `GALAXY` / `QSO`:
  * If `zwarn` == 0 → that class (high).
  * Otherwise → that class (medium). Reason includes "(zwarn flagged)".
* Otherwise → `unknown` (low).

Rationale: DESI's per-row `zwarn` bitmask is the survey's own
"do not trust this redshift" flag; we honor it by dropping
confidence one notch.

### 2.2 Schema fallback

If the source isn't in the table above:

* If schema `object_type` is in `KNOWN_CLASSES` and not
  `unknown` → that class (medium). Reason: "object_type field
  is '<x>'".
* If schema `object_type` is `STAR` / `GALAXY` / `QSO` (case-
  insensitive) → its canonical class (medium). Reason:
  "object_type field maps to '<x>'".

### 2.3 Heuristic fallbacks

If neither source nor `object_type` discriminates:

* If `obj.spectral_type` is populated → `star` (low). Reason:
  "has spectral_type but no catalog_source".
* If `obj.redshift > 0.001` → `galaxy` (low). Reason: "non-
  trivial redshift z=<x> suggests extragalactic". Note that
  this prefers `galaxy` over `quasar` because the
  galaxy/quasar split needs a luminosity, which we don't have
  without a survey tag.

### 2.4 Default

* `unknown` with confidence `unknown`.

---

## 3. Inputs the classifier looks at

In order of authority:

1. `catalog_source` (the survey label).
2. `object_type` (the schema-level field; the connectors
   already populate this with their best guess).
3. `metadata_json` survey-specific tags
   (`spec_class` / `spec_subclass` / `spectype` / `subtype`
   / `zwarn`).
4. `redshift`, `spectral_type` (heuristic-only fallbacks).

Inputs the classifier deliberately ignores:

* `apparent_magnitude` and `color_index` — many edge cases
  (e.g. brown dwarfs vs. cool stars vs. high-redshift galaxies)
  share magnitude / colour space.
* `distance_parsec` — distance is a downstream consequence of
  what kind of object you're looking at, not a discriminator.
* `name`, `common_name`, `uid` — these can be misleading
  (e.g. a pulsar with a stellar uid).

---

## 4. Properties

* **Total.** Every input — including `None`, malformed
  metadata, empty strings — produces a verdict. The classifier
  never raises.
* **Pure.** No side effects. No mutation of the input object.
  No I/O.
* **Stable.** A row's classification depends only on the
  fields named above; it does not depend on the order rows are
  processed in, the time of day, or any global state.

---

## 5. Adding a new rule

1. Decide *where* in the cascade it fires (typically a new
   `_classify_xyz` source-specific function).
2. Add a focused test in
   `unav_pro/tests/test_knowledge_classifier.py` for both the
   triggering row and the negative case.
3. Document the rule in this file under the right §2 sub-
   section.

The cascade order is intentionally rigid — adding rules at the
top changes existing behaviour for some rows. Always verify
the regression suite still passes before merging.
