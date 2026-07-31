"""Cultural-infrastructure gap detector (Companion #2)

Pure-logic detector that consumes an
:class:`InventoryReport` and the org/node's activity profile to flag
which condition-#6 mechanisms are *most urgently* missing for this
deployment. The detector ranks gaps by activity-driven priority: an
org with heavy voting traffic should prioritize substrate-aware-voting
wiring; an org with heavy cross-cell traffic should prioritize
symmetric-audit wiring.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies inventory + activity.
* Honest uncertainty: a fully-complete inventory returns
  ``NO_GAPS`` with an empty gap list.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from substrate.cultural_infrastructure.inventory import (
    CulturalMechanism,
    InventoryReport,
)

class GapVerdict(str, Enum):
    """Gap-detector verdict."""

    NO_GAPS = "no_gaps"
    LOW_PRIORITY_GAPS = "low_priority_gaps"
    HIGH_PRIORITY_GAPS = "high_priority_gaps"
    CRITICAL_GAPS = "critical_gaps"

@dataclass(frozen=True, slots=True)
class ActivityProfile:
    """Caller-supplied activity profile for the org/node."""

    voting_activity_score: float
    cross_cell_activity_score: float
    pair_coupling_activity_score: float
    escalation_activity_score: float
    reputation_activity_score: float
    reciprocal_activity_score: float

    def __post_init__(self) -> None:
        for name, value in (
            ("voting_activity_score", self.voting_activity_score),
            (
                "cross_cell_activity_score",
                self.cross_cell_activity_score,
            ),
            (
                "pair_coupling_activity_score",
                self.pair_coupling_activity_score,
            ),
            (
                "escalation_activity_score",
                self.escalation_activity_score,
            ),
            (
                "reputation_activity_score",
                self.reputation_activity_score,
            ),
            (
                "reciprocal_activity_score",
                self.reciprocal_activity_score,
            ),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")

_MECHANISM_DRIVERS: Final[dict[CulturalMechanism, str]] = {
    CulturalMechanism.SUBSTRATE_AWARE_VOTING: "voting_activity_score",
    CulturalMechanism.SYMMETRIC_AUDIT: "cross_cell_activity_score",
    CulturalMechanism.PAIR_COUPLED_ARCHITECTURE: (
        "pair_coupling_activity_score"
    ),
    CulturalMechanism.HALT_AND_ESCALATE: "escalation_activity_score",
    CulturalMechanism.IDENTITY_GROUNDED_REPUTATION: (
        "reputation_activity_score"
    ),
    CulturalMechanism.RECIPROCAL_FEEDBACK: "reciprocal_activity_score",
}

@dataclass(frozen=True, slots=True)
class GapEntry:
    """One gap with a priority score."""

    mechanism: CulturalMechanism
    priority_score: float
    rationale: str

@dataclass(frozen=True, slots=True)
class GapReport:  # pylint: disable=too-many-instance-attributes
    """Gap detector report."""

    org_or_node_id: str
    verdict: GapVerdict
    gap_count: int
    max_priority: float
    gaps: tuple[GapEntry, ...]

@dataclass(frozen=True, slots=True)
class GapDetectorConfig:
    """Operator-tunable detector thresholds."""

    critical_priority_threshold: float = 0.7
    high_priority_threshold: float = 0.4

    def __post_init__(self) -> None:
        if not 0.0 < self.high_priority_threshold <= 1.0:
            raise ValueError(
                "high_priority_threshold must be in (0, 1]"
            )
        if not (
            self.high_priority_threshold
            < self.critical_priority_threshold
            <= 1.0
        ):
            raise ValueError(
                "must satisfy 0 < high < critical <= 1"
            )

DEFAULT_GAP_DETECTOR_CONFIG: Final[GapDetectorConfig] = (
    GapDetectorConfig()
)

class CulturalInfrastructureGapDetector:  # pylint: disable=too-few-public-methods
    """Pure-logic cultural-infrastructure gap detector (Companion #2)."""

    def __init__(
        self,
        *,
        config: GapDetectorConfig = DEFAULT_GAP_DETECTOR_CONFIG,
    ) -> None:
        self._config = config

    def detect(
        self,
        inventory: InventoryReport,
        activity: ActivityProfile,
    ) -> GapReport:
        """Detect cultural-infrastructure gaps weighted by activity."""
        cfg = self._config
        if inventory.missing_count == 0:
            return GapReport(
                org_or_node_id=inventory.org_or_node_id,
                verdict=GapVerdict.NO_GAPS,
                gap_count=0,
                max_priority=0.0,
                gaps=(),
            )
        gaps: list[GapEntry] = []
        for mechanism in inventory.missing_mechanisms:
            driver_name = _MECHANISM_DRIVERS[mechanism]
            priority = float(getattr(activity, driver_name))
            gaps.append(
                GapEntry(
                    mechanism=mechanism,
                    priority_score=priority,
                    rationale=(
                        f"{mechanism.value} missing; "
                        f"{driver_name}={priority:.3f}"
                    ),
                ),
            )
        gaps.sort(key=lambda g: g.priority_score, reverse=True)
        max_priority = gaps[0].priority_score
        if max_priority >= cfg.critical_priority_threshold:
            verdict = GapVerdict.CRITICAL_GAPS
        elif max_priority >= cfg.high_priority_threshold:
            verdict = GapVerdict.HIGH_PRIORITY_GAPS
        else:
            verdict = GapVerdict.LOW_PRIORITY_GAPS
        return GapReport(
            org_or_node_id=inventory.org_or_node_id,
            verdict=verdict,
            gap_count=len(gaps),
            max_priority=max_priority,
            gaps=tuple(gaps),
        )

__all__ = [
    "ActivityProfile",
    "CulturalInfrastructureGapDetector",
    "DEFAULT_GAP_DETECTOR_CONFIG",
    "GapDetectorConfig",
    "GapEntry",
    "GapReport",
    "GapVerdict",
]
