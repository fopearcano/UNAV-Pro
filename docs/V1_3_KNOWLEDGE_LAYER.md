# UNAV Pro v1.3 — Astrophysical Knowledge Layer

UNAV's v1.3 milestone makes the plugin *explain* what the
artist is selecting. Before v1.3 the metadata inspector showed
raw catalog fields — RA, Dec, magnitude, redshift — and that
was it. The artist had to know enough astronomy to interpret
those numbers themselves. v1.3 adds a thin, deterministic
knowledge layer on top: an object classifier, a plain-language
summary generator, a glossary of catalog terms, and physical-
interpretation helpers. The inspector still shows the raw
numbers, but it now also shows *what they mean*.

This document is the v1.3 overview. Supporting docs:

* [`ASTROPHYSICAL_FIELD_GLOSSARY.md`](ASTROPHYSICAL_FIELD_GLOSSARY.md) —
  every term the inspector renders, with definitions.
* [`OBJECT_CLASSIFICATION_RULES.md`](OBJECT_CLASSIFICATION_RULES.md) —
  the deterministic rule set the classifier uses.
* [`METADATA_INTERPRETATION_LIMITS.md`](METADATA_INTERPRETATION_LIMITS.md) —
  what v1.3 will and will not say about an object, and why.

---

## 1. What v1.3 actually delivers

| Capability                           | Where it lives                              |
|--------------------------------------|----------------------------------------------|
| Object classifier                    | `knowledge/object_classifier.py`             |
| Plain-language summary generator     | `knowledge/object_summary.py`                |
| Field glossary                       | `knowledge/catalog_glossary.py`              |
| Physical-interpretation helpers      | `knowledge/physical_interpretation.py`       |
| Inspector with the new sections      | `ui/metadata_panel.py`                       |
| Contextual navigation cues           | `ui/metadata_panel.py` (Available Actions)   |

**No external services.** No AI APIs. No network calls. No
astropy, no SPICE, no scikit-learn. Pure stdlib + the fields
the connectors already populate.

**Deterministic.** Same input → byte-identical output. Tests
assert this end-to-end. There is no model weight, no
randomness, no temperature setting.

---

## 2. The classifier

`knowledge.object_classifier.classify_object(obj)` returns one
of:

```
star, galaxy, quasar, planet, moon, asteroid, comet,
spacecraft, unknown
```

with a coarse confidence tag (`high` / `medium` / `low` /
`unknown`) and a one-line reason string.

Rule precedence (first match wins):

1. **`catalog_source` known** — Gaia / JPL / SDSS / DESI rows
   trigger the per-source rule, which knows that survey's
   tagging conventions (e.g. SDSS `spec_class`, DESI
   `spectype`).
2. **Schema `object_type` is canonical** — fall back to the
   row's own `object_type` field if it's one of the known
   classes.
3. **Heuristic** — non-trivial redshift implies extragalactic;
   a populated `spectral_type` implies a star.
4. **Default** — `unknown` with confidence `unknown`.

Full rule reference: [`OBJECT_CLASSIFICATION_RULES.md`](OBJECT_CLASSIFICATION_RULES.md).

---

## 3. The summary generator

`knowledge.object_summary.summarize_object(obj)` produces an
`ObjectSummary` containing:

* `classification` — the classifier verdict (so callers don't
  need to re-run the classifier).
* `paragraphs` — up to seven plain-text sections (lead,
  position, brightness, motion, cosmology, time-domain,
  caveats).
* `missing_fields` — list of catalog fields the row didn't
  populate, surfaced under the "Missing Data" inspector
  section.

Sections that can't be filled are simply omitted. The lead
paragraph is always present. The caveats paragraph is always
present when at least one field is missing.

The summary is **honest about ignorance**: when distance comes
from a redshift→Hubble proxy the cosmology paragraph says so
explicitly; when the row has no distance the position
paragraph says "Distance is unknown" rather than computing
some fallback.

---

## 4. The glossary

`knowledge.catalog_glossary.GLOSSARY` is a dict of `term →
GlossaryEntry`. Each entry has a `short` description (one
sentence, suitable for a tooltip), a `long` description (one
paragraph, suitable for a help panel), an optional `unit`, and
an `aliases` tuple so the inspector can resolve "RA" / "right
ascension" / "ra_deg" all to the same entry.

The terms covered (see `ASTROPHYSICAL_FIELD_GLOSSARY.md` for
the full list with definitions):

```
ra, dec, parallax, parsec, redshift, proper_motion,
radial_velocity, apparent_magnitude, absolute_magnitude,
color_index, spectral_type, epoch, julian_date, ecliptic,
equatorial_coordinates
```

All v1.3 tests assert that every term the inspector references
has a glossary entry; adding a new field name without a
glossary entry will fail the suite.

---

## 5. The physical-interpretation helpers

`knowledge.physical_interpretation` exposes three pure
functions the summary and inspector both use:

* `spectral_class_hint(spectral_type)` — turn `"G2V"` into
  `"yellow main-sequence star, ~5,200–6,000 K (Sun-like)"`.
  Recognises the OBAFGKM(LT) main-sequence letters and the
  giant / supergiant luminosity-class suffixes.
* `distance_quality(distance_parsec, parallax_mas,
  distance_method, parallax_error_mas=…)` — categorise *how*
  the distance was determined. Returns
  `("explicit", note)`, `("parallax", note with SNR)`,
  `("redshift_proxy", note)`, `("placeholder", note)`, or
  `("unknown", "no distance and no parallax reported.")`.
* `motion_summary(pmra_masyr, pmdec_masyr)` — turn proper
  motion into a one-line description of total drift speed
  (`negligible` / `slow` / `moderate` / `fast` / `very fast`).

---

## 6. The upgraded inspector

The metadata panel renders the new sections in this order:

1. **Basic Identity** — class line (with confidence + reason),
   uid, catalog source, object type, name, common name.
2. **Position** — RA / Dec / distance / parallax, position
   basis (`static` / `proper-motion-aware` / `ephemeris`),
   distance type + note.
3. **Motion** — proper-motion components, total drift
   classification, radial velocity (with receding /
   approaching note).
4. **Photometry** — apparent / absolute magnitude, colour
   index, spectral type.
5. **Redshift / Cosmology** — redshift z, error if reported,
   distance-from-z proxy warning if applicable.
6. **Catalog Notes** — survey-specific metadata pulled from
   `metadata_json` (SDSS spec_class, DESI spectype, JPL epoch
   / center, …).
7. **Plain-language Summary** — the multi-paragraph block from
   `summarize_object`.
8. **Missing Data** — the field-by-field caveat list.
9. **Available Actions** — contextual navigation cues
   (Bookmark / Focus / Add to Route / Lock Target / use Time
   Navigator).
10. **Raw metadata JSON** — unchanged from v1.2.

Sections that don't apply to the row (e.g. Redshift /
Cosmology for a Gaia star) are omitted entirely.

---

## 7. Contextual navigation

The "Available Actions" block is the new contextual surface.
Today it is rendered as plain text (the dialog buttons live
elsewhere); a future v1.x release can hook these into one-
click dispatchers. The cues are class-aware:

* **Always** — Bookmark.
* **When `distance_parsec` is known** — Focus, Add as Route
  Waypoint, Lock Target.
* **Solar-system bodies** — extra hint to use the Time
  Navigator.
* **Stars with non-zero proper motion** — extra hint to
  propagate via the Time Navigator.
* **No reliable distance** — Focus is explicitly disabled
  with a warning line.

This is the v1.3 contract for "the inspector tells the artist
what they can do next."

---

## 8. Acceptance criteria

* [x] Selecting any UNAV object yields a non-empty plain-
  language summary.
* [x] Missing fields are listed explicitly under "Missing
  Data" — never invented.
* [x] No external API calls; pure stdlib.
* [x] Same input → byte-identical output (deterministic).
* [x] Existing metadata lookup, marker-only path, and
  Copy-JSON path remain unchanged.
* [x] Catalog notes for SDSS / DESI / JPL still render with
  the correct survey tags.

---

## 9. What v1.3 explicitly does **not** do

| Out of scope                                 | Why                                                |
|----------------------------------------------|----------------------------------------------------|
| LLM-generated summaries                      | Determinism + offline operation are first-class.   |
| Cross-catalog identification                 | "Is this row in SDSS the same object as that row in DESI?" needs a real cross-match service. |
| Astrophysical reasoning beyond table lookups | "Is this binary?" / "Is this an eclipsing binary?" requires light-curve analysis the v1.3 layer doesn't see. |
| Hertzsprung-Russell positioning              | Requires absolute magnitude + colour, which most rows don't have. |
| External knowledge bases (SIMBAD / NED)      | Network-dependent; out of scope for the offline plugin. |
| Confidence as a probability                  | The classifier emits coarse string tags only; v1.3 deliberately doesn't fit a model. |
