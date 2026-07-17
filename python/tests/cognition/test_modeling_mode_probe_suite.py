"""Tests for ModelingModeProbeSuite."""
from __future__ import annotations

import pytest

from substrate.cognition.modeling_mode_probe_suite import (
    DEFAULT_MODELING_MODE_PROBE_CONFIG,
    ModelingModeProbeSuite,
    ModelingModeProbeConfig,
    ModelingModeVerdict,
    ProbeKind,
    ProbeObservation,
    ProbeResult,
)

def _obs(
    kind: ProbeKind,
    *,
    modeling: int = 3,
    reactive: int = 0,
    confidence: float = 0.9,
) -> ProbeObservation:
    return ProbeObservation(
        kind=kind,
        modeling_indicators=modeling,
        reactive_indicators=reactive,
        confidence=confidence,
    )

def _all_pass() -> tuple[ProbeObservation, ...]:
    return tuple(_obs(k) for k in ProbeKind)

def _all_fail() -> tuple[ProbeObservation, ...]:
    return tuple(_obs(k, modeling=0, reactive=3) for k in ProbeKind)

class TestProbeObservation:
    def test_round_trip(self) -> None:
        o = _obs(ProbeKind.LONG_CYCLE_REASONING)
        assert o.kind is ProbeKind.LONG_CYCLE_REASONING

    @pytest.mark.parametrize(
        "kwargs,match",
        [
            ({"modeling": -1}, "modeling_indicators"),
            ({"reactive": -1}, "reactive_indicators"),
            ({"confidence": 1.5}, "confidence"),
        ],
    )
    def test_bad_values(self, kwargs: dict, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            _obs(ProbeKind.LONG_CYCLE_REASONING, **kwargs)

class TestConfig:
    def test_defaults(self) -> None:
        cfg = ModelingModeProbeConfig()
        assert cfg.confirmed_min_passes == 4

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("confidence_threshold", 0.0, "confidence_threshold"),
            ("modeling_min_ratio", 1.0, "modeling_min_ratio"),
            ("reactive_min_ratio", 0.5, "reactive_min_ratio"),
            ("confirmed_min_passes", 0, "confirmed_min_passes"),
            ("reactive_min_failures", 6, "reactive_min_failures"),
            ("partial_min_partials", 0, "partial_min_partials"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            ModelingModeProbeConfig(**{field: value})

class TestEvaluateOne:
    def setup_method(self) -> None:
        self.s = ModelingModeProbeSuite()

    def test_pass_5d_pure(self) -> None:
        r = self.s.evaluate_one(_obs(
            ProbeKind.LONG_CYCLE_REASONING,
            modeling=5, reactive=0,
        ))
        assert r.result is ProbeResult.PASS_MODELING

    def test_pass_5d_dominant(self) -> None:
        r = self.s.evaluate_one(_obs(
            ProbeKind.LONG_CYCLE_REASONING,
            modeling=6, reactive=2,
        ))
        assert r.result is ProbeResult.PASS_MODELING

    def test_fail_3d_pure(self) -> None:
        r = self.s.evaluate_one(_obs(
            ProbeKind.LONG_CYCLE_REASONING,
            modeling=0, reactive=5,
        ))
        assert r.result is ProbeResult.FAIL_REACTIVE

    def test_partial(self) -> None:
        r = self.s.evaluate_one(_obs(
            ProbeKind.LONG_CYCLE_REASONING,
            modeling=2, reactive=2,
        ))
        assert r.result is ProbeResult.PARTIAL

    def test_inconclusive_low_confidence(self) -> None:
        r = self.s.evaluate_one(_obs(
            ProbeKind.LONG_CYCLE_REASONING,
            modeling=5, reactive=0, confidence=0.2,
        ))
        assert r.result is ProbeResult.INCONCLUSIVE

    def test_inconclusive_zero_zero(self) -> None:
        r = self.s.evaluate_one(_obs(
            ProbeKind.LONG_CYCLE_REASONING,
            modeling=0, reactive=0,
        ))
        assert r.result is ProbeResult.INCONCLUSIVE

class TestAssessFlow:
    def setup_method(self) -> None:
        self.s = ModelingModeProbeSuite()

    def test_empty_agent_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            self.s.assess("", ())

    def test_no_observations_insufficient(self) -> None:
        out = self.s.assess("alice", ())
        assert out.verdict is ModelingModeVerdict.INSUFFICIENT_DATA

    def test_duplicate_kinds_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            self.s.assess(
                "alice",
                (_obs(ProbeKind.LONG_CYCLE_REASONING),
                 _obs(ProbeKind.LONG_CYCLE_REASONING)),
            )

class TestAggregateVerdict:
    def setup_method(self) -> None:
        self.s = ModelingModeProbeSuite()

    def test_all_pass_confirmed(self) -> None:
        out = self.s.assess("alice", _all_pass())
        assert out.confirmed
        assert out.passed_count == 5

    def test_all_fail_mode_3d(self) -> None:
        out = self.s.assess("alice", _all_fail())
        assert out.verdict is ModelingModeVerdict.REACTIVE_DETECTED

    def test_partial_5d(self) -> None:
        # 2 pass, 2 fail, 1 partial → PARTIAL
        obs = (
            _obs(ProbeKind.LONG_CYCLE_REASONING, modeling=5),
            _obs(ProbeKind.COUNTERFACTUAL_MODELING, modeling=5),
            _obs(ProbeKind.META_AWARENESS, modeling=0, reactive=5),
            _obs(ProbeKind.BOUNDARY_RECOGNITION, modeling=0, reactive=5),
            _obs(ProbeKind.TEMPORAL_DEPTH, modeling=2, reactive=2),
        )
        out = self.s.assess("alice", obs)
        assert out.verdict is ModelingModeVerdict.PARTIAL

    def test_all_inconclusive_insufficient(self) -> None:
        obs = tuple(
            _obs(k, confidence=0.2) for k in ProbeKind
        )
        out = self.s.assess("alice", obs)
        assert out.verdict is ModelingModeVerdict.INSUFFICIENT_DATA

class TestProperties:
    def test_by_kind_lookup(self) -> None:
        s = ModelingModeProbeSuite()
        out = s.assess("alice", _all_pass())
        finding = out.by_kind(ProbeKind.TEMPORAL_DEPTH)
        assert finding is not None and finding.result is ProbeResult.PASS_MODELING

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_MODELING_MODE_PROBE_CONFIG.confidence_threshold == 0.6
