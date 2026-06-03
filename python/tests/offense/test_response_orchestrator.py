# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=too-many-public-methods
# pylint: disable=too-few-public-methods
"""Tests for OffenseResponseOrchestrator (reflex gate -> deliberate path)."""
from __future__ import annotations

import pytest

from substrate.net_potential_gain_gate import NetPotentialGainVerdict
from substrate.offense.handling_protocol import (
    OffenseHandlingInput,
    OffenseSeverity,
)
from substrate.offense.pre_action_net_state_evaluator import (
    EntityDelta,
    PreActionInput,
)
from substrate.offense.reflex_restraint_gate import (
    ReflexRestraintGate,
    RestraintGateConfig,
    RestraintVerdict,
    ThreatAppraisal,
)
from substrate.offense.response_orchestrator import (
    OffenseResponseOrchestrator,
)
from substrate.offense.signal_type import OffenseSignalType
from substrate.pair_coupling.state_machine import PairCouplingState

_ACTOR = "alice"
_PEER = "bob"


def _appraisal(
    *,
    survival: float = 0.0,
    npg: NetPotentialGainVerdict = NetPotentialGainVerdict.NET_NEGATIVE,
    crosses_hard_limit: bool = False,
) -> ThreatAppraisal:
    return ThreatAppraisal(
        actor_entity_id=_ACTOR,
        threat_id="threat-1",
        survival_threat_score=survival,
        reactive_action_kind="retaliate",
        reactive_action_npg=npg,
        crosses_hard_limit=crosses_hard_limit,
    )


def _pre_action_input(*, actor: str = _ACTOR) -> PreActionInput:
    return PreActionInput(
        action_id="action-1",
        actor_entity_id=actor,
        affected_deltas=(EntityDelta(entity_id=_PEER, estimated_delta=-0.2),),
    )


def _handling_input(*, actor: str = _ACTOR) -> OffenseHandlingInput:
    return OffenseHandlingInput(
        actor_entity_id=actor,
        peer_entity_id=_PEER,
        signal_type=OffenseSignalType.SCARCITY_AGGRESSION,
        severity=OffenseSeverity.MODERATE,
        pair_state=PairCouplingState.COUPLED,
        prior_offense_count=0,
    )


class TestSurvivalPath:
    def test_survival_reactive_skips_deliberation(self) -> None:
        plan = OffenseResponseOrchestrator().plan(
            appraisal=_appraisal(survival=0.95),
            pre_action_input=_pre_action_input(),
            handling_input=_handling_input(),
        )
        assert plan.is_reactive is True
        assert plan.deliberation_performed is False
        assert plan.pre_action is None
        assert plan.handling is None
        assert plan.considered_response is None

    def test_hard_limit_refused_skips_deliberation(self) -> None:
        plan = OffenseResponseOrchestrator().plan(
            appraisal=_appraisal(survival=1.0, crosses_hard_limit=True),
            pre_action_input=_pre_action_input(),
            handling_input=_handling_input(),
        )
        assert plan.is_refused is True
        assert plan.restraint.verdict is RestraintVerdict.REFUSE_HARD_LIMIT
        assert plan.deliberation_performed is False


class TestDeliberatePath:
    def test_restraint_routes_to_deliberation(self) -> None:
        plan = OffenseResponseOrchestrator().plan(
            appraisal=_appraisal(
                survival=0.2, npg=NetPotentialGainVerdict.NET_NEGATIVE
            ),
            pre_action_input=_pre_action_input(),
            handling_input=_handling_input(),
        )
        assert plan.restraint.verdict is RestraintVerdict.DE_ESCALATE
        assert plan.deliberation_performed is True
        assert plan.pre_action is not None
        assert plan.handling is not None
        assert plan.considered_response is not None

    def test_insufficient_npg_still_deliberates(self) -> None:
        plan = OffenseResponseOrchestrator().plan(
            appraisal=_appraisal(
                survival=0.2,
                npg=NetPotentialGainVerdict.INSUFFICIENT_DATA,
            ),
            pre_action_input=_pre_action_input(),
            handling_input=_handling_input(),
        )
        assert plan.restraint.verdict is RestraintVerdict.INSUFFICIENT_DATA
        assert plan.deliberation_performed is True
        assert plan.handling is not None


class TestActorConsistency:
    def test_pre_action_actor_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="pre_action_input.actor_entity_id"):
            OffenseResponseOrchestrator().plan(
                appraisal=_appraisal(survival=0.2),
                pre_action_input=_pre_action_input(actor="someone-else"),
                handling_input=_handling_input(),
            )

    def test_handling_actor_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="handling_input.actor_entity_id"):
            OffenseResponseOrchestrator().plan(
                appraisal=_appraisal(survival=0.2),
                pre_action_input=_pre_action_input(),
                handling_input=_handling_input(actor="someone-else"),
            )


class TestInjection:
    def test_custom_reflex_gate_threshold(self) -> None:
        orch = OffenseResponseOrchestrator(
            reflex_gate=ReflexRestraintGate(
                config=RestraintGateConfig(survival_threshold=0.30)
            )
        )
        plan = orch.plan(
            appraisal=_appraisal(survival=0.35),
            pre_action_input=_pre_action_input(),
            handling_input=_handling_input(),
        )
        assert plan.is_reactive is True
        assert plan.deliberation_performed is False
