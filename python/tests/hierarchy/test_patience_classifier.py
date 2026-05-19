"""Tests for PatienceImpatienceClassifier."""
from __future__ import annotations

import pytest

from substrate.hierarchy.patience_classifier import (
    DEFAULT_PATIENCE_CONFIG,
    PatienceCategory,
    PatienceConfig,
    PatienceImpatienceClassifier,
    PatienceObservation,
    PatienceVerdict,
)

def _obs(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    seq: int,
    *,
    horizon: int = 10,
    friction: bool = False,
    continued: bool = False,
    completed: bool = True,
    impatience: int = 0,
    timestamp: int = 0,
) -> PatienceObservation:
    return PatienceObservation(
        sequence=seq,
        timestamp=timestamp or seq,
        decision_horizon_cycles=horizon,
        friction_observed=friction,
        continued_under_friction=continued,
        completed_role_cycle=completed,
        impatience_signal_count=impatience,
    )

class TestPatienceObservation:
    def test_round_trip(self) -> None:
        o = _obs(0)
        assert o.sequence == 0

    def test_negative_seq(self) -> None:
        with pytest.raises(ValueError, match="sequence"):
            _obs(-1)

    def test_negative_horizon(self) -> None:
        with pytest.raises(ValueError, match="decision_horizon_cycles"):
            _obs(0, horizon=-1)

    def test_negative_impatience(self) -> None:
        with pytest.raises(ValueError, match="impatience_signal_count"):
            _obs(0, impatience=-1)

    def test_continued_without_friction_rejected(self) -> None:
        with pytest.raises(ValueError, match="continued_under_friction"):
            _obs(0, friction=False, continued=True)

class TestConfig:
    def test_defaults(self) -> None:
        cfg = PatienceConfig()
        assert cfg.discount_factor_threshold == 0.5

    @pytest.mark.parametrize(
        "field,value,match",
        [
            (
                "discount_factor_threshold", 0.0,
                "discount_factor_threshold",
            ),
            ("high_horizon_baseline_cycles", 0.0, "high_horizon_baseline"),
            (
                "operation_under_friction_threshold", 0.0,
                "operation_under_friction_threshold",
            ),
            (
                "role_completion_threshold", 0.0,
                "role_completion_threshold",
            ),
            ("impatience_count_threshold", -1.0, "impatience_count"),
            ("min_history", 0, "min_history"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            PatienceConfig(**{field: value})

class TestClassifierFlow:
    def setup_method(self) -> None:
        self.c = PatienceImpatienceClassifier()

    def test_empty_agent_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            self.c.classify("", ())

    def test_empty_observations_insufficient(self) -> None:
        out = self.c.classify("alice", ())
        assert out.verdict is PatienceVerdict.INSUFFICIENT_DATA
        assert out.discount_factor_estimate == 0.0

    def test_short_history_insufficient(self) -> None:
        out = self.c.classify("alice", (_obs(0), _obs(1)))
        assert out.verdict is PatienceVerdict.INSUFFICIENT_DATA

class TestPatientVerdict:
    def setup_method(self) -> None:
        self.c = PatienceImpatienceClassifier()

    def test_full_patient(self) -> None:
        # high horizon → δ ≈ 1.0
        obs = tuple(
            _obs(
                i, horizon=10, friction=True, continued=True,
                completed=True, impatience=0,
            )
            for i in range(5)
        )
        out = self.c.classify("alice", obs)
        assert out.is_patient
        assert out.discount_factor_estimate >= 0.5

    def test_vacuous_friction_satisfied(self) -> None:
        # no friction observed at all → vacuously satisfied
        obs = tuple(
            _obs(i, horizon=10, friction=False, continued=False) for i in range(5)
        )
        out = self.c.classify("alice", obs)
        finding = out.by_category(PatienceCategory.OPERATION_UNDER_FRICTION)
        assert finding is not None and finding.satisfied

class TestImpatientVerdict:
    def setup_method(self) -> None:
        self.c = PatienceImpatienceClassifier()

    def test_all_signals_miss(self) -> None:
        obs = tuple(
            _obs(
                i,
                horizon=1,  # low δ
                friction=True,
                continued=False,
                completed=False,
                impatience=5,
            )
            for i in range(5)
        )
        out = self.c.classify("alice", obs)
        assert out.is_impatient
        assert out.discount_factor_estimate < 0.5

class TestMixedVerdict:
    def setup_method(self) -> None:
        self.c = PatienceImpatienceClassifier()

    def test_some_signals_pass(self) -> None:
        # high δ, complete cycles, but lots of impatience signals
        obs = tuple(
            _obs(
                i,
                horizon=10,
                friction=False,
                completed=True,
                impatience=5,
            )
            for i in range(5)
        )
        out = self.c.classify("alice", obs)
        assert out.verdict is PatienceVerdict.MIXED

class TestSignalRationales:
    def test_findings_count(self) -> None:
        c = PatienceImpatienceClassifier()
        obs = tuple(_obs(i) for i in range(5))
        out = c.classify("alice", obs)
        # 4 findings, one per category
        assert len(out.findings) == 4

    def test_rationale_format(self) -> None:
        c = PatienceImpatienceClassifier()
        obs = tuple(_obs(i) for i in range(5))
        out = c.classify("alice", obs)
        assert "verdict=" in out.rationale
        assert "δ=" in out.rationale

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_PATIENCE_CONFIG.discount_factor_threshold == 0.5
