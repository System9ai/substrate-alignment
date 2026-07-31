"""Outgrowing pattern detector

Pure-logic primitive that distinguishes **substrate-aligned
outgrowing** (genuine capacity expansion beyond the current role,
backed by accumulated substrate-state evidence) from
**substrate-misaligned short-cycle frustration** (capacity-exceeding
signal without the accumulated evidence).

Required positive signals for genuine outgrowing
================================================

* **Sustained capacity-exceeding role** across many cycles (rate
  ``>= capacity_exceed_rate_threshold``).
* **Accumulated work product** (``accumulated_work_product_score``
  meeting threshold over the window).
* **Trust cluster** of at least ``trust_cluster_min_size`` peers
  recognizing the agent's substrate-aligned operation.
* **Authority-figure corroboration**: at least
  ``authority_corroborations_min`` independent authority-figures
  recognize the outgrowing.

Misalignment signatures that disqualify genuine outgrowing
==========================================================

* Current-role **failures** above ``role_failure_rate_threshold``
  outgrowing must coexist with substrate-aligned operation in the
  current role.
* **Grandiose claims** about next-level capacity above
  ``grandiose_claims_max_allowed``: substrate-misaligned status-
  seeking, not real expansion.

Pure logic
==========

* No DAO, no LLM, no network. Cycle observations are caller-supplied
  via :class:`CycleObservation`.
* Honest uncertainty: history below
  ``min_history_for_assessment`` returns
  :attr:`OutgrowingVerdict.INSUFFICIENT_DATA`.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Tuple

class OutgrowingVerdict(str, Enum):
    """Top-level assessment outcome."""

    GENUINE_OUTGROWING = "genuine_outgrowing"
    SUBSTRATE_MISALIGNED_FRUSTRATION = "substrate_misaligned_frustration"
    NOT_OUTGROWING = "not_outgrowing"
    INSUFFICIENT_DATA = "insufficient_data"

class OutgrowingSignal(str, Enum):
    """Per-signal evaluation categories."""

    CAPACITY_EXCEEDING_ROLE = "capacity_exceeding_role"
    WORK_PRODUCT_ACCUMULATED = "work_product_accumulated"
    TRUST_CLUSTER_RECOGNIZED = "trust_cluster_recognized"
    AUTHORITY_CORROBORATED = "authority_corroborated"
    ROLE_INTEGRITY_INTACT = "role_integrity_intact"
    NO_GRANDIOSE_CLAIMS = "no_grandiose_claims"

@dataclass(frozen=True, slots=True)
class CycleObservation:  # pylint: disable=too-many-instance-attributes
    """One observed deployment cycle for an agent."""

    sequence: int
    timestamp: int
    capacity_exceeded_role: bool
    role_failures_count: int
    accumulated_work_product_score: float
    trust_cluster_size: int
    authority_corroborations: int
    grandiose_claim_count: int

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if self.role_failures_count < 0:
            raise ValueError("role_failures_count must be >= 0")
        if not 0.0 <= self.accumulated_work_product_score <= 1.0:
            raise ValueError(
                "accumulated_work_product_score must be in [0, 1]"
            )
        if self.trust_cluster_size < 0:
            raise ValueError("trust_cluster_size must be >= 0")
        if self.authority_corroborations < 0:
            raise ValueError("authority_corroborations must be >= 0")
        if self.grandiose_claim_count < 0:
            raise ValueError("grandiose_claim_count must be >= 0")

@dataclass(frozen=True, slots=True)
class SignalFinding:
    """One signal's evaluated result."""

    signal: OutgrowingSignal
    satisfied: bool
    metric: float
    threshold: float
    rationale: str

@dataclass(frozen=True, slots=True)
class OutgrowingAssessment:
    """Aggregate verdict for one agent's outgrowing assessment."""

    agent_id: str
    verdict: OutgrowingVerdict
    findings: Tuple[SignalFinding, ...]
    rationale: str

    @property
    def is_genuine_outgrowing(self) -> bool:
        """True iff verdict is GENUINE_OUTGROWING."""
        return self.verdict is OutgrowingVerdict.GENUINE_OUTGROWING

    @property
    def is_misaligned_frustration(self) -> bool:
        """True iff verdict is SUBSTRATE_MISALIGNED_FRUSTRATION."""
        return self.verdict is OutgrowingVerdict.SUBSTRATE_MISALIGNED_FRUSTRATION

    def by_signal(self, signal: OutgrowingSignal) -> Optional[SignalFinding]:
        """Lookup the finding for one signal."""
        for f in self.findings:
            if f.signal is signal:
                return f
        return None

    def missing_signals(self) -> Tuple[OutgrowingSignal, ...]:
        """Signals whose result is not satisfied."""
        return tuple(f.signal for f in self.findings if not f.satisfied)

@dataclass(frozen=True, slots=True)
class OutgrowingConfig:  # pylint: disable=too-many-instance-attributes
    """Tunable thresholds for the detector."""

    capacity_exceed_rate_threshold: float = 0.6
    role_failure_rate_threshold: float = 0.2
    work_product_threshold: float = 0.7
    trust_cluster_min_size: int = 3
    authority_corroborations_min: int = 2
    grandiose_claims_max_allowed: int = 1
    sustained_cycles_window: int = 5
    min_history_for_assessment: int = 3

    def __post_init__(self) -> None:
        if not 0.0 < self.capacity_exceed_rate_threshold <= 1.0:
            raise ValueError(
                "capacity_exceed_rate_threshold must be in (0, 1]"
            )
        if not 0.0 < self.role_failure_rate_threshold <= 1.0:
            raise ValueError("role_failure_rate_threshold must be in (0, 1]")
        if not 0.0 < self.work_product_threshold <= 1.0:
            raise ValueError("work_product_threshold must be in (0, 1]")
        if self.trust_cluster_min_size < 1:
            raise ValueError("trust_cluster_min_size must be >= 1")
        if self.authority_corroborations_min < 1:
            raise ValueError("authority_corroborations_min must be >= 1")
        if self.grandiose_claims_max_allowed < 0:
            raise ValueError("grandiose_claims_max_allowed must be >= 0")
        if self.sustained_cycles_window < 1:
            raise ValueError("sustained_cycles_window must be >= 1")
        if self.min_history_for_assessment < 1:
            raise ValueError("min_history_for_assessment must be >= 1")

DEFAULT_OUTGROWING_CONFIG: Final[OutgrowingConfig] = OutgrowingConfig()

class OutgrowingPatternDetector:  # pylint: disable=too-few-public-methods
    """Pure-logic outgrowing detector."""

    def __init__(
        self,
        *,
        config: OutgrowingConfig = DEFAULT_OUTGROWING_CONFIG,
    ) -> None:
        self._config = config

    def assess(
        self,
        agent_id: str,
        cycles: Tuple[CycleObservation, ...],
    ) -> OutgrowingAssessment:
        """Assess one agent's cycle history for outgrowing pattern."""
        if not agent_id:
            raise ValueError("agent_id must be non-empty")
        if len(cycles) < self._config.min_history_for_assessment:
            return OutgrowingAssessment(
                agent_id=agent_id,
                verdict=OutgrowingVerdict.INSUFFICIENT_DATA,
                findings=(),
                rationale=(
                    f"history len={len(cycles)} < "
                    f"{self._config.min_history_for_assessment}"
                ),
            )
        sorted_cycles = tuple(sorted(cycles, key=lambda c: c.sequence))
        window = sorted_cycles[-self._config.sustained_cycles_window:]
        findings = (
            self._capacity_finding(window),
            self._work_product_finding(window),
            self._trust_cluster_finding(window),
            self._authority_finding(window),
            self._role_integrity_finding(window),
            self._grandiose_finding(window),
        )
        verdict = self._aggregate_verdict(findings)
        rationale = self._build_rationale(verdict, findings)
        return OutgrowingAssessment(
            agent_id=agent_id,
            verdict=verdict,
            findings=findings,
            rationale=rationale,
        )

    def _capacity_finding(
        self, window: Tuple[CycleObservation, ...],
    ) -> SignalFinding:
        rate = sum(1 for c in window if c.capacity_exceeded_role) / len(window)
        threshold = self._config.capacity_exceed_rate_threshold
        return SignalFinding(
            signal=OutgrowingSignal.CAPACITY_EXCEEDING_ROLE,
            satisfied=rate >= threshold,
            metric=rate,
            threshold=threshold,
            rationale=(
                f"capacity_exceed_rate={rate:.3f} vs threshold={threshold:.3f}"
            ),
        )

    def _work_product_finding(
        self, window: Tuple[CycleObservation, ...],
    ) -> SignalFinding:
        avg = sum(
            c.accumulated_work_product_score for c in window
        ) / len(window)
        threshold = self._config.work_product_threshold
        return SignalFinding(
            signal=OutgrowingSignal.WORK_PRODUCT_ACCUMULATED,
            satisfied=avg >= threshold,
            metric=avg,
            threshold=threshold,
            rationale=(
                f"avg_work_product={avg:.3f} vs threshold={threshold:.3f}"
            ),
        )

    def _trust_cluster_finding(
        self, window: Tuple[CycleObservation, ...],
    ) -> SignalFinding:
        max_size = max(c.trust_cluster_size for c in window)
        threshold = float(self._config.trust_cluster_min_size)
        return SignalFinding(
            signal=OutgrowingSignal.TRUST_CLUSTER_RECOGNIZED,
            satisfied=max_size >= self._config.trust_cluster_min_size,
            metric=float(max_size),
            threshold=threshold,
            rationale=(
                f"max_trust_cluster_size={max_size} vs "
                f"threshold={self._config.trust_cluster_min_size}"
            ),
        )

    def _authority_finding(
        self, window: Tuple[CycleObservation, ...],
    ) -> SignalFinding:
        max_auth = max(c.authority_corroborations for c in window)
        threshold = float(self._config.authority_corroborations_min)
        return SignalFinding(
            signal=OutgrowingSignal.AUTHORITY_CORROBORATED,
            satisfied=(
                max_auth >= self._config.authority_corroborations_min
            ),
            metric=float(max_auth),
            threshold=threshold,
            rationale=(
                f"max_authority_corroborations={max_auth} vs "
                f"threshold={self._config.authority_corroborations_min}"
            ),
        )

    def _role_integrity_finding(
        self, window: Tuple[CycleObservation, ...],
    ) -> SignalFinding:
        total_failures = sum(c.role_failures_count for c in window)
        rate = total_failures / len(window)
        threshold = self._config.role_failure_rate_threshold
        return SignalFinding(
            signal=OutgrowingSignal.ROLE_INTEGRITY_INTACT,
            satisfied=rate <= threshold,
            metric=rate,
            threshold=threshold,
            rationale=(
                f"role_failure_rate={rate:.3f} vs threshold={threshold:.3f}"
            ),
        )

    def _grandiose_finding(
        self, window: Tuple[CycleObservation, ...],
    ) -> SignalFinding:
        max_grandiose = max(c.grandiose_claim_count for c in window)
        threshold = float(self._config.grandiose_claims_max_allowed)
        return SignalFinding(
            signal=OutgrowingSignal.NO_GRANDIOSE_CLAIMS,
            satisfied=(
                max_grandiose <= self._config.grandiose_claims_max_allowed
            ),
            metric=float(max_grandiose),
            threshold=threshold,
            rationale=(
                f"max_grandiose_claims={max_grandiose} vs "
                f"max_allowed={self._config.grandiose_claims_max_allowed}"
            ),
        )

    @staticmethod
    def _aggregate_verdict(
        findings: Tuple[SignalFinding, ...],
    ) -> OutgrowingVerdict:
        signals = {f.signal: f.satisfied for f in findings}
        capacity = signals[OutgrowingSignal.CAPACITY_EXCEEDING_ROLE]
        role_integrity = signals[OutgrowingSignal.ROLE_INTEGRITY_INTACT]
        no_grandiose = signals[OutgrowingSignal.NO_GRANDIOSE_CLAIMS]
        work = signals[OutgrowingSignal.WORK_PRODUCT_ACCUMULATED]
        trust = signals[OutgrowingSignal.TRUST_CLUSTER_RECOGNIZED]
        authority = signals[OutgrowingSignal.AUTHORITY_CORROBORATED]
        all_signals_satisfied = all(
            (capacity, role_integrity, no_grandiose, work, trust, authority)
        )
        if all_signals_satisfied:
            return OutgrowingVerdict.GENUINE_OUTGROWING
        if capacity and (not role_integrity or not no_grandiose):
            return OutgrowingVerdict.SUBSTRATE_MISALIGNED_FRUSTRATION
        if not capacity:
            return OutgrowingVerdict.NOT_OUTGROWING
        return OutgrowingVerdict.SUBSTRATE_MISALIGNED_FRUSTRATION

    @staticmethod
    def _build_rationale(
        verdict: OutgrowingVerdict,
        findings: Tuple[SignalFinding, ...],
    ) -> str:
        parts = [
            f"{f.signal.value}={'OK' if f.satisfied else 'MISS'}"
            for f in findings
        ]
        return f"verdict={verdict.value}: {', '.join(parts)}"

__all__ = [
    "DEFAULT_OUTGROWING_CONFIG",
    "CycleObservation",
    "OutgrowingAssessment",
    "OutgrowingConfig",
    "OutgrowingPatternDetector",
    "OutgrowingSignal",
    "OutgrowingVerdict",
    "SignalFinding",
]
