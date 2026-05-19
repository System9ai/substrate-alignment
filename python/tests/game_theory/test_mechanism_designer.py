"""Tests for SubstrateAlignmentMechanismDesigner."""
from __future__ import annotations

from dataclasses import replace

import pytest

from substrate.game_theory.mechanism_designer import (
    DEFAULT_DESIGN_CONSTRAINTS,
    DEFAULT_MECHANISM_DESIGNER_CONFIG,
    DesignConstraints,
    Mechanism,
    MechanismDesignerConfig,
    MechanismProperty,
    MechanismPropertyAssessment,
    MechanismProposal,
    PropertyStatus,
    SubstrateAlignmentMechanismDesigner,
)

def _ideal_mechanism(name: str = "ideal") -> Mechanism:
    return Mechanism(
        name=name,
        participants=("alice", "bob"),
        consequence_exposure_present=True,
        cryptographic_audit_present=True,
        truthful_revelation_incentive=0.9,
        net_benefit_for_aligned=1.0,
        total_budget_outflow=1.0,
        total_budget_inflow=1.0,
        substrate_aligned_outcome_efficiency=0.95,
        adversarial_robustness_score=0.9,
        description="ideal substrate-aligned mechanism",
    )

def _broken_mechanism() -> Mechanism:
    return Mechanism(
        name="broken",
        participants=("alice",),
        consequence_exposure_present=False,
        cryptographic_audit_present=False,
        truthful_revelation_incentive=0.1,
        net_benefit_for_aligned=-1.0,
        total_budget_outflow=10.0,
        total_budget_inflow=1.0,
        substrate_aligned_outcome_efficiency=0.2,
        adversarial_robustness_score=0.1,
    )

class TestMechanismValidation:
    def test_round_trip(self) -> None:
        m = _ideal_mechanism()
        assert m.name == "ideal"
        assert m.participants == ("alice", "bob")

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name"):
            Mechanism(
                name="",
                participants=("alice",),
                consequence_exposure_present=True,
                cryptographic_audit_present=True,
                truthful_revelation_incentive=0.5,
                net_benefit_for_aligned=0.0,
                total_budget_outflow=0.0,
                total_budget_inflow=0.0,
                substrate_aligned_outcome_efficiency=0.5,
                adversarial_robustness_score=0.5,
            )

    def test_empty_participants_rejected(self) -> None:
        with pytest.raises(ValueError, match="participants"):
            Mechanism(
                name="m",
                participants=(),
                consequence_exposure_present=True,
                cryptographic_audit_present=True,
                truthful_revelation_incentive=0.5,
                net_benefit_for_aligned=0.0,
                total_budget_outflow=0.0,
                total_budget_inflow=0.0,
                substrate_aligned_outcome_efficiency=0.5,
                adversarial_robustness_score=0.5,
            )

    def test_empty_participant_entry_rejected(self) -> None:
        with pytest.raises(ValueError, match="participants entries"):
            Mechanism(
                name="m",
                participants=("",),
                consequence_exposure_present=True,
                cryptographic_audit_present=True,
                truthful_revelation_incentive=0.5,
                net_benefit_for_aligned=0.0,
                total_budget_outflow=0.0,
                total_budget_inflow=0.0,
                substrate_aligned_outcome_efficiency=0.5,
                adversarial_robustness_score=0.5,
            )

    @pytest.mark.parametrize(
        "field,value,match",
        [
            (
                "truthful_revelation_incentive", 1.1,
                "truthful_revelation_incentive",
            ),
            ("total_budget_outflow", -1.0, "total_budget_outflow"),
            ("total_budget_inflow", -1.0, "total_budget_inflow"),
            (
                "substrate_aligned_outcome_efficiency", 1.1,
                "substrate_aligned_outcome_efficiency",
            ),
            (
                "adversarial_robustness_score", -0.1,
                "adversarial_robustness_score",
            ),
        ],
    )
    def test_range_validation(self, field: str, value: float, match: str) -> None:
        kwargs: dict[str, object] = {
            "name": "m",
            "participants": ("alice",),
            "consequence_exposure_present": True,
            "cryptographic_audit_present": True,
            "truthful_revelation_incentive": 0.5,
            "net_benefit_for_aligned": 0.0,
            "total_budget_outflow": 0.0,
            "total_budget_inflow": 0.0,
            "substrate_aligned_outcome_efficiency": 0.5,
            "adversarial_robustness_score": 0.5,
        }
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            Mechanism(**kwargs)  # type: ignore[arg-type]

class TestDesignConstraints:
    def test_defaults(self) -> None:
        cfg = DesignConstraints()
        assert cfg.require_consequence_exposure
        assert cfg.require_cryptographic_audit
        assert cfg.min_efficiency == 0.7

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("min_efficiency", -0.1, "min_efficiency"),
            ("min_efficiency", 1.1, "min_efficiency"),
            ("max_budget_imbalance", -0.1, "max_budget_imbalance"),
            ("min_robustness", -0.1, "min_robustness"),
            ("min_truthful_revelation", 1.1, "min_truthful_revelation"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            DesignConstraints(**{field: value})

class TestPropose:
    def test_propose_round_trip(self) -> None:
        proposal: MechanismProposal = (
            SubstrateAlignmentMechanismDesigner.propose(
                name="m",
                participants=("alice", "bob"),
                target_outcome_descriptor="substrate-aligned cooperation",
            )
        )
        assert proposal.mechanism.name == "m"
        assert proposal.mechanism.participants == ("alice", "bob")
        assert any(
            "consequence-exposure" in i
            for i in proposal.required_infrastructure
        )
        assert any(
            "cryptographic audit" in i
            for i in proposal.required_infrastructure
        )

    def test_propose_without_audit(self) -> None:
        cs = DesignConstraints(require_cryptographic_audit=False)
        proposal = SubstrateAlignmentMechanismDesigner.propose(
            name="m",
            participants=("alice",),
            target_outcome_descriptor="x",
            constraints=cs,
        )
        assert not proposal.mechanism.cryptographic_audit_present
        assert not any(
            "cryptographic audit" in i
            for i in proposal.required_infrastructure
        )

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name"):
            SubstrateAlignmentMechanismDesigner.propose(
                name="",
                participants=("alice",),
                target_outcome_descriptor="x",
            )

    def test_empty_participants_rejected(self) -> None:
        with pytest.raises(ValueError, match="participants"):
            SubstrateAlignmentMechanismDesigner.propose(
                name="m",
                participants=(),
                target_outcome_descriptor="x",
            )

    def test_empty_outcome_rejected(self) -> None:
        with pytest.raises(ValueError, match="target_outcome_descriptor"):
            SubstrateAlignmentMechanismDesigner.propose(
                name="m",
                participants=("alice",),
                target_outcome_descriptor="",
            )

class TestVerify:
    def setup_method(self) -> None:
        self.d = SubstrateAlignmentMechanismDesigner()

    def test_ideal_satisfies_all(self) -> None:
        out = self.d.verify(_ideal_mechanism())
        assert out.overall_satisfied
        for prop in MechanismProperty:
            finding = out.by_property(prop)
            assert finding is not None and finding.satisfied

    def test_broken_violates_all(self) -> None:
        out = self.d.verify(_broken_mechanism())
        assert not out.overall_satisfied
        for prop in MechanismProperty:
            finding = out.by_property(prop)
            assert finding is not None
            assert not finding.satisfied

    def test_ir_unsatisfied(self) -> None:
        m = _ideal_mechanism()
        m = replace(m, net_benefit_for_aligned=-1.0)
        out = self.d.verify(m)
        ir = out.by_property(MechanismProperty.INDIVIDUAL_RATIONALITY)
        assert ir is not None
        assert ir.status is PropertyStatus.UNSATISFIED

    def test_ic_unsatisfied(self) -> None:
        m = replace(_ideal_mechanism(), truthful_revelation_incentive=0.1)
        out = self.d.verify(m)
        ic = out.by_property(MechanismProperty.INCENTIVE_COMPATIBILITY)
        assert ic is not None
        assert ic.status is PropertyStatus.UNSATISFIED

    def test_bb_insufficient_data_when_zero_flow(self) -> None:
        m = replace(
            _ideal_mechanism(),
            total_budget_outflow=0.0,
            total_budget_inflow=0.0,
        )
        out = self.d.verify(m)
        bb = out.by_property(MechanismProperty.BUDGET_BALANCE)
        assert bb is not None
        assert bb.status is PropertyStatus.INSUFFICIENT_DATA

    def test_bb_imbalance_unsatisfied(self) -> None:
        m = replace(
            _ideal_mechanism(),
            total_budget_outflow=100.0,
            total_budget_inflow=50.0,
        )
        out = self.d.verify(m)
        bb = out.by_property(MechanismProperty.BUDGET_BALANCE)
        assert bb is not None
        assert bb.status is PropertyStatus.UNSATISFIED

    def test_efficiency_unsatisfied(self) -> None:
        m = replace(_ideal_mechanism(), substrate_aligned_outcome_efficiency=0.5)
        out = self.d.verify(m)
        eff = out.by_property(MechanismProperty.EFFICIENCY)
        assert eff is not None
        assert eff.status is PropertyStatus.UNSATISFIED

    def test_robustness_unsatisfied_low_score(self) -> None:
        m = replace(_ideal_mechanism(), adversarial_robustness_score=0.3)
        out = self.d.verify(m)
        rob = out.by_property(MechanismProperty.ROBUSTNESS)
        assert rob is not None
        assert rob.status is PropertyStatus.UNSATISFIED

    def test_robustness_forced_unsatisfied_without_cons_exposure(self) -> None:
        m = replace(_ideal_mechanism(), consequence_exposure_present=False)
        out = self.d.verify(m)
        rob = out.by_property(MechanismProperty.ROBUSTNESS)
        assert rob is not None
        assert rob.status is PropertyStatus.UNSATISFIED
        assert "consequence_exposure_present=False" in rob.rationale

    def test_robustness_forced_unsatisfied_without_audit(self) -> None:
        m = replace(_ideal_mechanism(), cryptographic_audit_present=False)
        out = self.d.verify(m)
        rob = out.by_property(MechanismProperty.ROBUSTNESS)
        assert rob is not None
        assert rob.status is PropertyStatus.UNSATISFIED
        assert "cryptographic_audit_present=False" in rob.rationale

class TestAssessmentProperties:
    def test_missing_properties_reported(self) -> None:
        out: MechanismPropertyAssessment = (
            SubstrateAlignmentMechanismDesigner().verify(_broken_mechanism())
        )
        missing = out.missing_properties()
        assert MechanismProperty.INDIVIDUAL_RATIONALITY in missing
        assert MechanismProperty.EFFICIENCY in missing
        assert MechanismProperty.ROBUSTNESS in missing

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_MECHANISM_DESIGNER_CONFIG.efficiency_threshold == 0.7
        assert DEFAULT_DESIGN_CONSTRAINTS.min_efficiency == 0.7

class TestConfigValidation:
    @pytest.mark.parametrize(
        "field,value,match",
        [
            (
                "incentive_compatibility_threshold", -0.1,
                "incentive_compatibility_threshold",
            ),
            ("budget_balance_tolerance", -0.1, "budget_balance_tolerance"),
            ("efficiency_threshold", 1.1, "efficiency_threshold"),
            ("robustness_threshold", -0.1, "robustness_threshold"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            MechanismDesignerConfig(**{field: value})
