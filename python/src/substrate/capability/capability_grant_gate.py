"""Substrate-aware capability grant gate

The substrate-mechanical authorization primitive for **capability
grants** — the act of giving an entity the right to perform actions
(MCP tool access, agent permissions, resource access, role
assignments, key issuance, etc.). Per substrate condition #6

power-loophole prevention requires that capability concentration is
gated on substrate-alignment, not on raw policy alone.

The gate evaluates a proposed grant against four substrate criteria:

1. **Grantee substrate-coherence trust** — the Phase 23
   :class:`TrustScore` of the entity receiving the capability. A
   DRIFTING entity is HIGH severity; INSUFFICIENT_DATA is MEDIUM
   (review required, no fabricated trust); MIXED / TRUSTED carry
   per-sensitivity thresholds.
2. **Net potential gain on the grant action** — the Phase 1
   :class:`NetPotentialGainGate` is asked: does granting this
   capability produce net potential gain across the affected
   entities? NEGATIVE → DENY; INSUFFICIENT_DATA → review.
3. **Capability sensitivity** — operator-supplied classification of
   the capability's substrate-impact (LOW / MEDIUM / HIGH /
   CRITICAL). CRITICAL automatically routes through review unless
   the operator explicitly disables the auto-escalation.
4. **Blast radius** — the estimated number of entities the grant
   could affect. Each sensitivity tier carries a maximum-blast-
   radius constraint; exceeding it is HIGH severity, approaching it
   is MEDIUM.

Decision composition: HIGH on any criterion → **DENY**, MEDIUM on
any → **NEEDS_REVIEW**, all NONE/LOW → **GRANT**.

Pure logic
==========

* No DAO, no LLM, no network. The trust score is caller-supplied
  (Phase 23 :meth:`SubstrateCoherenceTrustScorer.score_from_ledger`);
  the NPG gate is injected via Protocol.
* Honest uncertainty. Trust INSUFFICIENT_DATA → MEDIUM. NPG
  INSUFFICIENT_DATA → MEDIUM. The gate refuses to fabricate trust.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping, Optional, Tuple

from substrate.net_potential_gain_gate import (
    NetPotentialGainGate,
    NetPotentialGainVerdict,
)
from substrate.trust.substrate_coherence_trust_scorer import (
    TrustScore,
    TrustVerdict,
)

class CapabilitySensitivity(str, Enum):
    """Operator-supplied capability sensitivity classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class CapabilityGrantVerdict(str, Enum):
    """Top-level outcome of a capability grant evaluation."""

    GRANT = "grant"
    NEEDS_REVIEW = "needs_review"
    DENY = "deny"

class CapabilityCriterionKind(str, Enum):
    """Which of the four substrate criteria a finding covers."""

    TRUST_LEVEL = "trust_level"
    NET_POTENTIAL_GAIN = "net_potential_gain"
    BLAST_RADIUS = "blast_radius"
    SENSITIVITY_ESCALATION = "sensitivity_escalation"

class CapabilityFindingSeverity(str, Enum):
    """Per-criterion severity, ordered NONE < LOW < MEDIUM < HIGH."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

_SEVERITY_ORDER: Final[Mapping[CapabilityFindingSeverity, int]] = {
    CapabilityFindingSeverity.NONE: 0,
    CapabilityFindingSeverity.LOW: 1,
    CapabilityFindingSeverity.MEDIUM: 2,
    CapabilityFindingSeverity.HIGH: 3,
}

_TRUST_ORDER: Final[Mapping[TrustVerdict, int]] = {
    TrustVerdict.INSUFFICIENT_DATA: 0,
    TrustVerdict.DRIFTING: 1,
    TrustVerdict.MIXED: 2,
    TrustVerdict.TRUSTED: 3,
}

@dataclass(frozen=True, slots=True)
class CapabilityCriterionFinding:
    """One criterion's evaluated result."""

    kind: CapabilityCriterionKind
    severity: CapabilityFindingSeverity
    rationale: str

    @property
    def passed(self) -> bool:
        """True iff severity is NONE or LOW."""
        return _SEVERITY_ORDER[self.severity] <= _SEVERITY_ORDER[
            CapabilityFindingSeverity.LOW
        ]

@dataclass(frozen=True, slots=True)
class CapabilityGrantDecision:
    """Aggregate decision over all criteria."""

    verdict: CapabilityGrantVerdict
    findings: Tuple[CapabilityCriterionFinding, ...]
    rationale: str

    @property
    def granted(self) -> bool:
        """True iff verdict is GRANT."""
        return self.verdict is CapabilityGrantVerdict.GRANT

    @property
    def needs_review(self) -> bool:
        """True iff verdict is NEEDS_REVIEW."""
        return self.verdict is CapabilityGrantVerdict.NEEDS_REVIEW

    @property
    def denied(self) -> bool:
        """True iff verdict is DENY."""
        return self.verdict is CapabilityGrantVerdict.DENY

    @property
    def highest_severity(self) -> CapabilityFindingSeverity:
        """Highest per-criterion severity across all findings."""
        if not self.findings:
            return CapabilityFindingSeverity.NONE
        return max(
            (f.severity for f in self.findings),
            key=_SEVERITY_ORDER.__getitem__,
        )

    def by_kind(
        self, kind: CapabilityCriterionKind,
    ) -> Optional[CapabilityCriterionFinding]:
        """Return the finding for a given criterion (None if absent)."""
        for f in self.findings:
            if f.kind is kind:
                return f
        return None

@dataclass(frozen=True, slots=True)
class CapabilityGrantRequest:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied capability grant request."""

    grantor_entity_id: str
    grantee_entity_id: str
    capability_id: str
    sensitivity: CapabilitySensitivity
    estimated_blast_radius: int
    grantee_trust_score: TrustScore
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
        if self.grantee_trust_score.entity_id != self.grantee_entity_id:
            raise ValueError(
                "grantee_trust_score.entity_id must match "
                "grantee_entity_id"
            )

@dataclass(frozen=True, slots=True)
class CapabilityGateConfig:  # pylint: disable=too-many-instance-attributes
    """Thresholds for criterion severity classification."""

    min_trust_for_low: TrustVerdict = TrustVerdict.MIXED
    min_trust_for_medium: TrustVerdict = TrustVerdict.MIXED
    min_trust_for_high: TrustVerdict = TrustVerdict.TRUSTED
    min_trust_for_critical: TrustVerdict = TrustVerdict.TRUSTED
    max_blast_radius_low: int = 1000
    max_blast_radius_medium: int = 100
    max_blast_radius_high: int = 10
    max_blast_radius_critical: int = 1
    blast_radius_medium_warn_fraction: float = 0.7
    require_review_for_critical: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_blast_radius_low",
            "max_blast_radius_medium",
            "max_blast_radius_high",
            "max_blast_radius_critical",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
        if not 0.0 < self.blast_radius_medium_warn_fraction < 1.0:
            raise ValueError(
                "blast_radius_medium_warn_fraction must be in (0, 1)"
            )

    def min_trust_for(
        self, sensitivity: CapabilitySensitivity,
    ) -> TrustVerdict:
        """Return the minimum acceptable trust for one sensitivity."""
        if sensitivity is CapabilitySensitivity.LOW:
            return self.min_trust_for_low
        if sensitivity is CapabilitySensitivity.MEDIUM:
            return self.min_trust_for_medium
        if sensitivity is CapabilitySensitivity.HIGH:
            return self.min_trust_for_high
        return self.min_trust_for_critical

    def max_blast_radius_for(
        self, sensitivity: CapabilitySensitivity,
    ) -> int:
        """Return the max blast radius for one sensitivity."""
        if sensitivity is CapabilitySensitivity.LOW:
            return self.max_blast_radius_low
        if sensitivity is CapabilitySensitivity.MEDIUM:
            return self.max_blast_radius_medium
        if sensitivity is CapabilitySensitivity.HIGH:
            return self.max_blast_radius_high
        return self.max_blast_radius_critical

DEFAULT_CAPABILITY_GATE_CONFIG: Final[CapabilityGateConfig] = (
    CapabilityGateConfig()
)

class SubstrateCapabilityGrantGate:  # pylint: disable=too-few-public-methods
    """Substrate-aware capability grant gate."""

    def __init__(
        self,
        *,
        npg_gate: NetPotentialGainGate,
        config: CapabilityGateConfig = DEFAULT_CAPABILITY_GATE_CONFIG,
    ) -> None:
        self._npg = npg_gate
        self._config = config

    def evaluate(
        self, request: CapabilityGrantRequest,
    ) -> CapabilityGrantDecision:
        """Evaluate one capability grant request against the four criteria."""
        findings = (
            self._evaluate_trust(request),
            self._evaluate_npg(request),
            self._evaluate_blast_radius(request),
            self._evaluate_sensitivity_escalation(request),
        )
        verdict = self._verdict_for(findings)
        rationale = self._build_rationale(verdict, findings)
        return CapabilityGrantDecision(
            verdict=verdict, findings=findings, rationale=rationale,
        )

    def _evaluate_trust(
        self, request: CapabilityGrantRequest,
    ) -> CapabilityCriterionFinding:
        grantee_verdict = request.grantee_trust_score.verdict
        if grantee_verdict is TrustVerdict.INSUFFICIENT_DATA:
            return CapabilityCriterionFinding(
                kind=CapabilityCriterionKind.TRUST_LEVEL,
                severity=CapabilityFindingSeverity.MEDIUM,
                rationale=(
                    "grantee trust score is INSUFFICIENT_DATA; "
                    "manual review required to avoid fabricating trust"
                ),
            )
        if grantee_verdict is TrustVerdict.DRIFTING:
            return CapabilityCriterionFinding(
                kind=CapabilityCriterionKind.TRUST_LEVEL,
                severity=CapabilityFindingSeverity.HIGH,
                rationale=(
                    "grantee trust verdict is DRIFTING; "
                    "substrate-misaligned operation pattern"
                ),
            )
        min_required = self._config.min_trust_for(request.sensitivity)
        if _TRUST_ORDER[grantee_verdict] < _TRUST_ORDER[min_required]:
            return CapabilityCriterionFinding(
                kind=CapabilityCriterionKind.TRUST_LEVEL,
                severity=CapabilityFindingSeverity.HIGH,
                rationale=(
                    f"grantee trust verdict {grantee_verdict.value} below "
                    f"required {min_required.value} for sensitivity "
                    f"{request.sensitivity.value}"
                ),
            )
        return CapabilityCriterionFinding(
            kind=CapabilityCriterionKind.TRUST_LEVEL,
            severity=CapabilityFindingSeverity.NONE,
            rationale=(
                f"grantee trust verdict {grantee_verdict.value} meets "
                f"required {min_required.value}"
            ),
        )

    def _evaluate_npg(
        self, request: CapabilityGrantRequest,
    ) -> CapabilityCriterionFinding:
        evaluation = self._npg.evaluate(
            actor_entity_id=request.grantor_entity_id,
            action_kind=request.grant_action_kind,
            affected_entity_ids=request.affected_entity_ids,
            proposed_outcome={},
        )
        verdict = evaluation.verdict
        if verdict is NetPotentialGainVerdict.NET_NEGATIVE:
            return CapabilityCriterionFinding(
                kind=CapabilityCriterionKind.NET_POTENTIAL_GAIN,
                severity=CapabilityFindingSeverity.HIGH,
                rationale=(
                    f"NPG NET_NEGATIVE on grant action; "
                    f"score={evaluation.score:+.3f}"
                ),
            )
        if verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA:
            return CapabilityCriterionFinding(
                kind=CapabilityCriterionKind.NET_POTENTIAL_GAIN,
                severity=CapabilityFindingSeverity.MEDIUM,
                rationale=(
                    "NPG INSUFFICIENT_DATA on grant action — "
                    "operator must enrich substrate metadata"
                ),
            )
        if (
            verdict is NetPotentialGainVerdict.NET_NEUTRAL
            and request.sensitivity
            in (
                CapabilitySensitivity.HIGH,
                CapabilitySensitivity.CRITICAL,
            )
        ):
            return CapabilityCriterionFinding(
                kind=CapabilityCriterionKind.NET_POTENTIAL_GAIN,
                severity=CapabilityFindingSeverity.LOW,
                rationale=(
                    "NPG NEUTRAL on a HIGH/CRITICAL-sensitivity grant; "
                    "operator should consider whether grant is necessary"
                ),
            )
        return CapabilityCriterionFinding(
            kind=CapabilityCriterionKind.NET_POTENTIAL_GAIN,
            severity=CapabilityFindingSeverity.NONE,
            rationale=(
                f"NPG {verdict.value}; score={evaluation.score:+.3f}"
            ),
        )

    def _evaluate_blast_radius(
        self, request: CapabilityGrantRequest,
    ) -> CapabilityCriterionFinding:
        max_radius = self._config.max_blast_radius_for(request.sensitivity)
        radius = request.estimated_blast_radius
        warn = max_radius * self._config.blast_radius_medium_warn_fraction
        if radius > max_radius:
            return CapabilityCriterionFinding(
                kind=CapabilityCriterionKind.BLAST_RADIUS,
                severity=CapabilityFindingSeverity.HIGH,
                rationale=(
                    f"estimated_blast_radius={radius} exceeds "
                    f"max {max_radius} for sensitivity "
                    f"{request.sensitivity.value}"
                ),
            )
        if radius >= warn:
            return CapabilityCriterionFinding(
                kind=CapabilityCriterionKind.BLAST_RADIUS,
                severity=CapabilityFindingSeverity.MEDIUM,
                rationale=(
                    f"estimated_blast_radius={radius} >= "
                    f"{warn:.0f} (warn threshold for sensitivity "
                    f"{request.sensitivity.value})"
                ),
            )
        return CapabilityCriterionFinding(
            kind=CapabilityCriterionKind.BLAST_RADIUS,
            severity=CapabilityFindingSeverity.NONE,
            rationale=(
                f"estimated_blast_radius={radius} below "
                f"warn threshold for sensitivity "
                f"{request.sensitivity.value}"
            ),
        )

    def _evaluate_sensitivity_escalation(
        self, request: CapabilityGrantRequest,
    ) -> CapabilityCriterionFinding:
        if (
            request.sensitivity is CapabilitySensitivity.CRITICAL
            and self._config.require_review_for_critical
        ):
            return CapabilityCriterionFinding(
                kind=CapabilityCriterionKind.SENSITIVITY_ESCALATION,
                severity=CapabilityFindingSeverity.MEDIUM,
                rationale=(
                    "CRITICAL-sensitivity capability — "
                    "operator review required by policy"
                ),
            )
        return CapabilityCriterionFinding(
            kind=CapabilityCriterionKind.SENSITIVITY_ESCALATION,
            severity=CapabilityFindingSeverity.NONE,
            rationale="no automatic escalation for this sensitivity",
        )

    @staticmethod
    def _verdict_for(
        findings: Tuple[CapabilityCriterionFinding, ...],
    ) -> CapabilityGrantVerdict:
        top = max(
            (f.severity for f in findings),
            key=_SEVERITY_ORDER.__getitem__,
            default=CapabilityFindingSeverity.NONE,
        )
        if top is CapabilityFindingSeverity.HIGH:
            return CapabilityGrantVerdict.DENY
        if top is CapabilityFindingSeverity.MEDIUM:
            return CapabilityGrantVerdict.NEEDS_REVIEW
        return CapabilityGrantVerdict.GRANT

    @staticmethod
    def _build_rationale(
        verdict: CapabilityGrantVerdict,
        findings: Tuple[CapabilityCriterionFinding, ...],
    ) -> str:
        parts = [
            f"{f.kind.value}={f.severity.value}"
            for f in findings
            if f.severity is not CapabilityFindingSeverity.NONE
        ]
        if not parts:
            return f"verdict={verdict.value}: all criteria clean"
        return f"verdict={verdict.value}: {', '.join(parts)}"

__all__ = [
    "CapabilityCriterionFinding",
    "CapabilityCriterionKind",
    "CapabilityFindingSeverity",
    "CapabilityGateConfig",
    "CapabilityGrantDecision",
    "CapabilityGrantRequest",
    "CapabilityGrantVerdict",
    "CapabilitySensitivity",
    "DEFAULT_CAPABILITY_GATE_CONFIG",
    "SubstrateCapabilityGrantGate",
]
