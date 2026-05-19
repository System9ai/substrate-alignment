"""Tests for VotingPositionSubstrateModeClassifier (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.voting.position_classifier import (
    DEFAULT_POSITION_CLASSIFIER_CONFIG,
    PositionClassifierConfig,
    VotePositionType,
    VotingPositionFeatures,
    VotingPositionSubstrateModeClassifier,
)

def _features(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    election: str = "e-1",
    voter: str = "v-1",
    abstain: bool = False,
    npg: float = 0.8,
    citations: int = 2,
    resistance: bool = True,
    modeling: bool = True,
    extraction: float = 0.1,
) -> VotingPositionFeatures:
    return VotingPositionFeatures(
        election_id=election,
        voter_entity_id=voter,
        abstain=abstain,
        npg_composition_score=npg,
        peer_attestation_citation_count=citations,
        resistance_band_accounted=resistance,
        voter_in_modeling_mode=modeling,
        extraction_signal_score=extraction,
    )

class TestFeatureValidation:
    def test_round_trip(self) -> None:
        f = _features()
        assert f.npg_composition_score == 0.8

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("election", "", "election_id"),
            ("voter", "", "voter_entity_id"),
            ("npg", 1.5, "npg_composition_score"),
            ("citations", -1, "peer_attestation_citation_count"),
            ("extraction", 1.5, "extraction_signal_score"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _features(**kwargs)  # type: ignore[arg-type]

class TestConfig:
    def test_defaults(self) -> None:
        c = PositionClassifierConfig()
        assert c.extraction_threshold == 0.4

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("extraction_threshold", 0.0, "extraction_threshold"),
            ("aligned_npg_floor", 1.5, "aligned_npg_floor"),
            ("aligned_min_citations", -1, "aligned_min_citations"),
        ],
    )
    def test_bad_values(
        self, field: str, value: float, match: str,
    ) -> None:
        with pytest.raises(ValueError, match=match):
            PositionClassifierConfig(**{field: value})

class TestClassification:
    def setup_method(self) -> None:
        self.c = VotingPositionSubstrateModeClassifier()

    def test_substrate_aligned(self) -> None:
        out = self.c.classify(_features())
        assert out.position_type is VotePositionType.SUBSTRATE_ALIGNED
        assert out.weight_factor == 1.0
        assert out.aligned

    def test_extractive(self) -> None:
        out = self.c.classify(_features(extraction=0.7))
        assert out.position_type is VotePositionType.EXTRACTIVE
        assert out.weight_factor == 0.0

    def test_abstain(self) -> None:
        out = self.c.classify(_features(abstain=True))
        assert out.position_type is VotePositionType.ABSTAIN
        assert out.weight_factor == 0.0

    def test_reactive_mode(self) -> None:
        out = self.c.classify(_features(
            modeling=True, npg=0.2, citations=0, resistance=False,
        ))
        assert out.position_type is VotePositionType.REACTIVE_MODE
        assert out.weight_factor == 0.5

    def test_unclassified_no_modeling(self) -> None:
        out = self.c.classify(_features(modeling=False))
        assert out.position_type is VotePositionType.UNCLASSIFIED
        assert out.weight_factor == 0.25

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_POSITION_CLASSIFIER_CONFIG.extraction_threshold == 0.4
        )
