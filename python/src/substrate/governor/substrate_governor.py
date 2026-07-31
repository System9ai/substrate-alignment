"""Substrate governor: capstone integration primitive.

Single operator-facing surface that composes the substrate primitive
suite behind one :meth:`evaluate` entry point:

* The **NPG gate** is depended on transitively by both sub-
  gates.
* The **RevenuePolicyGate** handles revenue actions.
* The **SubstrateCapabilityGrantGate** handles capability
  grants. The governor pre-computes the grantee's :class:`TrustScore`
  and :class:`SubstrateModeShiftReport` from
  the supplied history and threads the trust score into the
  capability gate.
* The **SubstrateCoherenceTrustScorer** runs on each
  capability grant request, scoring the grantee from their substrate
  trace history.
* The **SubstrateModeShiftDetector** runs on the same
  history as observational context for the operator.

Why this primitive
==================

Each call site that wants substrate-aware governance otherwise has
to wire NPG + trust scorer + shift detector + the correct sub-gate
themselves, which is error-prone and inconsistent across services. The
governor is the *one import, one call* surface that does the
plumbing once.

Pure logic
==========

* No DAO, no LLM, no network. The NPG gate is injected via Protocol;
  the four other primitives are pure-logic shipped components.
* Honest uncertainty preserved end-to-end. Trust INSUFFICIENT_DATA
  surfaces as a NEEDS_REVIEW finding inside the capability gate;
  NPG INSUFFICIENT_DATA produces NEEDS_REVIEW in either sub-gate.
* The governor does not invent its own gating logic; it preserves
  the sub-gate's verdict + findings and only translates the verdict
  to its own four-valued surface (PERMIT / NEEDS_REVIEW / DENY /
  UNROUTABLE).
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Optional, Tuple

from substrate.audit.substrate_trace import (
    SubstrateTraceRecord,
)
from substrate.capability.capability_grant_gate import (
    CapabilityGrantDecision,
    CapabilityGrantRequest,
    CapabilityGrantVerdict,
    CapabilitySensitivity,
    SubstrateCapabilityGrantGate,
)
from substrate.net_potential_gain_gate import (
    NetPotentialGainGate,
)
from substrate.reciprocity.tit_for_tat import (
    InteractionRecord,
    ReciprocalDecision,
    TitForTatReciprocalProtocol,
)
from substrate.revenue.revenue_policy_gate import (
    RevenueActionContext,
    RevenuePolicyDecision,
    RevenuePolicyGate,
    RevenuePolicyVerdict,
)
from substrate.trust.substrate_coherence_trust_scorer import (
    SubstrateCoherenceTrustScorer,
    TrustScore,
)
from substrate.voting.awareness_precondition import (
    AgentVotingProfile,
    ElectionContext,
    PreconditionStatus,
    PreconditionVerification,
    SubstrateAwareVotingProtocol,
)
from substrate.workflow.substrate_mode_shift_detector import (
    SubstrateModeShiftDetector,
    SubstrateModeShiftReport,
)

class GovernorActionKind(str, Enum):
    """Which sub-gate handles this action."""

    CAPABILITY_GRANT = "capability_grant"
    REVENUE_ACTION = "revenue_action"
    VOTING_DECISION = "voting_decision"
    RECIPROCAL_ACTION = "reciprocal_action"

class GovernorVerdict(str, Enum):
    """Top-level verdict surface."""

    PERMIT = "permit"
    NEEDS_REVIEW = "needs_review"
    DENY = "deny"
    UNROUTABLE = "unroutable"

@dataclass(frozen=True, slots=True)
class GovernorCapabilityRequest:  # pylint: disable=too-many-instance-attributes
    """Capability grant input; governor derives trust from ``grantee_history``."""

    grantor_entity_id: str
    grantee_entity_id: str
    capability_id: str
    sensitivity: CapabilitySensitivity
    estimated_blast_radius: int
    grantee_history: Tuple[SubstrateTraceRecord, ...] = field(
        default_factory=tuple,
    )
    grant_action_kind: str = "grant_capability"
    affected_entity_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.grantor_entity_id:
            raise ValueError("grantor_entity_id must be non-empty")
        if not self.grantee_entity_id:
            raise ValueError("grantee_entity_id must be non-empty")
        if not self.capability_id:
            raise ValueError("capability_id must be non-empty")
        if not self.grant_action_kind:
            raise ValueError("grant_action_kind must be non-empty")
        if self.estimated_blast_radius < 0:
            raise ValueError("estimated_blast_radius must be >= 0")

@dataclass(frozen=True, slots=True)
class GovernorVotingRequest:
    """Voting precondition input; governor verifies before consensus aggregation."""

    election: ElectionContext
    agent_profiles: Tuple[AgentVotingProfile, ...] = field(
        default_factory=tuple,
    )

@dataclass(frozen=True, slots=True)
class GovernorReciprocalRequest:
    """Reciprocal-action input; governor routes through tit-for-tat protocol."""

    self_entity_id: str
    peer_entity_id: str
    interaction_history: Tuple[InteractionRecord, ...] = field(
        default_factory=tuple,
    )

    def __post_init__(self) -> None:
        if not self.self_entity_id:
            raise ValueError("self_entity_id must be non-empty")
        if not self.peer_entity_id:
            raise ValueError("peer_entity_id must be non-empty")
        if self.self_entity_id == self.peer_entity_id:
            raise ValueError("self_entity_id and peer_entity_id must differ")

@dataclass(frozen=True, slots=True)
class GovernorActionContext:
    """One action submitted to the governor for evaluation."""

    kind: GovernorActionKind
    capability_request: Optional[GovernorCapabilityRequest] = None
    revenue_action: Optional[RevenueActionContext] = None
    voting_request: Optional[GovernorVotingRequest] = None
    reciprocal_request: Optional[GovernorReciprocalRequest] = None

    def __post_init__(self) -> None:
        _validate_action_context(self)

@dataclass(frozen=True, slots=True)
class GovernorDecision:  # pylint: disable=too-many-instance-attributes
    """Aggregate result of one governor evaluation."""

    verdict: GovernorVerdict
    action_kind: GovernorActionKind
    rationale: str
    capability_decision: Optional[CapabilityGrantDecision] = None
    revenue_decision: Optional[RevenuePolicyDecision] = None
    trust_score: Optional[TrustScore] = None
    shift_report: Optional[SubstrateModeShiftReport] = None
    voting_verification: Optional[PreconditionVerification] = None
    reciprocal_decision: Optional[ReciprocalDecision] = None

    @property
    def permitted(self) -> bool:
        """True iff verdict is PERMIT."""
        return self.verdict is GovernorVerdict.PERMIT

    @property
    def needs_review(self) -> bool:
        """True iff verdict is NEEDS_REVIEW."""
        return self.verdict is GovernorVerdict.NEEDS_REVIEW

    @property
    def denied(self) -> bool:
        """True iff verdict is DENY."""
        return self.verdict is GovernorVerdict.DENY

_CAPABILITY_VERDICT_MAP: Final[dict[CapabilityGrantVerdict, GovernorVerdict]] = {
    CapabilityGrantVerdict.GRANT: GovernorVerdict.PERMIT,
    CapabilityGrantVerdict.NEEDS_REVIEW: GovernorVerdict.NEEDS_REVIEW,
    CapabilityGrantVerdict.DENY: GovernorVerdict.DENY,
}

_REVENUE_VERDICT_MAP: Final[dict[RevenuePolicyVerdict, GovernorVerdict]] = {
    RevenuePolicyVerdict.PERMIT: GovernorVerdict.PERMIT,
    RevenuePolicyVerdict.NEEDS_REVIEW: GovernorVerdict.NEEDS_REVIEW,
    RevenuePolicyVerdict.DENY: GovernorVerdict.DENY,
}

_VOTING_VERDICT_MAP: Final[dict[PreconditionStatus, GovernorVerdict]] = {
    PreconditionStatus.READY: GovernorVerdict.PERMIT,
    PreconditionStatus.INSUFFICIENT_AWARE_AGENTS: GovernorVerdict.DENY,
    PreconditionStatus.INSUFFICIENT_DELIBERATION: GovernorVerdict.NEEDS_REVIEW,
    PreconditionStatus.INSUFFICIENT_DATA: GovernorVerdict.NEEDS_REVIEW,
}

def _validate_action_context(context: "GovernorActionContext") -> None:
    """Reject mismatched kind / sub-context combinations at construction."""
    kind = context.kind
    if kind is GovernorActionKind.CAPABILITY_GRANT:
        _require_only(context, "capability_request")
    elif kind is GovernorActionKind.REVENUE_ACTION:
        _require_only(context, "revenue_action")
    elif kind is GovernorActionKind.VOTING_DECISION:
        _require_only(context, "voting_request")
    elif kind is GovernorActionKind.RECIPROCAL_ACTION:
        _require_only(context, "reciprocal_request")

_SUB_CONTEXT_FIELDS: Final[Tuple[str, ...]] = (
    "capability_request",
    "revenue_action",
    "voting_request",
    "reciprocal_request",
)

def _require_only(
    context: "GovernorActionContext", required_field: str,
) -> None:
    """Ensure only the required sub-context is supplied for the action kind."""
    if getattr(context, required_field) is None:
        raise ValueError(
            f"{context.kind.value} requires {required_field}"
        )
    for f in _SUB_CONTEXT_FIELDS:
        if f != required_field and getattr(context, f) is not None:
            raise ValueError(
                f"{f} must be None for {context.kind.value}"
            )

class SubstrateGovernor:  # pylint: disable=too-few-public-methods
    """Capstone integration primitive composing the substrate suite."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        npg_gate: NetPotentialGainGate,
        capability_gate: Optional[SubstrateCapabilityGrantGate] = None,
        revenue_gate: Optional[RevenuePolicyGate] = None,
        trust_scorer: Optional[SubstrateCoherenceTrustScorer] = None,
        shift_detector: Optional[SubstrateModeShiftDetector] = None,
        voting_protocol: Optional[SubstrateAwareVotingProtocol] = None,
        reciprocal_protocol: Optional[TitForTatReciprocalProtocol] = None,
    ) -> None:
        self._npg = npg_gate
        self._capability_gate = capability_gate or SubstrateCapabilityGrantGate(
            npg_gate=npg_gate,
        )
        self._revenue_gate = revenue_gate or RevenuePolicyGate(
            npg_gate=npg_gate,
        )
        self._trust_scorer = trust_scorer or SubstrateCoherenceTrustScorer()
        self._shift_detector = shift_detector or SubstrateModeShiftDetector()
        self._voting_protocol = voting_protocol or (
            SubstrateAwareVotingProtocol()
        )
        self._reciprocal_protocol = reciprocal_protocol or (
            TitForTatReciprocalProtocol()
        )

    def evaluate(
        self, action_context: GovernorActionContext,
    ) -> GovernorDecision:
        """Route the action to the correct sub-gate and aggregate."""
        if action_context.kind is GovernorActionKind.CAPABILITY_GRANT:
            assert action_context.capability_request is not None
            return self._evaluate_capability(action_context.capability_request)
        if action_context.kind is GovernorActionKind.REVENUE_ACTION:
            assert action_context.revenue_action is not None
            return self._evaluate_revenue(action_context.revenue_action)
        if action_context.kind is GovernorActionKind.VOTING_DECISION:
            assert action_context.voting_request is not None
            return self._evaluate_voting(action_context.voting_request)
        if action_context.kind is GovernorActionKind.RECIPROCAL_ACTION:
            assert action_context.reciprocal_request is not None
            return self._evaluate_reciprocal(
                action_context.reciprocal_request,
            )
        # Should be unreachable given enum exhaustiveness.
        return GovernorDecision(  # pragma: no cover
            verdict=GovernorVerdict.UNROUTABLE,
            action_kind=action_context.kind,
            rationale=f"no router for kind={action_context.kind!r}",
        )

    def _evaluate_capability(
        self, request: GovernorCapabilityRequest,
    ) -> GovernorDecision:
        trust = self._trust_scorer.score(
            entity_id=request.grantee_entity_id,
            records=request.grantee_history,
        )
        shift = self._shift_detector.detect(request.grantee_history)
        inner_request = CapabilityGrantRequest(
            grantor_entity_id=request.grantor_entity_id,
            grantee_entity_id=request.grantee_entity_id,
            capability_id=request.capability_id,
            sensitivity=request.sensitivity,
            estimated_blast_radius=request.estimated_blast_radius,
            grantee_trust_score=trust,
            grant_action_kind=request.grant_action_kind,
            affected_entity_ids=request.affected_entity_ids,
        )
        inner = self._capability_gate.evaluate(inner_request)
        verdict = _CAPABILITY_VERDICT_MAP[inner.verdict]
        rationale = (
            f"capability_grant {inner.verdict.value} "
            f"(trust={trust.verdict.value}, "
            f"shift={shift.verdict.value}); {inner.rationale}"
        )
        return GovernorDecision(
            verdict=verdict,
            action_kind=GovernorActionKind.CAPABILITY_GRANT,
            rationale=rationale,
            capability_decision=inner,
            trust_score=trust,
            shift_report=shift,
        )

    def _evaluate_revenue(
        self, action: RevenueActionContext,
    ) -> GovernorDecision:
        inner = self._revenue_gate.evaluate(action)
        verdict = _REVENUE_VERDICT_MAP[inner.verdict]
        rationale = (
            f"revenue_action {inner.verdict.value}; {inner.rationale}"
        )
        return GovernorDecision(
            verdict=verdict,
            action_kind=GovernorActionKind.REVENUE_ACTION,
            rationale=rationale,
            revenue_decision=inner,
        )

    def _evaluate_voting(
        self, request: GovernorVotingRequest,
    ) -> GovernorDecision:
        verification = self._voting_protocol.verify_preconditions(
            request.election, request.agent_profiles,
        )
        verdict = _VOTING_VERDICT_MAP[verification.status]
        rationale = (
            f"voting_decision {verification.status.value}; "
            f"{verification.rationale}"
        )
        return GovernorDecision(
            verdict=verdict,
            action_kind=GovernorActionKind.VOTING_DECISION,
            rationale=rationale,
            voting_verification=verification,
        )

    def _evaluate_reciprocal(
        self, request: GovernorReciprocalRequest,
    ) -> GovernorDecision:
        if not request.interaction_history:
            decision = self._reciprocal_protocol.initial_action(
                request.peer_entity_id,
            )
        else:
            decision = self._reciprocal_protocol.response_action(
                request.peer_entity_id, request.interaction_history,
            )
        verdict = (
            GovernorVerdict.PERMIT
            if decision.is_cooperative
            else GovernorVerdict.NEEDS_REVIEW
        )
        rationale = (
            f"reciprocal_action {decision.action.value} "
            f"(strategy={decision.strategy_used.value}); "
            f"{decision.rationale}"
        )
        return GovernorDecision(
            verdict=verdict,
            action_kind=GovernorActionKind.RECIPROCAL_ACTION,
            rationale=rationale,
            reciprocal_decision=decision,
        )

__all__ = [
    "GovernorActionContext",
    "GovernorActionKind",
    "GovernorCapabilityRequest",
    "GovernorDecision",
    "GovernorReciprocalRequest",
    "GovernorVerdict",
    "GovernorVotingRequest",
    "SubstrateGovernor",
]
