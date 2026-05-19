"""Trajectory-generation-capacity tracker — Companion #2b.

Pure-logic tracker that measures an entity's *capacity to generate
substrate-state-trajectories* over cycles. Declining capacity is a
drift signal: a substrate-aligned entity sustains its trajectory-
generation capability; an entity drifting toward reactive-mode loses
the capability to compose forward-moving trajectories even when
nominally healthy on other metrics.

Per Companion #2's articulation: trajectory-generation capacity is
distinct from substrate-state magnitude. An entity can hold high
substrate-state and yet lose the *capacity to produce new
trajectories* — that is the early warning the tracker surfaces.

Pure logic
==========

* No DAO, no LLM, no network. Caller pushes
  :class:`CapacityObservation` entries; the tracker returns a verdict
  computed from the in-memory window.
* Honest uncertainty: below ``min_observations`` returns
  ``INSUFFICIENT_DATA``.
* Frozen dataclasses for outputs; the tracker mutates only its
  bounded-ring window.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Final

class CapacityVerdict(str, Enum):
    """Capacity-tracker verdict."""

    SUSTAINED = "sustained"
    DECLINING = "declining"
    COLLAPSED = "collapsed"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class CapacityObservation:
    """One observation of trajectory-generation capacity."""

    entity_id: str
    cycle_index: int
    trajectories_generated: int
    """Count of new substrate-state-trajectories generated this cycle."""

    novel_trajectories_count: int
    """Subset of generated trajectories not seen in the window prior."""

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if self.cycle_index < 0:
            raise ValueError("cycle_index must be >= 0")
        if self.trajectories_generated < 0:
            raise ValueError(
                "trajectories_generated must be >= 0"
            )
        if self.novel_trajectories_count < 0:
            raise ValueError(
                "novel_trajectories_count must be >= 0"
            )
        if self.novel_trajectories_count > self.trajectories_generated:
            raise ValueError(
                "novel_trajectories_count cannot exceed "
                "trajectories_generated"
            )

    @property
    def novelty_ratio(self) -> float:
        """Fraction of generated trajectories that are novel."""
        if self.trajectories_generated == 0:
            return 0.0
        return (
            self.novel_trajectories_count
            / self.trajectories_generated
        )

@dataclass(frozen=True, slots=True)
class CapacityVerdictOutput:  # pylint: disable=too-many-instance-attributes
    """Tracker output."""

    entity_id: str
    verdict: CapacityVerdict
    observation_count: int
    mean_trajectories_per_cycle: float
    mean_novelty_ratio: float
    trend_slope: float
    rationale: str

    @property
    def declining(self) -> bool:
        """True iff verdict is DECLINING or COLLAPSED."""
        return self.verdict in (
            CapacityVerdict.DECLINING,
            CapacityVerdict.COLLAPSED,
        )

@dataclass(frozen=True, slots=True)
class CapacityTrackerConfig:
    """Operator-tunable tracker thresholds."""

    window_size: int = 20
    min_observations: int = 5
    declining_slope_threshold: float = -0.1
    collapsed_capacity_threshold: float = 0.5
    """Mean trajectories-per-cycle below this triggers COLLAPSED."""

    minimum_novelty_ratio: float = 0.2
    """Mean novelty-ratio below this contributes to DECLINING verdict."""

    def __post_init__(self) -> None:
        if self.window_size < 2:
            raise ValueError("window_size must be >= 2")
        if self.min_observations < 2:
            raise ValueError("min_observations must be >= 2")
        if self.min_observations > self.window_size:
            raise ValueError(
                "min_observations cannot exceed window_size"
            )
        if self.declining_slope_threshold >= 0:
            raise ValueError(
                "declining_slope_threshold must be < 0"
            )
        if self.collapsed_capacity_threshold <= 0:
            raise ValueError(
                "collapsed_capacity_threshold must be > 0"
            )
        if not 0.0 < self.minimum_novelty_ratio <= 1.0:
            raise ValueError(
                "minimum_novelty_ratio must be in (0, 1]"
            )

DEFAULT_CAPACITY_TRACKER_CONFIG: Final[CapacityTrackerConfig] = (
    CapacityTrackerConfig()
)

class TrajectoryGenerationCapacityTracker:
    """Pure-logic capacity tracker (Companion #2b)."""

    def __init__(
        self,
        *,
        entity_id: str,
        config: CapacityTrackerConfig = DEFAULT_CAPACITY_TRACKER_CONFIG,
    ) -> None:
        if not entity_id:
            raise ValueError("entity_id must be non-empty")
        self._entity_id = entity_id
        self._config = config
        self._window: Deque[CapacityObservation] = deque(
            maxlen=config.window_size,
        )

    def observe(self, observation: CapacityObservation) -> None:
        """Record an observation."""
        if observation.entity_id != self._entity_id:
            raise ValueError(
                f"observation.entity_id={observation.entity_id} "
                f"does not match tracker entity_id={self._entity_id}"
            )
        self._window.append(observation)

    def verdict(self) -> CapacityVerdictOutput:
        """Return the current verdict."""
        cfg = self._config
        n = len(self._window)
        if n < cfg.min_observations:
            return CapacityVerdictOutput(
                entity_id=self._entity_id,
                verdict=CapacityVerdict.INSUFFICIENT_DATA,
                observation_count=n,
                mean_trajectories_per_cycle=0.0,
                mean_novelty_ratio=0.0,
                trend_slope=0.0,
                rationale=(
                    f"observations={n} below min "
                    f"{cfg.min_observations}"
                ),
            )
        counts = [
            float(o.trajectories_generated) for o in self._window
        ]
        novelty = [o.novelty_ratio for o in self._window]
        mean_counts = sum(counts) / n
        mean_novelty = sum(novelty) / n
        slope = self._slope(counts)
        if mean_counts < cfg.collapsed_capacity_threshold:
            verdict = CapacityVerdict.COLLAPSED
        elif (
            slope <= cfg.declining_slope_threshold
            or mean_novelty < cfg.minimum_novelty_ratio
        ):
            verdict = CapacityVerdict.DECLINING
        else:
            verdict = CapacityVerdict.SUSTAINED
        return CapacityVerdictOutput(
            entity_id=self._entity_id,
            verdict=verdict,
            observation_count=n,
            mean_trajectories_per_cycle=mean_counts,
            mean_novelty_ratio=mean_novelty,
            trend_slope=slope,
            rationale=(
                f"mean_counts={mean_counts:.3f}, "
                f"mean_novelty={mean_novelty:.3f}, "
                f"slope={slope:+.4f}"
            ),
        )

    @staticmethod
    def _slope(values: list[float]) -> float:
        n = len(values)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n
        num = sum(
            (i - x_mean) * (v - y_mean) for i, v in enumerate(values)
        )
        den = sum((i - x_mean) ** 2 for i in range(n))
        if den == 0:
            return 0.0
        return num / den

__all__ = [
    "CapacityObservation",
    "CapacityTrackerConfig",
    "CapacityVerdict",
    "CapacityVerdictOutput",
    "DEFAULT_CAPACITY_TRACKER_CONFIG",
    "TrajectoryGenerationCapacityTracker",
]
