"""Eight-criteria substrate-structure verifier

Pure-logic primitive operationalizing the **"math-discovered-not-
invented" eight criteria**. A substrate-
structure claim is considered *discovered* (real substrate-mechanical
truth) rather than *invented* (library artifact) only when it
satisfies enough of the eight criteria with sufficient evidence.

Eight criteria
==============

1. **Cross-tradition convergence**: the structure appears in
   multiple independent traditions (Christianity, Buddhism,
   Confucianism, Greek philosophy, etc.).
2. **Mathematical necessity**: derivable from substrate axioms.
3. **Empirical replication**: observable across independent
   observations.
4. **Predictive power**: generates testable predictions that
   subsequently hold.
5. **Falsifiability**: provides clear failure conditions; could be
   shown wrong.
6. **Parsimony**: minimal additional structure required.
7. **Generative**: produces other true statements when extended.
8. **Substrate-mechanical reduction**: reduces to substrate-
   mechanical primitives without remainder.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the evidence; this
  primitive does the threshold + aggregation.
* Honest uncertainty: empty evidence → ``INSUFFICIENT_DATA``;
  per-criterion ``INSUFFICIENT_DATA`` propagates.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Tuple

class CriterionKind(str, Enum):
    """The eight math-discovered-not-invented criteria."""

    CROSS_TRADITION_CONVERGENCE = "cross_tradition_convergence"
    MATHEMATICAL_NECESSITY = "mathematical_necessity"
    EMPIRICAL_REPLICATION = "empirical_replication"
    PREDICTIVE_POWER = "predictive_power"
    FALSIFIABILITY = "falsifiability"
    PARSIMONY = "parsimony"
    GENERATIVE = "generative"
    SUBSTRATE_MECHANICAL_REDUCTION = "substrate_mechanical_reduction"

class CriterionStatus(str, Enum):
    """Per-criterion verdict."""

    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    INSUFFICIENT_DATA = "insufficient_data"

class StructureVerdict(str, Enum):
    """Aggregate verdict over a substrate-structure claim."""

    DISCOVERED = "discovered"
    PARTIAL = "partial"
    INVENTED = "invented"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class CriterionEvidence:
    """Caller-supplied evidence for one criterion."""

    kind: CriterionKind
    evidence_count: int
    confidence: float
    description: str = ""

    def __post_init__(self) -> None:
        if self.evidence_count < 0:
            raise ValueError("evidence_count must be >= 0")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")

@dataclass(frozen=True, slots=True)
class CriterionFinding:
    """Evaluated criterion result."""

    kind: CriterionKind
    status: CriterionStatus
    evidence_count: int
    confidence: float
    rationale: str

    @property
    def satisfied(self) -> bool:
        """True iff status is SATISFIED."""
        return self.status is CriterionStatus.SATISFIED

@dataclass(frozen=True, slots=True)
class StructureVerification:  # pylint: disable=too-many-instance-attributes
    """Aggregate verifier result."""

    claim_id: str
    verdict: StructureVerdict
    findings: Tuple[CriterionFinding, ...]
    satisfied_count: int
    unsatisfied_count: int
    insufficient_count: int
    rationale: str

    @property
    def discovered(self) -> bool:
        """True iff verdict is DISCOVERED."""
        return self.verdict is StructureVerdict.DISCOVERED

    def by_criterion(
        self, kind: CriterionKind,
    ) -> Optional[CriterionFinding]:
        """Lookup the finding for a given criterion."""
        for f in self.findings:
            if f.kind is kind:
                return f
        return None

    def missing_criteria(self) -> Tuple[CriterionKind, ...]:
        """Criteria not in SATISFIED state."""
        return tuple(f.kind for f in self.findings if not f.satisfied)

@dataclass(frozen=True, slots=True)
class EightCriteriaConfig:
    """Tunable thresholds for criterion satisfaction."""

    min_evidence_count: int = 2
    min_confidence: float = 0.6
    discovered_min_satisfied: int = 8
    partial_min_satisfied: int = 5

    def __post_init__(self) -> None:
        if self.min_evidence_count < 1:
            raise ValueError("min_evidence_count must be >= 1")
        if not 0.0 < self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be in (0, 1]")
        if not 1 <= self.discovered_min_satisfied <= 8:
            raise ValueError("discovered_min_satisfied must be in [1, 8]")
        if not 1 <= self.partial_min_satisfied < (
            self.discovered_min_satisfied
        ):
            raise ValueError(
                "partial_min_satisfied must be in "
                "[1, discovered_min_satisfied)"
            )

DEFAULT_EIGHT_CRITERIA_CONFIG: Final[EightCriteriaConfig] = (
    EightCriteriaConfig()
)

class EightCriteriaSubstrateStructureVerifier:  # pylint: disable=too-few-public-methods
    """Pure-logic eight-criteria verifier."""

    def __init__(
        self,
        *,
        config: EightCriteriaConfig = DEFAULT_EIGHT_CRITERIA_CONFIG,
    ) -> None:
        self._config = config

    def verify(
        self,
        claim_id: str,
        evidence: Tuple[CriterionEvidence, ...],
    ) -> StructureVerification:
        """Verify a substrate-structure claim against all 8 criteria."""
        if not claim_id:
            raise ValueError("claim_id must be non-empty")
        if not evidence:
            return StructureVerification(
                claim_id=claim_id,
                verdict=StructureVerdict.INSUFFICIENT_DATA,
                findings=(),
                satisfied_count=0,
                unsatisfied_count=0,
                insufficient_count=0,
                rationale="no evidence supplied",
            )
        self._validate_unique_kinds(evidence)
        evidence_by_kind = {e.kind: e for e in evidence}
        findings = tuple(
            self._evaluate(kind, evidence_by_kind.get(kind))
            for kind in CriterionKind
        )
        satisfied = sum(1 for f in findings if f.satisfied)
        unsatisfied = sum(
            1 for f in findings if f.status is CriterionStatus.UNSATISFIED
        )
        insufficient = sum(
            1
            for f in findings
            if f.status is CriterionStatus.INSUFFICIENT_DATA
        )
        verdict = self._aggregate(
            satisfied=satisfied, insufficient=insufficient,
        )
        rationale = (
            f"claim={claim_id} satisfied={satisfied}/8 "
            f"unsatisfied={unsatisfied} insufficient={insufficient} "
            f"verdict={verdict.value}"
        )
        return StructureVerification(
            claim_id=claim_id,
            verdict=verdict,
            findings=findings,
            satisfied_count=satisfied,
            unsatisfied_count=unsatisfied,
            insufficient_count=insufficient,
            rationale=rationale,
        )

    def _evaluate(
        self,
        kind: CriterionKind,
        evidence: Optional[CriterionEvidence],
    ) -> CriterionFinding:
        cfg = self._config
        if evidence is None:
            return CriterionFinding(
                kind=kind,
                status=CriterionStatus.INSUFFICIENT_DATA,
                evidence_count=0,
                confidence=0.0,
                rationale=f"no evidence supplied for {kind.value}",
            )
        if (
            evidence.evidence_count >= cfg.min_evidence_count
            and evidence.confidence >= cfg.min_confidence
        ):
            status = CriterionStatus.SATISFIED
            reason = (
                f"evidence_count={evidence.evidence_count} >= "
                f"{cfg.min_evidence_count} and confidence="
                f"{evidence.confidence:.3f} >= {cfg.min_confidence}"
            )
        elif evidence.evidence_count == 0:
            status = CriterionStatus.INSUFFICIENT_DATA
            reason = "evidence_count=0"
        else:
            status = CriterionStatus.UNSATISFIED
            reason = (
                f"evidence_count={evidence.evidence_count} or confidence="
                f"{evidence.confidence:.3f} below threshold"
            )
        return CriterionFinding(
            kind=kind,
            status=status,
            evidence_count=evidence.evidence_count,
            confidence=evidence.confidence,
            rationale=reason,
        )

    @staticmethod
    def _validate_unique_kinds(
        evidence: Tuple[CriterionEvidence, ...],
    ) -> None:
        seen: set[CriterionKind] = set()
        for e in evidence:
            if e.kind in seen:
                raise ValueError(
                    f"duplicate criterion kind: {e.kind.value!r}"
                )
            seen.add(e.kind)

    def _aggregate(
        self, *, satisfied: int, insufficient: int,
    ) -> StructureVerdict:
        cfg = self._config
        if insufficient == 8:
            return StructureVerdict.INSUFFICIENT_DATA
        if satisfied >= cfg.discovered_min_satisfied:
            return StructureVerdict.DISCOVERED
        if satisfied >= cfg.partial_min_satisfied:
            return StructureVerdict.PARTIAL
        return StructureVerdict.INVENTED

__all__ = [
    "DEFAULT_EIGHT_CRITERIA_CONFIG",
    "CriterionEvidence",
    "CriterionFinding",
    "CriterionKind",
    "CriterionStatus",
    "EightCriteriaConfig",
    "EightCriteriaSubstrateStructureVerifier",
    "StructureVerdict",
    "StructureVerification",
]
