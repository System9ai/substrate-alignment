"""Scale roll-up aggregator: substrate state UP the physical / grouping axes.

Executive function lives at every scale and intelligence rolls UP. The entity axis
(cell → node → org) already has health aggregators; this module builds the missing
**physical**
(cell → rack → zone → region) and **grouping** (service-group / entity-group) roll-
ups, so an operator can ask "how is this rack / this service-group doing?" and get
the same band-grounded read the entity axis already gives.

It is a *reading* faculty over the canonical band: each member's load classifies
through :func:`classify_load_zone`, and the members aggregate into one
:class:`ScaleAggregate` carrying the distribution, the mean, the worst member, and
the two failure-tell fractions (over-loaded vs idle). Both extremes matter: a rack
where every cell is idle is as much a problem as one where every cell is in danger.

Pure logic
==========

* No DAO, no LLM, no network. Deterministic.
* Reuses the canonical band classifier + scale topology; no parallel logic.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import mean
from typing import Final, Optional, Sequence, Tuple

from substrate.executive.band import (
    DEFAULT_BAND_PROFILE,
    BandProfile,
    LoadZone,
    classify_load_zone,
)
from substrate.executive.scale import (
    ExecutiveScale,
    ScaleAxis,
    axis_of,
)


#: LoadZone severity order (over-load ascending), used to pick the worst member.
#: DANGER is the most severe; IDLE the least (under-load is tracked separately as
#: ``fraction_idle``, since both extremes are failure tells).
_ZONE_SEVERITY: Final[Tuple[LoadZone, ...]] = (
    LoadZone.IDLE,
    LoadZone.RECREATION,
    LoadZone.LOWER_WORK,
    LoadZone.UPPER_WORK,
    LoadZone.EARLY_PEAKING,
    LoadZone.COMMITTED_PEAKING,
    LoadZone.WARNING,
    LoadZone.DANGER,
)
_SEVERITY_INDEX: Final[dict[LoadZone, int]] = {
    zone: i for i, zone in enumerate(_ZONE_SEVERITY)
}


class RollUpError(ValueError):
    """Raised when members cannot be rolled up to the requested scale."""


@dataclass(frozen=True, slots=True)
class MemberLoad:
    """One member's current load contribution to a roll-up."""

    member_id: str
    utilization: float
    member_scale: ExecutiveScale

    def __post_init__(self) -> None:
        if not self.member_id:
            raise ValueError("member_id must be non-empty")
        if not 0.0 <= self.utilization <= 1.0:
            raise ValueError(
                f"utilization must be in [0, 1]; got {self.utilization!r}"
            )


@dataclass(frozen=True, slots=True)
class ScaleAggregate:  # pylint: disable=too-many-instance-attributes
    """The rolled-up substrate state at a parent scale."""

    scale: ExecutiveScale
    axis: ScaleAxis
    member_count: int
    mean_utilization: float
    dominant_zone: LoadZone
    worst_zone: LoadZone
    zone_distribution: Tuple[Tuple[LoadZone, int], ...]
    fraction_in_danger: float
    fraction_idle: float
    rationale: str


def roll_up(
    members: Sequence[MemberLoad],
    *,
    to_scale: ExecutiveScale,
    profile: BandProfile = DEFAULT_BAND_PROFILE,
) -> Optional[ScaleAggregate]:
    """Aggregate member loads into a :class:`ScaleAggregate` at ``to_scale``.

    Every member must sit on the same roll-up axis as ``to_scale`` (a CELL rolls
    up the physical axis to a RACK / ZONE / REGION; a member rolls into its
    SERVICE_GROUP / ENTITY_GROUP on the grouping axis) and be at a strictly lower
    scale than ``to_scale`` on the physical axis. Returns ``None`` for an empty
    member set (honest uncertainty, nothing to aggregate). Raises
    :class:`RollUpError` for a cross-axis member.
    """
    if not members:
        return None

    target_axis = axis_of(to_scale)
    for m in members:
        if axis_of(m.member_scale) is not target_axis:
            raise RollUpError(
                f"member {m.member_id!r} is on axis {axis_of(m.member_scale).value}, "
                f"cannot roll up to {to_scale.value} (axis {target_axis.value})"
            )
        if (
            target_axis is ScaleAxis.PHYSICAL
            and not _is_physically_below(m.member_scale, to_scale)
        ):
            raise RollUpError(
                f"member {m.member_id!r} at {m.member_scale.value} is not below "
                f"the physical parent {to_scale.value}"
            )

    zones = [classify_load_zone(m.utilization, profile) for m in members]
    counts = Counter(zones)
    total = len(members)
    mean_u = mean(m.utilization for m in members)
    # dominant: most common, ties broken by higher severity (surface the worse one).
    dominant = max(
        counts.items(), key=lambda kv: (kv[1], _SEVERITY_INDEX[kv[0]])
    )[0]
    worst = max(zones, key=lambda z: _SEVERITY_INDEX[z])
    distribution = tuple(
        (zone, counts[zone]) for zone in _ZONE_SEVERITY if zone in counts
    )
    frac_danger = counts.get(LoadZone.DANGER, 0) / total
    frac_idle = counts.get(LoadZone.IDLE, 0) / total
    rationale = (
        f"rolled {total} {target_axis.value} members → {to_scale.value}: "
        f"mean={mean_u:.3f} dominant={dominant.value} worst={worst.value} "
        f"danger={frac_danger:.2f} idle={frac_idle:.2f}"
    )
    return ScaleAggregate(
        scale=to_scale,
        axis=target_axis,
        member_count=total,
        mean_utilization=mean_u,
        dominant_zone=dominant,
        worst_zone=worst,
        zone_distribution=distribution,
        fraction_in_danger=frac_danger,
        fraction_idle=frac_idle,
        rationale=rationale,
    )


#: Physical-axis rank (leaf → root) for the strictly-below check.
_PHYSICAL_RANK: Final[dict[ExecutiveScale, int]] = {
    ExecutiveScale.CELL: 0,
    ExecutiveScale.RACK: 1,
    ExecutiveScale.ZONE: 2,
    ExecutiveScale.REGION: 3,
}


def _is_physically_below(
    member_scale: ExecutiveScale, to_scale: ExecutiveScale,
) -> bool:
    """True iff ``member_scale`` is strictly below ``to_scale`` on the physical axis."""
    m = _PHYSICAL_RANK.get(member_scale)
    p = _PHYSICAL_RANK.get(to_scale)
    if m is None or p is None:
        return False
    return m < p


__all__ = [
    "MemberLoad",
    "RollUpError",
    "ScaleAggregate",
    "roll_up",
]
