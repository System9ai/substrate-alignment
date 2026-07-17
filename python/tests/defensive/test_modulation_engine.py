"""Tests for DefensiveModulationEngine."""
from __future__ import annotations

import pytest

from substrate.defensive.modulation_engine import (
    DEFAULT_DEFENSIVE_MODULATION_CONFIG,
    AttackObservation,
    AttackPattern,
    DefensiveModulationConfig,
    DefensiveModulationEngine,
    DefensiveResponse,
)

def _obs(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    seq: int,
    *,
    peer: str = "bob",
    pattern: AttackPattern = AttackPattern.MANIPULATION,
    severity: float = 0.5,
    long_cycle: bool = False,
    repeated: bool = False,
) -> AttackObservation:
    return AttackObservation(
        sequence=seq,
        timestamp=seq,
        peer_id=peer,
        pattern=pattern,
        severity=severity,
        long_cycle_framed=long_cycle,
        repeated=repeated,
    )

class TestAttackObservation:
    def test_round_trip(self) -> None:
        o = _obs(0)
        assert o.pattern is AttackPattern.MANIPULATION

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("seq", -1, "sequence"),
            ("peer", "", "peer_id"),
        ],
    )
    def test_bad_values(self, field: str, value: object, match: str) -> None:
        kwargs = {"seq": 0, "peer": "bob"}
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            _obs(**kwargs)

    def test_severity_range(self) -> None:
        with pytest.raises(ValueError, match="severity"):
            _obs(0, severity=1.5)

class TestConfig:
    def test_defaults(self) -> None:
        cfg = DefensiveModulationConfig()
        assert cfg.attack_severity_threshold == 0.1

    @pytest.mark.parametrize(
        "field,value,match",
        [
            (
                "attack_severity_threshold", 0.0,
                "attack_severity_threshold",
            ),
            ("walk_away_severity_max", 0.05, "walk_away_severity_max"),
            (
                "containment_severity_max", 0.2,
                "containment_severity_max",
            ),
            ("termination_severity_min", 0.5, "termination_severity_min"),
        ],
    )
    def test_bad_ordering(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            DefensiveModulationConfig(**{field: value})

class TestAssessFlow:
    def setup_method(self) -> None:
        self.e = DefensiveModulationEngine()

    def test_empty_peer_rejected(self) -> None:
        with pytest.raises(ValueError, match="peer_id"):
            self.e.assess("", ())

    def test_no_observations_insufficient(self) -> None:
        out = self.e.assess("bob", ())
        assert out.response is DefensiveResponse.INSUFFICIENT_DATA
        assert not out.attack_present

    def test_other_peer_filtered(self) -> None:
        obs = (_obs(0, peer="carol", severity=0.9),)
        out = self.e.assess("bob", obs)
        assert out.response is DefensiveResponse.INSUFFICIENT_DATA

class TestResponseSelection:
    def setup_method(self) -> None:
        self.e = DefensiveModulationEngine()

    def test_below_threshold_no_attack(self) -> None:
        out = self.e.assess("bob", (_obs(0, severity=0.05),))
        assert out.response is DefensiveResponse.NO_ATTACK_DETECTED

    def test_low_severity_walk_away(self) -> None:
        out = self.e.assess("bob", (_obs(0, severity=0.2),))
        assert out.response is DefensiveResponse.WOUND_AND_WALK_AWAY

    def test_moderate_reformable_reform(self) -> None:
        out = self.e.assess(
            "bob", (_obs(0, severity=0.4, pattern=AttackPattern.MANIPULATION),),
        )
        assert out.response is DefensiveResponse.REFORM_VIA_ENGAGEMENT

    def test_moderate_non_reformable_containment(self) -> None:
        out = self.e.assess(
            "bob",
            (
                _obs(
                    0,
                    severity=0.4,
                    pattern=AttackPattern.SUBSTRATE_STATE_EXTRACTION,
                ),
            ),
        )
        assert out.response is DefensiveResponse.CONTAINMENT

    def test_high_severity_containment(self) -> None:
        out = self.e.assess("bob", (_obs(0, severity=0.7),))
        assert out.response is DefensiveResponse.CONTAINMENT

    def test_extreme_severity_termination(self) -> None:
        out = self.e.assess("bob", (_obs(0, severity=0.9),))
        assert out.response is DefensiveResponse.TOTAL_TERMINATION

    def test_repeated_offense_escalates(self) -> None:
        out = self.e.assess(
            "bob",
            (
                _obs(0, severity=0.7, repeated=True),
                _obs(1, severity=0.7, repeated=True),
            ),
        )
        assert out.response is DefensiveResponse.TOTAL_TERMINATION

class TestInversionDetection:
    def setup_method(self) -> None:
        self.e = DefensiveModulationEngine()

    def test_explicit_inversion_flagged(self) -> None:
        out = self.e.assess(
            "bob",
            (_obs(0, pattern=AttackPattern.INVERSION_180, severity=0.4),),
        )
        assert out.inversion_detected

    def test_long_cycle_manipulation_flagged(self) -> None:
        out = self.e.assess(
            "bob",
            (
                _obs(
                    0,
                    pattern=AttackPattern.MANIPULATION,
                    severity=0.4,
                    long_cycle=True,
                ),
            ),
        )
        assert out.inversion_detected

    def test_no_inversion(self) -> None:
        out = self.e.assess(
            "bob",
            (_obs(0, pattern=AttackPattern.MANIPULATION, severity=0.4),),
        )
        assert not out.inversion_detected

class TestAssessmentDetails:
    def test_dominant_pattern_is_highest_severity(self) -> None:
        e = DefensiveModulationEngine()
        out = e.assess(
            "bob",
            (
                _obs(0, pattern=AttackPattern.MANIPULATION, severity=0.3),
                _obs(1, pattern=AttackPattern.FALSE_WITNESS, severity=0.9),
            ),
        )
        assert out.dominant_pattern is AttackPattern.FALSE_WITNESS

    def test_composite_severity_is_max(self) -> None:
        e = DefensiveModulationEngine()
        out = e.assess(
            "bob",
            (
                _obs(0, severity=0.3),
                _obs(1, severity=0.7),
                _obs(2, severity=0.5),
            ),
        )
        assert out.composite_severity == 0.7

    def test_default_config_singleton(self) -> None:
        assert (
            DEFAULT_DEFENSIVE_MODULATION_CONFIG.attack_severity_threshold
            == 0.1
        )
