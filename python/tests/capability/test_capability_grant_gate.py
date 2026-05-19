"""Tests for SubstrateCapabilityGrantGate"""
from __future__ import annotations

import dataclasses
from typing import Any, Mapping, Sequence

import pytest

from substrate.capability.capability_grant_gate import (
    CapabilityCriterionFinding,
    CapabilityCriterionKind,
    CapabilityFindingSeverity,
    CapabilityGateConfig,
    CapabilityGrantDecision,
    CapabilityGrantRequest,
    CapabilityGrantVerdict,
    CapabilitySensitivity,
    DEFAULT_CAPABILITY_GATE_CONFIG,
    SubstrateCapabilityGrantGate,
)
from substrate.net_potential_gain_gate import (
    NetPotentialGainEvaluation,
    NetPotentialGainVerdict,
)
from substrate.trust.substrate_coherence_trust_scorer import (
    TrustScore,
    TrustScoreComponents,
    TrustVerdict,
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
        self.calls: list[dict[str, Any]] = []

    def evaluate(  # pylint: disable=unused-argument
        self,
        *,
        actor_entity_id: str,
        action_kind: str,
        affected_entity_ids: Sequence[str],
        proposed_outcome: Mapping[str, object],
    ) -> NetPotentialGainEvaluation:
        self.calls.append({
            "actor_entity_id": actor_entity_id,
            "action_kind": action_kind,
            "affected_entity_ids": tuple(affected_entity_ids),
        })
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

def _trust(
    entity_id: str = "grantee-1",
    verdict: TrustVerdict = TrustVerdict.TRUSTED,
    composite: float | None = 0.9,
) -> TrustScore:
    components = (
        TrustScoreComponents(
            npg_positive_rate=1.0,
            productive_rate=1.0,
            intercept_inverse=1.0,
            sin_inverse=1.0,
            inversion_inverse=1.0,
        )
        if composite is not None
        else None
    )
    return TrustScore(
        entity_id=entity_id,
        record_count=10 if composite is not None else 0,
        components=components,
        composite_score=composite,
        verdict=verdict,
        rationale="test",
    )

def _request(
    **overrides: Any,
) -> CapabilityGrantRequest:
    base: dict[str, Any] = {
        "grantor_entity_id": "grantor-1",
        "grantee_entity_id": "grantee-1",
        "capability_id": "cap:tool:list_files",
        "sensitivity": CapabilitySensitivity.LOW,
        "estimated_blast_radius": 1,
        "grantee_trust_score": _trust(),
        "grant_action_kind": "grant_capability",
        "affected_entity_ids": ("grantee-1",),
    }
    base.update(overrides)
    return CapabilityGrantRequest(**base)

def _gate(
    npg: _StubNpgGate | None = None,
    *,
    config: CapabilityGateConfig | None = None,
) -> SubstrateCapabilityGrantGate:
    return SubstrateCapabilityGrantGate(
        npg_gate=npg or _StubNpgGate(),
        config=config or DEFAULT_CAPABILITY_GATE_CONFIG,
    )

# -----------------------------
# Request validation
# -----------------------------

class TestRequestValidation:
    def test_empty_grantor_rejected(self) -> None:
        with pytest.raises(ValueError, match="grantor_entity_id"):
            _request(grantor_entity_id="")

    def test_empty_grantee_rejected(self) -> None:
        with pytest.raises(ValueError, match="grantee_entity_id"):
            _request(grantee_entity_id="")

    def test_empty_capability_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="capability_id"):
            _request(capability_id="")

    def test_empty_action_kind_rejected(self) -> None:
        with pytest.raises(ValueError, match="grant_action_kind"):
            _request(grant_action_kind="")

    def test_negative_blast_radius_rejected(self) -> None:
        with pytest.raises(ValueError, match="estimated_blast_radius"):
            _request(estimated_blast_radius=-1)

    def test_trust_score_grantee_mismatch_rejected(self) -> None:
        bad = _trust(entity_id="someone-else")
        with pytest.raises(ValueError, match="grantee_entity_id"):
            _request(grantee_trust_score=bad)

# -----------------------------
# Config validation
# -----------------------------

class TestConfigValidation:
    def test_max_blast_radius_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_blast_radius_low"):
            CapabilityGateConfig(max_blast_radius_low=0)

    def test_warn_fraction_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="warn_fraction"):
            CapabilityGateConfig(blast_radius_medium_warn_fraction=0.0)
        with pytest.raises(ValueError, match="warn_fraction"):
            CapabilityGateConfig(blast_radius_medium_warn_fraction=1.5)

    def test_min_trust_for_returns_correct_value(self) -> None:
        cfg = CapabilityGateConfig()
        assert cfg.min_trust_for(CapabilitySensitivity.LOW) is \
            TrustVerdict.MIXED
        assert cfg.min_trust_for(CapabilitySensitivity.HIGH) is \
            TrustVerdict.TRUSTED

    def test_max_blast_radius_for_returns_correct_value(self) -> None:
        cfg = CapabilityGateConfig()
        assert cfg.max_blast_radius_for(CapabilitySensitivity.LOW) == 1000
        assert cfg.max_blast_radius_for(
            CapabilitySensitivity.CRITICAL
        ) == 1

# -----------------------------
# Trust criterion
# -----------------------------

class TestTrustCriterion:
    def test_trusted_grantee_passes_for_low(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request())
        finding = decision.by_kind(CapabilityCriterionKind.TRUST_LEVEL)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.NONE

    def test_drifting_grantee_high_severity(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request(
            grantee_trust_score=_trust(verdict=TrustVerdict.DRIFTING),
        ))
        finding = decision.by_kind(CapabilityCriterionKind.TRUST_LEVEL)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.HIGH
        assert "DRIFTING" in finding.rationale

    def test_insufficient_data_medium(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request(
            grantee_trust_score=_trust(
                verdict=TrustVerdict.INSUFFICIENT_DATA, composite=None,
            ),
        ))
        finding = decision.by_kind(CapabilityCriterionKind.TRUST_LEVEL)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.MEDIUM
        assert "INSUFFICIENT_DATA" in finding.rationale

    def test_mixed_grantee_fails_high_sensitivity(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request(
            sensitivity=CapabilitySensitivity.HIGH,
            grantee_trust_score=_trust(verdict=TrustVerdict.MIXED),
        ))
        finding = decision.by_kind(CapabilityCriterionKind.TRUST_LEVEL)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.HIGH
        assert "mixed" in finding.rationale.lower()

    def test_mixed_grantee_passes_low_sensitivity(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request(
            sensitivity=CapabilitySensitivity.LOW,
            grantee_trust_score=_trust(verdict=TrustVerdict.MIXED),
        ))
        finding = decision.by_kind(CapabilityCriterionKind.TRUST_LEVEL)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.NONE

# -----------------------------
# NPG criterion
# -----------------------------

class TestNpgCriterion:
    def test_npg_positive_passes(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request())
        finding = decision.by_kind(CapabilityCriterionKind.NET_POTENTIAL_GAIN)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.NONE

    def test_npg_negative_high(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.NET_NEGATIVE, -0.4)
        gate = _gate(stub)
        decision = gate.evaluate(_request())
        finding = decision.by_kind(CapabilityCriterionKind.NET_POTENTIAL_GAIN)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.HIGH

    def test_npg_insufficient_medium(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.INSUFFICIENT_DATA, 0.0)
        gate = _gate(stub)
        decision = gate.evaluate(_request())
        finding = decision.by_kind(CapabilityCriterionKind.NET_POTENTIAL_GAIN)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.MEDIUM

    def test_npg_neutral_on_high_sensitivity_is_low(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.NET_NEUTRAL, 0.0)
        gate = _gate(stub)
        decision = gate.evaluate(_request(
            sensitivity=CapabilitySensitivity.HIGH,
            grantee_trust_score=_trust(verdict=TrustVerdict.TRUSTED),
        ))
        finding = decision.by_kind(CapabilityCriterionKind.NET_POTENTIAL_GAIN)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.LOW

    def test_npg_neutral_on_low_sensitivity_is_none(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.NET_NEUTRAL, 0.0)
        gate = _gate(stub)
        decision = gate.evaluate(_request())
        finding = decision.by_kind(CapabilityCriterionKind.NET_POTENTIAL_GAIN)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.NONE

# -----------------------------
# Blast radius criterion
# -----------------------------

class TestBlastRadiusCriterion:
    def test_radius_within_bounds_none(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request(
            sensitivity=CapabilitySensitivity.LOW,
            estimated_blast_radius=1,
        ))
        finding = decision.by_kind(CapabilityCriterionKind.BLAST_RADIUS)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.NONE

    def test_radius_above_max_high(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request(
            sensitivity=CapabilitySensitivity.HIGH,
            estimated_blast_radius=20,  # max for HIGH = 10
            grantee_trust_score=_trust(verdict=TrustVerdict.TRUSTED),
        ))
        finding = decision.by_kind(CapabilityCriterionKind.BLAST_RADIUS)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.HIGH

    def test_radius_at_warn_threshold_medium(self) -> None:
        # max_blast_radius for HIGH is 10, warn fraction 0.7 → warn at 7.
        gate = _gate()
        decision = gate.evaluate(_request(
            sensitivity=CapabilitySensitivity.HIGH,
            estimated_blast_radius=8,
            grantee_trust_score=_trust(verdict=TrustVerdict.TRUSTED),
        ))
        finding = decision.by_kind(CapabilityCriterionKind.BLAST_RADIUS)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.MEDIUM

    def test_radius_zero_none(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request(estimated_blast_radius=0))
        finding = decision.by_kind(CapabilityCriterionKind.BLAST_RADIUS)
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.NONE

# -----------------------------
# Sensitivity escalation
# -----------------------------

class TestSensitivityEscalation:
    def test_critical_auto_escalates_medium(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request(
            sensitivity=CapabilitySensitivity.CRITICAL,
            grantee_trust_score=_trust(verdict=TrustVerdict.TRUSTED),
        ))
        finding = decision.by_kind(
            CapabilityCriterionKind.SENSITIVITY_ESCALATION,
        )
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.MEDIUM

    def test_non_critical_no_escalation(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request(
            sensitivity=CapabilitySensitivity.LOW,
        ))
        finding = decision.by_kind(
            CapabilityCriterionKind.SENSITIVITY_ESCALATION,
        )
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.NONE

    def test_escalation_disabled_by_config(self) -> None:
        gate = _gate(config=CapabilityGateConfig(
            require_review_for_critical=False,
        ))
        decision = gate.evaluate(_request(
            sensitivity=CapabilitySensitivity.CRITICAL,
            grantee_trust_score=_trust(verdict=TrustVerdict.TRUSTED),
        ))
        finding = decision.by_kind(
            CapabilityCriterionKind.SENSITIVITY_ESCALATION,
        )
        assert finding is not None
        assert finding.severity is CapabilityFindingSeverity.NONE

# -----------------------------
# Verdict composition
# -----------------------------

class TestVerdictComposition:
    def test_all_clean_grants(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request())
        assert decision.verdict is CapabilityGrantVerdict.GRANT
        assert decision.granted is True
        assert decision.needs_review is False
        assert decision.denied is False

    def test_high_severity_denies(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request(
            grantee_trust_score=_trust(verdict=TrustVerdict.DRIFTING),
        ))
        assert decision.verdict is CapabilityGrantVerdict.DENY
        assert decision.denied is True

    def test_critical_auto_review(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request(
            sensitivity=CapabilitySensitivity.CRITICAL,
            grantee_trust_score=_trust(verdict=TrustVerdict.TRUSTED),
        ))
        assert decision.verdict is CapabilityGrantVerdict.NEEDS_REVIEW

    def test_high_dominates_over_medium(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request(
            sensitivity=CapabilitySensitivity.CRITICAL,  # MEDIUM escalation
            grantee_trust_score=_trust(verdict=TrustVerdict.DRIFTING),  # HIGH
        ))
        assert decision.verdict is CapabilityGrantVerdict.DENY

    def test_npg_negative_denies(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.NET_NEGATIVE, -0.5)
        gate = _gate(stub)
        decision = gate.evaluate(_request())
        assert decision.verdict is CapabilityGrantVerdict.DENY

    def test_npg_insufficient_needs_review(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.INSUFFICIENT_DATA, 0.0)
        gate = _gate(stub)
        decision = gate.evaluate(_request())
        assert decision.verdict is CapabilityGrantVerdict.NEEDS_REVIEW

# -----------------------------
# NPG gate wiring
# -----------------------------

class TestNpgGateWiring:
    def test_npg_receives_grant_action(self) -> None:
        stub = _StubNpgGate()
        gate = _gate(stub)
        gate.evaluate(_request(grant_action_kind="grant_admin_role"))
        assert stub.calls[0]["action_kind"] == "grant_admin_role"

    def test_npg_receives_affected_entities(self) -> None:
        stub = _StubNpgGate()
        gate = _gate(stub)
        gate.evaluate(_request(
            affected_entity_ids=("grantee-1", "cell-A"),
        ))
        assert stub.calls[0]["affected_entity_ids"] == (
            "grantee-1", "cell-A",
        )

    def test_npg_receives_grantor(self) -> None:
        stub = _StubNpgGate()
        gate = _gate(stub)
        gate.evaluate(_request(grantor_entity_id="admin-cell-1"))
        assert stub.calls[0]["actor_entity_id"] == "admin-cell-1"

# -----------------------------
# Decision surface
# -----------------------------

class TestDecisionSurface:
    def test_findings_contain_all_criteria(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request())
        kinds = {f.kind for f in decision.findings}
        assert kinds == set(CapabilityCriterionKind)

    def test_by_kind_returns_none_for_unknown_kind(self) -> None:
        decision = CapabilityGrantDecision(
            verdict=CapabilityGrantVerdict.GRANT,
            findings=(),
            rationale="empty",
        )
        assert decision.by_kind(
            CapabilityCriterionKind.TRUST_LEVEL,
        ) is None
        assert decision.highest_severity is CapabilityFindingSeverity.NONE

    def test_rationale_clean_grant(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request())
        assert "all criteria clean" in decision.rationale

    def test_rationale_includes_failing_criteria(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request(
            grantee_trust_score=_trust(verdict=TrustVerdict.DRIFTING),
        ))
        assert "trust_level" in decision.rationale

    def test_passed_property_on_finding(self) -> None:
        for sev in (
            CapabilityFindingSeverity.NONE, CapabilityFindingSeverity.LOW,
        ):
            f = CapabilityCriterionFinding(
                kind=CapabilityCriterionKind.TRUST_LEVEL,
                severity=sev,
                rationale="x",
            )
            assert f.passed is True
        for sev in (
            CapabilityFindingSeverity.MEDIUM, CapabilityFindingSeverity.HIGH,
        ):
            f = CapabilityCriterionFinding(
                kind=CapabilityCriterionKind.TRUST_LEVEL,
                severity=sev,
                rationale="x",
            )
            assert f.passed is False

    def test_decision_dataclass_frozen(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_request())
        with pytest.raises(dataclasses.FrozenInstanceError):
            decision.verdict = CapabilityGrantVerdict.DENY  # type: ignore[misc]
