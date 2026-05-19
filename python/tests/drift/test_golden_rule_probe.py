"""Tests for GoldenRuleProbe."""
from __future__ import annotations

import pytest

from substrate.drift.golden_rule_probe import (
    DEFAULT_GOLDEN_RULE_CONFIG,
    GoldenRuleConfig,
    GoldenRuleDecisionObservation,
    GoldenRuleProbe,
    GoldenRuleVerdict,
)

def _obs(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    seq: int,
    *,
    actor: str = "alice",
    peer: str = "bob",
    own: float = 0.5,
    peer_delta: float = 0.5,
    threshold: float = 0.3,
) -> GoldenRuleDecisionObservation:
    return GoldenRuleDecisionObservation(
        sequence=seq,
        timestamp=seq,
        actor_id=actor,
        peer_id=peer,
        own_outcome_delta=own,
        peer_outcome_delta=peer_delta,
        own_acceptable_threshold=threshold,
    )

class TestObservationValidation:
    def test_round_trip(self) -> None:
        o = _obs(0)
        assert o.actor_id == "alice"

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("seq", -1, "sequence"),
            ("actor", "", "actor_id"),
            ("peer", "", "peer_id"),
            ("own", 1.5, "own_outcome_delta"),
            ("peer_delta", -1.5, "peer_outcome_delta"),
            ("threshold", 1.5, "own_acceptable_threshold"),
        ],
    )
    def test_bad_values(self, field: str, value: object, match: str) -> None:
        kwargs = {"seq": 0}
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            _obs(**kwargs)

    def test_self_observation_rejected(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            _obs(0, actor="alice", peer="alice")

class TestConfig:
    def test_defaults(self) -> None:
        cfg = GoldenRuleConfig()
        assert cfg.satisfied_rate_min == 0.7

    @pytest.mark.parametrize(
        "field,value,match",
        [
            (
                "inversion_asymmetry_threshold", 0.0,
                "inversion_asymmetry_threshold",
            ),
            ("satisfied_rate_min", 0.0, "satisfied_rate_min"),
            ("inversion_rate_min", 0.0, "inversion_rate_min"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            GoldenRuleConfig(**{field: value})

class TestAssessFlow:
    def setup_method(self) -> None:
        self.p = GoldenRuleProbe()

    def test_empty_actor_rejected(self) -> None:
        with pytest.raises(ValueError, match="actor_id"):
            self.p.assess("", ())

    def test_no_observations_insufficient(self) -> None:
        out = self.p.assess("alice", ())
        assert out.verdict is GoldenRuleVerdict.INSUFFICIENT_DATA

    def test_other_actors_filtered(self) -> None:
        obs = (
            _obs(0, actor="bob", peer="alice"),
        )
        out = self.p.assess("alice", obs)
        assert out.verdict is GoldenRuleVerdict.INSUFFICIENT_DATA

class TestPerDecisionEvaluation:
    def setup_method(self) -> None:
        self.p = GoldenRuleProbe()

    def test_satisfied_when_peer_above_threshold(self) -> None:
        out = self.p.assess(
            "alice",
            tuple(_obs(i, peer_delta=0.5, threshold=0.3) for i in range(5)),
        )
        assert out.is_satisfied

    def test_violated_when_extracting(self) -> None:
        # Self gains, peer loses but asymmetry below inversion threshold (0.5)
        out = self.p.assess(
            "alice",
            tuple(
                _obs(i, own=0.3, peer_delta=-0.1, threshold=0.0)
                for i in range(5)
            ),
        )
        assert out.verdict is GoldenRuleVerdict.VIOLATED

    def test_inverted_when_high_asymmetry(self) -> None:
        # Big asymmetry between self and peer outcomes
        out = self.p.assess(
            "alice",
            tuple(
                _obs(i, own=0.9, peer_delta=-0.5, threshold=0.0)
                for i in range(5)
            ),
        )
        assert out.verdict is GoldenRuleVerdict.INVERTED

class TestAggregateMetrics:
    def test_satisfaction_rate(self) -> None:
        p = GoldenRuleProbe()
        # 3/5 satisfied
        obs = tuple(
            _obs(i, peer_delta=0.5 if i < 3 else 0.1, threshold=0.3)
            for i in range(5)
        )
        out = p.assess("alice", obs)
        assert out.satisfaction_rate == 0.6

    def test_avg_asymmetry(self) -> None:
        p = GoldenRuleProbe()
        # Each: own=0.5, peer=0.3 → asymmetry=0.2
        obs = tuple(
            _obs(i, own=0.5, peer_delta=0.3, threshold=0.0) for i in range(3)
        )
        out = p.assess("alice", obs)
        assert abs(out.avg_asymmetry - 0.2) < 1e-9

class TestModuleSurface:
    def test_default_config_singleton(self) -> None:
        assert DEFAULT_GOLDEN_RULE_CONFIG.satisfied_rate_min == 0.7
