"""v3.3 PresentationManager tests."""

from __future__ import annotations

import os

import pytest

from presentation import (
    PresentationError,
    PresentationManager,
    PresentationSequence,
    PresentationStep,
)


def _seq(title: str = "demo") -> PresentationSequence:
    seq = PresentationSequence(title=title)
    seq.add_step(PresentationStep(title="A"))
    seq.add_step(PresentationStep(title="B"))
    return seq


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_and_list(tmp_path):
    pm = PresentationManager(str(tmp_path))
    pres = _seq("First")
    pm.create(pres)
    assert pres.presentation_id in pm
    assert len(pm) == 1
    listed = pm.list_all()
    assert listed[0].title == "First"


def test_create_rejects_duplicate_id(tmp_path):
    pm = PresentationManager(str(tmp_path))
    pres = _seq()
    pm.create(pres)
    with pytest.raises(PresentationError):
        pm.create(pres)


def test_get_returns_none_for_missing(tmp_path):
    pm = PresentationManager(str(tmp_path))
    assert pm.get("missing") is None


def test_update_persists_changes(tmp_path):
    pm = PresentationManager(str(tmp_path))
    pres = _seq()
    pm.create(pres)
    pres.title = "Updated"
    pm.update(pres)
    assert pres.updated_at_iso  # touched
    fresh = PresentationManager(str(tmp_path))
    assert fresh.get(pres.presentation_id).title == "Updated"


def test_update_rejects_unknown_id(tmp_path):
    pm = PresentationManager(str(tmp_path))
    pres = _seq()
    with pytest.raises(KeyError):
        pm.update(pres)


def test_delete_returns_true_when_present(tmp_path):
    pm = PresentationManager(str(tmp_path))
    pres = _seq()
    pm.create(pres)
    assert pm.delete(pres.presentation_id) is True
    assert pres.presentation_id not in pm
    fresh = PresentationManager(str(tmp_path))
    assert pres.presentation_id not in fresh


def test_delete_returns_false_when_missing(tmp_path):
    pm = PresentationManager(str(tmp_path))
    assert pm.delete("does-not-exist") is False


# ---------------------------------------------------------------------------
# Disk round-trip
# ---------------------------------------------------------------------------


def test_disk_round_trip(tmp_path):
    pm = PresentationManager(str(tmp_path))
    pres = _seq("Talk")
    pm.create(pres)
    fresh = PresentationManager(str(tmp_path))
    rt = fresh.get(pres.presentation_id)
    assert rt is not None
    assert rt.title == "Talk"
    assert len(rt.steps) == 2


def test_reload_picks_up_external_changes(tmp_path):
    """Two managers pointed at the same dir see each other's
    writes after a reload."""
    a = PresentationManager(str(tmp_path))
    b = PresentationManager(str(tmp_path))
    p = _seq("X")
    a.create(p)
    assert p.presentation_id not in b
    b.reload()
    assert p.presentation_id in b


def test_reload_skips_corrupt_files(tmp_path):
    pm = PresentationManager(str(tmp_path))
    pres = _seq()
    pm.create(pres)
    bad = tmp_path / "broken.json"
    bad.write_text("not json", encoding="utf-8")
    fresh = PresentationManager(str(tmp_path))
    assert pres.presentation_id in fresh


def test_reload_skips_index_file_itself(tmp_path):
    """The index file should never be loaded as a
    presentation."""
    pm = PresentationManager(str(tmp_path))
    pm.create(_seq())
    fresh = PresentationManager(str(tmp_path))
    # Only one presentation should be loaded.
    assert len(fresh) == 1


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------


def test_reorder_changes_display_order(tmp_path):
    pm = PresentationManager(str(tmp_path))
    a = _seq("a")
    b = _seq("b")
    c = _seq("c")
    pm.create(a)
    pm.create(b)
    pm.create(c)
    assert pm.reorder(c.presentation_id, 0) is True
    titles = [p.title for p in pm.list_all()]
    assert titles[0] == "c"


def test_reorder_unknown_id_returns_false(tmp_path):
    pm = PresentationManager(str(tmp_path))
    assert pm.reorder("nope", 0) is False


def test_list_ids_matches_list_all(tmp_path):
    pm = PresentationManager(str(tmp_path))
    a = _seq("a")
    b = _seq("b")
    pm.create(a)
    pm.create(b)
    ids = pm.list_ids()
    titles = [p.title for p in pm.list_all()]
    assert len(ids) == len(titles) == 2
