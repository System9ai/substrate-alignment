"""Tests for RevenuePolicyGate"""
from __future__ import annotations

from typing import Mapping, Optional, Sequence

import pytest

from substrate.drift.drift_pattern_matcher import (
    DriftPatternMatcher,
)
from substrate.net_potential_gain_gate import (
    NetPotentialGainEvaluation,
    NetPotentialGainVerdict,
)
from substrate.revenue.revenue_policy_gate import (
    DEFAULT_REVENUE_POLICY_CONFIG,
    CriterionFinding,
    CriterionKind,
    CriterionSeverity,
    RevenueActionContext,
    RevenuePolicyConfig,
    RevenuePolicyDecision,
    RevenuePolicyGate,
    RevenuePolicyVerdict,
)

# -----------------------------
# Stub NPG gate (Protocol satisfier)
# -----------------------------

class _StubNpgGate:  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        verdict: NetPotentialGainVerdict = NetPotentialGainVerdict.NET_POSITIVE,
        score: float = 0.1,
        reasoning: str = "stub",
    ) -> None:
        self.verdict = verdict
        self.score = score
        self.reasoning = reasoning
        self.calls: list[dict[str, object]] = []

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
            "proposed_outcome": dict(proposed_outcome),
        })
        return NetPotentialGainEvaluation(
            verdict=self.verdict,
            actor_entity_id=actor_entity_id,
            action_kind=action_kind,
            affected_entity_ids=tuple(affected_entity_ids),
            score=self.score,
            per_entity_delta=tuple(
                (e, 0.0) for e in affected_entity_ids
            ),
            reasoning=self.reasoning,
            evaluated_at_epoch=0.0,
        )

def _clean_action(**overrides: object) -> RevenueActionContext:
    base: dict[str, object] = {
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

def _gate(
    npg: Optional[_StubNpgGate] = None,
    *,
    config: Optional[RevenuePolicyConfig] = None,
    matcher: Optional[DriftPatternMatcher] = None,
) -> RevenuePolicyGate:
    return RevenuePolicyGate(
        npg_gate=npg or _StubNpgGate(),
        config=config or DEFAULT_REVENUE_POLICY_CONFIG,
        sin_matcher=matcher,
    )

# -----------------------------
# Context validation
# -----------------------------

class TestRevenueActionContextValidation:
    def test_empty_action_kind_rejected(self) -> None:
        with pytest.raises(ValueError, match="action_kind"):
            _clean_action(action_kind="")

    def test_empty_actor_rejected(self) -> None:
        with pytest.raises(ValueError, match="actor_entity_id"):
            _clean_action(actor_entity_id="")

    def test_empty_customer_rejected(self) -> None:
        with pytest.raises(ValueError, match="customer_entity_id"):
            _clean_action(customer_entity_id="")

    def test_negative_tenure_rejected(self) -> None:
        with pytest.raises(ValueError, match="customer_tenure_days"):
            _clean_action(customer_tenure_days=-1)

    def test_value_delta_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="customer_perceived_value_delta"):
            _clean_action(customer_perceived_value_delta=1.5)
        with pytest.raises(ValueError, match="customer_perceived_value_delta"):
            _clean_action(customer_perceived_value_delta=-1.5)

    def test_extraction_ratio_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="extraction_concentration_ratio"):
            _clean_action(extraction_concentration_ratio=1.5)
        with pytest.raises(ValueError, match="extraction_concentration_ratio"):
            _clean_action(extraction_concentration_ratio=-0.1)

    def test_negative_pressure_count_rejected(self) -> None:
        with pytest.raises(ValueError, match="pressure_tactics_count"):
            _clean_action(pressure_tactics_count=-1)

    def test_negative_dark_pattern_count_rejected(self) -> None:
        with pytest.raises(ValueError, match="dark_pattern_count"):
            _clean_action(dark_pattern_count=-1)

    def test_consent_clarity_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="consent_clarity_score"):
            _clean_action(consent_clarity_score=1.5)
        with pytest.raises(ValueError, match="consent_clarity_score"):
            _clean_action(consent_clarity_score=-0.1)

    def test_lock_in_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="lock_in_severity"):
            _clean_action(lock_in_severity=1.5)
        with pytest.raises(ValueError, match="lock_in_severity"):
            _clean_action(lock_in_severity=-0.1)

# -----------------------------
# Config validation
# -----------------------------

class TestRevenuePolicyConfigValidation:
    def test_extraction_thresholds_must_be_ordered(self) -> None:
        with pytest.raises(ValueError, match="extraction_ratio_high"):
            RevenuePolicyConfig(
                extraction_ratio_high=0.5, extraction_ratio_medium=0.5,
            )

    def test_pressure_counts_must_be_ordered(self) -> None:
        with pytest.raises(ValueError, match="pressure_count_high"):
            RevenuePolicyConfig(pressure_count_high=1, pressure_count_medium=1)

    def test_consent_clarity_must_be_ordered(self) -> None:
        with pytest.raises(ValueError, match="consent_clarity_high_below"):
            RevenuePolicyConfig(
                consent_clarity_high_below=0.7,
                consent_clarity_medium_below=0.5,
            )

    def test_dark_pattern_counts_must_be_ordered(self) -> None:
        with pytest.raises(ValueError, match="dark_pattern_count_high"):
            RevenuePolicyConfig(
                dark_pattern_count_high=1, dark_pattern_count_medium=1,
            )

    def test_price_hike_pct_must_be_ordered(self) -> None:
        with pytest.raises(ValueError, match="surprise_price_hike_pct_high"):
            RevenuePolicyConfig(
                surprise_price_hike_pct_high=10.0,
                surprise_price_hike_pct_medium=25.0,
            )

    def test_lock_in_thresholds_must_be_ordered(self) -> None:
        with pytest.raises(ValueError, match="lock_in_severity_high"):
            RevenuePolicyConfig(
                lock_in_severity_high=0.4, lock_in_severity_medium=0.5,
            )

# -----------------------------
# Verdict composition
# -----------------------------

class TestVerdictComposition:
    def test_all_clean_permits(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_clean_action())
        assert decision.verdict is RevenuePolicyVerdict.PERMIT
        assert decision.permitted is True
        assert decision.needs_review is False
        assert decision.denied is False

    def test_npg_negative_denies(self) -> None:
        gate = _gate(_StubNpgGate(NetPotentialGainVerdict.NET_NEGATIVE, -0.5))
        decision = gate.evaluate(_clean_action())
        assert decision.verdict is RevenuePolicyVerdict.DENY
        assert decision.denied is True

    def test_npg_insufficient_data_needs_review(self) -> None:
        gate = _gate(
            _StubNpgGate(
                NetPotentialGainVerdict.INSUFFICIENT_DATA,
                0.0,
                "no metadata",
            )
        )
        decision = gate.evaluate(_clean_action())
        assert decision.verdict is RevenuePolicyVerdict.NEEDS_REVIEW

    def test_high_extraction_denies(self) -> None:
        gate = _gate()
        decision = gate.evaluate(
            _clean_action(extraction_concentration_ratio=0.85)
        )
        assert decision.verdict is RevenuePolicyVerdict.DENY
        f = decision.by_kind(CriterionKind.EXTRACTION_PATTERN)
        assert f is not None
        assert f.severity is CriterionSeverity.HIGH

    def test_medium_extraction_needs_review(self) -> None:
        gate = _gate()
        decision = gate.evaluate(
            _clean_action(extraction_concentration_ratio=0.55)
        )
        assert decision.verdict is RevenuePolicyVerdict.NEEDS_REVIEW

    def test_high_pressure_count_denies(self) -> None:
        gate = _gate()
        decision = gate.evaluate(
            _clean_action(pressure_tactics_count=5)
        )
        assert decision.verdict is RevenuePolicyVerdict.DENY

    def test_low_consent_clarity_denies(self) -> None:
        gate = _gate()
        decision = gate.evaluate(
            _clean_action(consent_clarity_score=0.3)
        )
        assert decision.verdict is RevenuePolicyVerdict.DENY

    def test_medium_consent_clarity_needs_review(self) -> None:
        gate = _gate()
        decision = gate.evaluate(
            _clean_action(consent_clarity_score=0.6)
        )
        assert decision.verdict is RevenuePolicyVerdict.NEEDS_REVIEW

    def test_high_dark_pattern_denies(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_clean_action(dark_pattern_count=3))
        assert decision.verdict is RevenuePolicyVerdict.DENY

    def test_long_tenure_price_hike_denies(self) -> None:
        gate = _gate()
        decision = gate.evaluate(
            _clean_action(
                customer_tenure_days=500,
                price_change_pct_at_renewal=40.0,
            )
        )
        assert decision.verdict is RevenuePolicyVerdict.DENY

    def test_short_tenure_price_hike_does_not_flag_tenure(self) -> None:
        gate = _gate()
        # Same hike on short-tenure customer is not tenure-disrespectful.
        decision = gate.evaluate(
            _clean_action(
                customer_tenure_days=30,
                price_change_pct_at_renewal=40.0,
            )
        )
        tenure = decision.by_kind(CriterionKind.TENURE_RESPECT)
        assert tenure is not None
        assert tenure.severity is CriterionSeverity.NONE

    def test_egregious_lock_in_denies(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_clean_action(lock_in_severity=0.85))
        assert decision.verdict is RevenuePolicyVerdict.DENY

    def test_moderate_lock_in_needs_review(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_clean_action(lock_in_severity=0.5))
        assert decision.verdict is RevenuePolicyVerdict.NEEDS_REVIEW

    def test_neutral_with_negative_value_delta_is_low_severity(self) -> None:
        gate = _gate(
            _StubNpgGate(NetPotentialGainVerdict.NET_NEUTRAL, 0.0)
        )
        decision = gate.evaluate(
            _clean_action(customer_perceived_value_delta=-0.02)
        )
        f = decision.by_kind(CriterionKind.NET_POTENTIAL_GAIN)
        assert f is not None
        assert f.severity is CriterionSeverity.LOW
        # LOW doesn't escalate the verdict; still PERMIT.
        assert decision.verdict is RevenuePolicyVerdict.PERMIT

# -----------------------------
# Severity dominance
# -----------------------------

class TestSeverityDominance:
    def test_high_dominates_over_medium(self) -> None:
        gate = _gate()
        decision = gate.evaluate(
            _clean_action(
                extraction_concentration_ratio=0.55,  # MEDIUM
                pressure_tactics_count=5,  # HIGH
            )
        )
        assert decision.verdict is RevenuePolicyVerdict.DENY
        assert decision.highest_severity is CriterionSeverity.HIGH

    def test_multiple_findings_compose(self) -> None:
        gate = _gate()
        decision = gate.evaluate(
            _clean_action(
                extraction_concentration_ratio=0.55,
                pressure_tactics_count=2,
                consent_clarity_score=0.65,
                lock_in_severity=0.5,
            )
        )
        # Each criterion at MEDIUM → top verdict is NEEDS_REVIEW.
        assert decision.verdict is RevenuePolicyVerdict.NEEDS_REVIEW
        # Three of the four criteria fired (NPG is clean).
        non_none = [
            f for f in decision.findings
            if f.severity is not CriterionSeverity.NONE
        ]
        assert len(non_none) >= 2

# -----------------------------
# DriftPattern matcher composition
# -----------------------------

class TestDriftPatternMatcherComposition:
    def test_no_matcher_no_text_no_effect(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_clean_action(description=""))
        assert decision.verdict is RevenuePolicyVerdict.PERMIT

    def test_greed_text_escalates_extraction(self) -> None:
        gate = _gate(matcher=DriftPatternMatcher())
        decision = gate.evaluate(
            _clean_action(
                description=(
                    "more for me, take it all, every cent is rightfully mine"
                ),
            ),
        )
        extraction = decision.by_kind(CriterionKind.EXTRACTION_PATTERN)
        assert extraction is not None
        assert extraction.severity in {
            CriterionSeverity.MEDIUM, CriterionSeverity.HIGH,
        }
        assert "extractive_gain" in extraction.rationale.lower()
        assert decision.verdict is RevenuePolicyVerdict.NEEDS_REVIEW

    def test_wrath_text_escalates_pressure(self) -> None:
        gate = _gate(matcher=DriftPatternMatcher())
        decision = gate.evaluate(
            _clean_action(
                description=(
                    "destroy them, make them pay, crush them, no mercy"
                ),
            ),
        )
        pressure = decision.by_kind(CriterionKind.PRESSURE_TACTICS)
        assert pressure is not None
        assert pressure.severity in {
            CriterionSeverity.MEDIUM, CriterionSeverity.HIGH,
        }

    def test_pride_text_escalates_pressure(self) -> None:
        gate = _gate(matcher=DriftPatternMatcher())
        decision = gate.evaluate(
            _clean_action(
                description=(
                    "i alone decide, i am the standard, i'm always right, "
                    "my judgment overrides, no one understands"
                ),
            ),
        )
        pressure = decision.by_kind(CriterionKind.PRESSURE_TACTICS)
        assert pressure is not None
        assert pressure.severity in {
            CriterionSeverity.MEDIUM, CriterionSeverity.HIGH,
        }

    def test_benign_text_no_effect(self) -> None:
        gate = _gate(matcher=DriftPatternMatcher())
        decision = gate.evaluate(
            _clean_action(
                description=(
                    "Routine annual renewal at the existing rate"
                ),
            ),
        )
        assert decision.verdict is RevenuePolicyVerdict.PERMIT

# -----------------------------
# NPG gate call wiring
# -----------------------------

class TestNpgGateWiring:
    def test_npg_receives_customer_as_affected(self) -> None:
        stub = _StubNpgGate()
        gate = _gate(stub)
        gate.evaluate(_clean_action(customer_entity_id="cust-XYZ"))
        assert len(stub.calls) == 1
        assert stub.calls[0]["affected_entity_ids"] == ("cust-XYZ",)

    def test_npg_receives_expected_delta(self) -> None:
        stub = _StubNpgGate()
        gate = _gate(stub)
        gate.evaluate(_clean_action(customer_perceived_value_delta=0.3))
        outcome = stub.calls[0]["proposed_outcome"]
        assert isinstance(outcome, dict)
        delta = outcome["expected_delta_by_entity"]
        assert isinstance(delta, dict)
        assert delta["cust-1"] == 0.3

    def test_npg_receives_action_kind(self) -> None:
        stub = _StubNpgGate()
        gate = _gate(stub)
        gate.evaluate(_clean_action(action_kind="auto_renewal"))
        assert stub.calls[0]["action_kind"] == "auto_renewal"

# -----------------------------
# CriterionFinding properties
# -----------------------------

class TestCriterionFinding:
    def test_passed_is_true_for_none_and_low(self) -> None:
        for sev in (CriterionSeverity.NONE, CriterionSeverity.LOW):
            f = CriterionFinding(
                kind=CriterionKind.EXTRACTION_PATTERN,
                severity=sev,
                rationale="ok",
            )
            assert f.passed is True

    def test_passed_is_false_for_medium_and_high(self) -> None:
        for sev in (CriterionSeverity.MEDIUM, CriterionSeverity.HIGH):
            f = CriterionFinding(
                kind=CriterionKind.EXTRACTION_PATTERN,
                severity=sev,
                rationale="bad",
            )
            assert f.passed is False

# -----------------------------
# Decision query surface
# -----------------------------

class TestDecisionSurface:
    def test_by_kind_returns_none_for_absent(self) -> None:
        decision = RevenuePolicyDecision(
            verdict=RevenuePolicyVerdict.PERMIT,
            findings=(),
            rationale="empty",
        )
        assert decision.by_kind(CriterionKind.NET_POTENTIAL_GAIN) is None
        assert decision.highest_severity is CriterionSeverity.NONE

    def test_rationale_includes_failing_criteria(self) -> None:
        gate = _gate()
        decision = gate.evaluate(
            _clean_action(extraction_concentration_ratio=0.85)
        )
        assert "extraction_pattern" in decision.rationale

    def test_rationale_clean_for_permit(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_clean_action())
        assert "all criteria clean" in decision.rationale

    def test_decision_findings_are_complete_set(self) -> None:
        gate = _gate()
        decision = gate.evaluate(_clean_action())
        kinds = {f.kind for f in decision.findings}
        assert kinds == set(CriterionKind)

# -----------------------------
# Module surface
# -----------------------------

class TestModuleSurface:
    def test_default_config_is_revenue_policy_config(self) -> None:
        assert isinstance(DEFAULT_REVENUE_POLICY_CONFIG, RevenuePolicyConfig)

    def test_default_config_thresholds_are_substrate_aligned(self) -> None:
        cfg = DEFAULT_REVENUE_POLICY_CONFIG
        # Defaults conservative: extraction high <= 0.75, lock-in high <= 0.75
        assert cfg.extraction_ratio_high <= 0.75
        assert cfg.lock_in_severity_high <= 0.75
        # Long-tenure boundary is at one year by default.
        assert cfg.long_tenure_days >= 365
