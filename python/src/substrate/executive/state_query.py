"""Unified entity-state query — the substrate's "how are you doing?".

A single integration over an entity's recent load history that answers the
human question directly: *is it depleted or engaged, slacking or working hard,
recovering or deteriorating — and is that a passing mood or a sustained state?*

This is a **reading** faculty, not a new authority: it delegates the hard
judgements to the canonical band + temporal layers and integrates their output
into one legible report.

* **Energy** (the mood proxy) — where the entity sits on the band, read through
  the temporal trend: sustained idle reads DEPLETED, the work zone reads ENGAGED,
  a transient peak reads PEAKING (a good push), sustained warning/danger reads
  STRAINED.
* **Effort** (slacking vs working) — the tracker already names *avoidance*
  (bouncing off the work-entry threshold while work is pending); that is
  SLACKING. Idle with nothing pending is RESTING; the work zone is WORKING;
  sustained operation above it is OVEREXERTING.
* **Trajectory over time** (the "watching state change" part) — whether the
  entity is moving TOWARD the healthy work zone (RECOVERING), holding (STABLE),
  or drifting toward an extreme (DETERIORATING). Health is proximity to the work
  zone, so both "sinking into idle" and "climbing into danger" deteriorate.

Pure logic
==========

* No DAO, no LLM, no network. Deterministic on identical inputs.
* Reuses :class:`EwmaLoadTracker` as the sole sustained-vs-spike authority and
  :func:`classify_load_zone` as the sole level authority — no parallel logic.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import mean
from typing import Final, Optional, Sequence

from substrate.executive.band import (
    DEFAULT_BAND_PROFILE,
    BandProfile,
    LoadZone,
    classify_load_zone,
)
from substrate.executive.temporal import (
    EwmaLoadTracker,
    LoadTrend,
    SustainedLoadTracker,
)


class EnergyState(str, Enum):
    """The mood / energy proxy read from load × trend."""

    DEPLETED = "depleted"      # sustained under-load — flat, atrophying
    RESTED = "rested"          # low load, legitimately recovering
    ENGAGED = "engaged"        # in the work zone — healthy, "in the zone"
    PEAKING = "peaking"        # a transient growth push — good effort
    STRAINED = "strained"      # sustained above the work zone — winded / burning out


class EffortState(str, Enum):
    """Slacking vs working hard."""

    SLACKING = "slacking"          # avoiding pending work (the avoidance trend)
    RESTING = "resting"            # idle with nothing pending — fine
    WORKING = "working"            # productive work-zone effort
    OVEREXERTING = "overexerting"  # sustained operation past the work zone


class TrajectoryDirection(str, Enum):
    """Which way the state is moving, relative to the healthy work zone."""

    RECOVERING = "recovering"        # moving toward the work zone
    STABLE = "stable"                # holding
    DETERIORATING = "deteriorating"  # drifting toward an extreme (idle or danger)


@dataclass(frozen=True, slots=True)
class StateObservation:
    """One point in the entity's recent history."""

    utilization: float
    work_pending: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.utilization <= 1.0:
            raise ValueError(
                f"utilization must be in [0, 1]; got {self.utilization!r}"
            )


@dataclass(frozen=True, slots=True)
class EntityStateReport:  # pylint: disable=too-many-instance-attributes
    """The integrated answer to 'how are you doing?'."""

    entity_id: str
    energy: EnergyState
    effort: EffortState
    trajectory: TrajectoryDirection
    dominant_zone: LoadZone
    trend: LoadTrend
    sustained: bool
    observation_count: int
    summary: str


#: The healthy centre — the midpoint of the work zone ``[1/φ², 0.50]``. Health is
#: proximity to this point; both extremes (idle, danger) are equidistant-bad.
def _work_zone_centre(profile: BandProfile) -> float:
    return (profile.recreation_ceiling + profile.pivot) / 2.0


#: Trends that mean "the excursion is sustained", not an absorbed transient.
_SUSTAINED_TRENDS: Final[frozenset[LoadTrend]] = frozenset(
    {
        LoadTrend.SUSTAINED_STRAIN,
        LoadTrend.DEBT_ACCRUING,
        LoadTrend.RUNAWAY_GROWTH,
    }
)

#: Trends that read as over-drive (sustained over the work zone, or unbounded
#: growth-desire — the always-grow-never-consolidate drift).
_OVERDRIVE_TRENDS: Final[frozenset[LoadTrend]] = frozenset(
    {
        LoadTrend.SUSTAINED_STRAIN,
        LoadTrend.DEBT_ACCRUING,
        LoadTrend.RUNAWAY_GROWTH,
    }
)


def _energy_for(  # pylint: disable=too-many-return-statements
    zone: LoadZone, trend: LoadTrend,
) -> EnergyState:
    if trend in _OVERDRIVE_TRENDS:
        return EnergyState.STRAINED
    if trend is LoadTrend.AVOIDANCE:
        return EnergyState.DEPLETED
    if zone is LoadZone.IDLE:
        return EnergyState.DEPLETED
    if zone is LoadZone.RECREATION:
        return EnergyState.RESTED
    if zone is LoadZone.WORK:
        return EnergyState.ENGAGED
    if zone is LoadZone.PEAKING:
        return EnergyState.PEAKING
    # WARNING / DANGER reached without a sustained trend → a transient push.
    return EnergyState.PEAKING


def _effort_for(
    zone: LoadZone, trend: LoadTrend, work_pending: bool,
) -> EffortState:
    if trend is LoadTrend.AVOIDANCE:
        return EffortState.SLACKING
    if zone is LoadZone.IDLE:
        return EffortState.SLACKING if work_pending else EffortState.RESTING
    if trend in _OVERDRIVE_TRENDS:
        return EffortState.OVEREXERTING
    if zone in (LoadZone.WARNING, LoadZone.DANGER):
        return EffortState.OVEREXERTING
    return EffortState.WORKING


def _trajectory_for(
    utilizations: Sequence[float], centre: float,
) -> TrajectoryDirection:
    """Compare proximity-to-centre of the earlier half vs the recent half."""
    if len(utilizations) < 2:
        return TrajectoryDirection.STABLE
    mid = len(utilizations) // 2
    earlier = utilizations[:mid] or utilizations[:1]
    recent = utilizations[mid:]
    earlier_dist = abs(mean(earlier) - centre)
    recent_dist = abs(mean(recent) - centre)
    delta = recent_dist - earlier_dist
    # A small dead-band so noise does not read as movement.
    if delta < -0.02:
        return TrajectoryDirection.RECOVERING
    if delta > 0.02:
        return TrajectoryDirection.DETERIORATING
    return TrajectoryDirection.STABLE


def integrate_state(
    entity_id: str,
    observations: Sequence[StateObservation],
    *,
    profile: BandProfile = DEFAULT_BAND_PROFILE,
    tracker: Optional[SustainedLoadTracker] = None,
) -> Optional[EntityStateReport]:
    """Integrate an entity's recent history into a 'how are you doing?' report.

    Feeds the observations through the canonical :class:`SustainedLoadTracker`
    (default :class:`EwmaLoadTracker`) so the sustained-vs-spike judgement is the
    canonical one, classifies the latest reading's zone, and integrates the two
    into energy / effort / trajectory plus a human-readable summary.

    Returns ``None`` for an empty history (honest uncertainty — no state to read).
    """
    if not entity_id:
        raise ValueError("entity_id must be non-empty")
    if not observations:
        return None

    track = tracker or EwmaLoadTracker()
    for obs in observations:
        track.observe(obs.utilization, work_pending=obs.work_pending)
    trend = track.trend(profile=profile)

    latest = observations[-1]
    zone = classify_load_zone(latest.utilization, profile)
    sustained = trend in _SUSTAINED_TRENDS or trend is LoadTrend.AVOIDANCE

    energy = _energy_for(zone, trend)
    effort = _effort_for(zone, trend, latest.work_pending)
    trajectory = _trajectory_for(
        [o.utilization for o in observations], _work_zone_centre(profile),
    )

    summary = (
        f"{entity_id} is {energy.value} and {effort.value}, "
        f"{trajectory.value} (zone={zone.value}, trend={trend.value}, "
        f"{'sustained' if sustained else 'transient'}, "
        f"over {len(observations)} readings)"
    )
    return EntityStateReport(
        entity_id=entity_id,
        energy=energy,
        effort=effort,
        trajectory=trajectory,
        dominant_zone=zone,
        trend=trend,
        sustained=sustained,
        observation_count=len(observations),
        summary=summary,
    )


__all__ = [
    "EffortState",
    "EnergyState",
    "EntityStateReport",
    "StateObservation",
    "TrajectoryDirection",
    "integrate_state",
]
