"""Cause inference + scale-agnostic hallmarks.

The cause ladder distinguishes *why* a decision is stressed, which sets the
response: STRESS → warn + compensate; ACCIDENT → warn + remediate; MALICE →
hard-fail + SIEM. :func:`infer_cause` derives the cause from the substrate
signals (hallmarks, profile validity, NPG, temporal trend) under a fixed
precedence, then lets a caller-declared ``intent`` only *escalate* it (never
lower it, an actor cannot declare its own malice benign).

The :class:`HallmarkSource` is scale-agnostic (any entity/cell/node): the
tumor/runaway hallmarks generalised beyond any one host consumer rather than
bound to a specific cancer-report implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping, Optional, Protocol, runtime_checkable

from substrate.executive.scale import ExecutiveScale
from substrate.sustained_load import LoadTrend


class Cause(str, Enum):
    """Why a decision is stressed; sets the response ladder."""

    NONE = "none"
    STRESS = "stress"        # load strain: warn + compensate
    ACCIDENT = "accident"    # validation / data failure: warn + remediate
    MALICE = "malice"        # doctrine-malicious hallmark: hard-fail + SIEM


#: Severity ordering for escalation (``intent`` may only raise the inferred cause).
_SEVERITY: Final[Mapping[Cause, int]] = {
    Cause.NONE: 0,
    Cause.STRESS: 1,
    Cause.ACCIDENT: 2,
    Cause.MALICE: 3,
}

#: Trends that indicate load STRESS.
_STRESS_TRENDS: Final[frozenset[LoadTrend]] = frozenset(
    {LoadTrend.SUSTAINED_STRAIN, LoadTrend.DEBT_ACCRUING, LoadTrend.SPIKE}
)


@dataclass(frozen=True, slots=True)
class HallmarkReport:
    """Which doctrine-malicious runaway hallmarks fired for an actor.

    The four runaway/cancer hallmarks (condition #6), scale-agnostic. Any one at
    threshold pre-empts to MALICE; corruption is not negotiated with.
    """

    evading_limits: bool = False
    peer_displacement: bool = False
    resource_hoarding: bool = False
    unbounded_growth: bool = False

    @property
    def any_malicious(self) -> bool:
        """``True`` iff any doctrine-malicious hallmark fired."""
        return (
            self.evading_limits
            or self.peer_displacement
            or self.resource_hoarding
            or self.unbounded_growth
        )


@runtime_checkable
class HallmarkSource(Protocol):  # pylint: disable=too-few-public-methods
    """Scale-agnostic hallmark provider (host-agnostic, not bound to any one
    cancer-report implementation)."""

    def hallmarks(
        self, *, actor_entity_id: str, scale: ExecutiveScale
    ) -> HallmarkReport:
        """Return the hallmark report for an actor at a scale."""
        ...  # pylint: disable=unnecessary-ellipsis


def max_cause(a: Cause, b: Cause) -> Cause:
    """Return the more severe of two causes."""
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


def infer_cause(
    *,
    hallmarks: HallmarkReport,
    profile_valid: bool,
    npg_insufficient: bool,
    trend: LoadTrend,
    intent: Optional[Cause] = None,
) -> Cause:
    """Infer the cause from the substrate signals, then escalate by intent.

    Precedence (highest wins): a doctrine-malicious hallmark → MALICE (runs
    BEFORE the NPG row so malice pre-empts); invalid profile or insufficient NPG
    data → ACCIDENT; a stress trend → STRESS; otherwise NONE. The caller's
    ``intent`` may only *escalate* the result (``max_cause``).
    """
    if hallmarks.any_malicious:
        inferred = Cause.MALICE
    elif (not profile_valid) or npg_insufficient:
        inferred = Cause.ACCIDENT
    elif trend in _STRESS_TRENDS:
        inferred = Cause.STRESS
    else:
        inferred = Cause.NONE
    return max_cause(inferred, intent or Cause.NONE)


__all__ = [
    "Cause",
    "HallmarkReport",
    "HallmarkSource",
    "infer_cause",
    "max_cause",
]
