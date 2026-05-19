"""Self-model calibration tracker — Companion #2

Pure-logic primitive that tracks divergence between an entity's
*declared self-state* and its *observed substrate-state*. A
substrate-aligned entity's self-model converges over cycles; a
drifting entity's self-model diverges. The tracker computes per-cycle
divergence and a sustained-divergence verdict for downstream
guard-relaxation and offense-handling consumers.

Pure logic
==========

* No DAO, no LLM, no network. Caller pushes ``CalibrationObservation``
  entries; the tracker returns a verdict computed from the in-memory
  window.
* Honest uncertainty: below ``min_observations``, returns
  ``INSUFFICIENT_DATA``.
* Stateful only in the bounded-ring sense — uses a deque-like list
  truncated by config.
* Frozen dataclasses for outputs; the tracker itself is the only
  mutable element.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Final

class CalibrationVerdict(str, Enum):
    """Self-model calibration verdict."""

    CONVERGING = "converging"
    STEADY = "steady"
    DIVERGING = "diverging"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    """One observation cycle: declared vs. observed substrate-state."""

    entity_id: str
    cycle_index: int
    declared_substrate_state: float
    observed_substrate_state: float

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if self.cycle_index < 0:
            raise ValueError("cycle_index must be >= 0")
        if not 0.0 <= self.declared_substrate_state <= 1.0:
            raise ValueError(
                "declared_substrate_state must be in [0, 1]"
            )
        if not 0.0 <= self.observed_substrate_state <= 1.0:
            raise ValueError(
                "observed_substrate_state must be in [0, 1]"
            )

    @property
    def divergence(self) -> float:
        """Absolute divergence at this cycle."""
        return abs(
            self.declared_substrate_state - self.observed_substrate_state
        )

@dataclass(frozen=True, slots=True)
class CalibrationVerdictOutput:  # pylint: disable=too-many-instance-attributes
    """Tracker output."""

    entity_id: str
    verdict: CalibrationVerdict
    observation_count: int
    current_divergence: float
    trend_slope: float
    mean_divergence: float
    rationale: str

    @property
    def diverging(self) -> bool:
        """True iff verdict is DIVERGING."""
        return self.verdict is CalibrationVerdict.DIVERGING

@dataclass(frozen=True, slots=True)
class CalibrationConfig:
    """Operator-tunable thresholds."""

    window_size: int = 20
    min_observations: int = 5
    diverging_slope_threshold: float = 0.01
    converging_slope_threshold: float = -0.01
    high_divergence_threshold: float = 0.3

    def __post_init__(self) -> None:
        if self.window_size < 2:
            raise ValueError("window_size must be >= 2")
        if self.min_observations < 2:
            raise ValueError("min_observations must be >= 2")
        if self.min_observations > self.window_size:
            raise ValueError(
                "min_observations cannot exceed window_size"
            )
        if self.diverging_slope_threshold <= 0:
            raise ValueError(
                "diverging_slope_threshold must be > 0"
            )
        if self.converging_slope_threshold >= 0:
            raise ValueError(
                "converging_slope_threshold must be < 0"
            )
        if not 0.0 < self.high_divergence_threshold <= 1.0:
            raise ValueError(
                "high_divergence_threshold must be in (0, 1]"
            )

DEFAULT_CALIBRATION_CONFIG: Final[CalibrationConfig] = (
    CalibrationConfig()
)

class SelfModelCalibrationTracker:
    """Pure-logic self-model calibration tracker (Companion #2)."""

    def __init__(
        self,
        *,
        entity_id: str,
        config: CalibrationConfig = DEFAULT_CALIBRATION_CONFIG,
    ) -> None:
        if not entity_id:
            raise ValueError("entity_id must be non-empty")
        self._entity_id = entity_id
        self._config = config
        self._window: Deque[CalibrationObservation] = deque(
            maxlen=config.window_size,
        )

    def observe(self, observation: CalibrationObservation) -> None:
        """Record a new observation."""
        if observation.entity_id != self._entity_id:
            raise ValueError(
                f"observation.entity_id={observation.entity_id} "
                f"does not match tracker entity_id={self._entity_id}"
            )
        self._window.append(observation)

    def verdict(self) -> CalibrationVerdictOutput:
        """Return the current verdict."""
        cfg = self._config
        n = len(self._window)
        if n < cfg.min_observations:
            return CalibrationVerdictOutput(
                entity_id=self._entity_id,
                verdict=CalibrationVerdict.INSUFFICIENT_DATA,
                observation_count=n,
                current_divergence=0.0,
                trend_slope=0.0,
                mean_divergence=0.0,
                rationale=(
                    f"observations={n} below min "
                    f"{cfg.min_observations}"
                ),
            )
        divergences = [o.divergence for o in self._window]
        mean = sum(divergences) / n
        slope = self._slope(divergences)
        current = divergences[-1]
        if (
            slope >= cfg.diverging_slope_threshold
            or current >= cfg.high_divergence_threshold
        ):
            verdict = CalibrationVerdict.DIVERGING
        elif slope <= cfg.converging_slope_threshold:
            verdict = CalibrationVerdict.CONVERGING
        else:
            verdict = CalibrationVerdict.STEADY
        return CalibrationVerdictOutput(
            entity_id=self._entity_id,
            verdict=verdict,
            observation_count=n,
            current_divergence=current,
            trend_slope=slope,
            mean_divergence=mean,
            rationale=(
                f"slope={slope:+.4f}, mean={mean:.3f}, "
                f"current={current:.3f}"
            ),
        )

    @staticmethod
    def _slope(values: list[float]) -> float:
        n = len(values)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n
        num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        den = sum((i - x_mean) ** 2 for i in range(n))
        if den == 0:
            return 0.0
        return num / den

__all__ = [
    "CalibrationConfig",
    "CalibrationObservation",
    "CalibrationVerdict",
    "CalibrationVerdictOutput",
    "DEFAULT_CALIBRATION_CONFIG",
    "SelfModelCalibrationTracker",
]
