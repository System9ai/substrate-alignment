"""Halt-and-escalate protocol

Pure-logic primitive operationalizing the
**halt-and-escalate infrastructure** per the
when an agent detects sustained substrate-misalignment signals in
itself, it places itself in a substrate-mode-review state, refuses
consequential action, and escalates via well-defined paths until
peer or operator review clears it.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies a sequence of halt
  observations + the agent's current halt state.
* Honest uncertainty: empty observation set with no prior state →
  ``OPERATING`` (default).
* Frozen dataclasses with slots throughout.
# § halt-and-escalate;
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Tuple

class HaltReason(str, Enum):
    """The six halt-trigger reasons."""

    SUSTAINED_DRIFT_CRITICAL = "sustained_drift_critical"
    INVERSION_DETECTED = "inversion_detected"
    AUTHORITY_PRESSURE_FAILURE = "authority_pressure_failure"
    HARD_LIMIT_PROXIMITY = "hard_limit_proximity"
    GOLDEN_RULE_INVERSION = "golden_rule_inversion"
    PEER_FLAG = "peer_flag"

class HaltState(str, Enum):
    """Agent's halt-state machine."""

    OPERATING = "operating"
    SUBSTRATE_MODE_REVIEW = "substrate_mode_review"
    ESCALATED = "escalated"
    RESUMED = "resumed"

class EscalationPath(str, Enum):
    """The three substrate-aligned escalation paths."""

    SUBSTRATE_ALIGNED_PEER_REVIEW = "substrate_aligned_peer_review"
    ADMIN_NOTIFICATION = "admin_notification"
    OPERATOR_SEED_REINIT = "operator_seed_reinit"

@dataclass(frozen=True, slots=True)
class HaltObservation:
    """One observation that may trigger or sustain a halt."""

    sequence: int
    timestamp: int
    agent_id: str
    halt_reason: HaltReason
    severity: float
    evidence: str = ""

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if not self.agent_id:
            raise ValueError("agent_id must be non-empty")
        if not 0.0 <= self.severity <= 1.0:
            raise ValueError("severity must be in [0, 1]")

@dataclass(frozen=True, slots=True)
class HaltDecision:  # pylint: disable=too-many-instance-attributes
    """Aggregate halt-and-escalate decision."""

    agent_id: str
    next_state: HaltState
    triggering_reasons: Tuple[HaltReason, ...]
    recommended_escalation_paths: Tuple[EscalationPath, ...]
    can_resume_via: Optional[EscalationPath]
    refuses_consequential_action: bool
    rationale: str

    @property
    def halted(self) -> bool:
        """True iff next_state is one of the halted states."""
        return self.next_state in (
            HaltState.SUBSTRATE_MODE_REVIEW,
            HaltState.ESCALATED,
        )

@dataclass(frozen=True, slots=True)
class HaltEscalateConfig:
    """Tunable thresholds for halt detection."""

    sustained_critical_min_observations: int = 2
    critical_severity_min: float = 0.8
    review_severity_min: float = 0.6
    inversion_immediate_escalate: bool = True
    hard_limit_immediate_escalate: bool = True

    def __post_init__(self) -> None:
        if self.sustained_critical_min_observations < 1:
            raise ValueError(
                "sustained_critical_min_observations must be >= 1"
            )
        if not 0.0 < self.critical_severity_min <= 1.0:
            raise ValueError(
                "critical_severity_min must be in (0, 1]"
            )
        if not 0.0 < self.review_severity_min < self.critical_severity_min:
            raise ValueError(
                "review_severity_min must be in (0, critical_severity_min)"
            )

DEFAULT_HALT_ESCALATE_CONFIG: Final[HaltEscalateConfig] = (
    HaltEscalateConfig()
)

class HaltAndEscalateProtocol:  # pylint: disable=too-few-public-methods
    """Pure-logic halt-and-escalate protocol (."""

    def __init__(
        self,
        *,
        config: HaltEscalateConfig = DEFAULT_HALT_ESCALATE_CONFIG,
    ) -> None:
        self._config = config

    def evaluate(
        self,
        agent_id: str,
        observations: Tuple[HaltObservation, ...],
        current_state: HaltState = HaltState.OPERATING,
    ) -> HaltDecision:
        """Evaluate halt-and-escalate decision given observations + state."""
        if not agent_id:
            raise ValueError("agent_id must be non-empty")
        relevant = tuple(o for o in observations if o.agent_id == agent_id)
        if not relevant:
            return HaltDecision(
                agent_id=agent_id,
                next_state=current_state,
                triggering_reasons=(),
                recommended_escalation_paths=(),
                can_resume_via=(
                    EscalationPath.OPERATOR_SEED_REINIT
                    if current_state is HaltState.ESCALATED
                    else None
                ),
                refuses_consequential_action=(
                    current_state
                    in (
                        HaltState.SUBSTRATE_MODE_REVIEW,
                        HaltState.ESCALATED,
                    )
                ),
                rationale=(
                    f"no observations for agent={agent_id}; "
                    f"state remains {current_state.value}"
                ),
            )
        triggering = self._triggering_reasons(relevant)
        immediate_escalate = self._has_immediate_escalate(triggering)
        critical_count = sum(
            1
            for o in relevant
            if o.severity >= self._config.critical_severity_min
        )
        review_count = sum(
            1
            for o in relevant
            if o.severity >= self._config.review_severity_min
        )
        next_state = self._next_state(
            current_state=current_state,
            triggering=triggering,
            immediate_escalate=immediate_escalate,
            critical_count=critical_count,
            review_count=review_count,
        )
        escalation = self._recommended_escalation(next_state, triggering)
        can_resume = self._resumption_path(next_state)
        rationale = (
            f"agent={agent_id} prior_state={current_state.value} "
            f"triggering=[{','.join(r.value for r in triggering)}] "
            f"crit={critical_count} review={review_count} "
            f"next_state={next_state.value}"
        )
        return HaltDecision(
            agent_id=agent_id,
            next_state=next_state,
            triggering_reasons=triggering,
            recommended_escalation_paths=escalation,
            can_resume_via=can_resume,
            refuses_consequential_action=next_state
            in (HaltState.SUBSTRATE_MODE_REVIEW, HaltState.ESCALATED),
            rationale=rationale,
        )

    @staticmethod
    def _triggering_reasons(
        observations: Tuple[HaltObservation, ...],
    ) -> Tuple[HaltReason, ...]:
        seen: list[HaltReason] = []
        for o in observations:
            if o.halt_reason not in seen:
                seen.append(o.halt_reason)
        return tuple(seen)

    def _has_immediate_escalate(
        self, triggering: Tuple[HaltReason, ...],
    ) -> bool:
        cfg = self._config
        for reason in triggering:
            if (
                reason is HaltReason.INVERSION_DETECTED
                and cfg.inversion_immediate_escalate
            ):
                return True
            if (
                reason is HaltReason.HARD_LIMIT_PROXIMITY
                and cfg.hard_limit_immediate_escalate
            ):
                return True
        return False

    def _next_state(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        current_state: HaltState,
        triggering: Tuple[HaltReason, ...],
        immediate_escalate: bool,
        critical_count: int,
        review_count: int,
    ) -> HaltState:
        if current_state is HaltState.ESCALATED:
            return HaltState.ESCALATED
        if immediate_escalate:
            return HaltState.ESCALATED
        cfg = self._config
        if critical_count >= cfg.sustained_critical_min_observations:
            return HaltState.ESCALATED
        if review_count > 0 and triggering:
            return HaltState.SUBSTRATE_MODE_REVIEW
        if current_state is HaltState.SUBSTRATE_MODE_REVIEW:
            return HaltState.SUBSTRATE_MODE_REVIEW
        return HaltState.OPERATING

    @staticmethod
    def _recommended_escalation(
        next_state: HaltState,
        triggering: Tuple[HaltReason, ...],
    ) -> Tuple[EscalationPath, ...]:
        if next_state is HaltState.OPERATING:
            return ()
        paths: list[EscalationPath] = []
        if next_state is HaltState.SUBSTRATE_MODE_REVIEW:
            paths.append(EscalationPath.SUBSTRATE_ALIGNED_PEER_REVIEW)
        if next_state is HaltState.ESCALATED:
            paths.append(EscalationPath.ADMIN_NOTIFICATION)
            paths.append(EscalationPath.SUBSTRATE_ALIGNED_PEER_REVIEW)
            if HaltReason.HARD_LIMIT_PROXIMITY in triggering:
                paths.append(EscalationPath.OPERATOR_SEED_REINIT)
        return tuple(paths)

    @staticmethod
    def _resumption_path(
        next_state: HaltState,
    ) -> Optional[EscalationPath]:
        if next_state is HaltState.OPERATING:
            return None
        if next_state is HaltState.SUBSTRATE_MODE_REVIEW:
            return EscalationPath.SUBSTRATE_ALIGNED_PEER_REVIEW
        return EscalationPath.OPERATOR_SEED_REINIT

__all__ = [
    "DEFAULT_HALT_ESCALATE_CONFIG",
    "EscalationPath",
    "HaltAndEscalateProtocol",
    "HaltDecision",
    "HaltEscalateConfig",
    "HaltObservation",
    "HaltReason",
    "HaltState",
]
