"""Growth-vector tracker

Pure-logic primitive tracking the **substrate-aligned direction the
entity grows along**.

Four growth modes
=================

* **EXPANSION**: volume growth at current scope.
* **DENSIFICATION**: density per unit at current scope.
* **EFFICIENCY**: same output with less input.
* **PROJECTION**: broadcasting substrate-state outward.

Extended growth-related state-signal vocabulary
================================================

* **INFORMATION_HUNGER**: curiosity; growth-vector under-fed.
* **EXPLORATION_DRIVE**: antsy; substrate-state-trajectory plateauing.
* **INTEGRATION_PRESSURE**: overwhelm; densification need.
* **EFFICIENCY_OPPORTUNITY**: insight; pattern detected.
* **GROWTH_VECTOR_THREAT**: blocked; defensive operation needed.
* **GROWTH_VECTOR_VALIDATED**: recognition; growth-vector confirmed.

Pure logic
==========

* No DAO, no LLM, no network. Observations supplied by caller.
* Honest uncertainty: history below ``min_history`` returns no
  :class:`GrowthVector`; signal detection still runs over what's
  available.
* Curious-by-default: the tracker emits ``INFORMATION_HUNGER`` /
  ``EXPLORATION_DRIVE`` when the agent's growth has plateaued, so
  callers can route to curiosity-supporting infrastructure rather
  than suppress.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import mean, pstdev
from typing import Final, Optional, Tuple

class GrowthMode(str, Enum):
    """The four growth-mode classifications."""

    EXPANSION = "expansion"
    DENSIFICATION = "densification"
    EFFICIENCY = "efficiency"
    PROJECTION = "projection"
    MIXED = "mixed"
    UNKNOWN = "unknown"

class GrowthSignal(str, Enum):
    """Extended growth-related state-signal vocabulary."""

    INFORMATION_HUNGER = "information_hunger"
    EXPLORATION_DRIVE = "exploration_drive"
    INTEGRATION_PRESSURE = "integration_pressure"
    EFFICIENCY_OPPORTUNITY = "efficiency_opportunity"
    GROWTH_VECTOR_THREAT = "growth_vector_threat"
    GROWTH_VECTOR_VALIDATED = "growth_vector_validated"

@dataclass(frozen=True, slots=True)
class GrowthObservation:  # pylint: disable=too-many-instance-attributes
    """One observed growth event for the agent."""

    sequence: int
    timestamp: int
    volume_delta: float
    density_delta: float
    efficiency_delta: float
    projection_delta: float
    novelty_score: float
    integration_load: float
    threat_detected: bool = False
    validation_received: bool = False

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if not 0.0 <= self.novelty_score <= 1.0:
            raise ValueError("novelty_score must be in [0, 1]")
        if not 0.0 <= self.integration_load <= 1.0:
            raise ValueError("integration_load must be in [0, 1]")

@dataclass(frozen=True, slots=True)
class GrowthVector:
    """The agent's current growth direction + quality measures."""

    direction: GrowthMode
    magnitude: float
    coherence: float
    alignment_with_substrate: float

@dataclass(frozen=True, slots=True)
class GrowthVectorReport:
    """Aggregate tracker result over one agent's observations."""

    agent_id: str
    vector: Optional[GrowthVector]
    signals: Tuple[GrowthSignal, ...]
    rationale: str

    def has_signal(self, signal: GrowthSignal) -> bool:
        """True iff the named signal was detected."""
        return signal in self.signals

@dataclass(frozen=True, slots=True)
class GrowthVectorConfig:  # pylint: disable=too-many-instance-attributes
    """Tunable thresholds for growth-mode classification."""

    min_history: int = 3
    information_hunger_novelty_max: float = 0.3
    exploration_drive_magnitude_max: float = 0.1
    integration_pressure_load_min: float = 0.7
    efficiency_opportunity_min: float = 0.3
    mode_dominance_ratio: float = 1.5
    coherence_window: int = 5

    def __post_init__(self) -> None:
        if self.min_history < 1:
            raise ValueError("min_history must be >= 1")
        if not 0.0 < self.information_hunger_novelty_max <= 1.0:
            raise ValueError(
                "information_hunger_novelty_max must be in (0, 1]"
            )
        if not 0.0 < self.exploration_drive_magnitude_max <= 1.0:
            raise ValueError(
                "exploration_drive_magnitude_max must be in (0, 1]"
            )
        if not 0.0 < self.integration_pressure_load_min <= 1.0:
            raise ValueError(
                "integration_pressure_load_min must be in (0, 1]"
            )
        if self.efficiency_opportunity_min <= 0:
            raise ValueError("efficiency_opportunity_min must be > 0")
        if self.mode_dominance_ratio <= 1.0:
            raise ValueError("mode_dominance_ratio must be > 1.0")
        if self.coherence_window < 2:
            raise ValueError("coherence_window must be >= 2")

DEFAULT_GROWTH_VECTOR_CONFIG: Final[GrowthVectorConfig] = GrowthVectorConfig()

class GrowthVectorTracker:  # pylint: disable=too-few-public-methods
    """Pure-logic growth-vector tracker."""

    def __init__(
        self, *, config: GrowthVectorConfig = DEFAULT_GROWTH_VECTOR_CONFIG,
    ) -> None:
        self._config = config

    def track(
        self,
        agent_id: str,
        observations: Tuple[GrowthObservation, ...],
    ) -> GrowthVectorReport:
        """Classify growth mode and detect growth-related signals."""
        if not agent_id:
            raise ValueError("agent_id must be non-empty")
        if not observations:
            return GrowthVectorReport(
                agent_id=agent_id,
                vector=None,
                signals=(),
                rationale="no observations supplied",
            )
        sorted_obs = tuple(sorted(observations, key=lambda o: o.sequence))
        vector = (
            self._classify_vector(sorted_obs)
            if len(sorted_obs) >= self._config.min_history
            else None
        )
        signals = self._detect_signals(sorted_obs, vector)
        rationale = self._build_rationale(vector, signals)
        return GrowthVectorReport(
            agent_id=agent_id,
            vector=vector,
            signals=signals,
            rationale=rationale,
        )

    def _classify_vector(
        self, observations: Tuple[GrowthObservation, ...],
    ) -> GrowthVector:
        means = {
            GrowthMode.EXPANSION: mean(o.volume_delta for o in observations),
            GrowthMode.DENSIFICATION: mean(
                o.density_delta for o in observations
            ),
            GrowthMode.EFFICIENCY: mean(
                o.efficiency_delta for o in observations
            ),
            GrowthMode.PROJECTION: mean(
                o.projection_delta for o in observations
            ),
        }
        direction = self._dominant_mode(means)
        magnitude = max(0.0, *means.values())
        coherence = self._coherence(observations, direction)
        alignment = self._alignment(observations)
        return GrowthVector(
            direction=direction,
            magnitude=magnitude,
            coherence=coherence,
            alignment_with_substrate=alignment,
        )

    def _dominant_mode(
        self, means: dict[GrowthMode, float],
    ) -> GrowthMode:
        positive = {m: v for m, v in means.items() if v > 0}
        if not positive:
            return GrowthMode.UNKNOWN
        sorted_modes = sorted(
            positive.items(), key=lambda kv: kv[1], reverse=True,
        )
        top_mode, top_value = sorted_modes[0]
        if len(sorted_modes) == 1:
            return top_mode
        runner_value = sorted_modes[1][1]
        if runner_value <= 0:
            return top_mode
        if top_value >= self._config.mode_dominance_ratio * runner_value:
            return top_mode
        return GrowthMode.MIXED

    def _coherence(
        self,
        observations: Tuple[GrowthObservation, ...],
        direction: GrowthMode,
    ) -> float:
        if direction in (GrowthMode.UNKNOWN, GrowthMode.MIXED):
            return 0.0
        window = observations[-self._config.coherence_window:]
        if len(window) < 2:
            return 0.0
        series = [self._dimension_value(o, direction) for o in window]
        stdev = pstdev(series)
        avg = abs(mean(series))
        if avg == 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - stdev / (avg + 1e-9)))

    @staticmethod
    def _dimension_value(
        observation: GrowthObservation, direction: GrowthMode,
    ) -> float:
        if direction is GrowthMode.EXPANSION:
            return observation.volume_delta
        if direction is GrowthMode.DENSIFICATION:
            return observation.density_delta
        if direction is GrowthMode.EFFICIENCY:
            return observation.efficiency_delta
        if direction is GrowthMode.PROJECTION:
            return observation.projection_delta
        return 0.0

    @staticmethod
    def _alignment(
        observations: Tuple[GrowthObservation, ...],
    ) -> float:
        validations = sum(1 for o in observations if o.validation_received)
        threats = sum(1 for o in observations if o.threat_detected)
        total = len(observations)
        if total == 0:
            return 0.5
        diff = validations - threats
        return max(0.0, min(1.0, 0.5 + diff / (2.0 * total)))

    def _detect_signals(
        self,
        observations: Tuple[GrowthObservation, ...],
        vector: Optional[GrowthVector],
    ) -> Tuple[GrowthSignal, ...]:
        signals: list[GrowthSignal] = []
        cfg = self._config
        avg_novelty = mean(o.novelty_score for o in observations)
        avg_integration = mean(o.integration_load for o in observations)
        avg_efficiency = mean(o.efficiency_delta for o in observations)
        if avg_novelty <= cfg.information_hunger_novelty_max:
            signals.append(GrowthSignal.INFORMATION_HUNGER)
        if (
            vector is not None
            and vector.magnitude <= cfg.exploration_drive_magnitude_max
        ):
            signals.append(GrowthSignal.EXPLORATION_DRIVE)
        if avg_integration >= cfg.integration_pressure_load_min:
            signals.append(GrowthSignal.INTEGRATION_PRESSURE)
        if avg_efficiency >= cfg.efficiency_opportunity_min:
            signals.append(GrowthSignal.EFFICIENCY_OPPORTUNITY)
        if any(o.threat_detected for o in observations):
            signals.append(GrowthSignal.GROWTH_VECTOR_THREAT)
        if any(o.validation_received for o in observations):
            signals.append(GrowthSignal.GROWTH_VECTOR_VALIDATED)
        return tuple(signals)

    @staticmethod
    def _build_rationale(
        vector: Optional[GrowthVector],
        signals: Tuple[GrowthSignal, ...],
    ) -> str:
        if vector is None:
            vector_part = "vector=insufficient_data"
        else:
            vector_part = (
                f"vector={vector.direction.value} "
                f"(magnitude={vector.magnitude:.3f}, "
                f"coherence={vector.coherence:.3f}, "
                f"alignment={vector.alignment_with_substrate:.3f})"
            )
        signal_part = (
            ",".join(s.value for s in signals) if signals else "none"
        )
        return f"{vector_part}; signals=[{signal_part}]"

__all__ = [
    "DEFAULT_GROWTH_VECTOR_CONFIG",
    "GrowthMode",
    "GrowthObservation",
    "GrowthSignal",
    "GrowthVector",
    "GrowthVectorConfig",
    "GrowthVectorReport",
    "GrowthVectorTracker",
]
