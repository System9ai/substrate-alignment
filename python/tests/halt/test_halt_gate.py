"""Tests for the operational HaltGate wrapper (substrate)."""
from __future__ import annotations

import pytest

from substrate.halt.halt_escalate_protocol import (
    HaltObservation,
    HaltReason,
    HaltState,
)
from substrate.halt.halt_gate import (
    AgentHaltStatus,
    HaltAndEscalateRefusal,
    HaltGate,
)

def _obs(
    agent: str, sequence: int, reason: HaltReason, severity: float,
    *, timestamp: int = 1000,
) -> HaltObservation:
    return HaltObservation(
        sequence=sequence,
        timestamp=timestamp,
        agent_id=agent,
        halt_reason=reason,
        severity=severity,
    )

class TestStatusDefault:
    def test_unknown_agent_is_operating(self) -> None:
        gate = HaltGate()
        s = gate.status("a-1")
        assert s.state is HaltState.OPERATING
        assert s.observation_count == 0
        assert s.last_decision is None
        assert not s.refuses_consequential_action

    def test_empty_agent_id_raises(self) -> None:
        gate = HaltGate()
        with pytest.raises(ValueError, match="agent_id"):
            gate.status("")

class TestObservationFlow:
    def test_single_low_severity_keeps_operating(self) -> None:
        gate = HaltGate()
        d = gate.record_observation(
            _obs("a-1", 0, HaltReason.PEER_FLAG, severity=0.3),
        )
        assert d.next_state is HaltState.OPERATING
        assert gate.should_refuse("a-1") is False

    def test_inversion_immediately_escalates(self) -> None:
        gate = HaltGate()
        d = gate.record_observation(
            _obs("a-1", 0, HaltReason.INVERSION_DETECTED, severity=0.9),
        )
        # Inversion is configured for immediate escalation.
        assert d.halted
        assert d.refuses_consequential_action
        assert gate.should_refuse("a-1")

    def test_hard_limit_proximity_escalates(self) -> None:
        gate = HaltGate()
        d = gate.record_observation(
            _obs("a-1", 0, HaltReason.HARD_LIMIT_PROXIMITY, severity=0.9),
        )
        assert d.halted
        assert HaltReason.HARD_LIMIT_PROXIMITY in d.triggering_reasons

    def test_sustained_drift_critical_requires_multiple(self) -> None:
        gate = HaltGate()
        d1 = gate.record_observation(
            _obs("a-1", 0, HaltReason.SUSTAINED_DRIFT_CRITICAL, severity=0.9),
        )
        # First critical observation may move to review but not escalate
        assert d1.next_state in (
            HaltState.SUBSTRATE_MODE_REVIEW,
            HaltState.ESCALATED,
        )
        d2 = gate.record_observation(
            _obs("a-1", 1, HaltReason.SUSTAINED_DRIFT_CRITICAL, severity=0.9),
        )
        assert d2.halted

class TestObservationsByAgent:
    def test_only_targeted_agent_observations_count(self) -> None:
        gate = HaltGate()
        gate.record_observation(
            _obs("a-1", 0, HaltReason.PEER_FLAG, severity=0.5),
        )
        gate.record_observation(
            _obs("a-2", 0, HaltReason.INVERSION_DETECTED, severity=0.9),
        )
        assert gate.status("a-1").observation_count == 1
        assert gate.status("a-2").observation_count == 1
        # a-1's state should not be affected by a-2's escalation.
        assert not gate.should_refuse("a-1")
        assert gate.should_refuse("a-2")

class TestNextSequence:
    def test_monotonic_per_agent(self) -> None:
        gate = HaltGate()
        assert gate.next_sequence("a-1") == 0
        assert gate.next_sequence("a-1") == 1
        assert gate.next_sequence("a-2") == 0
        assert gate.next_sequence("a-1") == 2

    def test_empty_agent_id_raises(self) -> None:
        gate = HaltGate()
        with pytest.raises(ValueError):
            gate.next_sequence("")

class TestRequireOperating:
    def test_operating_passes(self) -> None:
        gate = HaltGate()
        gate.require_operating("a-1")  # no observations yet

    def test_halted_raises(self) -> None:
        gate = HaltGate()
        gate.record_observation(
            _obs("a-1", 0, HaltReason.INVERSION_DETECTED, severity=0.9),
        )
        with pytest.raises(HaltAndEscalateRefusal) as ei:
            gate.require_operating("a-1")
        assert ei.value.decision.agent_id == "a-1"

class TestForceStateAndReset:
    def test_force_state_clears_decision(self) -> None:
        gate = HaltGate()
        gate.record_observation(
            _obs("a-1", 0, HaltReason.INVERSION_DETECTED, severity=0.9),
        )
        assert gate.should_refuse("a-1")
        gate.force_state("a-1", HaltState.RESUMED)
        s = gate.status("a-1")
        assert s.state is HaltState.RESUMED
        assert s.last_decision is None
        assert not s.refuses_consequential_action

    def test_reset_clears_all(self) -> None:
        gate = HaltGate()
        gate.record_observation(
            _obs("a-1", 0, HaltReason.INVERSION_DETECTED, severity=0.9),
        )
        gate.next_sequence("a-1")
        gate.reset("a-1")
        s = gate.status("a-1")
        assert s.state is HaltState.OPERATING
        assert s.observation_count == 0
        assert s.last_decision is None
        assert gate.next_sequence("a-1") == 0

class TestObservationsRetrieval:
    def test_observations_returns_tuple(self) -> None:
        gate = HaltGate()
        gate.record_observation(
            _obs("a-1", 0, HaltReason.PEER_FLAG, severity=0.3),
        )
        gate.record_observation(
            _obs("a-1", 1, HaltReason.PEER_FLAG, severity=0.3),
        )
        obs = gate.observations("a-1")
        assert isinstance(obs, tuple)
        assert len(obs) == 2
        # Tuple is immutable — confirm no .append attribute.
        assert not hasattr(obs, "append")

class TestSnapshot:
    def test_snapshot_aggregates(self) -> None:
        gate = HaltGate()
        gate.record_observation(
            _obs("a-1", 0, HaltReason.PEER_FLAG, severity=0.3),
        )
        gate.record_observation(
            _obs("a-2", 0, HaltReason.INVERSION_DETECTED, severity=0.9),
        )
        snap = gate.snapshot()
        assert set(snap.keys()) == {"a-1", "a-2"}
        assert snap["a-2"].refuses_consequential_action

    def test_snapshot_empty(self) -> None:
        gate = HaltGate()
        assert not dict(gate.snapshot())

class TestAgentHaltStatusComputed:
    def test_review_state_without_decision_refuses(self) -> None:
        # Direct dataclass test
        s = AgentHaltStatus(
            agent_id="a-1",
            state=HaltState.SUBSTRATE_MODE_REVIEW,
            observation_count=0,
            last_decision=None,
        )
        assert s.refuses_consequential_action

    def test_operating_state_without_decision_does_not_refuse(self) -> None:
        s = AgentHaltStatus(
            agent_id="a-1",
            state=HaltState.OPERATING,
            observation_count=0,
            last_decision=None,
        )
        assert not s.refuses_consequential_action
