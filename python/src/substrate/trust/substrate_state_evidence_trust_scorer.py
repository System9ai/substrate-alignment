"""Substrate-state-evidence trust scorer — Companion #2

Pure-logic primitive that scores the *trustworthiness of an evidence
bundle* about an entity's substrate-state. Phase 23
:class:`SubstrateCoherenceTrustScorer` scores the entity itself from
its trace history; this scorer scores the *evidence about* an entity
from its provenance, freshness, attestation count, source diversity,
and provenance-chain integrity.

Downstream consumers (guard-relaxation curves, voting executors, cap
allocators) multiply their peer-trust weight by this evidence-trust
weight to avoid overweighting a single high-confidence assertion
backed by thin evidence.

Components
==========

1. **Freshness** — newer evidence weighted higher (exponential decay
   over the configured half-life).
2. **Attestation count** — log-saturating curve over the number of
   independent peer attestations.
3. **Source diversity** — entropy-like score over the unique sources
   contributing to the evidence bundle.
4. **Provenance-chain integrity** — fraction of attestations with
   verified cryptographic provenance.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the
  :class:`EvidenceBundle`.
* Honest uncertainty. Empty bundles produce
  :attr:`EvidenceTrustVerdict.INSUFFICIENT_DATA` with ``score=None``.
* Operator-overridable weights via :class:`EvidenceTrustConfig`.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Optional

class EvidenceTrustVerdict(str, Enum):
    """Trust verdict for a substrate-state evidence bundle."""

    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    """Caller-supplied evidence bundle to score."""

    subject_entity_id: str
    attestation_count: int
    unique_source_count: int
    provenance_verified_count: int
    youngest_attestation_age_seconds: float
    oldest_attestation_age_seconds: float

    def __post_init__(self) -> None:
        if not self.subject_entity_id:
            raise ValueError("subject_entity_id must be non-empty")
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
                "provenance_verified_count cannot exceed attestation_count"
            )
        if self.youngest_attestation_age_seconds < 0:
            raise ValueError(
                "youngest_attestation_age_seconds must be >= 0"
            )
        if self.oldest_attestation_age_seconds < 0:
            raise ValueError(
                "oldest_attestation_age_seconds must be >= 0"
            )
        if (
            self.oldest_attestation_age_seconds
            < self.youngest_attestation_age_seconds
        ):
            raise ValueError(
                "oldest_attestation_age_seconds must be >= youngest"
            )

@dataclass(frozen=True, slots=True)
class EvidenceTrustConfig:
    """Operator-tunable weights and thresholds."""

    freshness_half_life_seconds: float = 3600.0
    attestation_saturation_count: float = 10.0
    high_threshold: float = 0.75
    moderate_threshold: float = 0.5
    min_attestation_count: int = 2
    weights: tuple[float, float, float, float] = field(
        default=(0.25, 0.25, 0.25, 0.25),
    )

    def __post_init__(self) -> None:
        if self.freshness_half_life_seconds <= 0:
            raise ValueError(
                "freshness_half_life_seconds must be > 0"
            )
        if self.attestation_saturation_count <= 0:
            raise ValueError(
                "attestation_saturation_count must be > 0"
            )
        if not 0.0 < self.moderate_threshold < self.high_threshold <= 1.0:
            raise ValueError(
                "must satisfy 0 < moderate_threshold < "
                "high_threshold <= 1"
            )
        if self.min_attestation_count < 1:
            raise ValueError("min_attestation_count must be >= 1")
        if abs(sum(self.weights) - 1.0) > 1e-9:
            raise ValueError("weights must sum to 1.0")
        if any(w < 0.0 for w in self.weights):
            raise ValueError("weights must be non-negative")

DEFAULT_EVIDENCE_TRUST_CONFIG: Final[EvidenceTrustConfig] = (
    EvidenceTrustConfig()
)

@dataclass(frozen=True, slots=True)
class EvidenceTrustScore:  # pylint: disable=too-many-instance-attributes
    """Aggregate trust score for an evidence bundle."""

    subject_entity_id: str
    verdict: EvidenceTrustVerdict
    score: Optional[float]
    freshness_component: Optional[float]
    attestation_component: Optional[float]
    diversity_component: Optional[float]
    provenance_component: Optional[float]
    rationale: str

    @property
    def has_score(self) -> bool:
        """True iff a numeric score is available."""
        return self.score is not None

class SubstrateStateEvidenceTrustScorer:  # pylint: disable=too-few-public-methods
    """Pure-logic evidence trust scorer (Companion #2)."""

    def __init__(
        self,
        *,
        config: EvidenceTrustConfig = DEFAULT_EVIDENCE_TRUST_CONFIG,
    ) -> None:
        self._config = config

    def score(self, bundle: EvidenceBundle) -> EvidenceTrustScore:
        """Score an evidence bundle."""
        cfg = self._config
        if bundle.attestation_count < cfg.min_attestation_count:
            return EvidenceTrustScore(
                subject_entity_id=bundle.subject_entity_id,
                verdict=EvidenceTrustVerdict.INSUFFICIENT_DATA,
                score=None,
                freshness_component=None,
                attestation_component=None,
                diversity_component=None,
                provenance_component=None,
                rationale=(
                    f"attestation_count={bundle.attestation_count} "
                    f"below min {cfg.min_attestation_count}"
                ),
            )
        freshness = self._freshness(bundle, cfg)
        attestation = self._attestation(bundle, cfg)
        diversity = self._diversity(bundle)
        provenance = self._provenance(bundle)
        w_f, w_a, w_d, w_p = cfg.weights
        composite = (
            w_f * freshness
            + w_a * attestation
            + w_d * diversity
            + w_p * provenance
        )
        if composite >= cfg.high_threshold:
            verdict = EvidenceTrustVerdict.HIGH
        elif composite >= cfg.moderate_threshold:
            verdict = EvidenceTrustVerdict.MODERATE
        else:
            verdict = EvidenceTrustVerdict.LOW
        return EvidenceTrustScore(
            subject_entity_id=bundle.subject_entity_id,
            verdict=verdict,
            score=composite,
            freshness_component=freshness,
            attestation_component=attestation,
            diversity_component=diversity,
            provenance_component=provenance,
            rationale=(
                f"composite={composite:.3f} (freshness={freshness:.3f}, "
                f"attestation={attestation:.3f}, diversity={diversity:.3f}, "
                f"provenance={provenance:.3f})"
            ),
        )

    @staticmethod
    def _freshness(
        bundle: EvidenceBundle, cfg: EvidenceTrustConfig,
    ) -> float:
        decay = math.exp(
            -math.log(2.0)
            * bundle.youngest_attestation_age_seconds
            / cfg.freshness_half_life_seconds
        )
        return max(0.0, min(1.0, decay))

    @staticmethod
    def _attestation(
        bundle: EvidenceBundle, cfg: EvidenceTrustConfig,
    ) -> float:
        return min(
            1.0,
            math.log1p(bundle.attestation_count)
            / math.log1p(cfg.attestation_saturation_count),
        )

    @staticmethod
    def _diversity(bundle: EvidenceBundle) -> float:
        if bundle.attestation_count == 0:
            return 0.0
        return bundle.unique_source_count / bundle.attestation_count

    @staticmethod
    def _provenance(bundle: EvidenceBundle) -> float:
        if bundle.attestation_count == 0:
            return 0.0
        return (
            bundle.provenance_verified_count / bundle.attestation_count
        )

__all__ = [
    "DEFAULT_EVIDENCE_TRUST_CONFIG",
    "EvidenceBundle",
    "EvidenceTrustConfig",
    "EvidenceTrustScore",
    "EvidenceTrustVerdict",
    "SubstrateStateEvidenceTrustScorer",
]
