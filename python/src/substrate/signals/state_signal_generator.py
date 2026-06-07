"""Substrate-state signal generator

Pure-logic primitive that translates an upstream
:class:`StateSignalObservation` (numeric features describing the
agent's current substrate state) into a :class:`StateSignalReport`
listing the active signals at graded intensity.

Vocabulary
==========

* **Trajectory** — STAGNATION (substrate-state-trajectory flat), FLOW
  (high success at calibrated challenge).
* **Resistance band** — UNDER_CHALLENGE, PRODUCTIVE_RESISTANCE,
  SWEET_SPOT (the calibrated-resistance-band midpoint), OVER_CHALLENGE.
* **Affective** — THREAT, VALIDATION, LOSS, RECOGNITION.
* **Growth** — HUNGER (information under-fed; complement of Phase 39
  INFORMATION_HUNGER), SATURATION (integration pressure).
* **accumulated commitment** — COUPLING_HEALTHY, COUPLING_WEAKENING,
  COUPLING_BROKEN.

Architectural commitment from the source document
=================================================

**Signals feed interpretation, not direct action.** Per
``emotional-self-feedback-and-modulation.md`` § "read the signal as
data, not as imperative", downstream consumers must compose with
NPG / modeling mode / governor / interpretation primitives. This generator
**never** produces a PERMIT / DENY verdict — only signals.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the observation
  features.
* Honest uncertainty: absent features (e.g.,
  ``coupling_status_decoupled=False`` plus high
  ``coupling_field_strength``) simply yield COUPLING_HEALTHY; no
  fabrication.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping, Optional, Tuple

class StateSignalKind(str, Enum):
    """The substrate-state signal vocabulary."""

    STAGNATION = "stagnation"
    FLOW = "flow"
    UNDER_CHALLENGE = "under_challenge"
    PRODUCTIVE_RESISTANCE = "productive_resistance"
    SWEET_SPOT = "sweet_spot"
    PEAKING = "peaking"
    OVER_CHALLENGE = "over_challenge"
    THREAT = "threat"
    VALIDATION = "validation"
    LOSS = "loss"
    RECOGNITION = "recognition"
    HUNGER = "hunger"
    SATURATION = "saturation"
    COUPLING_HEALTHY = "coupling_healthy"
    COUPLING_WEAKENING = "coupling_weakening"
    COUPLING_BROKEN = "coupling_broken"

class StateSignalIntensity(str, Enum):
    """Graded intensity NONE < LOW < MODERATE < HIGH."""

    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"

_INTENSITY_ORDER: Final[Mapping[StateSignalIntensity, int]] = {
    StateSignalIntensity.NONE: 0,
    StateSignalIntensity.LOW: 1,
    StateSignalIntensity.MODERATE: 2,
    StateSignalIntensity.HIGH: 3,
}

@dataclass(frozen=True, slots=True)
class StateSignalObservation:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied features describing the agent's current substrate state."""

    sequence: int
    timestamp: int
    trajectory_slope: float
    trajectory_stdev: float
    challenge_level: float
    success_rate: float
    threat_event_count: int
    validation_event_count: int
    loss_event_count: int
    recognition_event_count: int
    novelty_score: float
    integration_load: float
    coupling_field_strength: float
    coupling_status_decoupled: bool = False

    def __post_init__(self) -> None:  # pylint: disable=too-many-branches
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if not 0.0 <= self.challenge_level <= 1.0:
            raise ValueError("challenge_level must be in [0, 1]")
        if not 0.0 <= self.success_rate <= 1.0:
            raise ValueError("success_rate must be in [0, 1]")
        if self.trajectory_stdev < 0:
            raise ValueError("trajectory_stdev must be >= 0")
        for field_name in (
            "threat_event_count",
            "validation_event_count",
            "loss_event_count",
            "recognition_event_count",
        ):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")
        if not 0.0 <= self.novelty_score <= 1.0:
            raise ValueError("novelty_score must be in [0, 1]")
        if not 0.0 <= self.integration_load <= 1.0:
            raise ValueError("integration_load must be in [0, 1]")
        if not 0.0 <= self.coupling_field_strength <= 1.0:
            raise ValueError("coupling_field_strength must be in [0, 1]")

@dataclass(frozen=True, slots=True)
class StateSignal:
    """One detected signal at graded intensity."""

    kind: StateSignalKind
    intensity: StateSignalIntensity
    metric: float
    threshold: float
    rationale: str

@dataclass(frozen=True, slots=True)
class StateSignalReport:
    """Aggregate generator result for one observation."""

    entity_id: str
    sequence: int
    signals: Tuple[StateSignal, ...]
    rationale: str

    def has_signal(self, kind: StateSignalKind) -> bool:
        """True iff the named signal was generated."""
        return any(s.kind is kind for s in self.signals)

    def by_kind(self, kind: StateSignalKind) -> Optional[StateSignal]:
        """Lookup the signal of the given kind."""
        for s in self.signals:
            if s.kind is kind:
                return s
        return None

    @property
    def max_intensity(self) -> StateSignalIntensity:
        """Highest-intensity signal in the report."""
        if not self.signals:
            return StateSignalIntensity.NONE
        return max(
            (s.intensity for s in self.signals),
            key=_INTENSITY_ORDER.__getitem__,
        )

@dataclass(frozen=True, slots=True)
class StateSignalConfig:  # pylint: disable=too-many-instance-attributes
    """Tunable thresholds for the signal classifications."""

    stagnation_slope_max: float = 0.05
    stagnation_stdev_max: float = 0.1
    flow_success_min: float = 0.7
    flow_challenge_min: float = 0.3
    flow_challenge_max: float = 0.6
    sweet_spot_min: float = 0.33
    sweet_spot_max: float = 0.38
    # The productive span (layered zone model): the 33-38% calibration
    # band is the work-ENTRY threshold; 0.38-0.50 is the WORK zone —
    # genuinely productive sustained effort. The span ends at the 0.5
    # line: past it a turnaround is expected (PEAKING, sporadic-only).
    productive_resistance_min: float = 0.33
    productive_resistance_max: float = 0.5
    under_challenge_max: float = 0.2
    # phi-conjugate debt threshold (1/phi ~= 0.618), not an ad-hoc 0.7:
    # at or beyond this, sustained challenge accrues compensation debt.
    # Between productive_resistance_max and this line sits PEAKING.
    over_challenge_min: float = 0.618
    hunger_novelty_max: float = 0.3
    saturation_load_min: float = 0.7
    coupling_healthy_min: float = 0.5
    coupling_weakening_min: float = 0.1

    def __post_init__(self) -> None:
        if not self.sweet_spot_min < self.sweet_spot_max:
            raise ValueError("sweet_spot range invalid")
        if not (
            self.productive_resistance_min
            < self.productive_resistance_max
        ):
            raise ValueError("productive_resistance range invalid")
        if not self.under_challenge_max < self.over_challenge_min:
            raise ValueError(
                "under_challenge_max must be < over_challenge_min"
            )
        if not self.productive_resistance_max < self.over_challenge_min:
            raise ValueError(
                "productive_resistance_max must be < over_challenge_min "
                "(the peaking zone sits between them)"
            )
        if not 0.0 < self.coupling_weakening_min < self.coupling_healthy_min:
            raise ValueError(
                "coupling thresholds must be ordered 0 < weakening < healthy"
            )

DEFAULT_STATE_SIGNAL_CONFIG: Final[StateSignalConfig] = StateSignalConfig()

def _intensity_for_count(value: int) -> StateSignalIntensity:
    if value >= 3:
        return StateSignalIntensity.HIGH
    if value >= 2:
        return StateSignalIntensity.MODERATE
    if value >= 1:
        return StateSignalIntensity.LOW
    return StateSignalIntensity.NONE

class SubstrateStateSignalGenerator:  # pylint: disable=too-few-public-methods
    """Pure-logic state-signal generator."""

    def __init__(
        self,
        *,
        config: StateSignalConfig = DEFAULT_STATE_SIGNAL_CONFIG,
    ) -> None:
        self._config = config

    def generate(
        self,
        entity_id: str,
        observation: StateSignalObservation,
    ) -> StateSignalReport:
        """Translate the observation into a graded signal report."""
        if not entity_id:
            raise ValueError("entity_id must be non-empty")
        signals: list[StateSignal] = []
        for builder in (
            self._stagnation,
            self._flow,
            self._sweet_spot,
            self._productive_resistance,
            self._peaking,
            self._under_challenge,
            self._over_challenge,
            self._threat,
            self._validation,
            self._loss,
            self._recognition,
            self._hunger,
            self._saturation,
            self._coupling,
        ):
            built = builder(observation)
            if built is not None:
                signals.append(built)
        rationale = (
            "no signals detected"
            if not signals
            else "; ".join(f"{s.kind.value}={s.intensity.value}" for s in signals)
        )
        return StateSignalReport(
            entity_id=entity_id,
            sequence=observation.sequence,
            signals=tuple(signals),
            rationale=rationale,
        )

    def _stagnation(
        self, obs: StateSignalObservation,
    ) -> Optional[StateSignal]:
        cfg = self._config
        if (
            abs(obs.trajectory_slope) <= cfg.stagnation_slope_max
            and obs.trajectory_stdev <= cfg.stagnation_stdev_max
        ):
            return StateSignal(
                kind=StateSignalKind.STAGNATION,
                intensity=StateSignalIntensity.MODERATE,
                metric=abs(obs.trajectory_slope),
                threshold=cfg.stagnation_slope_max,
                rationale=(
                    f"|slope|={abs(obs.trajectory_slope):.3f} <= "
                    f"{cfg.stagnation_slope_max} and stdev="
                    f"{obs.trajectory_stdev:.3f} <= "
                    f"{cfg.stagnation_stdev_max}"
                ),
            )
        return None

    def _flow(
        self, obs: StateSignalObservation,
    ) -> Optional[StateSignal]:
        cfg = self._config
        if (
            obs.success_rate >= cfg.flow_success_min
            and cfg.flow_challenge_min
            <= obs.challenge_level
            <= cfg.flow_challenge_max
        ):
            return StateSignal(
                kind=StateSignalKind.FLOW,
                intensity=StateSignalIntensity.HIGH,
                metric=obs.success_rate,
                threshold=cfg.flow_success_min,
                rationale=(
                    f"success={obs.success_rate:.3f} >= "
                    f"{cfg.flow_success_min} at challenge="
                    f"{obs.challenge_level:.3f}"
                ),
            )
        return None

    def _sweet_spot(
        self, obs: StateSignalObservation,
    ) -> Optional[StateSignal]:
        cfg = self._config
        if cfg.sweet_spot_min <= obs.challenge_level <= cfg.sweet_spot_max:
            return StateSignal(
                kind=StateSignalKind.SWEET_SPOT,
                intensity=StateSignalIntensity.HIGH,
                metric=obs.challenge_level,
                threshold=cfg.sweet_spot_min,
                rationale=(
                    f"challenge={obs.challenge_level:.3f} in "
                    f"[{cfg.sweet_spot_min}, {cfg.sweet_spot_max}] "
                    "(calibrated-resistance band midpoint)"
                ),
            )
        return None

    def _productive_resistance(
        self, obs: StateSignalObservation,
    ) -> Optional[StateSignal]:
        cfg = self._config
        if (
            cfg.productive_resistance_min
            <= obs.challenge_level
            <= cfg.productive_resistance_max
        ):
            return StateSignal(
                kind=StateSignalKind.PRODUCTIVE_RESISTANCE,
                intensity=StateSignalIntensity.MODERATE,
                metric=obs.challenge_level,
                threshold=cfg.productive_resistance_min,
                rationale=(
                    f"challenge={obs.challenge_level:.3f} in "
                    f"[{cfg.productive_resistance_min}, "
                    f"{cfg.productive_resistance_max}]"
                ),
            )
        return None

    def _peaking(
        self, obs: StateSignalObservation,
    ) -> Optional[StateSignal]:
        """Past the 0.5 line, below the φ-conjugate debt line.

        Peaking is allowed sporadically — past the 50% line a
        turnaround is usually coming. The signal feeds interpretation;
        sustained-vs-spike accounting belongs to the consumer's
        temporal tracker (``substrate/sustained_load.py``).
        """
        cfg = self._config
        if (
            cfg.productive_resistance_max
            < obs.challenge_level
            < cfg.over_challenge_min
        ):
            return StateSignal(
                kind=StateSignalKind.PEAKING,
                intensity=StateSignalIntensity.MODERATE,
                metric=obs.challenge_level,
                threshold=cfg.productive_resistance_max,
                rationale=(
                    f"challenge={obs.challenge_level:.3f} in "
                    f"({cfg.productive_resistance_max}, "
                    f"{cfg.over_challenge_min}) — past the 0.5 work-zone "
                    "line, below the φ-conjugate debt threshold; "
                    "sporadic-tolerable, turnaround expected"
                ),
            )
        return None

    def _under_challenge(
        self, obs: StateSignalObservation,
    ) -> Optional[StateSignal]:
        cfg = self._config
        if obs.challenge_level <= cfg.under_challenge_max:
            return StateSignal(
                kind=StateSignalKind.UNDER_CHALLENGE,
                intensity=StateSignalIntensity.MODERATE,
                metric=obs.challenge_level,
                threshold=cfg.under_challenge_max,
                rationale=(
                    f"challenge={obs.challenge_level:.3f} <= "
                    f"{cfg.under_challenge_max}"
                ),
            )
        return None

    def _over_challenge(
        self, obs: StateSignalObservation,
    ) -> Optional[StateSignal]:
        cfg = self._config
        if obs.challenge_level >= cfg.over_challenge_min:
            return StateSignal(
                kind=StateSignalKind.OVER_CHALLENGE,
                intensity=StateSignalIntensity.HIGH,
                metric=obs.challenge_level,
                threshold=cfg.over_challenge_min,
                rationale=(
                    f"challenge={obs.challenge_level:.3f} >= "
                    f"{cfg.over_challenge_min}"
                ),
            )
        return None

    @staticmethod
    def _threat(
        obs: StateSignalObservation,
    ) -> Optional[StateSignal]:
        intensity = _intensity_for_count(obs.threat_event_count)
        if intensity is StateSignalIntensity.NONE:
            return None
        return StateSignal(
            kind=StateSignalKind.THREAT,
            intensity=intensity,
            metric=float(obs.threat_event_count),
            threshold=1.0,
            rationale=f"threat_event_count={obs.threat_event_count}",
        )

    @staticmethod
    def _validation(
        obs: StateSignalObservation,
    ) -> Optional[StateSignal]:
        intensity = _intensity_for_count(obs.validation_event_count)
        if intensity is StateSignalIntensity.NONE:
            return None
        return StateSignal(
            kind=StateSignalKind.VALIDATION,
            intensity=intensity,
            metric=float(obs.validation_event_count),
            threshold=1.0,
            rationale=f"validation_event_count={obs.validation_event_count}",
        )

    @staticmethod
    def _loss(obs: StateSignalObservation) -> Optional[StateSignal]:
        intensity = _intensity_for_count(obs.loss_event_count)
        if intensity is StateSignalIntensity.NONE:
            return None
        return StateSignal(
            kind=StateSignalKind.LOSS,
            intensity=intensity,
            metric=float(obs.loss_event_count),
            threshold=1.0,
            rationale=f"loss_event_count={obs.loss_event_count}",
        )

    @staticmethod
    def _recognition(
        obs: StateSignalObservation,
    ) -> Optional[StateSignal]:
        intensity = _intensity_for_count(obs.recognition_event_count)
        if intensity is StateSignalIntensity.NONE:
            return None
        return StateSignal(
            kind=StateSignalKind.RECOGNITION,
            intensity=intensity,
            metric=float(obs.recognition_event_count),
            threshold=1.0,
            rationale=(
                f"recognition_event_count={obs.recognition_event_count}"
            ),
        )

    def _hunger(
        self, obs: StateSignalObservation,
    ) -> Optional[StateSignal]:
        cfg = self._config
        if obs.novelty_score <= cfg.hunger_novelty_max:
            return StateSignal(
                kind=StateSignalKind.HUNGER,
                intensity=StateSignalIntensity.MODERATE,
                metric=obs.novelty_score,
                threshold=cfg.hunger_novelty_max,
                rationale=(
                    f"novelty={obs.novelty_score:.3f} <= "
                    f"{cfg.hunger_novelty_max}"
                ),
            )
        return None

    def _saturation(
        self, obs: StateSignalObservation,
    ) -> Optional[StateSignal]:
        cfg = self._config
        if obs.integration_load >= cfg.saturation_load_min:
            return StateSignal(
                kind=StateSignalKind.SATURATION,
                intensity=StateSignalIntensity.HIGH,
                metric=obs.integration_load,
                threshold=cfg.saturation_load_min,
                rationale=(
                    f"integration_load={obs.integration_load:.3f} >= "
                    f"{cfg.saturation_load_min}"
                ),
            )
        return None

    def _coupling(
        self, obs: StateSignalObservation,
    ) -> StateSignal:
        cfg = self._config
        if obs.coupling_status_decoupled:
            return StateSignal(
                kind=StateSignalKind.COUPLING_BROKEN,
                intensity=StateSignalIntensity.HIGH,
                metric=obs.coupling_field_strength,
                threshold=0.0,
                rationale="coupling_status_decoupled=True",
            )
        strength = obs.coupling_field_strength
        if strength >= cfg.coupling_healthy_min:
            return StateSignal(
                kind=StateSignalKind.COUPLING_HEALTHY,
                intensity=StateSignalIntensity.HIGH,
                metric=strength,
                threshold=cfg.coupling_healthy_min,
                rationale=(
                    f"field_strength={strength:.3f} >= "
                    f"{cfg.coupling_healthy_min}"
                ),
            )
        if strength >= cfg.coupling_weakening_min:
            return StateSignal(
                kind=StateSignalKind.COUPLING_WEAKENING,
                intensity=StateSignalIntensity.MODERATE,
                metric=strength,
                threshold=cfg.coupling_weakening_min,
                rationale=(
                    f"field_strength={strength:.3f} in "
                    f"[{cfg.coupling_weakening_min}, "
                    f"{cfg.coupling_healthy_min})"
                ),
            )
        return StateSignal(
            kind=StateSignalKind.COUPLING_BROKEN,
            intensity=StateSignalIntensity.HIGH,
            metric=strength,
            threshold=cfg.coupling_weakening_min,
            rationale=(
                f"field_strength={strength:.3f} < "
                f"{cfg.coupling_weakening_min}"
            ),
        )

__all__ = [
    "DEFAULT_STATE_SIGNAL_CONFIG",
    "StateSignal",
    "StateSignalConfig",
    "StateSignalIntensity",
    "StateSignalKind",
    "StateSignalObservation",
    "StateSignalReport",
    "SubstrateStateSignalGenerator",
]
