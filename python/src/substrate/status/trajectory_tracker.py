"""Substrate-state-trajectory status tracker

Pure-logic primitive for **long-cycle substrate-state-trajectory
verification** at both cell and node scales.
§ "Substrate-state-trajectory accumulation", an entity's status is
the cumulative substrate-state evidence over an extended window
the long-cycle "track record" that distinguishes momentary alignment
from sustained substrate-aligned operation.

Scale awareness
===============

The tracker is explicitly :class:`StatusScale`-aware:

* ``CELL`` — physical-instance trajectory tracking. One physical
  cell's track record over its operational window.
* ``NODE`` — logical-aggregate trajectory tracking. The persistent
  cryptographic identity's track record (typically derived from the
  Phase 44 node-aggregated state across cells).

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies sorted
  :class:`TrajectoryDataPoint` records; tracker computes slope +
  persistence + direction.
* Honest uncertainty: histories below
  :attr:`TrajectoryStatusConfig.min_data_points` surface
  ``INSUFFICIENT_DATA``; the tracker never extrapolates a
  trajectory from a thin record.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import mean
from typing import Final, Tuple

class StatusScale(str, Enum):
    """the host application entity hierarchy scale for the status tracking."""

    CELL = "cell"
    NODE = "node"

class TrajectoryDirection(str, Enum):
    """Trajectory direction over the observation window."""

    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class TrajectoryDataPoint:
    """One point in an entity's substrate-state trajectory."""

    sequence: int
    timestamp: int
    alignment_score: float
    health_score: float
    npg_positive_rate: float

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if not 0.0 <= self.alignment_score <= 1.0:
            raise ValueError("alignment_score must be in [0, 1]")
        if not 0.0 <= self.health_score <= 1.0:
            raise ValueError("health_score must be in [0, 1]")
        if not 0.0 <= self.npg_positive_rate <= 1.0:
            raise ValueError("npg_positive_rate must be in [0, 1]")

@dataclass(frozen=True, slots=True)
class TrajectoryStatus:  # pylint: disable=too-many-instance-attributes
    """Aggregate trajectory status over an entity's window."""

    entity_id: str
    scale: StatusScale
    data_point_count: int
    window_start_timestamp: int
    window_end_timestamp: int
    alignment_slope: float
    composite_slope: float
    direction: TrajectoryDirection
    accumulated_alignment_score: float
    persistence_score: float
    rationale: str

    @property
    def is_improving(self) -> bool:
        """True iff direction is IMPROVING."""
        return self.direction is TrajectoryDirection.IMPROVING

    @property
    def is_declining(self) -> bool:
        """True iff direction is DECLINING."""
        return self.direction is TrajectoryDirection.DECLINING

    @property
    def is_stable(self) -> bool:
        """True iff direction is STABLE."""
        return self.direction is TrajectoryDirection.STABLE

@dataclass(frozen=True, slots=True)
class TrajectoryStatusConfig:
    """Tunable thresholds for direction classification."""

    min_data_points: int = 3
    improving_slope_min: float = 0.005
    declining_slope_max: float = -0.005
    persistence_threshold: float = 0.6

    def __post_init__(self) -> None:
        if self.min_data_points < 2:
            raise ValueError("min_data_points must be >= 2")
        if self.improving_slope_min <= 0:
            raise ValueError("improving_slope_min must be > 0")
        if self.declining_slope_max >= 0:
            raise ValueError("declining_slope_max must be < 0")
        if not 0.0 < self.persistence_threshold <= 1.0:
            raise ValueError("persistence_threshold must be in (0, 1]")

DEFAULT_TRAJECTORY_STATUS_CONFIG: Final[TrajectoryStatusConfig] = (
    TrajectoryStatusConfig()
)

class SubstrateStateTrajectoryStatusTracker:  # pylint: disable=too-few-public-methods
    """Pure-logic trajectory status tracker."""

    def __init__(
        self,
        *,
        config: TrajectoryStatusConfig = DEFAULT_TRAJECTORY_STATUS_CONFIG,
    ) -> None:
        self._config = config

    def track(
        self,
        entity_id: str,
        scale: StatusScale,
        data_points: Tuple[TrajectoryDataPoint, ...],
    ) -> TrajectoryStatus:
        """Compute trajectory status from sorted data points."""
        if not entity_id:
            raise ValueError("entity_id must be non-empty")
        if len(data_points) < self._config.min_data_points:
            return TrajectoryStatus(
                entity_id=entity_id,
                scale=scale,
                data_point_count=len(data_points),
                window_start_timestamp=(
                    data_points[0].timestamp if data_points else 0
                ),
                window_end_timestamp=(
                    data_points[-1].timestamp if data_points else 0
                ),
                alignment_slope=0.0,
                composite_slope=0.0,
                direction=TrajectoryDirection.INSUFFICIENT_DATA,
                accumulated_alignment_score=0.0,
                persistence_score=0.0,
                rationale=(
                    f"data_point_count={len(data_points)} < "
                    f"{self._config.min_data_points}"
                ),
            )
        sorted_points = tuple(sorted(data_points, key=lambda p: p.sequence))
        alignment_slope = self._slope(
            [(p.sequence, p.alignment_score) for p in sorted_points]
        )
        composite_slope = self._slope(
            [
                (
                    p.sequence,
                    (p.alignment_score + p.health_score + p.npg_positive_rate)
                    / 3.0,
                )
                for p in sorted_points
            ]
        )
        direction = self._direction(alignment_slope)
        accumulated = mean(p.alignment_score for p in sorted_points)
        persistence = sum(
            1
            for p in sorted_points
            if p.alignment_score >= self._config.persistence_threshold
        ) / len(sorted_points)
        rationale = (
            f"entity={entity_id} scale={scale.value} "
            f"points={len(sorted_points)} "
            f"alignment_slope={alignment_slope:+.4f} "
            f"composite_slope={composite_slope:+.4f} "
            f"direction={direction.value} "
            f"accumulated={accumulated:.3f} "
            f"persistence={persistence:.3f}"
        )
        return TrajectoryStatus(
            entity_id=entity_id,
            scale=scale,
            data_point_count=len(sorted_points),
            window_start_timestamp=sorted_points[0].timestamp,
            window_end_timestamp=sorted_points[-1].timestamp,
            alignment_slope=alignment_slope,
            composite_slope=composite_slope,
            direction=direction,
            accumulated_alignment_score=accumulated,
            persistence_score=persistence,
            rationale=rationale,
        )

    @staticmethod
    def _slope(points: list[tuple[int, float]]) -> float:
        # Simple linear regression slope; pure logic.
        if len(points) < 2:
            return 0.0
        xs = [float(x) for x, _ in points]
        ys = [y for _, y in points]
        x_mean = mean(xs)
        y_mean = mean(ys)
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        denominator = sum((x - x_mean) ** 2 for x in xs)
        if denominator == 0:
            return 0.0
        return numerator / denominator

    def _direction(self, slope: float) -> TrajectoryDirection:
        cfg = self._config
        if slope >= cfg.improving_slope_min:
            return TrajectoryDirection.IMPROVING
        if slope <= cfg.declining_slope_max:
            return TrajectoryDirection.DECLINING
        return TrajectoryDirection.STABLE

__all__ = [
    "DEFAULT_TRAJECTORY_STATUS_CONFIG",
    "StatusScale",
    "SubstrateStateTrajectoryStatusTracker",
    "TrajectoryDataPoint",
    "TrajectoryDirection",
    "TrajectoryStatus",
    "TrajectoryStatusConfig",
]
