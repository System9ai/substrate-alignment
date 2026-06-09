"""The band — two lenses on one resistance value.

The corrected **symmetric ladder**, anchored on the φ-conjugates and the thirds,
mirror-symmetric about the 0.50 pivot:

    1/3 (0.3333) · 1/φ² (0.3820) · 0.50 · 1/φ (0.6180) · 2/3 (0.6667)

Two named lenses on the same utilization value (never a name collision):

- :class:`LoadZone` — the LOAD lens: "how loaded am I right now."
- :class:`CyclePhase` — the CYCLE lens: position on the 24-step work-span cycle.

**Levels are geometric, consequences are temporal.** :func:`classify_load_zone`
only says *where* the instantaneous reading sits. Whether you are *actually*
pivoting or taking damage is a sustained-vs-spike call owned by the
``SustainedLoadTracker`` (see :mod:`substrate.sustained_load`) — never a geometric
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
    PHI_CONJUGATE,
    UPPER_BOUND,
    WORK_ZONE_UPPER,
    ZoneClassification,
)

#: ``2/3`` — the danger line; sustained above it = damage/debt. The thirds
#: ``1/3 + 2/3 = 1`` are a conjugate pair, mirror of the φ-conjugates.
TWO_THIRDS: Final[float] = 2.0 / 3.0

#: Structural tolerance for the φ-anchor / symmetry rules (R2–R4). The structure
#: is invariant; the exact numbers within are free (framework-with-tolerance).
BAND_TOLERANCE: Final[float] = 0.05


class LoadZone(str, Enum):
    """The LOAD lens — how loaded an entity is right now."""

    IDLE = "idle"               # < 1/3        sustained → decay/atrophy
    RECREATION = "recreation"   # 1/3 … 1/φ²   light/enjoyable; resistance setpoint
    WORK = "work"               # 1/φ² … 0.50  the only SUSTAINABLE cruise
    PEAKING = "peaking"         # 0.50 … 1/φ   growth — TRANSIENT peaks build
    WARNING = "warning"         # 1/φ … 2/3    winded; mirror of RECREATION
    DANGER = "danger"           # > 2/3        sustained → breakdown/damage/debt


class CyclePhase(str, Enum):
    """The CYCLE lens — position on the 24-step work-and-growth span."""

    ASCENDING = "ascending"     # below the 0.50 half-period pivot (building)
    PIVOT = "pivot"             # at the pivot (position 12) — half-period reversal
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
    tuning) but not the *structure* — :func:`validate_band_profile` enforces the
    ordering, the φ-anchors, the conjugate sum, the symmetry, and (for a
    RESISTANCE profile) tighten-only. There is no ``spike_tolerance`` — the
    temporal tolerance belongs to the tracker.
    """

    idle_ceiling: float = LOWER_BOUND          # 1/3   — IDLE strictly below
    recreation_ceiling: float = UPPER_BOUND    # 1/φ²  — RECREATION top / WORK bottom
    pivot: float = WORK_ZONE_UPPER             # 0.50  — WORK top / PEAKING bottom
    growth_ceiling: float = PHI_CONJUGATE      # 1/φ   — PEAKING top / WARNING bottom
    danger_line: float = TWO_THIRDS            # 2/3   — WARNING top; above = damage
    quantity: Quantity | None = None           # if RESISTANCE, R5 applies
    resource: ResourceKind = field(default=ResourceKind.GENERIC)

    def __post_init__(self) -> None:
        validate_band_profile(self)


def validate_band_profile(p: BandProfile) -> None:
    """Raise :class:`BandProfileInvalid` unless all structural rules hold."""
    tol = BAND_TOLERANCE
    # R1 — ordering.
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
    # R2 — φ anchors.
    if abs(p.recreation_ceiling - UPPER_BOUND) > tol:
        raise BandProfileInvalid(
            "R2", f"recreation_ceiling must be within {tol} of 1/φ² ({UPPER_BOUND:.4f})"
        )
    if abs(p.growth_ceiling - PHI_CONJUGATE) > tol:
        raise BandProfileInvalid(
            "R2", f"growth_ceiling must be within {tol} of 1/φ ({PHI_CONJUGATE:.4f})"
        )
    # R3 — conjugate sum (1/φ² + 1/φ = 1).
    if abs(p.recreation_ceiling + p.growth_ceiling - 1.0) > tol:
        raise BandProfileInvalid(
            "R3", "recreation_ceiling + growth_ceiling must be within "
            f"{tol} of 1.0 (φ-conjugate sum)"
        )
    # R4 — symmetry about the pivot (and the thirds conjugate 1/3 + 2/3 = 1).
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
    # R5 — resistance tighten-only (no widening to escape challenge).
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


def classify_load_zone(
    u: float, profile: BandProfile = DEFAULT_BAND_PROFILE
) -> LoadZone:
    """Classify a utilization reading into a :class:`LoadZone`.

    Each zone is ``(prev_ceiling, ceiling]`` (upper-inclusive) except
    ``IDLE = [0, idle_ceiling)`` — so ``1/3`` belongs to RECREATION. This is the
    geometric *where*; SPIKE-vs-SUSTAINED (the consequences) is the tracker's.
    """
    if u < profile.idle_ceiling:
        return LoadZone.IDLE
    if u <= profile.recreation_ceiling:
        return LoadZone.RECREATION
    if u <= profile.pivot:
        return LoadZone.WORK
    if u <= profile.growth_ceiling:
        return LoadZone.PEAKING
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
    LoadZone.WORK: ZoneClassification.WORKING,
    LoadZone.PEAKING: ZoneClassification.WORKING,
    LoadZone.WARNING: ZoneClassification.PEAKING,
    LoadZone.DANGER: ZoneClassification.DEBT,
}


def zone_to_legacy(zone: LoadZone) -> ZoneClassification:
    """Project a :class:`LoadZone` to the legacy 5-band classification.

    Serialization / wire compatibility for consumers on the older layered-zone
    enum. The projection is exact and lossy-by-design (the new PEAKING growth zone
    maps to legacy WORKING; new WARNING → legacy PEAKING; new DANGER → legacy DEBT).
    """
    return _ZONE_TO_LEGACY[zone]


__all__ = [
    "BAND_TOLERANCE",
    "DEFAULT_BAND_PROFILE",
    "TWO_THIRDS",
    "BandProfile",
    "BandProfileInvalid",
    "CyclePhase",
    "LoadZone",
    "classify_cycle_phase",
    "classify_load_zone",
    "validate_band_profile",
    "zone_to_legacy",
]
