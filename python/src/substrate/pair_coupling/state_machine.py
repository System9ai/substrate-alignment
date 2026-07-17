"""Pair-coupling state machine (Companion #2)

Pure-logic state machine for the lifecycle of a sustained two-pole
coupling. The machine encodes the substrate-aligned lifecycle:
``FORMING`` → ``COUPLED`` → ``AUDIT_PENDING`` →
{``AUDIT_PASSED`` | ``EXTRACTIVE_FLAGGED`` | ``DEGRADING_FLAGGED``} →
{``RESTORING`` | ``DISSOLVING``} → ``DISSOLVED``.

The state machine is a *vocabulary surface* for the audit verdicts
produced by the pair-coupling auditor. The auditor
produces *what is*; the state machine produces *what follows*.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the current state and a
  trigger; the machine returns the next state or raises.
* Total over the (state, trigger) cross product: every legal pair is
  enumerated; illegal pairs raise ``IllegalStateTransition``.
* Frozen dataclasses with slots throughout.
# § "The pair-coupling lifecycle"
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

class PairCouplingState(str, Enum):
    """States in the pair-coupling lifecycle."""

    FORMING = "forming"
    COUPLED = "coupled"
    AUDIT_PENDING = "audit_pending"
    AUDIT_PASSED = "audit_passed"
    EXTRACTIVE_FLAGGED = "extractive_flagged"
    DEGRADING_FLAGGED = "degrading_flagged"
    RESTORING = "restoring"
    DISSOLVING = "dissolving"
    DISSOLVED = "dissolved"

class PairCouplingTrigger(str, Enum):
    """Triggers that drive state transitions."""

    BIND = "bind"
    AUDIT_REQUESTED = "audit_requested"
    AUDIT_VERDICT_ALIGNED = "audit_verdict_aligned"
    AUDIT_VERDICT_EXTRACTIVE = "audit_verdict_extractive"
    AUDIT_VERDICT_DEGRADING = "audit_verdict_degrading"
    AUDIT_VERDICT_INSUFFICIENT_DATA = "audit_verdict_insufficient_data"
    REPAIR_INITIATED = "repair_initiated"
    REPAIR_SUCCEEDED = "repair_succeeded"
    REPAIR_FAILED = "repair_failed"
    DISSOLUTION_INITIATED = "dissolution_initiated"
    DISSOLUTION_COMPLETED = "dissolution_completed"

class IllegalStateTransition(ValueError):
    """Raised when a trigger is not legal in the current state."""

_TRANSITIONS: Final[
    dict[tuple[PairCouplingState, PairCouplingTrigger], PairCouplingState]
] = {
    (PairCouplingState.FORMING, PairCouplingTrigger.BIND): (
        PairCouplingState.COUPLED
    ),
    (PairCouplingState.COUPLED, PairCouplingTrigger.AUDIT_REQUESTED): (
        PairCouplingState.AUDIT_PENDING
    ),
    (PairCouplingState.AUDIT_PASSED, PairCouplingTrigger.AUDIT_REQUESTED): (
        PairCouplingState.AUDIT_PENDING
    ),
    (PairCouplingState.RESTORING, PairCouplingTrigger.AUDIT_REQUESTED): (
        PairCouplingState.AUDIT_PENDING
    ),
    (
        PairCouplingState.AUDIT_PENDING,
        PairCouplingTrigger.AUDIT_VERDICT_ALIGNED,
    ): PairCouplingState.AUDIT_PASSED,
    (
        PairCouplingState.AUDIT_PENDING,
        PairCouplingTrigger.AUDIT_VERDICT_EXTRACTIVE,
    ): PairCouplingState.EXTRACTIVE_FLAGGED,
    (
        PairCouplingState.AUDIT_PENDING,
        PairCouplingTrigger.AUDIT_VERDICT_DEGRADING,
    ): PairCouplingState.DEGRADING_FLAGGED,
    (
        PairCouplingState.AUDIT_PENDING,
        PairCouplingTrigger.AUDIT_VERDICT_INSUFFICIENT_DATA,
    ): PairCouplingState.COUPLED,
    (
        PairCouplingState.AUDIT_PASSED,
        PairCouplingTrigger.AUDIT_VERDICT_EXTRACTIVE,
    ): PairCouplingState.EXTRACTIVE_FLAGGED,
    (
        PairCouplingState.DEGRADING_FLAGGED,
        PairCouplingTrigger.REPAIR_INITIATED,
    ): PairCouplingState.RESTORING,
    (
        PairCouplingState.EXTRACTIVE_FLAGGED,
        PairCouplingTrigger.REPAIR_INITIATED,
    ): PairCouplingState.RESTORING,
    (
        PairCouplingState.RESTORING,
        PairCouplingTrigger.REPAIR_SUCCEEDED,
    ): PairCouplingState.COUPLED,
    (
        PairCouplingState.RESTORING,
        PairCouplingTrigger.REPAIR_FAILED,
    ): PairCouplingState.DISSOLVING,
    (
        PairCouplingState.EXTRACTIVE_FLAGGED,
        PairCouplingTrigger.DISSOLUTION_INITIATED,
    ): PairCouplingState.DISSOLVING,
    (
        PairCouplingState.DEGRADING_FLAGGED,
        PairCouplingTrigger.DISSOLUTION_INITIATED,
    ): PairCouplingState.DISSOLVING,
    (
        PairCouplingState.DISSOLVING,
        PairCouplingTrigger.DISSOLUTION_COMPLETED,
    ): PairCouplingState.DISSOLVED,
}

@dataclass(frozen=True, slots=True)
class PairCouplingTransition:
    """Result of a successful state transition."""

    pair_id: str
    from_state: PairCouplingState
    trigger: PairCouplingTrigger
    to_state: PairCouplingState

class PairCouplingStateMachine:  # pylint: disable=too-few-public-methods
    """Pure-logic state machine for pair-coupling lifecycle (Companion #2)."""

    @staticmethod
    def next_state(
        *,
        pair_id: str,
        current: PairCouplingState,
        trigger: PairCouplingTrigger,
    ) -> PairCouplingTransition:
        """Return the next state for ``(current, trigger)`` or raise."""
        if not pair_id:
            raise ValueError("pair_id must be non-empty")
        key = (current, trigger)
        if key not in _TRANSITIONS:
            raise IllegalStateTransition(
                f"illegal transition: {current.value} -> {trigger.value}"
            )
        return PairCouplingTransition(
            pair_id=pair_id,
            from_state=current,
            trigger=trigger,
            to_state=_TRANSITIONS[key],
        )

    @staticmethod
    def legal_triggers(
        current: PairCouplingState,
    ) -> frozenset[PairCouplingTrigger]:
        """Return the set of triggers legal in ``current``."""
        return frozenset(
            trigger for (state, trigger) in _TRANSITIONS if state is current
        )

TERMINAL_STATES: Final[frozenset[PairCouplingState]] = frozenset(
    {PairCouplingState.DISSOLVED}
)

__all__ = [
    "IllegalStateTransition",
    "PairCouplingState",
    "PairCouplingStateMachine",
    "PairCouplingTransition",
    "PairCouplingTrigger",
    "TERMINAL_STATES",
]
