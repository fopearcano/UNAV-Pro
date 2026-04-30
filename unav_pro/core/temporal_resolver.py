"""Epoch-aware position resolution for the v1.2 temporal layer.

Given a list of ``CatalogObject`` and a target ``Epoch``, the
resolver returns the same list with positions updated to the
target epoch:

* **Static** rows (no proper motion, no ephemeris row) pass
  through unchanged.
* **Proper-motion** rows (Gaia-style: ``pmra``/``pmdec`` set or
  an ``object_states`` row of ``state_type='proper_motion'``)
  are propagated linearly via ``core.proper_motion``.
* **Ephemeris** rows (JPL-style: one or more
  ``object_states`` rows of ``state_type='ephemeris'``) are
  resolved to the nearest snapshot, with optional linear
  interpolation between two bracketing snapshots when
  ``interpolate=True``.

The resolver is the bridge between the DB / JSONL row model and
the v1.0 binary export. It runs *before* the cone refine, so
``apply_filter`` always sees the position the user expects at
the target epoch.

For documentation see ``docs/V1_2_TIME_NAVIGATION.md``. For the
proper-motion limitations see
``docs/GAIA_PROPER_MOTION_LIMITATIONS.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.logging_util import get_logger
from core.proper_motion import (
    ProperMotionState,
    is_propagatable,
    propagate_object,
    propagate_position,
    reference_epoch_for,
)
from core.time_model import (
    DEFAULT_REFERENCE_EPOCH_JD,
    Epoch,
    coerce_epoch,
)
from data.schema import CatalogObject, compute_derived_fields

_log = get_logger("core.temporal_resolver")


@dataclass
class ResolveStats:
    """Per-pass counters surfaced in the visible-sector status log."""

    static: int = 0
    propagated: int = 0
    ephemeris_exact: int = 0
    ephemeris_interpolated: int = 0
    ephemeris_nearest: int = 0
    skipped_no_state: int = 0

    def short_summary(self) -> str:
        parts = [f"static {self.static}"]
        if self.propagated:
            parts.append(f"pm {self.propagated}")
        if self.ephemeris_exact:
            parts.append(f"eph-exact {self.ephemeris_exact}")
        if self.ephemeris_interpolated:
            parts.append(f"eph-interp {self.ephemeris_interpolated}")
        if self.ephemeris_nearest:
            parts.append(f"eph-near {self.ephemeris_nearest}")
        if self.skipped_no_state:
            parts.append(f"skipped {self.skipped_no_state}")
        return ", ".join(parts)


# ---------------------------------------------------------------------------
# Ephemeris snapshot store
# ---------------------------------------------------------------------------


@dataclass
class EphemerisStore:
    """Per-uid sorted list of ``object_states`` rows.

    The temporal resolver consumes this for ``ephemeris`` rows;
    the v1.2 sector-streaming wrapper builds it once per Sync click
    and hands it over.
    """

    by_uid: Dict[str, List[Any]] = field(default_factory=dict)

    def add(self, state) -> None:
        bucket = self.by_uid.setdefault(state.uid, [])
        bucket.append(state)
        # Keep sorted by epoch_jd so the nearest / bracketing
        # lookup is a binary search.
        bucket.sort(key=lambda s: float(s.epoch_jd))

    def for_uid(self, uid: str) -> List[Any]:
        return self.by_uid.get(uid, [])

    def is_empty(self) -> bool:
        return not self.by_uid


# ---------------------------------------------------------------------------
# Proper-motion overrides
# ---------------------------------------------------------------------------


@dataclass
class ProperMotionOverride:
    """Pure-rate slot for the override store. Stores just the
    proper-motion components and the reference epoch; the row's
    own ra/dec are the propagation start."""

    pmra_masyr: float
    pmdec_masyr: float
    reference_epoch_jd: float = DEFAULT_REFERENCE_EPOCH_JD


@dataclass
class ProperMotionStore:
    """Optional override map ``uid -> ProperMotionOverride`` used
    by callers that have proper-motion state in a separate table
    (the v1.2 ``object_states`` rows of
    ``state_type='proper_motion'``)."""

    overrides: Dict[str, ProperMotionOverride] = field(default_factory=dict)

    def add(
        self, uid: str,
        pmra_masyr: float, pmdec_masyr: float,
        reference_epoch_jd: float = DEFAULT_REFERENCE_EPOCH_JD,
    ) -> None:
        self.overrides[uid] = ProperMotionOverride(
            pmra_masyr=float(pmra_masyr),
            pmdec_masyr=float(pmdec_masyr),
            reference_epoch_jd=float(reference_epoch_jd),
        )


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def _interpolate_xyz(
    snapshots: Sequence,
    target_jd: float,
    *,
    interpolate: bool,
) -> Tuple[Tuple[float, float, float], str]:
    """Pick / interpolate ``(x, y, z)`` from a sorted ephemeris
    state list. Returns ``((x, y, z), kind)`` where ``kind`` is
    ``"exact"`` / ``"interpolated"`` / ``"nearest"``.

    ``snapshots`` is sorted by ``epoch_jd``."""
    n = len(snapshots)
    if n == 0:
        raise ValueError("empty ephemeris snapshot list")
    if n == 1:
        s = snapshots[0]
        return (
            (float(s.x), float(s.y), float(s.z)),
            "exact" if abs(float(s.epoch_jd) - target_jd) < 1e-9 else "nearest",
        )

    # Find the bracket [lo, hi] in epoch_jd.
    epochs = [float(s.epoch_jd) for s in snapshots]
    if target_jd <= epochs[0]:
        s = snapshots[0]
        return (
            (float(s.x), float(s.y), float(s.z)),
            "exact" if abs(epochs[0] - target_jd) < 1e-9 else "nearest",
        )
    if target_jd >= epochs[-1]:
        s = snapshots[-1]
        return (
            (float(s.x), float(s.y), float(s.z)),
            "exact" if abs(epochs[-1] - target_jd) < 1e-9 else "nearest",
        )
    # bisect for the bracket.
    lo = 0
    hi = n - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if epochs[mid] <= target_jd:
            lo = mid
        else:
            hi = mid
    s_lo = snapshots[lo]
    s_hi = snapshots[hi]
    if abs(epochs[lo] - target_jd) < 1e-9:
        return ((float(s_lo.x), float(s_lo.y), float(s_lo.z)), "exact")
    if abs(epochs[hi] - target_jd) < 1e-9:
        return ((float(s_hi.x), float(s_hi.y), float(s_hi.z)), "exact")
    if not interpolate:
        # Pick the nearer of the two snapshots.
        if abs(epochs[lo] - target_jd) <= abs(epochs[hi] - target_jd):
            return (
                (float(s_lo.x), float(s_lo.y), float(s_lo.z)), "nearest",
            )
        return (
            (float(s_hi.x), float(s_hi.y), float(s_hi.z)), "nearest",
        )
    # Linear interpolation.
    t = (target_jd - epochs[lo]) / (epochs[hi] - epochs[lo])
    return (
        (
            float(s_lo.x) + (float(s_hi.x) - float(s_lo.x)) * t,
            float(s_lo.y) + (float(s_hi.y) - float(s_lo.y)) * t,
            float(s_lo.z) + (float(s_hi.z) - float(s_lo.z)) * t,
        ),
        "interpolated",
    )


def _apply_position(
    obj: CatalogObject, x: float, y: float, z: float,
) -> None:
    """Drop a Cartesian position back onto a ``CatalogObject``,
    invalidating the spherical / c4d caches so downstream code
    recomputes them at the new scale_mode."""
    obj.cartesian_x = x
    obj.cartesian_y = y
    obj.cartesian_z = z
    # Recompute ra/dec/distance from the cartesian.
    r = math.sqrt(x * x + y * y + z * z)
    if r > 0:
        obj.distance_parsec = r
        obj.dec_deg = math.degrees(math.asin(max(-1.0, min(1.0, z / r))))
        obj.ra_deg = math.degrees(math.atan2(y, x)) % 360.0
    obj.c4d_x = None
    obj.c4d_y = None
    obj.c4d_z = None


def resolve_for_epoch(
    objects: Iterable[CatalogObject],
    target_epoch,
    *,
    ephemeris: Optional[EphemerisStore] = None,
    proper_motions: Optional[ProperMotionStore] = None,
    interpolate: bool = True,
    in_place: bool = False,
    recompute_cartesian: bool = True,
) -> Tuple[List[CatalogObject], ResolveStats]:
    """Walk ``objects`` and return them at ``target_epoch``.

    ``target_epoch`` accepts an ``Epoch``, a JD float, or an ISO
    string (anything ``coerce_epoch`` understands). ``None``
    short-circuits to a no-op pass — useful for callers that
    haven't installed a time navigator yet.

    The resolver handles three categories per row:

    * **Ephemeris hit** — ``uid`` in ``ephemeris``. Pick the
      nearest / interpolated snapshot and drop it onto the object.
    * **Proper motion** — either ``uid`` in ``proper_motions`` or
      the row's own ``pmra``/``pmdec`` are non-null. Linearly
      propagate.
    * **Static** — pass through unchanged.

    Returns ``(rows, stats)``. The list contains the same
    ``CatalogObject`` instances when ``in_place=True``; otherwise
    it is a new list with shallow clones.
    """
    epoch = coerce_epoch(target_epoch)
    stats = ResolveStats()

    if epoch is None:
        # No-op: just clone the list when the caller asked for it.
        rows = list(objects)
        stats.static = len(rows)
        return rows, stats

    target_jd = epoch.jd

    out: List[CatalogObject] = []
    for obj in objects:
        # Ephemeris path takes priority; a uid present in both
        # stores is treated as ephemeris because that's the
        # higher-fidelity model for solar-system bodies.
        if (
            ephemeris is not None
            and not ephemeris.is_empty()
            and obj.uid in ephemeris.by_uid
        ):
            snapshots = ephemeris.for_uid(obj.uid)
            (x, y, z), kind = _interpolate_xyz(
                snapshots, target_jd, interpolate=interpolate,
            )
            target_obj = obj if in_place else _shallow_clone(obj)
            _apply_position(target_obj, x, y, z)
            if recompute_cartesian:
                # Cartesian is now correct; the c4d_* slots stay
                # None so compute_derived_fields refills them at
                # the active scale_mode.
                pass
            if kind == "exact":
                stats.ephemeris_exact += 1
            elif kind == "interpolated":
                stats.ephemeris_interpolated += 1
            else:
                stats.ephemeris_nearest += 1
            out.append(target_obj)
            continue

        # Proper-motion path.
        pm_state: Optional[ProperMotionState] = None
        if proper_motions is not None and obj.uid in proper_motions.overrides:
            ovr = proper_motions.overrides[obj.uid]
            pm_state = ProperMotionState(
                ra_deg=float(obj.ra_deg),
                dec_deg=float(obj.dec_deg),
                pmra_masyr=ovr.pmra_masyr,
                pmdec_masyr=ovr.pmdec_masyr,
                reference_epoch_jd=ovr.reference_epoch_jd,
            )
        elif is_propagatable(obj):
            pm_state = ProperMotionState(
                ra_deg=float(obj.ra_deg),
                dec_deg=float(obj.dec_deg),
                pmra_masyr=float(obj.proper_motion_ra),
                pmdec_masyr=float(obj.proper_motion_dec),
                reference_epoch_jd=reference_epoch_for(obj),
            )
        if pm_state is not None:
            new_ra, new_dec = propagate_position(pm_state, target_jd)
            target_obj = obj if in_place else _shallow_clone(obj)
            target_obj.ra_deg = new_ra
            target_obj.dec_deg = new_dec
            target_obj.cartesian_x = None
            target_obj.cartesian_y = None
            target_obj.cartesian_z = None
            target_obj.c4d_x = None
            target_obj.c4d_y = None
            target_obj.c4d_z = None
            stats.propagated += 1
            out.append(target_obj)
            continue

        # Static.
        stats.static += 1
        out.append(obj if in_place else _shallow_clone(obj))

    if recompute_cartesian:
        for o in out:
            if o.cartesian_x is None and o.distance_parsec is not None:
                try:
                    compute_derived_fields(o)
                except Exception:  # noqa: BLE001
                    pass

    return out, stats


def _shallow_clone(obj: CatalogObject) -> CatalogObject:
    return CatalogObject(**{k: v for k, v in obj.to_dict().items()
                            if k in {f.name for f in CatalogObject.__dataclass_fields__.values()}})


# ---------------------------------------------------------------------------
# Convenience: build stores from db rows
# ---------------------------------------------------------------------------


def stores_from_db_states(states: Sequence) -> Tuple[EphemerisStore, ProperMotionStore]:
    """Split a flat list of ``ObjectState`` into the two stores
    the resolver consumes."""
    eph = EphemerisStore()
    pm = ProperMotionStore()
    for s in states:
        st = s.state_type
        if st == "ephemeris":
            eph.add(s)
        elif st == "proper_motion":
            if s.pmra_masyr is None or s.pmdec_masyr is None:
                continue
            ref_jd = s.reference_epoch_jd
            if ref_jd is None:
                ref_jd = s.epoch_jd
            pm.add(
                s.uid,
                pmra_masyr=float(s.pmra_masyr),
                pmdec_masyr=float(s.pmdec_masyr),
                reference_epoch_jd=float(ref_jd),
            )
        # static rows are no-ops for the resolver.
    return eph, pm
