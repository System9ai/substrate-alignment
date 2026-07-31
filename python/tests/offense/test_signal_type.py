"""Tests for OffenseSignalClassifier (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.offense.signal_type import (
    DEFAULT_OFFENSE_CLASSIFIER_CONFIG,
    OffenseClassifierConfig,
    OffenseFeatures,
    OffenseSignalClassifier,
    OffenseSignalType,
)

def _features(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    actor: str = "alice",
    peer: str = "bob",
    boundary: float = 0.0,
    scarcity: float = 0.0,
    commitment: float = 0.0,
    capability: float = 0.0,
    attribution: float = 0.0,
    harm: float = 0.0,
) -> OffenseFeatures:
    return OffenseFeatures(
        actor_entity_id=actor,
        peer_entity_id=peer,
        boundary_trespass_score=boundary,
        scarcity_aggression_score=scarcity,
        accumulated_commitment_breach_score=commitment,
        capability_overreach_score=capability,
        attribution_concealment_score=attribution,
        asymmetric_harm_score=harm,
    )

class TestFeatureValidation:
    def test_round_trip(self) -> None:
        f = _features(boundary=0.5)
        assert f.boundary_trespass_score == 0.5

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("actor", "", "actor_entity_id"),
            ("peer", "", "peer_entity_id"),
            ("boundary", 1.5, "boundary_trespass_score"),
            ("scarcity", -0.1, "scarcity_aggression_score"),
            ("commitment", 1.5, "accumulated_commitment_breach_score"),
            ("capability", -0.1, "capability_overreach_score"),
            ("attribution", 1.5, "attribution_concealment_score"),
            ("harm", -0.1, "asymmetric_harm_score"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _features(**kwargs)

    def test_same_actor_peer_rejected(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            _features(actor="x", peer="x")

class TestConfig:
    def test_defaults(self) -> None:
        c = OffenseClassifierConfig()
        assert c.min_dominance_margin == 0.15

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("min_dominance_margin", 0.0, "min_dominance_margin"),
            ("min_dominance_margin", 1.5, "min_dominance_margin"),
            ("min_confidence_floor", 0.0, "min_confidence_floor"),
            ("min_confidence_floor", 1.5, "min_confidence_floor"),
        ],
    )
    def test_bad_values(
        self, field: str, value: float, match: str,
    ) -> None:
        with pytest.raises(ValueError, match=match):
            OffenseClassifierConfig(**{field: value})

class TestClassification:
    def setup_method(self) -> None:
        self.c = OffenseSignalClassifier()

    def test_boundary_trespass_classified(self) -> None:
        out = self.c.classify(_features(boundary=0.9))
        assert out.signal_type is OffenseSignalType.BOUNDARY_TRESPASS
        assert out.classified

    def test_scarcity_classified(self) -> None:
        out = self.c.classify(_features(scarcity=0.7))
        assert out.signal_type is OffenseSignalType.SCARCITY_AGGRESSION

    def test_commitment_breach_classified(self) -> None:
        out = self.c.classify(_features(commitment=0.8))
        assert (
            out.signal_type
            is OffenseSignalType.ACCUMULATED_COMMITMENT_BREACH
        )

    def test_capability_overreach_classified(self) -> None:
        out = self.c.classify(_features(capability=0.7))
        assert out.signal_type is OffenseSignalType.CAPABILITY_OVERREACH

    def test_attribution_concealment_classified(self) -> None:
        out = self.c.classify(_features(attribution=0.7))
        assert (
            out.signal_type is OffenseSignalType.ATTRIBUTION_CONCEALMENT
        )

    def test_asymmetric_harm_classified(self) -> None:
        out = self.c.classify(_features(harm=0.7))
        assert out.signal_type is OffenseSignalType.ASYMMETRIC_HARM

    def test_unclassified_low_confidence(self) -> None:
        out = self.c.classify(_features(boundary=0.3, scarcity=0.2))
        assert out.signal_type is OffenseSignalType.UNCLASSIFIED
        assert not out.classified

    def test_unclassified_low_margin(self) -> None:
        out = self.c.classify(_features(
            boundary=0.6, scarcity=0.55,
        ))
        assert out.signal_type is OffenseSignalType.UNCLASSIFIED

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_OFFENSE_CLASSIFIER_CONFIG.min_dominance_margin == 0.15
        )
