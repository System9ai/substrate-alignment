"""Offense handling protocol — Companion #2

Pure-logic decision protocol that routes a classified offense-signal
to one of four substrate-aligned responses: acknowledge, repair,
escalate, or dissolve. The protocol composes
:class:`~app.services.common.substrate.offense.signal_type.OffenseSignalType`
(Phase 108), the relationship's pair-coupling state (Phase 103), and
the offense severity to pick the substrate-aligned next step.

Responses
=========

* ``ACKNOWLEDGE`` — log + emit symmetric audit entry; no further
  action.
* ``REPAIR`` — initiate substrate-aligned repair (mediation,
  re-binding, restitution).
* ``ESCALATE`` — hand off to Phase 100 :class:`HaltAndEscalateProtocol`
  with appropriate halt reason.
* ``DISSOLVE`` — terminate the coupling via Phase 43 exit protocol.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the inputs.
* Total over the (signal_type, severity, pair_state) cross product
  every combination resolves to one of four responses.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from substrate.offense.signal_type import (
    OffenseSignalType,
)
from substrate.pair_coupling.state_machine import (
    PairCouplingState,
)

class OffenseResponse(str, Enum):
    """Substrate-aligned offense responses."""

    ACKNOWLEDGE = "acknowledge"
    REPAIR = "repair"
    ESCALATE = "escalate"
    DISSOLVE = "dissolve"

class OffenseSeverity(str, Enum):
    """Severity classes for offenses."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"

_SEVERITY_RANK: Final[dict[OffenseSeverity, int]] = {
    OffenseSeverity.LOW: 1,
    OffenseSeverity.MODERATE: 2,
    OffenseSeverity.HIGH: 3,
    OffenseSeverity.CRITICAL: 4,
}

@dataclass(frozen=True, slots=True)
class OffenseHandlingInput:
    """Caller-supplied offense-handling inputs."""

    actor_entity_id: str
    peer_entity_id: str
    signal_type: OffenseSignalType
    severity: OffenseSeverity
    pair_state: PairCouplingState
    prior_offense_count: int

    def __post_init__(self) -> None:
        if not self.actor_entity_id:
            raise ValueError("actor_entity_id must be non-empty")
        if not self.peer_entity_id:
            raise ValueError("peer_entity_id must be non-empty")
        if self.actor_entity_id == self.peer_entity_id:
            raise ValueError(
                "actor and peer must differ"
            )
        if self.prior_offense_count < 0:
            raise ValueError(
                "prior_offense_count must be >= 0"
            )

@dataclass(frozen=True, slots=True)
class OffenseHandlingDecision:  # pylint: disable=too-many-instance-attributes
    """Offense-handling decision."""

    actor_entity_id: str
    peer_entity_id: str
    signal_type: OffenseSignalType
    severity: OffenseSeverity
    pair_state: PairCouplingState
    response: OffenseResponse
    halt_reason_hint: str
    rationale: str

    @property
    def is_terminal_response(self) -> bool:
        """True iff the response terminates the coupling."""
        return self.response is OffenseResponse.DISSOLVE

@dataclass(frozen=True, slots=True)
class OffenseHandlingConfig:
    """Operator-tunable handling thresholds."""

    repeat_offense_escalation_count: int = 3
    """If prior_offense_count >= this AND severity >= MODERATE,
    escalate."""

    dissolve_at_critical: bool = True
    """If True, CRITICAL severity dissolves the coupling
    unconditionally."""

    def __post_init__(self) -> None:
        if self.repeat_offense_escalation_count < 1:
            raise ValueError(
                "repeat_offense_escalation_count must be >= 1"
            )

DEFAULT_OFFENSE_HANDLING_CONFIG: Final[OffenseHandlingConfig] = (
    OffenseHandlingConfig()
)

_UNRECOVERABLE_SIGNALS: Final[frozenset[OffenseSignalType]] = frozenset(
    {OffenseSignalType.ATTRIBUTION_CONCEALMENT}
)

class OffenseHandlingProtocol:  # pylint: disable=too-few-public-methods
    """Pure-logic offense-handling protocol (Companion #2)."""

    def __init__(
        self,
        *,
        config: OffenseHandlingConfig = DEFAULT_OFFENSE_HANDLING_CONFIG,
    ) -> None:
        self._config = config

    def handle(  # pylint: disable=too-many-return-statements
        self, input_: OffenseHandlingInput,
    ) -> OffenseHandlingDecision:
        """Route the offense to a substrate-aligned response."""
        cfg = self._config
        rank = _SEVERITY_RANK[input_.severity]
        if input_.pair_state in (
            PairCouplingState.DISSOLVING,
            PairCouplingState.DISSOLVED,
        ):
            return self._decide(
                input_,
                OffenseResponse.ACKNOWLEDGE,
                "",
                f"coupling already {input_.pair_state.value}; "
                f"only log",
            )
        if input_.signal_type is OffenseSignalType.UNCLASSIFIED:
            return self._decide(
                input_,
                OffenseResponse.ACKNOWLEDGE,
                "",
                "signal unclassified; record only",
            )
        if input_.signal_type in _UNRECOVERABLE_SIGNALS:
            return self._decide(
                input_,
                OffenseResponse.DISSOLVE,
                "INVERSION_DETECTED",
                f"{input_.signal_type.value} is substrate-unrecoverable",
            )
        if (
            cfg.dissolve_at_critical
            and input_.severity is OffenseSeverity.CRITICAL
        ):
            return self._decide(
                input_,
                OffenseResponse.DISSOLVE,
                "HARD_LIMIT_PROXIMITY",
                "CRITICAL severity triggers dissolution",
            )
        if (
            input_.prior_offense_count
            >= cfg.repeat_offense_escalation_count
            and rank >= _SEVERITY_RANK[OffenseSeverity.MODERATE]
        ):
            return self._decide(
                input_,
                OffenseResponse.ESCALATE,
                "SUSTAINED_DRIFT_CRITICAL",
                f"prior_offenses={input_.prior_offense_count} "
                f">= {cfg.repeat_offense_escalation_count} with "
                f"severity={input_.severity.value}",
            )
        if rank >= _SEVERITY_RANK[OffenseSeverity.HIGH]:
            return self._decide(
                input_,
                OffenseResponse.ESCALATE,
                "PEER_FLAG",
                f"severity={input_.severity.value} requires escalation",
            )
        if rank >= _SEVERITY_RANK[OffenseSeverity.MODERATE]:
            return self._decide(
                input_,
                OffenseResponse.REPAIR,
                "",
                f"severity={input_.severity.value} routed to repair",
            )
        return self._decide(
            input_,
            OffenseResponse.ACKNOWLEDGE,
            "",
            f"severity={input_.severity.value} acknowledged",
        )

    @staticmethod
    def _decide(
        input_: OffenseHandlingInput,
        response: OffenseResponse,
        halt_reason_hint: str,
        rationale: str,
    ) -> OffenseHandlingDecision:
        return OffenseHandlingDecision(
            actor_entity_id=input_.actor_entity_id,
            peer_entity_id=input_.peer_entity_id,
            signal_type=input_.signal_type,
            severity=input_.severity,
            pair_state=input_.pair_state,
            response=response,
            halt_reason_hint=halt_reason_hint,
            rationale=rationale,
        )

__all__ = [
    "DEFAULT_OFFENSE_HANDLING_CONFIG",
    "OffenseHandlingConfig",
    "OffenseHandlingDecision",
    "OffenseHandlingInput",
    "OffenseHandlingProtocol",
    "OffenseResponse",
    "OffenseSeverity",
]
