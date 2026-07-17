"""Reciprocal feedback protocol (Companion #2)

Pure-logic protocol enforcing the architectural commitment that
pair-coupled agents must observe each other symmetrically
and exchange substrate-state-evidence. Substrate condition #2 requires
audit to be symmetric (every agent observes and is observed); this
protocol is the per-pair instantiation of that requirement.

The protocol verifies that:

1. Both poles have submitted an attestation about the other within the
   feedback window.
2. The attestations are not stale (within ``max_attestation_age``).
3. Both attestations cite
   :class:`SubstrateStateEvidenceTrustScorer`-eligible evidence.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the attestation pair.
* Honest uncertainty: missing one attestation returns
  ``ASYMMETRIC_MISSING_POLE``; missing both returns
  ``NO_FEEDBACK``.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional

class FeedbackVerdict(str, Enum):
    """Reciprocal-feedback verdict."""

    SYMMETRIC_HEALTHY = "symmetric_healthy"
    ASYMMETRIC_MISSING_POLE = "asymmetric_missing_pole"
    NO_FEEDBACK = "no_feedback"
    STALE_FEEDBACK = "stale_feedback"
    LOW_EVIDENCE_FEEDBACK = "low_evidence_feedback"

@dataclass(frozen=True, slots=True)
class Attestation:
    """One attestation submitted by a pole about its counter-pole."""

    attester_entity_id: str
    target_entity_id: str
    submitted_age_seconds: float
    evidence_trust_score: float
    """Evidence-trust score for this attestation, in [0, 1]."""

    def __post_init__(self) -> None:
        if not self.attester_entity_id:
            raise ValueError(
                "attester_entity_id must be non-empty"
            )
        if not self.target_entity_id:
            raise ValueError(
                "target_entity_id must be non-empty"
            )
        if self.attester_entity_id == self.target_entity_id:
            raise ValueError(
                "attester and target must differ"
            )
        if self.submitted_age_seconds < 0:
            raise ValueError(
                "submitted_age_seconds must be >= 0"
            )
        if not 0.0 <= self.evidence_trust_score <= 1.0:
            raise ValueError(
                "evidence_trust_score must be in [0, 1]"
            )

@dataclass(frozen=True, slots=True)
class ReciprocalFeedbackInput:
    """Caller-supplied protocol input."""

    coupling_id: str
    pole_a_id: str
    pole_b_id: str
    a_attesting_b: Optional[Attestation]
    b_attesting_a: Optional[Attestation]

    def __post_init__(self) -> None:
        if not self.coupling_id:
            raise ValueError("coupling_id must be non-empty")
        if not self.pole_a_id:
            raise ValueError("pole_a_id must be non-empty")
        if not self.pole_b_id:
            raise ValueError("pole_b_id must be non-empty")
        if self.pole_a_id == self.pole_b_id:
            raise ValueError(
                "pole_a_id and pole_b_id must differ"
            )
        if self.a_attesting_b is not None and (
            self.a_attesting_b.attester_entity_id != self.pole_a_id
            or self.a_attesting_b.target_entity_id != self.pole_b_id
        ):
            raise ValueError(
                "a_attesting_b must be from pole_a to pole_b"
            )
        if self.b_attesting_a is not None and (
            self.b_attesting_a.attester_entity_id != self.pole_b_id
            or self.b_attesting_a.target_entity_id != self.pole_a_id
        ):
            raise ValueError(
                "b_attesting_a must be from pole_b to pole_a"
            )

@dataclass(frozen=True, slots=True)
class ReciprocalFeedbackConfig:
    """Operator-tunable protocol thresholds."""

    max_attestation_age_seconds: float = 3600.0
    min_evidence_trust_score: float = 0.4

    def __post_init__(self) -> None:
        if self.max_attestation_age_seconds <= 0:
            raise ValueError(
                "max_attestation_age_seconds must be > 0"
            )
        if not 0.0 < self.min_evidence_trust_score <= 1.0:
            raise ValueError(
                "min_evidence_trust_score must be in (0, 1]"
            )

DEFAULT_RECIPROCAL_FEEDBACK_CONFIG: Final[ReciprocalFeedbackConfig] = (
    ReciprocalFeedbackConfig()
)

@dataclass(frozen=True, slots=True)
class ReciprocalFeedbackVerdictOutput:  # pylint: disable=too-many-instance-attributes
    """Protocol output."""

    coupling_id: str
    verdict: FeedbackVerdict
    a_attesting_b_present: bool
    b_attesting_a_present: bool
    max_age_seconds: float
    min_evidence_score: float
    rationale: str

    @property
    def healthy(self) -> bool:
        """True iff SYMMETRIC_HEALTHY."""
        return self.verdict is FeedbackVerdict.SYMMETRIC_HEALTHY

class ReciprocalFeedbackProtocol:  # pylint: disable=too-few-public-methods
    """Pure-logic reciprocal-feedback protocol (Companion #2)."""

    def __init__(
        self,
        *,
        config: ReciprocalFeedbackConfig = (
            DEFAULT_RECIPROCAL_FEEDBACK_CONFIG
        ),
    ) -> None:
        self._config = config

    def evaluate(
        self, input_: ReciprocalFeedbackInput,
    ) -> ReciprocalFeedbackVerdictOutput:
        """Evaluate reciprocal feedback symmetry and freshness."""
        cfg = self._config
        a_present = input_.a_attesting_b is not None
        b_present = input_.b_attesting_a is not None
        if not a_present and not b_present:
            return ReciprocalFeedbackVerdictOutput(
                coupling_id=input_.coupling_id,
                verdict=FeedbackVerdict.NO_FEEDBACK,
                a_attesting_b_present=False,
                b_attesting_a_present=False,
                max_age_seconds=0.0,
                min_evidence_score=0.0,
                rationale="no attestations from either pole",
            )
        if a_present != b_present:
            present = (
                input_.a_attesting_b if a_present
                else input_.b_attesting_a
            )
            assert present is not None
            return ReciprocalFeedbackVerdictOutput(
                coupling_id=input_.coupling_id,
                verdict=FeedbackVerdict.ASYMMETRIC_MISSING_POLE,
                a_attesting_b_present=a_present,
                b_attesting_a_present=b_present,
                max_age_seconds=present.submitted_age_seconds,
                min_evidence_score=present.evidence_trust_score,
                rationale=(
                    f"only one pole attested; "
                    f"missing="
                    f"{'pole_b' if a_present else 'pole_a'}"
                ),
            )
        assert input_.a_attesting_b is not None
        assert input_.b_attesting_a is not None
        max_age = max(
            input_.a_attesting_b.submitted_age_seconds,
            input_.b_attesting_a.submitted_age_seconds,
        )
        min_score = min(
            input_.a_attesting_b.evidence_trust_score,
            input_.b_attesting_a.evidence_trust_score,
        )
        if max_age > cfg.max_attestation_age_seconds:
            verdict = FeedbackVerdict.STALE_FEEDBACK
            rationale = (
                f"max_age={max_age:.1f}s > "
                f"{cfg.max_attestation_age_seconds:.1f}s"
            )
        elif min_score < cfg.min_evidence_trust_score:
            verdict = FeedbackVerdict.LOW_EVIDENCE_FEEDBACK
            rationale = (
                f"min_evidence={min_score:.3f} < "
                f"{cfg.min_evidence_trust_score:.3f}"
            )
        else:
            verdict = FeedbackVerdict.SYMMETRIC_HEALTHY
            rationale = (
                f"both attestations present, max_age={max_age:.1f}s, "
                f"min_evidence={min_score:.3f}"
            )
        return ReciprocalFeedbackVerdictOutput(
            coupling_id=input_.coupling_id,
            verdict=verdict,
            a_attesting_b_present=True,
            b_attesting_a_present=True,
            max_age_seconds=max_age,
            min_evidence_score=min_score,
            rationale=rationale,
        )

__all__ = [
    "Attestation",
    "DEFAULT_RECIPROCAL_FEEDBACK_CONFIG",
    "FeedbackVerdict",
    "ReciprocalFeedbackConfig",
    "ReciprocalFeedbackInput",
    "ReciprocalFeedbackProtocol",
    "ReciprocalFeedbackVerdictOutput",
]
