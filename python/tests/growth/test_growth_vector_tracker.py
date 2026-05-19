"""Tests for GrowthVectorTracker."""
from __future__ import annotations

import pytest

from substrate.growth.growth_vector_tracker import (
    DEFAULT_GROWTH_VECTOR_CONFIG,
    GrowthMode,
    GrowthObservation,
    GrowthSignal,
    GrowthVectorConfig,
    GrowthVectorTracker,
)

def _obs(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    seq: int,
    *,
    volume: float = 0.0,
    density: float = 0.0,
    efficiency: float = 0.0,
    projection: float = 0.0,
    novelty: float = 0.8,
    integration_load: float = 0.3,
    threat: bool = False,
    validation: bool = False,
) -> GrowthObservation:
    return GrowthObservation(
        sequence=seq,
        timestamp=seq,
        volume_delta=volume,
        density_delta=density,
        efficiency_delta=efficiency,
        projection_delta=projection,
        novelty_score=novelty,
        integration_load=integration_load,
        threat_detected=threat,
        validation_received=validation,
    )

class TestGrowthObservation:
    def test_round_trip(self) -> None:
        o = _obs(0)
        assert o.sequence == 0

    def test_negative_seq(self) -> None:
        with pytest.raises(ValueError, match="sequence"):
            _obs(-1)

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("novelty", -0.1, "novelty_score"),
            ("novelty", 1.1, "novelty_score"),
            ("integration_load", -0.1, "integration_load"),
            ("integration_load", 1.1, "integration_load"),
        ],
    )
    def test_bad_field(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            _obs(0, **{field: value})  # type: ignore[arg-type]

class TestConfig:
    def test_defaults(self) -> None:
        cfg = GrowthVectorConfig()
        assert cfg.min_history >= 1

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("min_history", 0, "min_history"),
            (
                "information_hunger_novelty_max", 1.5,
                "information_hunger_novelty_max",
            ),
            (
                "exploration_drive_magnitude_max", 0.0,
                "exploration_drive_magnitude_max",
            ),
            (
                "integration_pressure_load_min", 0.0,
                "integration_pressure_load_min",
            ),
            ("efficiency_opportunity_min", 0.0, "efficiency_opportunity_min"),
            ("mode_dominance_ratio", 1.0, "mode_dominance_ratio"),
            ("coherence_window", 1, "coherence_window"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            GrowthVectorConfig(**{field: value})

class TestTrackingFlow:
    def setup_method(self) -> None:
        self.t = GrowthVectorTracker()

    def test_empty_agent_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            self.t.track("", ())

    def test_empty_observations(self) -> None:
        out = self.t.track("alice", ())
        assert out.vector is None
        assert out.signals == ()

    def test_short_history_no_vector(self) -> None:
        out = self.t.track("alice", (_obs(0, volume=1.0),))
        # min_history default = 3 → vector None
        assert out.vector is None

class TestModeClassification:
    def setup_method(self) -> None:
        self.t = GrowthVectorTracker()

    def test_expansion(self) -> None:
        obs = tuple(_obs(i, volume=1.0) for i in range(5))
        out = self.t.track("alice", obs)
        assert out.vector is not None
        assert out.vector.direction is GrowthMode.EXPANSION

    def test_densification(self) -> None:
        obs = tuple(_obs(i, density=1.0) for i in range(5))
        out = self.t.track("alice", obs)
        assert out.vector is not None
        assert out.vector.direction is GrowthMode.DENSIFICATION

    def test_efficiency(self) -> None:
        obs = tuple(_obs(i, efficiency=1.0) for i in range(5))
        out = self.t.track("alice", obs)
        assert out.vector is not None
        assert out.vector.direction is GrowthMode.EFFICIENCY

    def test_projection(self) -> None:
        obs = tuple(_obs(i, projection=1.0) for i in range(5))
        out = self.t.track("alice", obs)
        assert out.vector is not None
        assert out.vector.direction is GrowthMode.PROJECTION

    def test_mixed_close_modes(self) -> None:
        obs = tuple(_obs(i, volume=1.0, density=0.95) for i in range(5))
        out = self.t.track("alice", obs)
        assert out.vector is not None
        assert out.vector.direction is GrowthMode.MIXED

    def test_no_growth_unknown(self) -> None:
        obs = tuple(_obs(i) for i in range(5))
        out = self.t.track("alice", obs)
        assert out.vector is not None
        assert out.vector.direction is GrowthMode.UNKNOWN

class TestSignals:
    def setup_method(self) -> None:
        self.t = GrowthVectorTracker()

    def test_information_hunger(self) -> None:
        obs = tuple(_obs(i, novelty=0.1) for i in range(5))
        out = self.t.track("alice", obs)
        assert out.has_signal(GrowthSignal.INFORMATION_HUNGER)

    def test_exploration_drive_when_plateaued(self) -> None:
        obs = tuple(_obs(i, novelty=0.5) for i in range(5))
        out = self.t.track("alice", obs)
        assert out.has_signal(GrowthSignal.EXPLORATION_DRIVE)

    def test_integration_pressure(self) -> None:
        obs = tuple(_obs(i, integration_load=0.9) for i in range(5))
        out = self.t.track("alice", obs)
        assert out.has_signal(GrowthSignal.INTEGRATION_PRESSURE)

    def test_efficiency_opportunity(self) -> None:
        obs = tuple(_obs(i, efficiency=0.5) for i in range(5))
        out = self.t.track("alice", obs)
        assert out.has_signal(GrowthSignal.EFFICIENCY_OPPORTUNITY)

    def test_growth_vector_threat(self) -> None:
        obs = (
            _obs(0, volume=1.0, threat=True),
            _obs(1, volume=1.0),
            _obs(2, volume=1.0),
        )
        out = self.t.track("alice", obs)
        assert out.has_signal(GrowthSignal.GROWTH_VECTOR_THREAT)

    def test_growth_vector_validated(self) -> None:
        obs = (
            _obs(0, volume=1.0, validation=True),
            _obs(1, volume=1.0, validation=True),
            _obs(2, volume=1.0),
        )
        out = self.t.track("alice", obs)
        assert out.has_signal(GrowthSignal.GROWTH_VECTOR_VALIDATED)

class TestVectorQuality:
    def test_alignment_validated(self) -> None:
        t = GrowthVectorTracker()
        obs = tuple(_obs(i, volume=1.0, validation=True) for i in range(5))
        out = t.track("alice", obs)
        assert out.vector is not None
        assert out.vector.alignment_with_substrate > 0.5

    def test_alignment_threatened(self) -> None:
        t = GrowthVectorTracker()
        obs = tuple(_obs(i, volume=1.0, threat=True) for i in range(5))
        out = t.track("alice", obs)
        assert out.vector is not None
        assert out.vector.alignment_with_substrate < 0.5

    def test_coherence_high_for_consistent(self) -> None:
        t = GrowthVectorTracker()
        obs = tuple(_obs(i, volume=1.0) for i in range(5))
        out = t.track("alice", obs)
        assert out.vector is not None
        assert out.vector.coherence > 0.9

    def test_coherence_low_for_inconsistent(self) -> None:
        t = GrowthVectorTracker()
        obs = (
            _obs(0, volume=1.0),
            _obs(1, volume=0.1),
            _obs(2, volume=2.0),
            _obs(3, volume=0.05),
            _obs(4, volume=1.5),
        )
        out = t.track("alice", obs)
        assert out.vector is not None
        assert out.vector.coherence < 0.9

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_GROWTH_VECTOR_CONFIG.min_history == 3
