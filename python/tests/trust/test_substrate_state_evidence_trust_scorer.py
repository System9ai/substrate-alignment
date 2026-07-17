"""Tests for SubstrateStateEvidenceTrustScorer (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.trust.substrate_state_evidence_trust_scorer import (
    DEFAULT_EVIDENCE_TRUST_CONFIG,
    EvidenceBundle,
    EvidenceTrustConfig,
    EvidenceTrustVerdict,
    SubstrateStateEvidenceTrustScorer,
)

def _bundle(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    subject: str = "agent-1",
    attest: int = 10,
    sources: int = 8,
    provenance: int = 9,
    youngest: float = 60.0,
    oldest: float = 1800.0,
) -> EvidenceBundle:
    return EvidenceBundle(
        subject_entity_id=subject,
        attestation_count=attest,
        unique_source_count=sources,
        provenance_verified_count=provenance,
        youngest_attestation_age_seconds=youngest,
        oldest_attestation_age_seconds=oldest,
    )

class TestBundleValidation:
    def test_round_trip(self) -> None:
        b = _bundle()
        assert b.attestation_count == 10

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("subject", "", "subject_entity_id"),
            ("attest", -1, "attestation_count"),
            ("sources", -1, "unique_source_count"),
            ("provenance", -1, "provenance_verified_count"),
            ("youngest", -1.0, "youngest_attestation_age_seconds"),
            ("oldest", -1.0, "oldest_attestation_age_seconds"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _bundle(**kwargs)

    def test_sources_cannot_exceed_attestations(self) -> None:
        with pytest.raises(ValueError, match="unique_source_count"):
            _bundle(attest=2, sources=3, provenance=2)

    def test_provenance_cannot_exceed_attestations(self) -> None:
        with pytest.raises(
            ValueError, match="provenance_verified_count",
        ):
            _bundle(attest=2, sources=1, provenance=3)

    def test_youngest_oldest_ordering(self) -> None:
        with pytest.raises(ValueError, match="oldest"):
            _bundle(youngest=1000.0, oldest=10.0)

class TestConfig:
    def test_defaults(self) -> None:
        c = EvidenceTrustConfig()
        assert c.high_threshold == 0.75

    def test_weights_must_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="weights must sum"):
            EvidenceTrustConfig(weights=(0.5, 0.5, 0.5, 0.5))

    def test_negative_weights_rejected(self) -> None:
        with pytest.raises(
            ValueError, match="weights must be non-negative",
        ):
            EvidenceTrustConfig(weights=(-0.1, 0.4, 0.4, 0.3))

    def test_threshold_ordering(self) -> None:
        with pytest.raises(ValueError, match="moderate_threshold"):
            EvidenceTrustConfig(high_threshold=0.5, moderate_threshold=0.7)

class TestScoring:
    def setup_method(self) -> None:
        self.s = SubstrateStateEvidenceTrustScorer()

    def test_high_trust(self) -> None:
        out = self.s.score(_bundle(
            attest=15, sources=12, provenance=15,
            youngest=10.0, oldest=600.0,
        ))
        assert out.verdict is EvidenceTrustVerdict.HIGH

    def test_low_trust(self) -> None:
        out = self.s.score(_bundle(
            attest=3, sources=1, provenance=0,
            youngest=86400.0, oldest=86400.0,
        ))
        assert out.verdict is EvidenceTrustVerdict.LOW

    def test_insufficient_data(self) -> None:
        out = self.s.score(_bundle(attest=1, sources=1, provenance=1))
        assert out.verdict is EvidenceTrustVerdict.INSUFFICIENT_DATA
        assert out.score is None
        assert not out.has_score

    def test_components_all_present(self) -> None:
        out = self.s.score(_bundle())
        assert out.has_score
        assert (
            out.freshness_component is not None
            and out.attestation_component is not None
            and out.diversity_component is not None
            and out.provenance_component is not None
        )

    def test_diversity_zero_when_one_source(self) -> None:
        out = self.s.score(_bundle(attest=10, sources=1, provenance=10))
        assert out.diversity_component == 0.1

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_EVIDENCE_TRUST_CONFIG.freshness_half_life_seconds
            == 3600.0
        )
