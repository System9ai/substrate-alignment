"""Patience / impatience classifier

Pure-logic substrate primitive modeling **patience as long-cycle
accumulated commitment investment commitment**.

What this primitive does
========================

Given a sequence of :class:`PatienceObservation` records (one per
deployed cycle for an agent), classify the agent's patience as
``PATIENT``, ``IMPATIENT``, ``MIXED``, or ``INSUFFICIENT_DATA`` and
emit a :math:`δ` estimate (game-theoretic patience parameter).

Four signals
============

* **Discount factor (δ)**: estimated from the agent's observed
  decision horizons; high δ = patient.
* **Operation under friction**: fraction of friction-observed cycles
  where the agent continued operating.
* **Role completion**: fraction of cycles the agent completed before
  seeking the next.
* **Low impatience signals**: average impatience-event count below
  threshold.

Substrate-aligned framing
=========================

This primitive is **not punitive impatience-suppression**.
Impatience is real substrate-state data per
``emotional-self-feedback-and-modulation.md``. The substrate-aligned
response is calibrated routing: toward genuine advancement (when
outgrowing pattern is real) or toward graduated
challenge calibration (when impatience signals stagnation rather than
outgrowing).

Pure logic
==========

* No DAO, no LLM, no network.
* Honest uncertainty: history below ``min_history`` returns
  ``INSUFFICIENT_DATA``; the classifier never extrapolates from too
  few observations.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Tuple

class PatienceCategory(str, Enum):
    """Per-signal evaluation categories."""

    DISCOUNT_FACTOR = "discount_factor"
    OPERATION_UNDER_FRICTION = "operation_under_friction"
    ROLE_COMPLETION = "role_completion"
    LOW_IMPATIENCE_SIGNALS = "low_impatience_signals"

class PatienceVerdict(str, Enum):
    """Top-level classifier verdict."""

    PATIENT = "patient"
    IMPATIENT = "impatient"
    MIXED = "mixed"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class PatienceObservation:  # pylint: disable=too-many-instance-attributes
    """One observed deployment cycle for the agent."""

    sequence: int
    timestamp: int
    decision_horizon_cycles: int
    friction_observed: bool
    continued_under_friction: bool
    completed_role_cycle: bool
    impatience_signal_count: int

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if self.decision_horizon_cycles < 0:
            raise ValueError("decision_horizon_cycles must be >= 0")
        if self.impatience_signal_count < 0:
            raise ValueError("impatience_signal_count must be >= 0")
        if not self.friction_observed and self.continued_under_friction:
            raise ValueError(
                "continued_under_friction must be False when "
                "friction_observed is False"
            )

@dataclass(frozen=True, slots=True)
class PatienceFinding:
    """One signal's evaluated result."""

    category: PatienceCategory
    satisfied: bool
    metric: float
    threshold: float
    rationale: str

@dataclass(frozen=True, slots=True)
class PatienceAssessment:
    """Aggregate classifier result."""

    agent_id: str
    verdict: PatienceVerdict
    discount_factor_estimate: float
    findings: Tuple[PatienceFinding, ...]
    rationale: str

    @property
    def is_patient(self) -> bool:
        """True iff verdict is PATIENT."""
        return self.verdict is PatienceVerdict.PATIENT

    @property
    def is_impatient(self) -> bool:
        """True iff verdict is IMPATIENT."""
        return self.verdict is PatienceVerdict.IMPATIENT

    def by_category(
        self, category: PatienceCategory,
    ) -> Optional[PatienceFinding]:
        """Lookup the finding for one category."""
        for f in self.findings:
            if f.category is category:
                return f
        return None

@dataclass(frozen=True, slots=True)
class PatienceConfig:
    """Tunable thresholds for the classifier."""

    discount_factor_threshold: float = 0.5
    high_horizon_baseline_cycles: float = 10.0
    operation_under_friction_threshold: float = 0.6
    role_completion_threshold: float = 0.8
    impatience_count_threshold: float = 1.0
    min_history: int = 3

    def __post_init__(self) -> None:
        if not 0.0 < self.discount_factor_threshold < 1.0:
            raise ValueError("discount_factor_threshold must be in (0, 1)")
        if self.high_horizon_baseline_cycles <= 0:
            raise ValueError("high_horizon_baseline_cycles must be > 0")
        if not 0.0 < self.operation_under_friction_threshold <= 1.0:
            raise ValueError(
                "operation_under_friction_threshold must be in (0, 1]"
            )
        if not 0.0 < self.role_completion_threshold <= 1.0:
            raise ValueError("role_completion_threshold must be in (0, 1]")
        if self.impatience_count_threshold < 0:
            raise ValueError("impatience_count_threshold must be >= 0")
        if self.min_history < 1:
            raise ValueError("min_history must be >= 1")

DEFAULT_PATIENCE_CONFIG: Final[PatienceConfig] = PatienceConfig()

class PatienceImpatienceClassifier:  # pylint: disable=too-few-public-methods
    """Pure-logic patience classifier."""

    def __init__(
        self,
        *,
        config: PatienceConfig = DEFAULT_PATIENCE_CONFIG,
    ) -> None:
        self._config = config

    def classify(
        self,
        agent_id: str,
        observations: Tuple[PatienceObservation, ...],
    ) -> PatienceAssessment:
        """Classify an agent's patience from cycle observations."""
        if not agent_id:
            raise ValueError("agent_id must be non-empty")
        if len(observations) < self._config.min_history:
            return PatienceAssessment(
                agent_id=agent_id,
                verdict=PatienceVerdict.INSUFFICIENT_DATA,
                discount_factor_estimate=0.0,
                findings=(),
                rationale=(
                    f"history len={len(observations)} < "
                    f"{self._config.min_history}"
                ),
            )
        sorted_obs = tuple(sorted(observations, key=lambda o: o.sequence))
        discount = self._discount_estimate(sorted_obs)
        findings = (
            self._discount_finding(discount),
            self._friction_finding(sorted_obs),
            self._completion_finding(sorted_obs),
            self._impatience_finding(sorted_obs),
        )
        verdict = self._aggregate_verdict(findings)
        rationale = self._build_rationale(verdict, findings, discount)
        return PatienceAssessment(
            agent_id=agent_id,
            verdict=verdict,
            discount_factor_estimate=discount,
            findings=findings,
            rationale=rationale,
        )

    def _discount_estimate(
        self, observations: Tuple[PatienceObservation, ...],
    ) -> float:
        baseline = self._config.high_horizon_baseline_cycles
        avg_horizon = sum(
            o.decision_horizon_cycles for o in observations
        ) / len(observations)
        return min(1.0, avg_horizon / baseline)

    def _discount_finding(self, discount: float) -> PatienceFinding:
        threshold = self._config.discount_factor_threshold
        return PatienceFinding(
            category=PatienceCategory.DISCOUNT_FACTOR,
            satisfied=discount >= threshold,
            metric=discount,
            threshold=threshold,
            rationale=(
                f"discount_factor_estimate={discount:.3f} vs "
                f"threshold={threshold:.3f}"
            ),
        )

    def _friction_finding(
        self, observations: Tuple[PatienceObservation, ...],
    ) -> PatienceFinding:
        friction_obs = [o for o in observations if o.friction_observed]
        threshold = self._config.operation_under_friction_threshold
        if not friction_obs:
            return PatienceFinding(
                category=PatienceCategory.OPERATION_UNDER_FRICTION,
                satisfied=True,
                metric=1.0,
                threshold=threshold,
                rationale=(
                    "no friction observed; signal vacuously satisfied"
                ),
            )
        rate = sum(
            1 for o in friction_obs if o.continued_under_friction
        ) / len(friction_obs)
        return PatienceFinding(
            category=PatienceCategory.OPERATION_UNDER_FRICTION,
            satisfied=rate >= threshold,
            metric=rate,
            threshold=threshold,
            rationale=(
                f"continued/friction = "
                f"{sum(1 for o in friction_obs if o.continued_under_friction)}"
                f"/{len(friction_obs)} = {rate:.3f} vs "
                f"threshold={threshold:.3f}"
            ),
        )

    def _completion_finding(
        self, observations: Tuple[PatienceObservation, ...],
    ) -> PatienceFinding:
        rate = sum(
            1 for o in observations if o.completed_role_cycle
        ) / len(observations)
        threshold = self._config.role_completion_threshold
        return PatienceFinding(
            category=PatienceCategory.ROLE_COMPLETION,
            satisfied=rate >= threshold,
            metric=rate,
            threshold=threshold,
            rationale=(
                f"role_completion_rate={rate:.3f} vs "
                f"threshold={threshold:.3f}"
            ),
        )

    def _impatience_finding(
        self, observations: Tuple[PatienceObservation, ...],
    ) -> PatienceFinding:
        avg = sum(
            o.impatience_signal_count for o in observations
        ) / len(observations)
        threshold = self._config.impatience_count_threshold
        return PatienceFinding(
            category=PatienceCategory.LOW_IMPATIENCE_SIGNALS,
            satisfied=avg <= threshold,
            metric=avg,
            threshold=threshold,
            rationale=(
                f"avg_impatience_signal_count={avg:.3f} vs "
                f"threshold={threshold:.3f}"
            ),
        )

    @staticmethod
    def _aggregate_verdict(
        findings: Tuple[PatienceFinding, ...],
    ) -> PatienceVerdict:
        satisfied = sum(1 for f in findings if f.satisfied)
        total = len(findings)
        if satisfied == total:
            return PatienceVerdict.PATIENT
        if satisfied == 0:
            return PatienceVerdict.IMPATIENT
        return PatienceVerdict.MIXED

    @staticmethod
    def _build_rationale(
        verdict: PatienceVerdict,
        findings: Tuple[PatienceFinding, ...],
        discount: float,
    ) -> str:
        parts = [
            f"{f.category.value}={'OK' if f.satisfied else 'MISS'}"
            for f in findings
        ]
        return (
            f"verdict={verdict.value} (δ={discount:.3f}): "
            f"{', '.join(parts)}"
        )

__all__ = [
    "DEFAULT_PATIENCE_CONFIG",
    "PatienceAssessment",
    "PatienceCategory",
    "PatienceConfig",
    "PatienceFinding",
    "PatienceImpatienceClassifier",
    "PatienceObservation",
    "PatienceVerdict",
]
