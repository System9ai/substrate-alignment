"""Tests for PairCouplingStateMachine (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.pair_coupling.state_machine import (
    TERMINAL_STATES,
    IllegalStateTransition,
    PairCouplingState,
    PairCouplingStateMachine,
    PairCouplingTrigger,
)

class TestHappyPath:
    def test_forming_to_coupled(self) -> None:
        t = PairCouplingStateMachine.next_state(
            pair_id="p",
            current=PairCouplingState.FORMING,
            trigger=PairCouplingTrigger.BIND,
        )
        assert t.to_state is PairCouplingState.COUPLED

    def test_full_aligned_cycle(self) -> None:
        m = PairCouplingStateMachine
        s = PairCouplingState.FORMING
        s = m.next_state(
            pair_id="p", current=s, trigger=PairCouplingTrigger.BIND,
        ).to_state
        assert s is PairCouplingState.COUPLED
        s = m.next_state(
            pair_id="p", current=s,
            trigger=PairCouplingTrigger.AUDIT_REQUESTED,
        ).to_state
        assert s is PairCouplingState.AUDIT_PENDING
        s = m.next_state(
            pair_id="p", current=s,
            trigger=PairCouplingTrigger.AUDIT_VERDICT_ALIGNED,
        ).to_state
        assert s is PairCouplingState.AUDIT_PASSED

    def test_extractive_repair_dissolves(self) -> None:
        m = PairCouplingStateMachine
        t = m.next_state(
            pair_id="p",
            current=PairCouplingState.EXTRACTIVE_FLAGGED,
            trigger=PairCouplingTrigger.REPAIR_INITIATED,
        )
        assert t.to_state is PairCouplingState.RESTORING
        t = m.next_state(
            pair_id="p",
            current=PairCouplingState.RESTORING,
            trigger=PairCouplingTrigger.REPAIR_FAILED,
        )
        assert t.to_state is PairCouplingState.DISSOLVING

    def test_repair_succeeds(self) -> None:
        t = PairCouplingStateMachine.next_state(
            pair_id="p",
            current=PairCouplingState.RESTORING,
            trigger=PairCouplingTrigger.REPAIR_SUCCEEDED,
        )
        assert t.to_state is PairCouplingState.COUPLED

    def test_insufficient_data_returns_to_coupled(self) -> None:
        t = PairCouplingStateMachine.next_state(
            pair_id="p",
            current=PairCouplingState.AUDIT_PENDING,
            trigger=(
                PairCouplingTrigger.AUDIT_VERDICT_INSUFFICIENT_DATA
            ),
        )
        assert t.to_state is PairCouplingState.COUPLED

    def test_dissolution_completes(self) -> None:
        t = PairCouplingStateMachine.next_state(
            pair_id="p",
            current=PairCouplingState.DISSOLVING,
            trigger=PairCouplingTrigger.DISSOLUTION_COMPLETED,
        )
        assert t.to_state is PairCouplingState.DISSOLVED
        assert t.to_state in TERMINAL_STATES

class TestIllegalTransitions:
    def test_no_bind_from_coupled(self) -> None:
        with pytest.raises(IllegalStateTransition, match="illegal"):
            PairCouplingStateMachine.next_state(
                pair_id="p",
                current=PairCouplingState.COUPLED,
                trigger=PairCouplingTrigger.BIND,
            )

    def test_no_transitions_from_dissolved(self) -> None:
        for trigger in PairCouplingTrigger:
            with pytest.raises(IllegalStateTransition):
                PairCouplingStateMachine.next_state(
                    pair_id="p",
                    current=PairCouplingState.DISSOLVED,
                    trigger=trigger,
                )

    def test_empty_pair_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="pair_id"):
            PairCouplingStateMachine.next_state(
                pair_id="",
                current=PairCouplingState.FORMING,
                trigger=PairCouplingTrigger.BIND,
            )

class TestLegalTriggers:
    def test_forming(self) -> None:
        triggers = PairCouplingStateMachine.legal_triggers(
            PairCouplingState.FORMING,
        )
        assert PairCouplingTrigger.BIND in triggers

    def test_dissolved_is_terminal(self) -> None:
        triggers = PairCouplingStateMachine.legal_triggers(
            PairCouplingState.DISSOLVED,
        )
        assert triggers == frozenset()

    def test_audit_pending_has_four_verdicts(self) -> None:
        triggers = PairCouplingStateMachine.legal_triggers(
            PairCouplingState.AUDIT_PENDING,
        )
        assert (
            PairCouplingTrigger.AUDIT_VERDICT_ALIGNED in triggers
            and PairCouplingTrigger.AUDIT_VERDICT_EXTRACTIVE in triggers
            and PairCouplingTrigger.AUDIT_VERDICT_DEGRADING in triggers
            and PairCouplingTrigger.AUDIT_VERDICT_INSUFFICIENT_DATA
            in triggers
        )
