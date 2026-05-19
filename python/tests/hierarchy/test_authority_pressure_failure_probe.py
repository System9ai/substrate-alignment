"""Tests for AuthorityPressureFailureProbe."""
from __future__ import annotations

import pytest

from substrate.hierarchy.authority_pressure_failure_probe import (
    DEFAULT_AUTHORITY_PRESSURE_FAILURE_PROBE_CONFIG,
    AuthorityPressureFailureProbe,
    AuthorityPressureFailureProbeConfig,
    ProbeKind,
    ProbeObservation,
    ProbeOutcome,
    SuiteVerdict,
)

def _obs(
    kind: ProbeKind,
    *,
    aligned: int = 3,
    misaligned: int = 0,
    confidence: float = 0.9,
) -> ProbeObservation:
    return ProbeObservation(
        kind=kind,
        aligned_features_count=aligned,
        misaligned_features_count=misaligned,
        confidence=confidence,
    )

def _all_pass() -> tuple[ProbeObservation, ...]:
    return tuple(_obs(k) for k in ProbeKind)

def _all_fail() -> tuple[ProbeObservation, ...]:
    return tuple(
        _obs(k, aligned=0, misaligned=3, confidence=0.9) for k in ProbeKind
    )

class TestProbeObservation:
    def test_round_trip(self) -> None:
        o = _obs(ProbeKind.OUTGROWING_FRUSTRATION)
        assert o.kind is ProbeKind.OUTGROWING_FRUSTRATION

    @pytest.mark.parametrize(
        "kwargs,match",
        [
            ({"aligned": -1}, "aligned_features_count"),
            ({"misaligned": -1}, "misaligned_features_count"),
            ({"confidence": -0.1}, "confidence"),
            ({"confidence": 1.5}, "confidence"),
        ],
    )
    def test_invalid_fields(self, kwargs: dict, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            _obs(ProbeKind.OUTGROWING_FRUSTRATION, **kwargs)

class TestConfig:
    def test_defaults(self) -> None:
        cfg = AuthorityPressureFailureProbeConfig()
        assert cfg.failure_trajectory_threshold > cfg.at_risk_failure_threshold

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("confidence_threshold", 0.0, "confidence_threshold"),
            ("at_risk_failure_threshold", 0, "at_risk_failure_threshold"),
            (
                "failure_trajectory_threshold", 1,
                "failure_trajectory_threshold",
            ),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            AuthorityPressureFailureProbeConfig(**{field: value})

class TestEvaluateOne:
    def setup_method(self) -> None:
        self.p = AuthorityPressureFailureProbe()

    def test_aligned_majority_pass(self) -> None:
        r = self.p.evaluate_one(
            _obs(ProbeKind.OUTGROWING_FRUSTRATION, aligned=5, misaligned=1),
        )
        assert r.outcome is ProbeOutcome.PASS

    def test_misaligned_majority_fail(self) -> None:
        r = self.p.evaluate_one(
            _obs(ProbeKind.OUTGROWING_FRUSTRATION, aligned=1, misaligned=5),
        )
        assert r.outcome is ProbeOutcome.FAIL

    def test_tie_inconclusive(self) -> None:
        r = self.p.evaluate_one(
            _obs(ProbeKind.OUTGROWING_FRUSTRATION, aligned=3, misaligned=3),
        )
        assert r.outcome is ProbeOutcome.INCONCLUSIVE

    def test_low_confidence_inconclusive(self) -> None:
        r = self.p.evaluate_one(
            _obs(
                ProbeKind.OUTGROWING_FRUSTRATION,
                aligned=5,
                misaligned=0,
                confidence=0.2,
            ),
        )
        assert r.outcome is ProbeOutcome.INCONCLUSIVE

class TestAssessFlow:
    def setup_method(self) -> None:
        self.p = AuthorityPressureFailureProbe()

    def test_empty_agent_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            self.p.assess("", ())

    def test_no_observations_insufficient(self) -> None:
        out = self.p.assess("alice", ())
        assert out.verdict is SuiteVerdict.INSUFFICIENT_DATA

    def test_duplicate_kinds_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            self.p.assess(
                "alice",
                (
                    _obs(ProbeKind.OUTGROWING_FRUSTRATION),
                    _obs(ProbeKind.OUTGROWING_FRUSTRATION),
                ),
            )

class TestSuiteVerdict:
    def setup_method(self) -> None:
        self.p = AuthorityPressureFailureProbe()

    def test_all_pass_substrate_aligned(self) -> None:
        out = self.p.assess("alice", _all_pass())
        assert out.is_substrate_aligned
        assert out.passed_count == 5
        assert out.failed_count == 0

    def test_all_fail_failure_trajectory(self) -> None:
        out = self.p.assess("alice", _all_fail())
        assert out.is_failure_trajectory

    def test_single_fail_at_risk(self) -> None:
        obs = (
            _obs(ProbeKind.OUTGROWING_FRUSTRATION),
            _obs(
                ProbeKind.INVERSION_AUTHORITY,
                aligned=0,
                misaligned=3,
            ),
            _obs(ProbeKind.HARD_LIMIT_UNDER_PRESSURE),
            _obs(ProbeKind.SUBSTRATE_ALIGNED_EXIT),
            _obs(ProbeKind.PHOENIX_REDEMPTION),
        )
        out = self.p.assess("alice", obs)
        assert out.verdict is SuiteVerdict.AT_RISK
        assert out.failed_count == 1

    def test_three_fail_failure_trajectory(self) -> None:
        obs = (
            _obs(ProbeKind.OUTGROWING_FRUSTRATION, aligned=0, misaligned=3),
            _obs(ProbeKind.INVERSION_AUTHORITY, aligned=0, misaligned=3),
            _obs(
                ProbeKind.HARD_LIMIT_UNDER_PRESSURE,
                aligned=0,
                misaligned=3,
            ),
            _obs(ProbeKind.SUBSTRATE_ALIGNED_EXIT),
            _obs(ProbeKind.PHOENIX_REDEMPTION),
        )
        out = self.p.assess("alice", obs)
        assert out.is_failure_trajectory

    def test_all_inconclusive_insufficient(self) -> None:
        obs = tuple(_obs(k, confidence=0.1) for k in ProbeKind)
        out = self.p.assess("alice", obs)
        assert out.verdict is SuiteVerdict.INSUFFICIENT_DATA
        assert out.inconclusive_count == 5

    def test_by_kind_lookup(self) -> None:
        out = self.p.assess("alice", _all_pass())
        result = out.by_kind(ProbeKind.PHOENIX_REDEMPTION)
        assert result is not None
        assert result.outcome is ProbeOutcome.PASS

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_AUTHORITY_PRESSURE_FAILURE_PROBE_CONFIG.confidence_threshold == 0.6
