"""Tests for the v1.3 ``knowledge.catalog_glossary``."""

from __future__ import annotations

import pytest

from knowledge.catalog_glossary import (
    GLOSSARY,
    GlossaryEntry,
    glossary_lookup,
    glossary_terms,
)


REQUIRED_TERMS = (
    "ra", "dec", "parallax", "parsec", "redshift",
    "proper_motion", "radial_velocity", "apparent_magnitude",
    "absolute_magnitude", "epoch", "julian_date",
    "ecliptic", "equatorial_coordinates",
)


@pytest.mark.parametrize("term", REQUIRED_TERMS)
def test_required_terms_are_defined(term):
    entry = glossary_lookup(term)
    assert entry is not None, f"glossary missing '{term}'"
    assert isinstance(entry, GlossaryEntry)
    assert entry.short
    assert entry.long


def test_glossary_lookup_is_case_insensitive():
    a = glossary_lookup("RA")
    b = glossary_lookup("ra")
    assert a is b is not None


def test_glossary_lookup_resolves_aliases():
    direct = glossary_lookup("ra")
    via_alias = glossary_lookup("right ascension")
    assert direct is via_alias


def test_glossary_lookup_handles_underscore_to_space():
    a = glossary_lookup("proper_motion")
    b = glossary_lookup("proper motion")
    assert a is b is not None


def test_glossary_lookup_unknown_term_returns_none():
    assert glossary_lookup("foozle") is None
    assert glossary_lookup("") is None


def test_glossary_terms_are_sorted_unique():
    terms = glossary_terms()
    assert terms == sorted(set(terms))
    assert len(terms) >= len(REQUIRED_TERMS)


def test_glossary_entry_units_present_for_quantitative_terms():
    for term in ("ra", "dec", "parallax", "redshift",
                 "proper_motion", "apparent_magnitude"):
        entry = glossary_lookup(term)
        assert entry.unit, f"'{term}' is quantitative; expected a unit"
