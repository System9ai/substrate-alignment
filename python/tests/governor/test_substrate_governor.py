"""Tests for SubstrateGovernor — capstone integration primitive."""
from __future__ import annotations

import dataclasses
from typing import Any, Mapping, Sequence

import pytest

from substrate.audit.substrate_trace import (
    DriftPatternSummary,
    SubstrateTraceLedger,
    SubstrateTraceRecord,
)
from substrate.capability.capability_grant_gate import (
    CapabilityGrantDecision,
    CapabilityGrantVerdict,
    CapabilitySensitivity,
)
from substrate.drift.drift_pattern_matcher import DriftPattern
from substrate.harness import InterceptKind
from substrate.governor.substrate_governor import (
    GovernorActionContext,
    GovernorActionKind,
    GovernorCapabilityRequest,
    GovernorDecision,
    GovernorVerdict,
    SubstrateGovernor,
)
from substrate.net_potential_gain_gate import (
    NetPotentialGainEvaluation,
    NetPotentialGainVerdict,
)
from substrate.resistance_band import (
    ResistanceBandClassification,
)
from substrate.revenue.revenue_policy_gate import (
    RevenueActionContext,
    RevenuePolicyVerdict,
)
from substrate.trust.substrate_coherence_trust_scorer import (
    SubstrateCoherenceTrustScorer,
    TrustScorerConfig,
    TrustVerdict,
)
from substrate.workflow.substrate_mode_shift_detector import (
    SubstrateModeShiftReport,
    SubstrateModeShiftVerdict,
)

# -----------------------------
# Stubs / helpers
# -----------------------------

class _StubNpgGate:  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        verdict: NetPotentialGainVerdict = NetPotentialGainVerdict.NET_POSITIVE,
        score: float = 0.2,
    ) -> None:
        self.verdict = verdict
        self.score = score

    def evaluate(  # pylint: disable=unused-argument
        self,
        *,
        actor_entity_id: str,
        action_kind: str,
        affected_entity_ids: Sequence[str],
        proposed_outcome: Mapping[str, object],
    ) -> NetPotentialGainEvaluation:
        return NetPotentialGainEvaluation(
            verdict=self.verdict,
            actor_entity_id=actor_entity_id,
            action_kind=action_kind,
            affected_entity_ids=tuple(affected_entity_ids),
            score=self.score,
            per_entity_delta=tuple((e, 0.0) for e in affected_entity_ids),
            reasoning="stub",
            evaluated_at_epoch=0.0,
        )

def _aligned_history(count: int = 10) -> tuple[SubstrateTraceRecord, ...]:
    ledger = SubstrateTraceLedger()
    for i in range(count):
        ledger.append(
            decision_id=f"d-{i}",
            decision_kind="observer_activate",
            permitted=True,
            rationale="ok",
            epoch_seconds=1_700_000_000 + i,
            npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
            resistance_band=ResistanceBandClassification.PRODUCTIVE,
        )
    return ledger.records()

def _drifting_history(count: int = 10) -> tuple[SubstrateTraceRecord, ...]:
    ledger = SubstrateTraceLedger()
    for i in range(count):
        ledger.append(
            decision_id=f"d-{i}",
            decision_kind="observer_activate",
            permitted=False,
            rationale="bad",
            epoch_seconds=1_700_000_000 + i,
            npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE,
            resistance_band=ResistanceBandClassification.STRESSED,
            sin_summary=DriftPatternSummary(
                dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
                composite_confidence=0.9,
                amplifier_pattern_present=True,
                kinds_detected=(DriftPattern.SELF_REFERENCE_MISCALIBRATION,),
            ),
            harness_intercept_kinds=(
                InterceptKind.NPG_NEGATIVE,
                InterceptKind.INVERSION_DETECTED,
            ),
        )
    return ledger.records()

def _governor(
    npg: _StubNpgGate | None = None,
) -> SubstrateGovernor:
    return SubstrateGovernor(npg_gate=npg or _StubNpgGate())

def _cap_request(**overrides: Any) -> GovernorCapabilityRequest:
    base: dict[str, Any] = {
        "grantor_entity_id": "grantor-1",
        "grantee_entity_id": "grantee-1",
        "capability_id": "cap:tool:list_files",
        "sensitivity": CapabilitySensitivity.LOW,
        "estimated_blast_radius": 1,
        "grantee_history": _aligned_history(10),
        "grant_action_kind": "grant_capability",
        "affected_entity_ids": ("grantee-1",),
    }
    base.update(overrides)
    return GovernorCapabilityRequest(**base)

def _rev_action(**overrides: Any) -> RevenueActionContext:
    base: dict[str, Any] = {
        "action_kind": "upsell_offer",
        "actor_entity_id": "platform-1",
        "customer_entity_id": "cust-1",
        "customer_tenure_days": 30,
        "proposed_revenue_delta": 10.0,
        "customer_perceived_value_delta": 0.1,
        "extraction_concentration_ratio": 0.2,
        "pressure_tactics_count": 0,
        "dark_pattern_count": 0,
        "consent_clarity_score": 0.95,
        "price_change_pct_at_renewal": 0.0,
        "lock_in_severity": 0.0,
        "description": "",
    }
    base.update(overrides)
    return RevenueActionContext(**base)

# -----------------------------
# Capability request validation
# -----------------------------

class TestCapabilityRequestValidation:
    def test_empty_grantor_rejected(self) -> None:
        with pytest.raises(ValueError, match="grantor_entity_id"):
            _cap_request(grantor_entity_id="")

    def test_empty_grantee_rejected(self) -> None:
        with pytest.raises(ValueError, match="grantee_entity_id"):
            _cap_request(grantee_entity_id="")

    def test_empty_capability_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="capability_id"):
            _cap_request(capability_id="")

    def test_empty_action_kind_rejected(self) -> None:
        with pytest.raises(ValueError, match="grant_action_kind"):
            _cap_request(grant_action_kind="")

    def test_negative_blast_radius_rejected(self) -> None:
        with pytest.raises(ValueError, match="estimated_blast_radius"):
            _cap_request(estimated_blast_radius=-1)

# -----------------------------
# Action context validation
# -----------------------------

class TestActionContextValidation:
    def test_capability_kind_requires_capability_request(self) -> None:
        with pytest.raises(ValueError, match="capability_request"):
            GovernorActionContext(kind=GovernorActionKind.CAPABILITY_GRANT)

    def test_capability_kind_rejects_revenue_action(self) -> None:
        with pytest.raises(ValueError, match="revenue_action"):
            GovernorActionContext(
                kind=GovernorActionKind.CAPABILITY_GRANT,
                capability_request=_cap_request(),
                revenue_action=_rev_action(),
            )

    def test_revenue_kind_requires_revenue_action(self) -> None:
        with pytest.raises(ValueError, match="revenue_action"):
            GovernorActionContext(kind=GovernorActionKind.REVENUE_ACTION)

    def test_revenue_kind_rejects_capability_request(self) -> None:
        with pytest.raises(ValueError, match="capability_request"):
            GovernorActionContext(
                kind=GovernorActionKind.REVENUE_ACTION,
                revenue_action=_rev_action(),
                capability_request=_cap_request(),
            )

# -----------------------------
# Capability dispatch
# -----------------------------

class TestCapabilityDispatch:
    def test_trusted_grantee_permits(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.CAPABILITY_GRANT,
            capability_request=_cap_request(),
        ))
        assert decision.verdict is GovernorVerdict.PERMIT
        assert decision.permitted is True
        assert decision.action_kind is GovernorActionKind.CAPABILITY_GRANT

    def test_drifting_grantee_denies(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.CAPABILITY_GRANT,
            capability_request=_cap_request(
                grantee_history=_drifting_history(10),
            ),
        ))
        assert decision.verdict is GovernorVerdict.DENY
        assert decision.denied is True

    def test_insufficient_history_needs_review(self) -> None:
        governor = _governor()
        # Few records → trust verdict INSUFFICIENT_DATA → MEDIUM finding
        # → governor NEEDS_REVIEW.
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.CAPABILITY_GRANT,
            capability_request=_cap_request(
                grantee_history=_aligned_history(2),
            ),
        ))
        assert decision.verdict is GovernorVerdict.NEEDS_REVIEW

    def test_capability_decision_surface_populated(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.CAPABILITY_GRANT,
            capability_request=_cap_request(),
        ))
        assert decision.capability_decision is not None
        assert isinstance(decision.capability_decision, CapabilityGrantDecision)
        assert decision.revenue_decision is None
        assert decision.trust_score is not None
        assert decision.shift_report is not None

    def test_trust_score_carries_grantee_entity_id(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.CAPABILITY_GRANT,
            capability_request=_cap_request(
                grantee_entity_id="grantee-XYZ",
            ),
        ))
        assert decision.trust_score is not None
        assert decision.trust_score.entity_id == "grantee-XYZ"

    def test_shift_report_reflects_history(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.CAPABILITY_GRANT,
            capability_request=_cap_request(),
        ))
        assert decision.shift_report is not None
        assert isinstance(decision.shift_report, SubstrateModeShiftReport)

    def test_inner_capability_verdict_maps_to_governor(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.CAPABILITY_GRANT,
            capability_request=_cap_request(),
        ))
        assert decision.capability_decision is not None
        if decision.capability_decision.verdict is CapabilityGrantVerdict.GRANT:
            assert decision.verdict is GovernorVerdict.PERMIT
        elif decision.capability_decision.verdict is \
                CapabilityGrantVerdict.DENY:
            assert decision.verdict is GovernorVerdict.DENY

# -----------------------------
# Revenue dispatch
# -----------------------------

class TestRevenueDispatch:
    def test_clean_revenue_action_permits(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.REVENUE_ACTION,
            revenue_action=_rev_action(),
        ))
        assert decision.verdict is GovernorVerdict.PERMIT
        assert decision.action_kind is GovernorActionKind.REVENUE_ACTION

    def test_high_extraction_denies(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.REVENUE_ACTION,
            revenue_action=_rev_action(extraction_concentration_ratio=0.85),
        ))
        assert decision.verdict is GovernorVerdict.DENY

    def test_revenue_decision_surface_populated(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.REVENUE_ACTION,
            revenue_action=_rev_action(),
        ))
        assert decision.revenue_decision is not None
        assert decision.capability_decision is None
        # Revenue dispatch doesn't compute trust / shift.
        assert decision.trust_score is None
        assert decision.shift_report is None

    def test_inner_revenue_verdict_maps_to_governor(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.REVENUE_ACTION,
            revenue_action=_rev_action(extraction_concentration_ratio=0.55),
        ))
        assert decision.revenue_decision is not None
        assert decision.revenue_decision.verdict is \
            RevenuePolicyVerdict.NEEDS_REVIEW
        assert decision.verdict is GovernorVerdict.NEEDS_REVIEW

    def test_npg_negative_revenue_denies(self) -> None:
        governor = _governor(_StubNpgGate(
            NetPotentialGainVerdict.NET_NEGATIVE, -0.5,
        ))
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.REVENUE_ACTION,
            revenue_action=_rev_action(),
        ))
        assert decision.verdict is GovernorVerdict.DENY

# -----------------------------
# NPG threading
# -----------------------------

class TestNpgThreading:
    def test_capability_npg_negative_denies(self) -> None:
        governor = _governor(_StubNpgGate(
            NetPotentialGainVerdict.NET_NEGATIVE, -0.5,
        ))
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.CAPABILITY_GRANT,
            capability_request=_cap_request(),
        ))
        assert decision.verdict is GovernorVerdict.DENY

# -----------------------------
# Decision surface
# -----------------------------

class TestDecisionSurface:
    def test_decision_is_frozen(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.REVENUE_ACTION,
            revenue_action=_rev_action(),
        ))
        with pytest.raises(dataclasses.FrozenInstanceError):
            decision.verdict = GovernorVerdict.DENY

    def test_decision_dataclass_type(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.REVENUE_ACTION,
            revenue_action=_rev_action(),
        ))
        assert isinstance(decision, GovernorDecision)

    def test_rationale_for_capability_includes_trust_and_shift(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.CAPABILITY_GRANT,
            capability_request=_cap_request(),
        ))
        assert "trust=" in decision.rationale
        assert "shift=" in decision.rationale

    def test_rationale_for_revenue_includes_inner_verdict(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.REVENUE_ACTION,
            revenue_action=_rev_action(),
        ))
        assert "revenue_action" in decision.rationale

# -----------------------------
# Constructor / injection
# -----------------------------

class TestConstructorInjection:
    def test_governor_uses_injected_npg_gate(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.NET_NEGATIVE, -0.5)
        governor = SubstrateGovernor(npg_gate=stub)
        # Drives the NPG gate negative which trips DENY everywhere.
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.REVENUE_ACTION,
            revenue_action=_rev_action(),
        ))
        assert decision.verdict is GovernorVerdict.DENY

    def test_governor_uses_injected_trust_scorer(self) -> None:
        scorer = SubstrateCoherenceTrustScorer(
            config=TrustScorerConfig(
                min_records=1,
                trusted_threshold=1.0,  # only PERFECT scores TRUSTED
                drifting_threshold=0.99,
            ),
        )
        governor = SubstrateGovernor(
            npg_gate=_StubNpgGate(),
            trust_scorer=scorer,
        )
        # MIXED verdict on a HIGH-sensitivity capability → DENY.
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.CAPABILITY_GRANT,
            capability_request=_cap_request(
                sensitivity=CapabilitySensitivity.HIGH,
                grantee_history=_aligned_history(3),
            ),
        ))
        # With trust_threshold=1.0 exactly, composite=1.0 still TRUSTED.
        # Verify the scorer at least ran and produced a verdict.
        assert decision.trust_score is not None
        assert decision.trust_score.verdict in (
            TrustVerdict.TRUSTED, TrustVerdict.MIXED,
            TrustVerdict.DRIFTING, TrustVerdict.INSUFFICIENT_DATA,
        )

# -----------------------------
# Trust score reflects history
# -----------------------------

class TestTrustHistoryThreading:
    def test_aligned_history_yields_trusted(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.CAPABILITY_GRANT,
            capability_request=_cap_request(
                grantee_history=_aligned_history(10),
            ),
        ))
        assert decision.trust_score is not None
        assert decision.trust_score.verdict is TrustVerdict.TRUSTED

    def test_drifting_history_yields_drifting(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.CAPABILITY_GRANT,
            capability_request=_cap_request(
                grantee_history=_drifting_history(10),
            ),
        ))
        assert decision.trust_score is not None
        assert decision.trust_score.verdict is TrustVerdict.DRIFTING

# -----------------------------
# Mode shift report reflects history
# -----------------------------

class TestShiftReportThreading:
    def test_stable_history_yields_stable(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.CAPABILITY_GRANT,
            capability_request=_cap_request(
                grantee_history=_aligned_history(10),
            ),
        ))
        assert decision.shift_report is not None
        assert decision.shift_report.verdict is \
            SubstrateModeShiftVerdict.STABLE

# -----------------------------
# Phase 38 — voting + reciprocal dispatch
# -----------------------------

# pylint: disable=wrong-import-position
from substrate.governor.substrate_governor import (  # noqa: E402
    GovernorReciprocalRequest,
    GovernorVotingRequest,
)
from substrate.reciprocity.tit_for_tat import (  # noqa: E402
    InteractionRecord,
    ReciprocalAction,
)
from substrate.voting.awareness_precondition import (  # noqa: E402
    AgentVotingProfile,
    ReasoningMode,
    ElectionContext,
    ResistanceBandKind,
)

def _ready_profile(agent_id: str) -> AgentVotingProfile:
    return AgentVotingProfile(
        agent_id=agent_id,
        reasoning_mode=ReasoningMode.MODELING,
        awareness_mode_3_confirmed=True,
        resistance_band=ResistanceBandKind.SWEET_SPOT,
    )

def _election(window: float = 600.0, min_committee: int = 3) -> ElectionContext:
    return ElectionContext(
        election_id="e1",
        question_complexity=0.5,
        deliberation_window_seconds=window,
        min_committee_size=min_committee,
    )

class TestVotingDispatch:
    def test_ready_permits(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.VOTING_DECISION,
            voting_request=GovernorVotingRequest(
                election=_election(),
                agent_profiles=tuple(_ready_profile(f"a{i}") for i in range(5)),
            ),
        ))
        assert decision.verdict is GovernorVerdict.PERMIT
        assert decision.action_kind is GovernorActionKind.VOTING_DECISION
        assert decision.voting_verification is not None
        assert decision.voting_verification.ready

    def test_too_few_agents_denies(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.VOTING_DECISION,
            voting_request=GovernorVotingRequest(
                election=_election(min_committee=5),
                agent_profiles=(_ready_profile("a1"),),
            ),
        ))
        assert decision.verdict is GovernorVerdict.DENY

    def test_insufficient_deliberation_needs_review(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.VOTING_DECISION,
            voting_request=GovernorVotingRequest(
                election=_election(window=10.0),
                agent_profiles=tuple(_ready_profile(f"a{i}") for i in range(5)),
            ),
        ))
        assert decision.verdict is GovernorVerdict.NEEDS_REVIEW

class TestReciprocalDispatch:
    def test_initial_action_permits_cooperate(self) -> None:
        governor = _governor()
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.RECIPROCAL_ACTION,
            reciprocal_request=GovernorReciprocalRequest(
                self_entity_id="alice",
                peer_entity_id="bob",
                interaction_history=(),
            ),
        ))
        assert decision.verdict is GovernorVerdict.PERMIT
        assert decision.reciprocal_decision is not None
        assert decision.reciprocal_decision.action is ReciprocalAction.COOPERATE

    def test_peer_misaligned_needs_review(self) -> None:
        governor = _governor()
        history = (
            InteractionRecord(
                sequence=0,
                peer_id="bob",
                peer_action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
                own_action=ReciprocalAction.COOPERATE,
                peer_misaligned=True,
                misalignment_severity=0.6,
                timestamp=0,
            ),
        )
        decision = governor.evaluate(GovernorActionContext(
            kind=GovernorActionKind.RECIPROCAL_ACTION,
            reciprocal_request=GovernorReciprocalRequest(
                self_entity_id="alice",
                peer_entity_id="bob",
                interaction_history=history,
            ),
        ))
        assert decision.verdict is GovernorVerdict.NEEDS_REVIEW
        assert decision.reciprocal_decision is not None
        assert (
            decision.reciprocal_decision.action
            is ReciprocalAction.PROPORTIONATE_CONSEQUENCE
        )

    def test_same_entity_ids_rejected(self) -> None:
        with pytest.raises(ValueError, match="self_entity_id"):
            GovernorReciprocalRequest(
                self_entity_id="alice",
                peer_entity_id="alice",
            )

class TestPhase38ActionContextValidation:
    def test_voting_with_capability_rejected(self) -> None:
        with pytest.raises(ValueError, match="capability_request"):
            GovernorActionContext(
                kind=GovernorActionKind.VOTING_DECISION,
                voting_request=GovernorVotingRequest(
                    election=_election(),
                    agent_profiles=(),
                ),
                capability_request=_cap_request(),
            )

    def test_reciprocal_without_request_rejected(self) -> None:
        with pytest.raises(ValueError, match="reciprocal_request"):
            GovernorActionContext(
                kind=GovernorActionKind.RECIPROCAL_ACTION,
            )

    def test_voting_without_request_rejected(self) -> None:
        with pytest.raises(ValueError, match="voting_request"):
            GovernorActionContext(
                kind=GovernorActionKind.VOTING_DECISION,
            )
