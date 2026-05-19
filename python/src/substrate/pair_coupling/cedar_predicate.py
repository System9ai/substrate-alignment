"""Pair-coupling Cedar predicate — Companion #2

Pure-logic Cedar-predicate-shaped helper that downstream policy code
calls to gate actions on pair-coupling audit verdicts. The predicate
returns ``ALLOW`` / ``DENY`` / ``REQUIRE_REVIEW`` shaped to a Cedar
policy decision; the actual Cedar policy bindings live elsewhere.

This primitive is the bridge between the audit/state-machine layer and
the policy enforcement layer.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the inputs.
* Total over the (state, action) cross product.
* Frozen dataclasses with slots throughout.
# § "Cedar predicate for pair-coupling gating"
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from substrate.pair_coupling.state_machine import (
    PairCouplingState,
)

class PairCouplingAction(str, Enum):
    """Actions that may be gated by pair-coupling state."""

    GRANT_AUTHORITY = "grant_authority"
    EXPAND_SCOPE = "expand_scope"
    DELEGATE_DECISION = "delegate_decision"
    INITIATE_REPAIR = "initiate_repair"
    INITIATE_DISSOLUTION = "initiate_dissolution"
    READ_ONLY = "read_only"

class PairCouplingDecision(str, Enum):
    """Cedar-shaped policy decision."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_REVIEW = "require_review"

@dataclass(frozen=True, slots=True)
class PairCouplingPredicateInput:
    """Caller-supplied inputs to the Cedar predicate."""

    pair_id: str
    state: PairCouplingState
    action: PairCouplingAction

    def __post_init__(self) -> None:
        if not self.pair_id:
            raise ValueError("pair_id must be non-empty")

@dataclass(frozen=True, slots=True)
class PairCouplingPredicateResult:
    """Cedar-shaped predicate result."""

    pair_id: str
    state: PairCouplingState
    action: PairCouplingAction
    decision: PairCouplingDecision
    rationale: str

    @property
    def allowed(self) -> bool:
        """True iff the action is allowed without further review."""
        return self.decision is PairCouplingDecision.ALLOW

_EXPANSION_ACTIONS = frozenset(
    {
        PairCouplingAction.GRANT_AUTHORITY,
        PairCouplingAction.EXPAND_SCOPE,
        PairCouplingAction.DELEGATE_DECISION,
    }
)

class PairCouplingCedarPredicate:  # pylint: disable=too-few-public-methods
    """Pure-logic pair-coupling Cedar predicate (Companion #2)."""

    @staticmethod
    def evaluate(
        input_: PairCouplingPredicateInput,
    ) -> PairCouplingPredicateResult:
        """Evaluate the predicate for ``(state, action)``."""
        state = input_.state
        action = input_.action

        if action is PairCouplingAction.READ_ONLY:
            return PairCouplingCedarPredicate._result(
                input_,
                PairCouplingDecision.ALLOW,
                "read-only actions are unconditionally allowed",
            )

        if state in (
            PairCouplingState.FORMING,
            PairCouplingState.AUDIT_PENDING,
            PairCouplingState.RESTORING,
        ):
            if action in _EXPANSION_ACTIONS:
                return PairCouplingCedarPredicate._result(
                    input_,
                    PairCouplingDecision.REQUIRE_REVIEW,
                    f"state={state.value} requires review for expansion action",
                )

        if state in (
            PairCouplingState.EXTRACTIVE_FLAGGED,
            PairCouplingState.DEGRADING_FLAGGED,
        ):
            if action in _EXPANSION_ACTIONS:
                return PairCouplingCedarPredicate._result(
                    input_,
                    PairCouplingDecision.DENY,
                    (
                        f"state={state.value}: expansion denied until "
                        f"repair or dissolution"
                    ),
                )

        if state is PairCouplingState.DISSOLVED:
            return PairCouplingCedarPredicate._result(
                input_,
                PairCouplingDecision.DENY,
                "dissolved pair-couplings deny all non-read actions",
            )

        if state is PairCouplingState.DISSOLVING:
            if action is PairCouplingAction.INITIATE_DISSOLUTION:
                return PairCouplingCedarPredicate._result(
                    input_,
                    PairCouplingDecision.DENY,
                    "dissolution already in progress",
                )

        return PairCouplingCedarPredicate._result(
            input_,
            PairCouplingDecision.ALLOW,
            f"state={state.value} permits action={action.value}",
        )

    @staticmethod
    def _result(
        input_: PairCouplingPredicateInput,
        decision: PairCouplingDecision,
        rationale: str,
    ) -> PairCouplingPredicateResult:
        return PairCouplingPredicateResult(
            pair_id=input_.pair_id,
            state=input_.state,
            action=input_.action,
            decision=decision,
            rationale=rationale,
        )

__all__ = [
    "PairCouplingAction",
    "PairCouplingCedarPredicate",
    "PairCouplingDecision",
    "PairCouplingPredicateInput",
    "PairCouplingPredicateResult",
]
