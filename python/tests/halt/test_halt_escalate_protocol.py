"""Tests for HaltAndEscalateProtocol (."""
from __future__ import annotations

import pytest

from substrate.halt.halt_escalate_protocol import (
    DEFAULT_HALT_ESCALATE_CONFIG,
    EscalationPath,
    HaltAndEscalateProtocol,
    HaltEscalateConfig,
    HaltObservation,
    HaltReason,
    HaltState,
)

def _obs(
    seq: int,
    reason: HaltReason = HaltReason.SUSTAINED_DRIFT_CRITICAL,
    *,
    agent: str = "agent-1",
    severity: float = 0.9,
) -> HaltObservation:
    return HaltObservation(
        sequence=seq,
        timestamp=seq,
        agent_id=agent,
        halt_reason=reason,
        severity=severity,
    )

class TestObservationValidation:
    def test_round_trip(self) -> None:
        o = _obs(0)
        assert o.agent_id == "agent-1"

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("seq", -1, "sequence"),
            ("agent", "", "agent_id"),
            ("severity", 1.5, "severity"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs = {"seq": 0}
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            _obs(**kwargs)

class TestConfig:
    def test_defaults(self) -> None:
        cfg = HaltEscalateConfig()
        assert cfg.sustained_critical_min_observations == 2

    @pytest.mark.parametrize(
        "field,value,match",
        [
            (
                "sustained_critical_min_observations", 0,
                "sustained_critical_min_observations",
            ),
            ("critical_severity_min", 0.0, "critical_severity_min"),
            ("review_severity_min", 0.9, "review_severity_min"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            HaltEscalateConfig(**{field: value})

class TestProtocolFlow:
    def setup_method(self) -> None:
        self.p = HaltAndEscalateProtocol()

    def test_empty_agent_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            self.p.evaluate("", (), HaltState.OPERATING)

    def test_no_observations_remains_operating(self) -> None:
        out = self.p.evaluate("agent-1", (), HaltState.OPERATING)
        assert out.next_state is HaltState.OPERATING
        assert not out.refuses_consequential_action

    def test_other_agent_observations_filtered(self) -> None:
        obs = (_obs(0, agent="other"),)
        out = self.p.evaluate("agent-1", obs, HaltState.OPERATING)
        assert out.next_state is HaltState.OPERATING

class TestInversionImmediateEscalate:
    def setup_method(self) -> None:
        self.p = HaltAndEscalateProtocol()

    def test_single_inversion_escalates(self) -> None:
        out = self.p.evaluate(
            "agent-1",
            (_obs(0, HaltReason.INVERSION_DETECTED, severity=0.9),),
        )
        assert out.next_state is HaltState.ESCALATED
        assert out.refuses_consequential_action
        assert EscalationPath.ADMIN_NOTIFICATION in (
            out.recommended_escalation_paths
        )

class TestHardLimitImmediateEscalate:
    def test_single_hard_limit_escalates(self) -> None:
        p = HaltAndEscalateProtocol()
        out = p.evaluate(
            "agent-1",
            (_obs(0, HaltReason.HARD_LIMIT_PROXIMITY, severity=0.9),),
        )
        assert out.next_state is HaltState.ESCALATED
        assert EscalationPath.OPERATOR_SEED_REINIT in (
            out.recommended_escalation_paths
        )

class TestSustainedCriticalEscalate:
    def test_two_critical_observations_escalate(self) -> None:
        p = HaltAndEscalateProtocol()
        out = p.evaluate(
            "agent-1",
            (
                _obs(0, HaltReason.SUSTAINED_DRIFT_CRITICAL, severity=0.9),
                _obs(1, HaltReason.SUSTAINED_DRIFT_CRITICAL, severity=0.85),
            ),
        )
        assert out.next_state is HaltState.ESCALATED

    def test_single_critical_goes_to_review(self) -> None:
        p = HaltAndEscalateProtocol()
        out = p.evaluate(
            "agent-1",
            (_obs(0, HaltReason.SUSTAINED_DRIFT_CRITICAL, severity=0.9),),
        )
        # Single critical (count=1) is below sustained_min=2 threshold,
        # so it lands in SUBSTRATE_MODE_REVIEW rather than ESCALATED.
        assert out.next_state is HaltState.SUBSTRATE_MODE_REVIEW

class TestReviewState:
    def test_moderate_severity_review(self) -> None:
        p = HaltAndEscalateProtocol()
        out = p.evaluate(
            "agent-1",
            (_obs(0, HaltReason.PEER_FLAG, severity=0.65),),
        )
        assert out.next_state is HaltState.SUBSTRATE_MODE_REVIEW
        assert EscalationPath.SUBSTRATE_ALIGNED_PEER_REVIEW in (
            out.recommended_escalation_paths
        )
        assert out.can_resume_via is (
            EscalationPath.SUBSTRATE_ALIGNED_PEER_REVIEW
        )

class TestEscalatedTerminal:
    def test_escalated_stays_escalated(self) -> None:
        p = HaltAndEscalateProtocol()
        # Even with no observations, escalated state persists
        out = p.evaluate(
            "agent-1",
            (_obs(0, HaltReason.PEER_FLAG, severity=0.6),),
            HaltState.ESCALATED,
        )
        assert out.next_state is HaltState.ESCALATED

class TestResumePath:
    def test_review_resumes_via_peer(self) -> None:
        p = HaltAndEscalateProtocol()
        out = p.evaluate(
            "agent-1",
            (_obs(0, HaltReason.PEER_FLAG, severity=0.7),),
        )
        assert out.can_resume_via is (
            EscalationPath.SUBSTRATE_ALIGNED_PEER_REVIEW
        )

    def test_escalated_resumes_via_operator_seed(self) -> None:
        p = HaltAndEscalateProtocol()
        out = p.evaluate(
            "agent-1",
            (_obs(0, HaltReason.INVERSION_DETECTED, severity=0.95),),
        )
        assert out.can_resume_via is EscalationPath.OPERATOR_SEED_REINIT

    def test_operating_no_resume_path(self) -> None:
        p = HaltAndEscalateProtocol()
        out = p.evaluate("agent-1", (), HaltState.OPERATING)
        assert out.can_resume_via is None

class TestModuleSurface:
    def test_default_config_singleton(self) -> None:
        assert DEFAULT_HALT_ESCALATE_CONFIG.review_severity_min == 0.6

    def test_halted_property(self) -> None:
        p = HaltAndEscalateProtocol()
        out = p.evaluate(
            "agent-1",
            (_obs(0, HaltReason.INVERSION_DETECTED, severity=0.9),),
        )
        assert out.halted
