"""Tests for PairCouplingCedarPredicate (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.pair_coupling.cedar_predicate import (
    PairCouplingAction,
    PairCouplingCedarPredicate,
    PairCouplingDecision,
    PairCouplingPredicateInput,
)
from substrate.pair_coupling.state_machine import (
    PairCouplingState,
)

def _in(
    *,
    state: PairCouplingState,
    action: PairCouplingAction,
    pair_id: str = "p",
) -> PairCouplingPredicateInput:
    return PairCouplingPredicateInput(
        pair_id=pair_id, state=state, action=action,
    )

class TestReadOnly:
    def test_read_allowed_in_every_state(self) -> None:
        p = PairCouplingCedarPredicate
        for state in PairCouplingState:
            r = p.evaluate(
                _in(state=state, action=PairCouplingAction.READ_ONLY),
            )
            assert r.decision is PairCouplingDecision.ALLOW

class TestExpansionGated:
    def test_audit_pending_requires_review(self) -> None:
        r = PairCouplingCedarPredicate.evaluate(
            _in(
                state=PairCouplingState.AUDIT_PENDING,
                action=PairCouplingAction.GRANT_AUTHORITY,
            ),
        )
        assert r.decision is PairCouplingDecision.REQUIRE_REVIEW

    def test_extractive_denies_expansion(self) -> None:
        r = PairCouplingCedarPredicate.evaluate(
            _in(
                state=PairCouplingState.EXTRACTIVE_FLAGGED,
                action=PairCouplingAction.EXPAND_SCOPE,
            ),
        )
        assert r.decision is PairCouplingDecision.DENY

    def test_degrading_denies_delegation(self) -> None:
        r = PairCouplingCedarPredicate.evaluate(
            _in(
                state=PairCouplingState.DEGRADING_FLAGGED,
                action=PairCouplingAction.DELEGATE_DECISION,
            ),
        )
        assert r.decision is PairCouplingDecision.DENY

    def test_coupled_allows_expansion(self) -> None:
        r = PairCouplingCedarPredicate.evaluate(
            _in(
                state=PairCouplingState.COUPLED,
                action=PairCouplingAction.GRANT_AUTHORITY,
            ),
        )
        assert r.decision is PairCouplingDecision.ALLOW
        assert r.allowed

class TestDissolutionGated:
    def test_dissolved_denies_non_read(self) -> None:
        r = PairCouplingCedarPredicate.evaluate(
            _in(
                state=PairCouplingState.DISSOLVED,
                action=PairCouplingAction.GRANT_AUTHORITY,
            ),
        )
        assert r.decision is PairCouplingDecision.DENY

    def test_dissolving_denies_second_dissolution(self) -> None:
        r = PairCouplingCedarPredicate.evaluate(
            _in(
                state=PairCouplingState.DISSOLVING,
                action=PairCouplingAction.INITIATE_DISSOLUTION,
            ),
        )
        assert r.decision is PairCouplingDecision.DENY

    def test_extractive_allows_repair(self) -> None:
        r = PairCouplingCedarPredicate.evaluate(
            _in(
                state=PairCouplingState.EXTRACTIVE_FLAGGED,
                action=PairCouplingAction.INITIATE_REPAIR,
            ),
        )
        assert r.decision is PairCouplingDecision.ALLOW

class TestInputValidation:
    def test_empty_pair_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="pair_id"):
            _in(
                state=PairCouplingState.COUPLED,
                action=PairCouplingAction.READ_ONLY,
                pair_id="",
            )
