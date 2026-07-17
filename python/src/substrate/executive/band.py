"""The band: two lenses on one resistance value.

The corrected **symmetric ladder**, anchored on the φ-conjugates and the thirds,
mirror-symmetric about the 0.50 pivot, with the **inner ninths** ``4/9`` and
``5/9`` as first-class levels straddling the pivot, giving **eight levels**:

    1/3 (0.333) · 1/φ² (0.382) · 4/9 (0.444) · 0.50 · 5/9 (0.556) · 1/φ (0.618) · 2/3 (0.667)
     idle  │ recreation │ lower work │ upper work │ early peak │ committed peak │ warning │ danger

The inner ninths are the mod-9 refinement of the thirds (``3/9 = 1/3`` and
``6/9 = 2/3`` are the outer thirds; ``4/9``/``5/9`` the ninths straddling the
``4.5/9 = 0.50`` pivot, a mirror pair summing to 1). They split the work band
into a **lower** and **upper** work level and the peaking band into **early**
and **committed** peaking. These are real levels; the sustained-load, cycle,
and roll-up logic classify against them directly; the outer φ-conjugate / thirds
boundaries are unchanged. Consumers that reason about the coarse work/peaking
band use the :data:`WORK_LEVELS` / :data:`PEAKING_LEVELS` grouping sets.

Two named lenses on the same utilization value (never a name collision):

- :class:`LoadZone`: the LOAD lens: "how loaded am I right now" (eight levels).
- :class:`CyclePhase`: the CYCLE lens: position on the 24-step work-span cycle.

**Levels are geometric, consequences are temporal.** :func:`classify_load_zone`
only says *where* the instantaneous reading sits. Whether you are *actually*
pivoting or taking damage is a sustained-vs-spike call owned by the
``SustainedLoadTracker`` (see :mod:`substrate.sustained_load`), never a geometric
window here. A transient peak to 0.62 is healthy (intervals); 0.62 *sustained* is
overload. There is **no spike-tolerance field** on the profile: the temporal
tolerance is the tracker's, so there is nothing to desync.

The φ anchors are reused from :mod:`substrate.resistance_band` (one source of
constants); the legacy :class:`substrate.resistance_band.ZoneClassification` is the
wire-compatible projection target.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final

from substrate.executive.quantities import Quantity, ResourceKind
from substrate.resistance_band import (
    LOWER_BOUND,
    PEAKING_MIDPOINT,
    PHI_CONJUGATE,
    UPPER_BOUND,
    WORK_ZONE_MIDPOINT,
    WORK_ZONE_UPPER,
    ZoneClassification,
)

#: ``2/3``: the danger line; sustained above it = damage/debt. The thirds
#: ``1/3 + 2/3 = 1`` are a conjugate pair, mirror of the φ-conjugates.
TWO_THIRDS: Final[float] = 2.0 / 3.0

#: Structural tolerance for the φ-anchor / symmetry rules (R2–R4). The structure
#: is invariant; the exact numbers within are free (framework-with-tolerance).
BAND_TOLERANCE: Final[float] = 0.05


class LoadZone(str, Enum):
    """The LOAD lens: how loaded an entity is right now (the eight levels).

    The symmetric ladder at inner-ninth resolution. The φ-conjugate / thirds
    boundaries are joined by the two inner ninths ``4/9`` and ``5/9`` (a mirror
    pair, ``4/9 + 5/9 = 1``), which split the two levels straddling the ``0.50``
    pivot: WORK → LOWER_WORK / UPPER_WORK, PEAKING → EARLY_PEAKING /
    COMMITTED_PEAKING. These are first-class levels; the sustained-load and
    cycle logic reads them directly. Consumers that care only about the coarse
    band use :data:`WORK_LEVELS` / :data:`PEAKING_LEVELS` (grouping, not a
    separate model).
    """

    # pylint: disable=duplicate-code
    # The level names are 1:1 with the persist twin ZoneClassification by
    # design (runtime lens ↔ wire form); the parallel is intentional.
    IDLE = "idle"                            # < 1/3          sustained → decay/atrophy
    RECREATION = "recreation"                # 1/3 … 1/φ²     light/enjoyable; setpoint
    LOWER_WORK = "lower_work"                # 1/φ² … 4/9     settling into cruise
    UPPER_WORK = "upper_work"                # 4/9 … 0.50     climbing to the pivot
    EARLY_PEAKING = "early_peaking"          # 0.50 … 5/9     burst beginning; headroom
    COMMITTED_PEAKING = "committed_peaking"  # 5/9 … 1/φ      deep in the burst
    WARNING = "warning"                      # 1/φ … 2/3      winded; mirror of RECREATION
    DANGER = "danger"                        # > 2/3          sustained → breakdown/debt


#: The two WORK levels: grouping for consumers that reason about the coarse
#: work band ``(1/φ², 0.50]``. Not a separate model: the levels are first-class;
#: this is a convenience membership set.
WORK_LEVELS: Final[frozenset[LoadZone]] = frozenset(
    {LoadZone.LOWER_WORK, LoadZone.UPPER_WORK}
)

#: The two PEAKING levels: grouping for the coarse peaking band ``(0.50, 1/φ]``.
PEAKING_LEVELS: Final[frozenset[LoadZone]] = frozenset(
    {LoadZone.EARLY_PEAKING, LoadZone.COMMITTED_PEAKING}
)


class CyclePhase(str, Enum):
    """The CYCLE lens: position on the 24-step work-and-growth span."""

    ASCENDING = "ascending"     # below the 0.50 half-period pivot (building)
    PIVOT = "pivot"             # at the pivot (position 12), half-period reversal
    PAST_PIVOT = "past_pivot"   # above the pivot (the cycle's reverse half)


class BandProfileInvalid(ValueError):
    """Raised when a :class:`BandProfile` violates a structural rule (R1–R5)."""

    def __init__(self, rule: str, detail: str) -> None:
        super().__init__(f"{rule}: {detail}")
        self.rule = rule
        self.detail = detail


@dataclass(frozen=True, slots=True)
class BandProfile:
    """The geometric levels, parameterizable but structurally validated.

    Defaults are the φ anchors. A caller may shift the numbers (per-resource
    tuning) but not the *structure*; :func:`validate_band_profile` enforces the
    ordering, the φ-anchors, the conjugate sum, the symmetry, and (for a
    RESISTANCE profile) tighten-only. There is no ``spike_tolerance``; the
    temporal tolerance belongs to the tracker.
    """

    idle_ceiling: float = LOWER_BOUND          # 1/3   : IDLE strictly below
    recreation_ceiling: float = UPPER_BOUND    # 1/φ²  : RECREATION top / WORK bottom
    pivot: float = WORK_ZONE_UPPER             # 0.50  : WORK top / PEAKING bottom
    growth_ceiling: float = PHI_CONJUGATE      # 1/φ   : PEAKING top / WARNING bottom
    danger_line: float = TWO_THIRDS            # 2/3   : WARNING top; above = damage
    quantity: Quantity | None = None           # if RESISTANCE, R5 applies
    resource: ResourceKind = field(default=ResourceKind.GENERIC)

    def __post_init__(self) -> None:
        validate_band_profile(self)


def validate_band_profile(p: BandProfile) -> None:
    """Raise :class:`BandProfileInvalid` unless all structural rules hold."""
    tol = BAND_TOLERANCE
    # R1: ordering.
    if not (
        0.0 < p.idle_ceiling < p.recreation_ceiling < p.pivot
        < p.growth_ceiling < p.danger_line < 1.0
    ):
        raise BandProfileInvalid(
            "R1",
            "require 0 < idle < recreation < pivot < growth < danger < 1; got "
            f"{p.idle_ceiling}/{p.recreation_ceiling}/{p.pivot}/"
            f"{p.growth_ceiling}/{p.danger_line}",
        )
    # R2: φ anchors.
    if abs(p.recreation_ceiling - UPPER_BOUND) > tol:
        raise BandProfileInvalid(
            "R2", f"recreation_ceiling must be within {tol} of 1/φ² ({UPPER_BOUND:.4f})"
        )
    if abs(p.growth_ceiling - PHI_CONJUGATE) > tol:
        raise BandProfileInvalid(
            "R2", f"growth_ceiling must be within {tol} of 1/φ ({PHI_CONJUGATE:.4f})"
        )
    # R3: conjugate sum (1/φ² + 1/φ = 1).
    if abs(p.recreation_ceiling + p.growth_ceiling - 1.0) > tol:
        raise BandProfileInvalid(
            "R3", "recreation_ceiling + growth_ceiling must be within "
            f"{tol} of 1.0 (φ-conjugate sum)"
        )
    # R4: symmetry about the pivot (and the thirds conjugate 1/3 + 2/3 = 1).
    midpoint = (p.recreation_ceiling + p.growth_ceiling) / 2.0
    if abs(p.pivot - midpoint) > tol:
        raise BandProfileInvalid(
            "R4", f"pivot must be within {tol} of the φ-anchor midpoint {midpoint:.4f}"
        )
    if abs(p.idle_ceiling + p.danger_line - 1.0) > tol:
        raise BandProfileInvalid(
            "R4", "idle_ceiling + danger_line must be within "
            f"{tol} of 1.0 (thirds conjugate)"
        )
    # R5: resistance tighten-only (no widening to escape challenge).
    if p.quantity is Quantity.RESISTANCE:
        if p.idle_ceiling < LOWER_BOUND - 1e-9:
            raise BandProfileInvalid(
                "R5", "RESISTANCE: idle_ceiling may only TIGHTEN (≥ 1/3)"
            )
        if p.recreation_ceiling > UPPER_BOUND + 1e-9:
            raise BandProfileInvalid(
                "R5", "RESISTANCE: recreation_ceiling may only TIGHTEN (≤ 1/φ²)"
            )


#: The canonical φ-anchored profile.
DEFAULT_BAND_PROFILE: Final[BandProfile] = BandProfile()


def classify_load_zone(  # pylint: disable=too-many-return-statements
    u: float, profile: BandProfile = DEFAULT_BAND_PROFILE
) -> LoadZone:
    """Classify a utilization reading into one of the eight :class:`LoadZone` levels.

    Each level is ``(prev_ceiling, ceiling]`` (upper-inclusive) except
    ``IDLE = [0, idle_ceiling)``, so ``1/3`` belongs to RECREATION. The two
    inner-ninth boundaries ``4/9`` (:data:`WORK_ZONE_MIDPOINT`) and ``5/9``
    (:data:`PEAKING_MIDPOINT`) split the work band (LOWER/UPPER_WORK) and the
    peaking band (EARLY/COMMITTED_PEAKING). The ninths are fixed substrate
    anchors (like the ``0.50`` pivot), not profile-tunable; for any valid
    profile they stay inside their band
    (``recreation_ceiling ≤ 1/φ² < 4/9 < 0.50 < 5/9 < 1/φ ≤ growth_ceiling``).
    This is the geometric *where*; SPIKE-vs-SUSTAINED (the consequences) is the
    tracker's.
    """
    if u < profile.idle_ceiling:
        return LoadZone.IDLE
    if u <= profile.recreation_ceiling:
        return LoadZone.RECREATION
    if u <= WORK_ZONE_MIDPOINT:
        return LoadZone.LOWER_WORK
    if u <= profile.pivot:
        return LoadZone.UPPER_WORK
    if u <= PEAKING_MIDPOINT:
        return LoadZone.EARLY_PEAKING
    if u <= profile.growth_ceiling:
        return LoadZone.COMMITTED_PEAKING
    if u <= profile.danger_line:
        return LoadZone.WARNING
    return LoadZone.DANGER


def classify_cycle_phase(
    u: float, profile: BandProfile = DEFAULT_BAND_PROFILE
) -> CyclePhase:
    """Classify a reading's position relative to the 0.50 half-period pivot.

    The work-and-growth span ``[recreation_ceiling, growth_ceiling]`` ≈
    ``[0.38, 0.62]`` is the 24-position cycle (12 steps each side of the pivot);
    the PIVOT window is half a step wide.
    """
    span = profile.growth_ceiling - profile.recreation_ceiling
    half_step = (span / 24.0) / 2.0
    if u < profile.pivot - half_step:
        return CyclePhase.ASCENDING
    if u > profile.pivot + half_step:
        return CyclePhase.PAST_PIVOT
    return CyclePhase.PIVOT


_ZONE_TO_LEGACY: Final[dict[LoadZone, ZoneClassification]] = {
    LoadZone.IDLE: ZoneClassification.UNDER_LOADED,
    LoadZone.RECREATION: ZoneClassification.CALIBRATION,
    LoadZone.LOWER_WORK: ZoneClassification.LOWER_WORK,
    LoadZone.UPPER_WORK: ZoneClassification.UPPER_WORK,
    LoadZone.EARLY_PEAKING: ZoneClassification.EARLY_PEAKING,
    LoadZone.COMMITTED_PEAKING: ZoneClassification.COMMITTED_PEAKING,
    LoadZone.WARNING: ZoneClassification.WARNING,
    LoadZone.DANGER: ZoneClassification.DEBT,
}


def zone_to_legacy(zone: LoadZone) -> ZoneClassification:
    """Project a :class:`LoadZone` to the persisted :class:`ZoneClassification`.

    Serialization / wire compatibility: **1:1** across all eight levels
    (``ZoneClassification`` carries the same eight-level ladder, with
    IDLE↔UNDER_LOADED, RECREATION↔CALIBRATION, DANGER↔DEBT the only vocabulary
    differences). No shims.
    """
    return _ZONE_TO_LEGACY[zone]


__all__ = [
    "BAND_TOLERANCE",
    "DEFAULT_BAND_PROFILE",
    "PEAKING_LEVELS",
    "TWO_THIRDS",
    "WORK_LEVELS",
    "BandProfile",
    "BandProfileInvalid",
    "CyclePhase",
    "LoadZone",
    "classify_cycle_phase",
    "classify_load_zone",
    "validate_band_profile",
    "zone_to_legacy",
]
