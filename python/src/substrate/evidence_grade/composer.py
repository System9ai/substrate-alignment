"""Deterministic evidence-grade composer.

Implements the algorithm in ``spec/evidence-grade.md`` § 3. Pure logic;
no DAO, no LLM, no network. Honest uncertainty: zero attestations
produce :attr:`EvidenceGrade.UNVERIFIED_HEARSAY` with the youngest /
oldest age set to ``+inf``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import (
    Final,
    Optional,
    Protocol,
    Sequence,
    runtime_checkable,
)


class EvidenceGrade(str, Enum):
    """Four-step evidence-grade ladder per ``spec/evidence-grade.md`` § 2.1.

    Ordered: ``UNVERIFIED_HEARSAY < CORROBORATED < ATTESTED <
    DOCUMENTED_CRYSTALLIZED``. The :attr:`_rank` mapping below provides
    a stable comparison key for downstream callers.
    """

    UNVERIFIED_HEARSAY = "unverified_hearsay"
    CORROBORATED = "corroborated"
    ATTESTED = "attested"
    DOCUMENTED_CRYSTALLIZED = "documented_crystallized"

    @property
    def rank(self) -> int:
        """Ordinal rank from 0 (weakest) to 3 (strongest)."""
        return _RANK_BY_GRADE[self]


#: Canonical iteration order, weakest-to-strongest.
EVIDENCE_GRADES: Final[tuple[EvidenceGrade, ...]] = (
    EvidenceGrade.UNVERIFIED_HEARSAY,
    EvidenceGrade.CORROBORATED,
    EvidenceGrade.ATTESTED,
    EvidenceGrade.DOCUMENTED_CRYSTALLIZED,
)


_RANK_BY_GRADE: Final[dict[EvidenceGrade, int]] = {
    grade: rank for rank, grade in enumerate(EVIDENCE_GRADES)
}


def _downgrade_one_step(grade: EvidenceGrade) -> EvidenceGrade:
    """Return the next-weaker grade, or ``UNVERIFIED_HEARSAY`` if at floor."""
    rank = grade.rank
    if rank == 0:
        return EvidenceGrade.UNVERIFIED_HEARSAY
    return EVIDENCE_GRADES[rank - 1]


@dataclass(frozen=True, slots=True)
class EvidenceAttestation:
    """Per spec/evidence-grade.md § 2.2."""

    source_id: str
    observed_at_epoch_seconds: float
    provenance_verified: bool

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("source_id must be non-empty")
        if math.isnan(self.observed_at_epoch_seconds):
            raise ValueError("observed_at_epoch_seconds must not be NaN")


@dataclass(frozen=True, slots=True)
class EvidenceComposition:
    """Per spec/evidence-grade.md § 2.3."""

    grade: EvidenceGrade
    attestation_count: int
    unique_source_count: int
    provenance_verified_count: int
    youngest_age_seconds: float
    oldest_age_seconds: float
    rationale: str

    def __post_init__(self) -> None:
        if self.attestation_count < 0:
            raise ValueError("attestation_count must be >= 0")
        if self.unique_source_count < 0:
            raise ValueError("unique_source_count must be >= 0")
        if self.unique_source_count > self.attestation_count:
            raise ValueError(
                "unique_source_count cannot exceed attestation_count"
            )
        if self.provenance_verified_count < 0:
            raise ValueError(
                "provenance_verified_count must be >= 0"
            )
        if self.provenance_verified_count > self.attestation_count:
            raise ValueError(
                "provenance_verified_count cannot exceed "
                "attestation_count"
            )
        if not self.rationale:
            raise ValueError("rationale must be non-empty")
        if self.youngest_age_seconds < 0 and not math.isinf(
            self.youngest_age_seconds
        ):
            raise ValueError("youngest_age_seconds must be >= 0 or +inf")
        if self.oldest_age_seconds < 0 and not math.isinf(
            self.oldest_age_seconds
        ):
            raise ValueError("oldest_age_seconds must be >= 0 or +inf")


@dataclass(frozen=True, slots=True)
class EvidenceGradeConfig:
    """Per spec/evidence-grade.md § 3.1.

    Defaults: 7-day half-life, downgrade beyond 2 × half-life.
    """

    decay_half_life_seconds: float
    decay_multiplier: float

    def __post_init__(self) -> None:
        if self.decay_half_life_seconds <= 0:
            raise ValueError(
                "decay_half_life_seconds must be > 0"
            )
        if self.decay_multiplier < 1.0:
            raise ValueError("decay_multiplier must be >= 1.0")


#: Default config from spec § 3.1. 7-day half-life, 2× multiplier.
DEFAULT_CONFIG: Final[EvidenceGradeConfig] = EvidenceGradeConfig(
    decay_half_life_seconds=7 * 24 * 3600,
    decay_multiplier=2.0,
)


@runtime_checkable
class SubstrateStateClaim(Protocol):
    """Per spec/evidence-grade.md § 2.4.

    Host applications declare conformance by exposing these attributes
    on their canonical-state records.
    """

    claim_id: str
    subject_entity_type: str
    subject_entity_id: str

    @property
    def attestations(self) -> Sequence[EvidenceAttestation]:
        ...

    @property
    def evidence_composition(self) -> EvidenceComposition:
        ...


def compose_evidence_grade(
    attestations: Sequence[EvidenceAttestation],
    *,
    now_epoch_seconds: float,
    config: Optional[EvidenceGradeConfig] = None,
) -> EvidenceComposition:
    """Deterministic algorithm per spec/evidence-grade.md § 3.

    Pure logic. The caller supplies the attestations and the wall-clock
    reference (``now_epoch_seconds``); the function does not read a
    clock.
    """
    cfg = config or DEFAULT_CONFIG
    attestation_count = len(attestations)
    unique_source_count = len({a.source_id for a in attestations})
    provenance_verified_count = sum(
        1 for a in attestations if a.provenance_verified
    )

    if attestation_count == 0:
        return EvidenceComposition(
            grade=EvidenceGrade.UNVERIFIED_HEARSAY,
            attestation_count=0,
            unique_source_count=0,
            provenance_verified_count=0,
            youngest_age_seconds=math.inf,
            oldest_age_seconds=math.inf,
            rationale="no attestations",
        )

    raw_ages = [
        now_epoch_seconds - a.observed_at_epoch_seconds
        for a in attestations
    ]
    ages = [max(age, 0.0) for age in raw_ages]
    youngest_age_seconds = min(ages)
    oldest_age_seconds = max(ages)

    base_grade, base_rationale = _classify_base_grade(
        unique_source_count=unique_source_count,
        provenance_verified_count=provenance_verified_count,
    )

    decay_threshold = (
        cfg.decay_half_life_seconds * cfg.decay_multiplier
    )
    decayed = (
        base_grade.rank > 0
        and youngest_age_seconds > decay_threshold
    )
    if decayed:
        final_grade = _downgrade_one_step(base_grade)
        rationale = (
            f"{base_rationale}; downgraded one step "
            f"(youngest_age={youngest_age_seconds:.0f}s > "
            f"{decay_threshold:.0f}s decay threshold)"
        )
    else:
        final_grade = base_grade
        rationale = base_rationale

    return EvidenceComposition(
        grade=final_grade,
        attestation_count=attestation_count,
        unique_source_count=unique_source_count,
        provenance_verified_count=provenance_verified_count,
        youngest_age_seconds=youngest_age_seconds,
        oldest_age_seconds=oldest_age_seconds,
        rationale=rationale,
    )


def _classify_base_grade(
    *,
    unique_source_count: int,
    provenance_verified_count: int,
) -> tuple[EvidenceGrade, str]:
    """Apply the rule-table from spec § 3 step 6."""
    if unique_source_count >= 3 and provenance_verified_count >= 1:
        return (
            EvidenceGrade.DOCUMENTED_CRYSTALLIZED,
            "three+ unique sources with at least one verified provenance",
        )
    if provenance_verified_count >= 1:
        return (
            EvidenceGrade.ATTESTED,
            "at least one attestation has verified provenance",
        )
    if unique_source_count >= 2:
        return (
            EvidenceGrade.CORROBORATED,
            "two+ unique sources without verified provenance",
        )
    return (
        EvidenceGrade.UNVERIFIED_HEARSAY,
        "single source without verified provenance",
    )


__all__ = [
    "DEFAULT_CONFIG",
    "EVIDENCE_GRADES",
    "EvidenceAttestation",
    "EvidenceComposition",
    "EvidenceGrade",
    "EvidenceGradeConfig",
    "SubstrateStateClaim",
    "compose_evidence_grade",
]
