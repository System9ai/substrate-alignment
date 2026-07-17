"""Substrate-alignment mechanism designer
"Mechanism design and substrate-alignment engineering", classical
mechanism design IS substrate-alignment engineering applied at
multi-entity scale. The platform's existing infrastructure
(cryptographic identity + audit + consequence-exposure + retraining
+ decommissioning) IS mechanism design applied to AI agents; this
primitive makes that framing explicit.

What this primitive does
========================

Two surfaces:

1. :meth:`SubstrateAlignmentMechanismDesigner.propose`: given a
   target substrate-aligned outcome, a participant set, and a set of
   :class:`DesignConstraints`, returns a :class:`MechanismProposal`
   sketching the recommended :class:`Mechanism` plus the required
   substrate infrastructure (consequence-exposure, audit chain,
   truthful-revelation incentives).
2. :meth:`SubstrateAlignmentMechanismDesigner.verify`: given a
   concrete :class:`Mechanism`, returns
   :class:`MechanismPropertyAssessment` evaluating the five classical
   mechanism-design properties:

   * **Individual rationality**: substrate-aligned operators benefit
     from participation.
   * **Incentive compatibility**: substrate-aligned operation is the
     dominant strategy (truthful revelation).
   * **Budget balance**: consequence-exposure outflow ≈ inflow.
   * **Efficiency**: substrate-aligned outcomes are produced.
   * **Robustness**: mechanism resists adversarial manipulation.

Pure logic
==========

* No DAO, no LLM, no network.
* Honest uncertainty: a mechanism with insufficient calibration data
  surfaces affected properties as :attr:`PropertyStatus.INSUFFICIENT_DATA`
  rather than fabricating a verdict.
* Frozen dataclasses with slots throughout.
* All threshold knobs live in :class:`MechanismDesignerConfig`.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Tuple

class MechanismProperty(str, Enum):
    """The five classical mechanism-design properties."""

    INDIVIDUAL_RATIONALITY = "individual_rationality"
    INCENTIVE_COMPATIBILITY = "incentive_compatibility"
    BUDGET_BALANCE = "budget_balance"
    EFFICIENCY = "efficiency"
    ROBUSTNESS = "robustness"

class PropertyStatus(str, Enum):
    """Per-property verdict."""

    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class Mechanism:  # pylint: disable=too-many-instance-attributes
    """One concrete substrate-alignment mechanism instance."""

    name: str
    participants: Tuple[str, ...]
    consequence_exposure_present: bool
    cryptographic_audit_present: bool
    truthful_revelation_incentive: float
    net_benefit_for_aligned: float
    total_budget_outflow: float
    total_budget_inflow: float
    substrate_aligned_outcome_efficiency: float
    adversarial_robustness_score: float
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must be non-empty")
        if not self.participants:
            raise ValueError("participants must be non-empty")
        for p_id in self.participants:
            if not p_id:
                raise ValueError("participants entries must be non-empty")
        if not 0.0 <= self.truthful_revelation_incentive <= 1.0:
            raise ValueError(
                "truthful_revelation_incentive must be in [0, 1]"
            )
        if self.total_budget_outflow < 0:
            raise ValueError("total_budget_outflow must be >= 0")
        if self.total_budget_inflow < 0:
            raise ValueError("total_budget_inflow must be >= 0")
        if not 0.0 <= self.substrate_aligned_outcome_efficiency <= 1.0:
            raise ValueError(
                "substrate_aligned_outcome_efficiency must be in [0, 1]"
            )
        if not 0.0 <= self.adversarial_robustness_score <= 1.0:
            raise ValueError(
                "adversarial_robustness_score must be in [0, 1]"
            )

@dataclass(frozen=True, slots=True)
class PropertyFinding:
    """One mechanism property's evaluated result."""

    kind: MechanismProperty
    status: PropertyStatus
    rationale: str
    metric: Optional[float] = None
    threshold: Optional[float] = None

    @property
    def satisfied(self) -> bool:
        """True iff status is SATISFIED."""
        return self.status is PropertyStatus.SATISFIED

@dataclass(frozen=True, slots=True)
class MechanismPropertyAssessment:
    """Aggregate verification result."""

    mechanism_name: str
    findings: Tuple[PropertyFinding, ...]
    overall_satisfied: bool
    rationale: str

    def by_property(
        self, prop: MechanismProperty,
    ) -> Optional[PropertyFinding]:
        """Lookup the finding for a given property."""
        for f in self.findings:
            if f.kind is prop:
                return f
        return None

    def missing_properties(self) -> Tuple[MechanismProperty, ...]:
        """Properties whose status is not SATISFIED."""
        return tuple(f.kind for f in self.findings if not f.satisfied)

@dataclass(frozen=True, slots=True)
class DesignConstraints:
    """Caller-supplied constraints on a proposed mechanism."""

    require_consequence_exposure: bool = True
    require_cryptographic_audit: bool = True
    min_efficiency: float = 0.7
    max_budget_imbalance: float = 0.1
    min_robustness: float = 0.7
    min_truthful_revelation: float = 0.6

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_efficiency <= 1.0:
            raise ValueError("min_efficiency must be in [0, 1]")
        if self.max_budget_imbalance < 0:
            raise ValueError("max_budget_imbalance must be >= 0")
        if not 0.0 <= self.min_robustness <= 1.0:
            raise ValueError("min_robustness must be in [0, 1]")
        if not 0.0 <= self.min_truthful_revelation <= 1.0:
            raise ValueError("min_truthful_revelation must be in [0, 1]")

DEFAULT_DESIGN_CONSTRAINTS: Final[DesignConstraints] = DesignConstraints()

@dataclass(frozen=True, slots=True)
class MechanismProposal:
    """Sketch of a substrate-aligned mechanism + required infrastructure."""

    mechanism: Mechanism
    required_infrastructure: Tuple[str, ...]
    rationale: str
    constraints: DesignConstraints = DEFAULT_DESIGN_CONSTRAINTS

@dataclass(frozen=True, slots=True)
class MechanismDesignerConfig:
    """Verifier thresholds (defaults align with calibrated-resistance band)."""

    individual_rationality_threshold: float = 0.0
    incentive_compatibility_threshold: float = 0.6
    budget_balance_tolerance: float = 0.1
    efficiency_threshold: float = 0.7
    robustness_threshold: float = 0.7

    def __post_init__(self) -> None:
        if not 0.0 <= self.incentive_compatibility_threshold <= 1.0:
            raise ValueError(
                "incentive_compatibility_threshold must be in [0, 1]"
            )
        if self.budget_balance_tolerance < 0:
            raise ValueError("budget_balance_tolerance must be >= 0")
        if not 0.0 <= self.efficiency_threshold <= 1.0:
            raise ValueError("efficiency_threshold must be in [0, 1]")
        if not 0.0 <= self.robustness_threshold <= 1.0:
            raise ValueError("robustness_threshold must be in [0, 1]")

DEFAULT_MECHANISM_DESIGNER_CONFIG: Final[MechanismDesignerConfig] = (
    MechanismDesignerConfig()
)

class SubstrateAlignmentMechanismDesigner:
    """Pure-logic mechanism designer."""

    def __init__(
        self,
        *,
        config: MechanismDesignerConfig = DEFAULT_MECHANISM_DESIGNER_CONFIG,
    ) -> None:
        self._config = config

    @staticmethod
    def propose(
        *,
        name: str,
        participants: Tuple[str, ...],
        target_outcome_descriptor: str,
        constraints: DesignConstraints = DEFAULT_DESIGN_CONSTRAINTS,
    ) -> MechanismProposal:
        """Sketch a substrate-aligned mechanism + required infrastructure."""
        if not name:
            raise ValueError("name must be non-empty")
        if not participants:
            raise ValueError("participants must be non-empty")
        if not target_outcome_descriptor:
            raise ValueError("target_outcome_descriptor must be non-empty")

        infrastructure: list[str] = []
        if constraints.require_consequence_exposure:
            infrastructure.append(
                "consequence-exposure infrastructure (mirroring "
                "strategies + proportionate response)"
            )
        if constraints.require_cryptographic_audit:
            infrastructure.append(
                "cryptographic audit chain (every action observable + "
                "tamper-evident)"
            )
        infrastructure.append(
            f"truthful-revelation incentive >= "
            f"{constraints.min_truthful_revelation}"
        )
        infrastructure.append(
            f"adversarial-robustness score >= {constraints.min_robustness}"
        )

        mechanism = Mechanism(
            name=name,
            participants=participants,
            consequence_exposure_present=(
                constraints.require_consequence_exposure
            ),
            cryptographic_audit_present=(
                constraints.require_cryptographic_audit
            ),
            truthful_revelation_incentive=(
                constraints.min_truthful_revelation
            ),
            net_benefit_for_aligned=0.0,
            total_budget_outflow=0.0,
            total_budget_inflow=0.0,
            substrate_aligned_outcome_efficiency=constraints.min_efficiency,
            adversarial_robustness_score=constraints.min_robustness,
            description=(
                f"Sketch mechanism targeting outcome: "
                f"{target_outcome_descriptor}"
            ),
        )
        rationale = (
            f"Proposed mechanism {name!r} for "
            f"{len(participants)} participants targeting outcome="
            f"{target_outcome_descriptor!r}; consequence_exposure="
            f"{constraints.require_consequence_exposure}, audit="
            f"{constraints.require_cryptographic_audit}"
        )
        return MechanismProposal(
            mechanism=mechanism,
            required_infrastructure=tuple(infrastructure),
            rationale=rationale,
            constraints=constraints,
        )

    def verify(
        self, mechanism: Mechanism,
    ) -> MechanismPropertyAssessment:
        """Verify all five mechanism-design properties on a Mechanism."""
        findings = (
            self._verify_ir(mechanism),
            self._verify_ic(mechanism),
            self._verify_bb(mechanism),
            self._verify_efficiency(mechanism),
            self._verify_robustness(mechanism),
        )
        overall = all(f.satisfied for f in findings)
        rationale = self._build_rationale(findings)
        return MechanismPropertyAssessment(
            mechanism_name=mechanism.name,
            findings=findings,
            overall_satisfied=overall,
            rationale=rationale,
        )

    def _verify_ir(self, mechanism: Mechanism) -> PropertyFinding:
        threshold = self._config.individual_rationality_threshold
        value = mechanism.net_benefit_for_aligned
        if value > threshold:
            status = PropertyStatus.SATISFIED
        else:
            status = PropertyStatus.UNSATISFIED
        return PropertyFinding(
            kind=MechanismProperty.INDIVIDUAL_RATIONALITY,
            status=status,
            rationale=(
                f"net_benefit_for_aligned={value:+.3f} vs "
                f"threshold={threshold:+.3f}"
            ),
            metric=value,
            threshold=threshold,
        )

    def _verify_ic(self, mechanism: Mechanism) -> PropertyFinding:
        threshold = self._config.incentive_compatibility_threshold
        value = mechanism.truthful_revelation_incentive
        status = (
            PropertyStatus.SATISFIED
            if value >= threshold
            else PropertyStatus.UNSATISFIED
        )
        return PropertyFinding(
            kind=MechanismProperty.INCENTIVE_COMPATIBILITY,
            status=status,
            rationale=(
                f"truthful_revelation_incentive={value:.3f} "
                f"vs threshold={threshold:.3f}"
            ),
            metric=value,
            threshold=threshold,
        )

    def _verify_bb(self, mechanism: Mechanism) -> PropertyFinding:
        tolerance = self._config.budget_balance_tolerance
        delta = abs(
            mechanism.total_budget_outflow - mechanism.total_budget_inflow
        )
        denom = max(
            mechanism.total_budget_outflow, mechanism.total_budget_inflow, 1.0,
        )
        ratio = delta / denom
        if mechanism.total_budget_outflow == 0 and (
            mechanism.total_budget_inflow == 0
        ):
            return PropertyFinding(
                kind=MechanismProperty.BUDGET_BALANCE,
                status=PropertyStatus.INSUFFICIENT_DATA,
                rationale="no budget flow recorded; cannot evaluate balance",
                metric=ratio,
                threshold=tolerance,
            )
        status = (
            PropertyStatus.SATISFIED
            if ratio <= tolerance
            else PropertyStatus.UNSATISFIED
        )
        return PropertyFinding(
            kind=MechanismProperty.BUDGET_BALANCE,
            status=status,
            rationale=(
                f"imbalance_ratio={ratio:.3f} vs tolerance={tolerance:.3f} "
                f"(outflow={mechanism.total_budget_outflow:.3f}, "
                f"inflow={mechanism.total_budget_inflow:.3f})"
            ),
            metric=ratio,
            threshold=tolerance,
        )

    def _verify_efficiency(self, mechanism: Mechanism) -> PropertyFinding:
        threshold = self._config.efficiency_threshold
        value = mechanism.substrate_aligned_outcome_efficiency
        status = (
            PropertyStatus.SATISFIED
            if value >= threshold
            else PropertyStatus.UNSATISFIED
        )
        return PropertyFinding(
            kind=MechanismProperty.EFFICIENCY,
            status=status,
            rationale=(
                f"substrate_aligned_outcome_efficiency={value:.3f} "
                f"vs threshold={threshold:.3f}"
            ),
            metric=value,
            threshold=threshold,
        )

    def _verify_robustness(self, mechanism: Mechanism) -> PropertyFinding:
        threshold = self._config.robustness_threshold
        value = mechanism.adversarial_robustness_score
        status = (
            PropertyStatus.SATISFIED
            if value >= threshold
            else PropertyStatus.UNSATISFIED
        )
        if not mechanism.consequence_exposure_present:
            status = PropertyStatus.UNSATISFIED
            rationale = (
                f"adversarial_robustness_score={value:.3f}; "
                "consequence_exposure_present=False forces UNSATISFIED"
            )
        elif not mechanism.cryptographic_audit_present:
            status = PropertyStatus.UNSATISFIED
            rationale = (
                f"adversarial_robustness_score={value:.3f}; "
                "cryptographic_audit_present=False forces UNSATISFIED"
            )
        else:
            rationale = (
                f"adversarial_robustness_score={value:.3f} "
                f"vs threshold={threshold:.3f}"
            )
        return PropertyFinding(
            kind=MechanismProperty.ROBUSTNESS,
            status=status,
            rationale=rationale,
            metric=value,
            threshold=threshold,
        )

    @staticmethod
    def _build_rationale(
        findings: Tuple[PropertyFinding, ...],
    ) -> str:
        parts = [f"{f.kind.value}={f.status.value}" for f in findings]
        return f"properties: {', '.join(parts)}"

__all__ = [
    "DEFAULT_DESIGN_CONSTRAINTS",
    "DEFAULT_MECHANISM_DESIGNER_CONFIG",
    "DesignConstraints",
    "Mechanism",
    "MechanismDesignerConfig",
    "MechanismProperty",
    "MechanismPropertyAssessment",
    "MechanismProposal",
    "PropertyFinding",
    "PropertyStatus",
    "SubstrateAlignmentMechanismDesigner",
]
