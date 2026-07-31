"""Tests for SubstrateAlignedTrainingRewards."""
from __future__ import annotations

from typing import Mapping, Sequence

import pytest

from substrate.net_potential_gain_gate import (
    NetPotentialGainEvaluation,
    NetPotentialGainVerdict,
)
from substrate.progress_signaling.emitter import (
    ProgressSignalEmitter,
)
from substrate.progress_signaling.interval_calibrator import (
    SubstrateAlignedIntervalCalibrator,
)
from substrate.progress_signaling.signal import (
    SubstrateEvidence,
    SubstrateSignalType,
)
from substrate.resistance_band import (
    ResistanceBandAssessment,
    assess,
)
from substrate.training.reward_architecture import (
    DEFAULT_TRAINING_REWARD_CONFIG,
    RewardEmissionVerdict,
    RewardSchedulerState,
    SubstrateAlignedTrainingRewards,
    TrainingRewardConfig,
    TrainingRewardRequest,
)

class _StubGate:
    """Stub NPG gate that returns a fixed verdict."""

    def __init__(self, verdict: NetPotentialGainVerdict) -> None:
        self._verdict = verdict

    def evaluate(  # pylint: disable=too-many-arguments,too-many-positional-arguments,unused-argument
        self, *,
        actor_entity_id: str,
        action_kind: str,
        affected_entity_ids: Sequence[str],
        proposed_outcome: Mapping[str, object],
    ) -> NetPotentialGainEvaluation:
        return NetPotentialGainEvaluation(
            verdict=self._verdict,
            actor_entity_id=actor_entity_id,
            action_kind=action_kind,
            affected_entity_ids=tuple(affected_entity_ids),
            score=0.5,
            per_entity_delta=(),
            reasoning="stub",
            evaluated_at_epoch=100.0,
        )

def _evidence(
    *, eid: str = "e-1", kind: str = "audit_pass", weight: float = 0.6,
) -> SubstrateEvidence:
    return SubstrateEvidence(
        evidence_id=eid, evidence_kind=kind,
        weight=weight, rationale="ok",
    )

def _request(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    agent: str = "agent-1",
    trajectory: str = "t-1",
    action: str = "step",
    affected: tuple[str, ...] = ("peer-1",),
    outcome: Mapping[str, object] = None,
    evidence: tuple[SubstrateEvidence, ...] = (),
    signal_type: SubstrateSignalType = SubstrateSignalType.PROGRESS_MARKER,
    quantity: float = 1.0,
    tier: int = 0,
    resistance: ResistanceBandAssessment | None = None,
    epoch: float = 100.0,
    sid: str = "s-1",
) -> TrainingRewardRequest:
    return TrainingRewardRequest(
        agent_id=agent, trajectory_id=trajectory, action_kind=action,
        affected_entity_ids=affected,
        proposed_outcome=outcome or {},
        evidence=evidence, signal_type=signal_type,
        progress_quantity=quantity, tier_index=tier,
        resistance=resistance or assess(utilization=0.35),
        epoch=epoch, signal_id=sid,
    )

def _orchestrator(
    *,
    verdict: NetPotentialGainVerdict = NetPotentialGainVerdict.NET_POSITIVE,
    config: TrainingRewardConfig | None = None,
) -> tuple[SubstrateAlignedTrainingRewards, RewardSchedulerState]:
    state = RewardSchedulerState()
    orch = SubstrateAlignedTrainingRewards(
        npg_gate=_StubGate(verdict),
        emitter=ProgressSignalEmitter(),
        interval_calibrator=SubstrateAlignedIntervalCalibrator(),
        scheduler_state=state,
        config=config or DEFAULT_TRAINING_REWARD_CONFIG,
    )
    return orch, state

class TestConfig:
    def test_defaults(self) -> None:
        c = TrainingRewardConfig()
        assert c.min_distinct_evidence_kinds == 2

    def test_bad_kinds(self) -> None:
        with pytest.raises(ValueError, match="min_distinct_evidence_kinds"):
            TrainingRewardConfig(min_distinct_evidence_kinds=0)

class TestRequest:
    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("agent", "", "agent_id"),
            ("trajectory", "", "trajectory_id"),
            ("action", "", "action_kind"),
            ("sid", "", "signal_id"),
            ("tier", -1, "tier_index"),
            ("epoch", -1.0, "epoch"),
            ("quantity", -1.0, "progress_quantity"),
        ],
    )
    def test_bad(self, field: str, value: object, match: str) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _request(**kwargs)

class TestSchedulerState:
    def test_round_trip(self) -> None:
        s = RewardSchedulerState()
        assert s.last_emit(
            "agent-1", SubstrateSignalType.PROGRESS_MARKER,
        ) is None
        s.record_emit(
            agent_id="agent-1",
            signal_type=SubstrateSignalType.PROGRESS_MARKER,
            epoch=100.0,
        )
        assert s.last_emit(
            "agent-1", SubstrateSignalType.PROGRESS_MARKER,
        ) == 100.0

    def test_bad_epoch(self) -> None:
        s = RewardSchedulerState()
        with pytest.raises(ValueError, match="epoch"):
            s.record_emit(
                agent_id="agent-1",
                signal_type=SubstrateSignalType.PROGRESS_MARKER,
                epoch=-1.0,
            )

class TestOrchestrator:
    def test_emit_happy_path(self) -> None:
        orch, _state = _orchestrator()
        req = _request(evidence=(
            _evidence(kind="audit_pass"),
            _evidence(eid="e-2", kind="peer_attestation"),
        ))
        decision = orch.evaluate(req)
        assert decision.verdict is RewardEmissionVerdict.EMIT
        assert decision.emitted

    def test_skip_net_negative(self) -> None:
        orch, _state = _orchestrator(
            verdict=NetPotentialGainVerdict.NET_NEGATIVE,
        )
        decision = orch.evaluate(_request(evidence=(
            _evidence(),
            _evidence(eid="e-2", kind="peer_attestation"),
        )))
        assert decision.verdict is RewardEmissionVerdict.SKIP_NET_NEGATIVE

    def test_skip_insufficient_data(self) -> None:
        orch, _state = _orchestrator(
            verdict=NetPotentialGainVerdict.INSUFFICIENT_DATA,
        )
        decision = orch.evaluate(_request(evidence=(
            _evidence(), _evidence(eid="e-2", kind="peer_attestation"),
        )))
        assert decision.verdict is RewardEmissionVerdict.SKIP_NET_NEGATIVE

    def test_skip_evidence_diversity(self) -> None:
        orch, _state = _orchestrator()
        decision = orch.evaluate(_request(evidence=(
            _evidence(kind="audit_pass"),
        )))
        assert (
            decision.verdict
            is RewardEmissionVerdict.SKIP_INSUFFICIENT_EVIDENCE_DIVERSITY
        )

    def test_skip_interval_not_elapsed(self) -> None:
        orch, state = _orchestrator()
        # First emit succeeds at epoch=100
        req1 = _request(evidence=(
            _evidence(),
            _evidence(eid="e-2", kind="peer_attestation"),
        ), epoch=100.0, sid="s-1")
        d1 = orch.evaluate(req1)
        assert d1.emitted

        # Second emit at epoch=120 (before 180s interval elapsed) → skip
        req2 = _request(evidence=(
            _evidence(),
            _evidence(eid="e-3", kind="peer_attestation"),
        ), epoch=120.0, sid="s-2")
        d2 = orch.evaluate(req2)
        assert (
            d2.verdict is RewardEmissionVerdict.SKIP_INTERVAL_NOT_ELAPSED
        )
        # State unchanged
        assert state.last_emit(
            "agent-1", SubstrateSignalType.PROGRESS_MARKER,
        ) == 100.0

    def test_emit_after_interval(self) -> None:
        orch, _state = _orchestrator()
        ev = (
            _evidence(),
            _evidence(eid="e-x", kind="peer_attestation"),
        )
        d1 = orch.evaluate(_request(evidence=ev, epoch=100.0, sid="s-1"))
        assert d1.emitted
        d2 = orch.evaluate(_request(evidence=ev, epoch=300.0, sid="s-2"))
        assert d2.emitted

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_TRAINING_REWARD_CONFIG.min_distinct_evidence_kinds == 2
        )
