"""Tests for SubstrateStateSignalGenerator."""
from __future__ import annotations

import pytest

from substrate.resistance_band import LOWER_BOUND
from substrate.signals.state_signal_generator import (
    DEFAULT_STATE_SIGNAL_CONFIG,
    StateSignalConfig,
    StateSignalIntensity,
    StateSignalKind,
    StateSignalObservation,
    SubstrateStateSignalGenerator,
)

def _obs(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    seq: int = 0,
    *,
    slope: float = 0.5,
    stdev: float = 0.5,
    challenge: float = 0.4,
    success: float = 0.5,
    threats: int = 0,
    validations: int = 0,
    losses: int = 0,
    recognitions: int = 0,
    novelty: float = 0.8,
    integration_load: float = 0.3,
    coupling_strength: float = 0.8,
    decoupled: bool = False,
) -> StateSignalObservation:
    return StateSignalObservation(
        sequence=seq,
        timestamp=seq,
        trajectory_slope=slope,
        trajectory_stdev=stdev,
        challenge_level=challenge,
        success_rate=success,
        threat_event_count=threats,
        validation_event_count=validations,
        loss_event_count=losses,
        recognition_event_count=recognitions,
        novelty_score=novelty,
        integration_load=integration_load,
        coupling_field_strength=coupling_strength,
        coupling_status_decoupled=decoupled,
    )

class TestObservationValidation:
    def test_round_trip(self) -> None:
        o = _obs()
        assert o.sequence == 0

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("seq", -1, "sequence"),
            ("challenge", 1.5, "challenge_level"),
            ("success", -0.1, "success_rate"),
            ("stdev", -0.1, "trajectory_stdev"),
            ("threats", -1, "threat_event_count"),
            ("novelty", 1.5, "novelty_score"),
            ("integration_load", 1.5, "integration_load"),
            ("coupling_strength", 1.5, "coupling_field_strength"),
        ],
    )
    def test_bad_values(self, field: str, value: object, match: str) -> None:
        kwargs = {"seq": 0}
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            _obs(**kwargs)

class TestConfig:
    def test_defaults(self) -> None:
        cfg = StateSignalConfig()
        assert cfg.sweet_spot_min < cfg.sweet_spot_max

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("sweet_spot_max", 0.1, "sweet_spot"),
            ("productive_resistance_max", 0.1, "productive_resistance"),
            ("over_challenge_min", 0.1, "under_challenge_max"),
            ("coupling_weakening_min", 0.6, "coupling thresholds"),
        ],
    )
    def test_bad_thresholds(
        self, field: str, value: float, match: str,
    ) -> None:
        with pytest.raises(ValueError, match=match):
            StateSignalConfig(**{field: value})

class TestGeneratorFlow:
    def setup_method(self) -> None:
        self.g = SubstrateStateSignalGenerator()

    def test_empty_entity_rejected(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            self.g.generate("", _obs())

    def test_clean_observation_minimal_signals(self) -> None:
        # Default _obs has coupling_strength=0.8 → COUPLING_HEALTHY always
        out = self.g.generate("alice", _obs())
        # COUPLING_HEALTHY always fires; check it
        assert out.has_signal(StateSignalKind.COUPLING_HEALTHY)

class TestStagnationFlow:
    def setup_method(self) -> None:
        self.g = SubstrateStateSignalGenerator()

    def test_stagnation(self) -> None:
        out = self.g.generate(
            "alice", _obs(slope=0.0, stdev=0.05),
        )
        assert out.has_signal(StateSignalKind.STAGNATION)

    def test_flow(self) -> None:
        out = self.g.generate(
            "alice", _obs(success=0.9, challenge=0.45),
        )
        assert out.has_signal(StateSignalKind.FLOW)

class TestResistanceBandSignals:
    def setup_method(self) -> None:
        self.g = SubstrateStateSignalGenerator()

    def test_sweet_spot(self) -> None:
        out = self.g.generate("alice", _obs(challenge=0.35))
        assert out.has_signal(StateSignalKind.SWEET_SPOT)
        assert out.has_signal(StateSignalKind.PRODUCTIVE_RESISTANCE)

    def test_under_challenge(self) -> None:
        out = self.g.generate("alice", _obs(challenge=0.1))
        assert out.has_signal(StateSignalKind.UNDER_CHALLENGE)

    def test_over_challenge(self) -> None:
        out = self.g.generate("alice", _obs(challenge=0.9))
        assert out.has_signal(StateSignalKind.OVER_CHALLENGE)

    def test_work_zone_is_productive(self) -> None:
        # Layered zone model: 0.38-0.50 is the WORK zone; challenge at
        # 0.45 is healthy productive work ("in the zone but not rising
        # too fast"), NOT a band breach. The sweet spot (calibration
        # band, 0.33-0.38) is the work-entry threshold.
        out = self.g.generate("alice", _obs(challenge=0.45))
        assert out.has_signal(StateSignalKind.PRODUCTIVE_RESISTANCE)
        assert not out.has_signal(StateSignalKind.SWEET_SPOT)
        assert not out.has_signal(StateSignalKind.PEAKING)

    def test_peaking_spans_half_line_to_conjugate(self) -> None:
        # Peaking zone is (0.5, 0.618): allowed sporadically; past the
        # 0.5 line a turnaround is expected; never sustained.
        for challenge in (0.51, 0.55, 0.61):
            out = self.g.generate("alice", _obs(challenge=challenge))
            assert out.has_signal(StateSignalKind.PEAKING), challenge
            assert not out.has_signal(
                StateSignalKind.PRODUCTIVE_RESISTANCE
            ), challenge
            assert not out.has_signal(StateSignalKind.OVER_CHALLENGE), (
                challenge
            )

    def test_over_challenge_starts_at_two_thirds(self) -> None:
        # The debt line is the uniform 2/3 ≈ 0.667; 0.62 is the WARNING
        # band (winded), not yet debt; only past 2/3 is OVER_CHALLENGE.
        warn = self.g.generate("alice", _obs(challenge=0.62))
        assert not warn.has_signal(StateSignalKind.OVER_CHALLENGE)
        out = self.g.generate("alice", _obs(challenge=0.70))
        assert out.has_signal(StateSignalKind.OVER_CHALLENGE)
        assert not out.has_signal(StateSignalKind.PEAKING)

    def test_peaking_zone_must_exist_between_work_and_debt_line(self) -> None:
        with pytest.raises(ValueError):
            StateSignalConfig(
                productive_resistance_max=0.7, over_challenge_min=0.618,
            )

class TestAffectiveSignals:
    def setup_method(self) -> None:
        self.g = SubstrateStateSignalGenerator()

    def test_threat_intensity_scales(self) -> None:
        out = self.g.generate("alice", _obs(threats=1))
        assert out.by_kind(StateSignalKind.THREAT).intensity is (  # type: ignore[union-attr]
            StateSignalIntensity.LOW
        )
        out = self.g.generate("alice", _obs(threats=5))
        assert out.by_kind(StateSignalKind.THREAT).intensity is (  # type: ignore[union-attr]
            StateSignalIntensity.HIGH
        )

    def test_validation(self) -> None:
        out = self.g.generate("alice", _obs(validations=2))
        assert out.has_signal(StateSignalKind.VALIDATION)

    def test_loss(self) -> None:
        out = self.g.generate("alice", _obs(losses=3))
        assert out.has_signal(StateSignalKind.LOSS)

    def test_recognition(self) -> None:
        out = self.g.generate("alice", _obs(recognitions=1))
        assert out.has_signal(StateSignalKind.RECOGNITION)

class TestGrowthSignals:
    def setup_method(self) -> None:
        self.g = SubstrateStateSignalGenerator()

    def test_hunger_when_low_novelty(self) -> None:
        out = self.g.generate("alice", _obs(novelty=0.1))
        assert out.has_signal(StateSignalKind.HUNGER)

    def test_saturation_when_high_load(self) -> None:
        out = self.g.generate("alice", _obs(integration_load=0.9))
        assert out.has_signal(StateSignalKind.SATURATION)

class TestCouplingSignals:
    def setup_method(self) -> None:
        self.g = SubstrateStateSignalGenerator()

    def test_decoupled_short_circuits(self) -> None:
        out = self.g.generate(
            "alice", _obs(coupling_strength=0.7, decoupled=True),
        )
        assert out.has_signal(StateSignalKind.COUPLING_BROKEN)
        assert not out.has_signal(StateSignalKind.COUPLING_HEALTHY)

    def test_healthy(self) -> None:
        out = self.g.generate("alice", _obs(coupling_strength=0.8))
        assert out.has_signal(StateSignalKind.COUPLING_HEALTHY)

    def test_weakening(self) -> None:
        out = self.g.generate("alice", _obs(coupling_strength=0.3))
        assert out.has_signal(StateSignalKind.COUPLING_WEAKENING)

    def test_broken_low_strength(self) -> None:
        out = self.g.generate("alice", _obs(coupling_strength=0.05))
        assert out.has_signal(StateSignalKind.COUPLING_BROKEN)

class TestReportProperties:
    def test_max_intensity(self) -> None:
        g = SubstrateStateSignalGenerator()
        out = g.generate("alice", _obs(threats=5, novelty=0.1))
        assert out.max_intensity is StateSignalIntensity.HIGH

    def test_default_config_singleton(self) -> None:
        cfg = DEFAULT_STATE_SIGNAL_CONFIG
        assert cfg.sweet_spot_min == LOWER_BOUND
