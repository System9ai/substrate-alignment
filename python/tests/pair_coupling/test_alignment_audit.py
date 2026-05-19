"""Tests for PairCouplingAuditor (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.pair_coupling.alignment_audit import (
    DEFAULT_PAIR_COUPLING_AUDIT_CONFIG,
    AuditVerdict,
    PairCouplingAuditConfig,
    PairCouplingAuditInput,
    PairCouplingAuditor,
    PairScale,
)

def _input(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    pair: str = "pair-1",
    pole_a: str = "alice",
    pole_b: str = "bob",
    scale: PairScale = PairScale.CELL_PAIR,
    delta_a: float = 0.2,
    delta_b: float = 0.2,
    binding: float = 0.1,
    obs_count: int = 10,
    window: float = 600.0,
) -> PairCouplingAuditInput:
    return PairCouplingAuditInput(
        pair_id=pair,
        pole_a_id=pole_a,
        pole_b_id=pole_b,
        scale=scale,
        pole_a_trajectory_delta=delta_a,
        pole_b_trajectory_delta=delta_b,
        binding_field_coherence_delta=binding,
        observation_count=obs_count,
        observation_window_seconds=window,
    )

class TestInputValidation:
    def test_round_trip(self) -> None:
        i = _input()
        assert i.pair_id == "pair-1"

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("pair", "", "pair_id"),
            ("pole_a", "", "pole_a_id"),
            ("pole_b", "", "pole_b_id"),
            ("delta_a", 1.5, "pole_a_trajectory_delta"),
            ("delta_b", -1.5, "pole_b_trajectory_delta"),
            ("binding", 1.5, "binding_field_coherence_delta"),
            ("obs_count", -1, "observation_count"),
            ("window", -1.0, "observation_window_seconds"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs = {}
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            _input(**kwargs)  # type: ignore[arg-type]

    def test_same_pole_ids_rejected(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            _input(pole_a="alice", pole_b="alice")

class TestConfig:
    def test_defaults(self) -> None:
        cfg = PairCouplingAuditConfig()
        assert cfg.min_observations == 5

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("rising_trajectory_min", 0.0, "rising_trajectory_min"),
            ("extraction_asymmetry_min", 0.0, "extraction_asymmetry_min"),
            ("min_observations", 0, "min_observations"),
            ("min_observation_window", 0.0, "min_observation_window"),
            ("binding_decay_threshold", 0.1, "binding_decay_threshold"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            PairCouplingAuditConfig(**{field: value})

class TestAuditFlow:
    def setup_method(self) -> None:
        self.a = PairCouplingAuditor()

    def test_substrate_aligned_both_rising(self) -> None:
        out = self.a.audit(_input(delta_a=0.3, delta_b=0.25, binding=0.1))
        assert out.substrate_aligned
        assert not out.extractive

    def test_extractive_toward_a(self) -> None:
        out = self.a.audit(_input(delta_a=0.6, delta_b=0.1, binding=-0.05))
        assert out.verdict is AuditVerdict.EXTRACTIVE_TOWARD_A
        assert out.extractive

    def test_extractive_toward_b(self) -> None:
        out = self.a.audit(_input(delta_a=0.05, delta_b=0.6, binding=-0.05))
        assert out.verdict is AuditVerdict.EXTRACTIVE_TOWARD_B
        assert out.extractive

    def test_degrading_both(self) -> None:
        out = self.a.audit(_input(
            delta_a=-0.1, delta_b=-0.1, binding=-0.2,
        ))
        assert out.degrading_both

    def test_one_rising_one_stagnant_degrading(self) -> None:
        out = self.a.audit(_input(
            delta_a=0.2, delta_b=0.01, binding=0.0,
        ))
        # Asymmetry 0.19 < 0.3 extraction threshold → DEGRADING_BOTH
        assert out.degrading_both

class TestInsufficientData:
    def setup_method(self) -> None:
        self.a = PairCouplingAuditor()

    def test_too_few_observations(self) -> None:
        out = self.a.audit(_input(obs_count=2))
        assert out.verdict is AuditVerdict.INSUFFICIENT_DATA

    def test_too_short_window(self) -> None:
        out = self.a.audit(_input(window=30.0))
        assert out.verdict is AuditVerdict.INSUFFICIENT_DATA

class TestScaleAwareness:
    def test_cell_pair(self) -> None:
        a = PairCouplingAuditor()
        out = a.audit(_input(scale=PairScale.CELL_PAIR))
        assert out.scale is PairScale.CELL_PAIR

    def test_node_pair(self) -> None:
        a = PairCouplingAuditor()
        out = a.audit(_input(scale=PairScale.NODE_PAIR))
        assert out.scale is PairScale.NODE_PAIR

class TestAsymmetry:
    def test_asymmetry_metric(self) -> None:
        a = PairCouplingAuditor()
        out = a.audit(_input(delta_a=0.5, delta_b=0.1))
        assert abs(out.asymmetry - 0.4) < 1e-9

class TestModuleSurface:
    def test_default_config_singleton(self) -> None:
        assert DEFAULT_PAIR_COUPLING_AUDIT_CONFIG.min_observations == 5
