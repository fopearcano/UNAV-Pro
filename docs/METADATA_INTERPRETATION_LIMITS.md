# Metadata Interpretation Limits

What v1.3 will and will not say about a UNAV catalog row, and
why. The knowledge layer is deliberately narrow: it surfaces
what the catalog already knows, classifies the row, and
generates a deterministic plain-text summary. It does not
infer beyond that.

This document is the contract between the inspector and the
artist: if you see a sentence in the inspector, it is grounded
in a field the source catalog populated. If a field is
missing, the inspector says so explicitly under "Missing
Data". There are no silent fabrications.

---

## 1. The honesty rule

Every sentence in the v1.3 plain-language summary follows this
rule:

> If the source catalog did not provide the field, the summary
> either skips the corresponding sentence entirely or says
> "unknown" / "not reported" out loud.

Concretely:

* No distance + no parallax → "Distance is unknown."
* No proper motion → no Motion paragraph.
* No redshift → no Cosmology paragraph.
* No spectral type → no spectral-class hint.
* Distance from a redshift Hubble proxy → "the catalogued
  distance is a Hubble-law proxy and is approximate."

The summary never invents a value. It also never paraphrases a
value into something stronger than the source claims (e.g. it
won't turn `parallax_mas = 5 ± 4` into "well-determined
distance").

---

## 2. What v1.3 *does* claim

* **Class** — one of nine canonical classes plus a coarse
  confidence tag. The reasoning is exposed via
  `classification.reason`; the inspector renders it next to
  the class label.
* **Position basis** — `static` (no proper motion), `proper-
  motion-aware` (the v1.2 resolver can advance it), or
  `ephemeris` (epoch-dependent solar-system body).
* **Distance type** — `explicit` / `parallax` / `redshift_proxy`
  / `placeholder` / `unknown`, with a one-line note describing
  how reliable each is.
* **Drift bucket** — proper motion in mas/yr binned into
  `negligible` / `slow` / `moderate` / `fast` / `very fast`.
* **Spectral hint** — for stars with a recognisable spectral
  type, a one-line description ("yellow main-sequence star,
  ~5,200–6,000 K (Sun-like)").
* **Available actions** — class-aware list of buttons /
  navigation cues (Bookmark, Focus, Add to Route, Lock,
  Time Navigator hints).

---

## 3. What v1.3 *does not* claim

### 3.1 Cross-catalog identification

"Is this SDSS row the same object as that DESI row?" Resolving
that requires a cross-match service that compares positions,
photometry, redshifts, and proper motions across surveys —
outside scope for the offline plugin.

If the artist needs cross-catalog identity they should use a
dedicated tool (e.g. SIMBAD, NED, or one of the Gaia / SDSS /
DESI cross-match services) and import the result as another
catalog.

### 3.2 Dynamical state

"Is this star in a binary?" "What is the orbital period?"
"What is the orbital plane?" These need light-curve or
spectroscopic time-series analysis the v1.3 layer doesn't see.

The v1.2 Time Navigator can step proper motion linearly, but
the resulting trajectory is the *mean* path — not the
photocentre wobble of an unresolved binary. See
[`GAIA_PROPER_MOTION_LIMITATIONS.md`](GAIA_PROPER_MOTION_LIMITATIONS.md) §2.6.

### 3.3 Variability

"Is this a variable star?" / "What's the amplitude?" Catalog
rows in UNAV carry mean magnitudes, not light curves.

### 3.4 Composition / chemistry / age

"What's the metallicity?" / "What stellar population is this?"
The schema doesn't carry these fields. The connectors don't
populate them. The summary doesn't claim them.

### 3.5 Hertzsprung-Russell positioning

"Is this a main-sequence star or a giant?" The HR diagram
needs absolute magnitude + a temperature proxy. v1.3 prints
the spectral-class hint when it has it, which captures the
luminosity class for a few suffixes (`III` → giant, `Ia/Ib` →
supergiant), but only when the source catalog encoded that
hint into the spectral_type string.

### 3.6 Confidence as a probability

The classifier's `confidence` field is a coarse string tag
(`high` / `medium` / `low` / `unknown`). It is not a
probability. There is no calibration, no model, and no
training data behind it — just a set of hand-written rules.
Treat it as a hint, not as a Bayesian posterior.

### 3.7 LLM / AI summaries

v1.3 is deterministic. Same input → byte-identical output. No
LLM call, no temperature, no training cutoff. This is a
non-goal: a future feature could layer an offline LLM on top
of the deterministic baseline, but the v1.3 contract is that
the inspector text is reproducible.

---

## 4. Per-source caveats

### 4.1 Gaia DR3

Gaia is a stellar catalog. Every row's class is `star` unless
the importer overrode it. v1.3 does not detect:

* White dwarfs vs. main-sequence stars (no surface gravity).
* Resolved binaries (Gaia's per-source row is the photocentre).
* Variable stars (the bulk catalog mean magnitude only).

### 4.2 JPL Horizons

The classifier trusts whatever `object_type` the artist tagged
each body with at fetch time (`--bodies "Mars=planet,Voyager 1=spacecraft"`). v1.3 does not validate that the tag matches
the body's true class — if the artist mislabels Pluto as a
spacecraft, the inspector will believe it.

The position is epoch-dependent. The summary surfaces the
epoch and center frame from `metadata_json` so the artist
knows the position is *not* fixed in time.

### 4.3 SDSS / DESI

Both surveys publish spectroscopic and photometric tags. v1.3
prefers the spectroscopic tag (`spec_class` / `spectype`)
because it's more reliable. DESI's per-row `zwarn` bitmask
drops confidence to `medium` even when spectype is set.

The redshift→distance conversion is a Hubble-law proxy and is
explicitly flagged. Do not use it for cosmology.

---

## 5. When in doubt — read the raw JSON

The inspector still renders the raw `metadata_json` blob at
the bottom of the panel. If the v1.3 sections don't show
something the artist needs, the underlying data is one scroll
away. **Copy Metadata JSON** dumps the full record to the
clipboard, intact.

This is the v1.3 escape hatch: the knowledge layer is a
helpful overlay, never a replacement for the raw data.
