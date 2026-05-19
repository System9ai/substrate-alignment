"""Tests for ConvergenceTracker"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from substrate.voting.convergence_tracker import (
    CONVERGENCE_VERDICTS,
    ConvergenceTracker,
    ConvergenceTrajectory,
    ConvergenceVerdict,
    DEFAULT_DIVERGENCE_SLOPE_THRESHOLD,
    DEFAULT_MIN_ROUNDS,
    DEFAULT_OSCILLATION_THRESHOLD,
    DEFAULT_STABILITY_THRESHOLD,
    DEFAULT_STABLE_WINDOW_ROUNDS,
    RoundResult,
    round_results_from_records,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rounds(*, winners: list[str], confidences: list[float]) -> list[RoundResult]:
    assert len(winners) == len(confidences)
    return [
        RoundResult(round_index=i, winner=w, confidence=c)
        for i, (w, c) in enumerate(zip(winners, confidences))
    ]

@dataclass
class _FakeRecord:
    outcome: Optional[str]
    confidence: float

# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

class TestConstructorValidation:
    def test_defaults(self) -> None:
        t = ConvergenceTracker()
        assert t.min_rounds == DEFAULT_MIN_ROUNDS
        assert t.stable_window_rounds == DEFAULT_STABLE_WINDOW_ROUNDS
        assert t.stability_threshold == DEFAULT_STABILITY_THRESHOLD
        assert t.oscillation_threshold == DEFAULT_OSCILLATION_THRESHOLD
        assert (
            t.divergence_slope_threshold == DEFAULT_DIVERGENCE_SLOPE_THRESHOLD
        )

    def test_min_rounds_below_two_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConvergenceTracker(min_rounds=1)
        with pytest.raises(ValueError):
            ConvergenceTracker(min_rounds=0)

    def test_stable_window_below_one_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConvergenceTracker(stable_window_rounds=0)

    def test_stability_threshold_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConvergenceTracker(stability_threshold=0.0)

    def test_stability_threshold_above_one_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConvergenceTracker(stability_threshold=1.5)

    def test_oscillation_threshold_above_one_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConvergenceTracker(oscillation_threshold=1.5)

# ---------------------------------------------------------------------------
# Insufficient rounds
# ---------------------------------------------------------------------------

class TestInsufficientRounds:
    def test_empty_rounds(self) -> None:
        t = ConvergenceTracker()
        result = t.assess([])
        assert result.verdict is ConvergenceVerdict.INSUFFICIENT_ROUNDS
        assert result.current_winner is None
        assert result.rounds_assessed == 0

    def test_below_min_rounds(self) -> None:
        t = ConvergenceTracker(min_rounds=3)
        rounds = _rounds(winners=["alice", "alice"], confidences=[0.6, 0.7])
        result = t.assess(rounds)
        assert result.verdict is ConvergenceVerdict.INSUFFICIENT_ROUNDS
        assert result.current_winner == "alice"

# ---------------------------------------------------------------------------
# CONVERGED
# ---------------------------------------------------------------------------

class TestConverged:
    def test_stable_winner_rising_confidence(self) -> None:
        t = ConvergenceTracker(
            min_rounds=3,
            stable_window_rounds=3,
            stability_threshold=1.0,
        )
        rounds = _rounds(
            winners=["alice", "alice", "alice"],
            confidences=[0.6, 0.7, 0.8],
        )
        result = t.assess(rounds)
        assert result.verdict is ConvergenceVerdict.CONVERGED
        assert result.is_converged is True
        assert result.current_winner == "alice"
        assert result.winner_stability == pytest.approx(1.0)
        assert result.oscillation_count == 0
        assert result.confidence_trend_slope > 0

    def test_stable_winner_flat_confidence(self) -> None:
        # Flat confidence (slope 0) still permits CONVERGED.
        t = ConvergenceTracker(min_rounds=3, stable_window_rounds=3)
        rounds = _rounds(
            winners=["x", "x", "x"],
            confidences=[0.7, 0.7, 0.7],
        )
        result = t.assess(rounds)
        assert result.verdict is ConvergenceVerdict.CONVERGED

# ---------------------------------------------------------------------------
# CONVERGING
# ---------------------------------------------------------------------------

class TestConverging:
    def test_recent_stable_after_earlier_oscillation(self) -> None:
        # Earlier rounds had different winners; last 3 all alice.
        t = ConvergenceTracker(
            min_rounds=3,
            stable_window_rounds=3,
            oscillation_threshold=0.6,
        )
        rounds = _rounds(
            winners=["bob", "carol", "alice", "alice", "alice"],
            confidences=[0.5, 0.6, 0.7, 0.75, 0.8],
        )
        # 2 changes out of 4 transitions → oscillation_rate=0.5 < 0.6
        result = t.assess(rounds)
        # Recent window 100% alice + rising confidence → CONVERGED;
        # but oscillation_rate=0.5 falls below the threshold so it
        # passes the convergence gate.
        assert result.verdict in (
            ConvergenceVerdict.CONVERGED,
            ConvergenceVerdict.CONVERGING,
        )
        assert result.current_winner == "alice"

# ---------------------------------------------------------------------------
# OSCILLATING
# ---------------------------------------------------------------------------

class TestOscillating:
    def test_frequent_winner_changes(self) -> None:
        t = ConvergenceTracker(
            min_rounds=3,
            oscillation_threshold=0.5,
            stable_window_rounds=2,
        )
        # 3 changes out of 3 transitions → rate=1.0 >= 0.5
        rounds = _rounds(
            winners=["a", "b", "a", "b"],
            confidences=[0.5, 0.5, 0.5, 0.5],
        )
        result = t.assess(rounds)
        assert result.verdict is ConvergenceVerdict.OSCILLATING
        assert result.oscillation_rate == pytest.approx(1.0)

    def test_oscillation_count(self) -> None:
        t = ConvergenceTracker(min_rounds=2)
        rounds = _rounds(
            winners=["x", "y", "y", "z"],
            confidences=[0.5, 0.5, 0.5, 0.5],
        )
        result = t.assess(rounds)
        assert result.oscillation_count == 2  # x→y, y→z

# ---------------------------------------------------------------------------
# DIVERGING
# ---------------------------------------------------------------------------

class TestDiverging:
    def test_stable_winner_dropping_confidence(self) -> None:
        # Same winner but confidence drops sharply → DIVERGING.
        t = ConvergenceTracker(
            min_rounds=3,
            stable_window_rounds=3,
            divergence_slope_threshold=-0.05,
        )
        rounds = _rounds(
            winners=["alice", "alice", "alice"],
            confidences=[0.9, 0.7, 0.5],
        )
        result = t.assess(rounds)
        assert result.verdict is ConvergenceVerdict.DIVERGING
        assert result.confidence_trend_slope < 0

    def test_diverging_takes_precedence_over_converged(self) -> None:
        # Even with 100% stability, falling confidence wins.
        t = ConvergenceTracker(
            min_rounds=3,
            divergence_slope_threshold=-0.02,
        )
        rounds = _rounds(
            winners=["x", "x", "x", "x"],
            confidences=[0.95, 0.85, 0.75, 0.65],
        )
        result = t.assess(rounds)
        assert result.verdict is ConvergenceVerdict.DIVERGING

# ---------------------------------------------------------------------------
# Confidence slope math
# ---------------------------------------------------------------------------

class TestConfidenceSlope:
    def test_positive_slope_linear(self) -> None:
        t = ConvergenceTracker(min_rounds=2)
        rounds = _rounds(
            winners=["x", "x", "x"],
            confidences=[0.0, 0.5, 1.0],
        )
        result = t.assess(rounds)
        # Slope of (0,0), (1,0.5), (2,1.0) is 0.5
        assert result.confidence_trend_slope == pytest.approx(0.5)

    def test_zero_slope_flat(self) -> None:
        t = ConvergenceTracker(min_rounds=2)
        rounds = _rounds(
            winners=["x", "x"],
            confidences=[0.5, 0.5],
        )
        result = t.assess(rounds)
        assert result.confidence_trend_slope == pytest.approx(0.0)

    def test_negative_slope(self) -> None:
        t = ConvergenceTracker(min_rounds=2)
        rounds = _rounds(
            winners=["x", "x", "x"],
            confidences=[1.0, 0.5, 0.0],
        )
        result = t.assess(rounds)
        assert result.confidence_trend_slope == pytest.approx(-0.5)

# ---------------------------------------------------------------------------
# Order validation
# ---------------------------------------------------------------------------

class TestOrderValidation:
    def test_out_of_order_rejected(self) -> None:
        t = ConvergenceTracker()
        rounds = [
            RoundResult(round_index=5, winner="a", confidence=0.5),
            RoundResult(round_index=3, winner="a", confidence=0.5),  # out
        ]
        with pytest.raises(ValueError):
            t.assess(rounds)

    def test_duplicate_index_rejected(self) -> None:
        t = ConvergenceTracker()
        rounds = [
            RoundResult(round_index=1, winner="a", confidence=0.5),
            RoundResult(round_index=1, winner="a", confidence=0.6),
        ]
        with pytest.raises(ValueError):
            t.assess(rounds)

    def test_sparse_indices_allowed_if_increasing(self) -> None:
        t = ConvergenceTracker()
        rounds = [
            RoundResult(round_index=0, winner="x", confidence=0.5),
            RoundResult(round_index=100, winner="x", confidence=0.6),
            RoundResult(round_index=999, winner="x", confidence=0.7),
        ]
        result = t.assess(rounds)
        # Indices can be sparse; slope math uses positional ordering.
        assert result.verdict is ConvergenceVerdict.CONVERGED

# ---------------------------------------------------------------------------
# Quality composition
# ---------------------------------------------------------------------------

class TestQualityComposition:
    def test_quality_clamped_to_unit_interval(self) -> None:
        t = ConvergenceTracker()
        rounds = _rounds(
            winners=["x", "x", "x", "x"],
            confidences=[0.7, 0.75, 0.8, 0.85],
        )
        result = t.assess(rounds)
        assert 0.0 <= result.convergence_quality <= 1.0

    def test_quality_zero_when_no_stability(self) -> None:
        # Pure oscillation, current winner stays only 1 round in window.
        t = ConvergenceTracker(
            min_rounds=3,
            stable_window_rounds=3,
        )
        rounds = _rounds(
            winners=["a", "b", "c", "d"],
            confidences=[0.5, 0.5, 0.5, 0.5],
        )
        result = t.assess(rounds)
        # d won only the most recent round; stability = 1/3
        # quality should be small.
        assert result.convergence_quality < 0.5

    def test_quality_high_when_converged(self) -> None:
        t = ConvergenceTracker(min_rounds=3, stable_window_rounds=3)
        rounds = _rounds(
            winners=["x", "x", "x", "x"],
            confidences=[0.5, 0.6, 0.7, 0.8],
        )
        result = t.assess(rounds)
        assert result.convergence_quality > 0.8

# ---------------------------------------------------------------------------
# round_results_from_records adapter
# ---------------------------------------------------------------------------

class TestAdapter:
    def test_projects_records(self) -> None:
        records = [
            _FakeRecord(outcome="x", confidence=0.5),
            _FakeRecord(outcome="x", confidence=0.6),
            _FakeRecord(outcome="y", confidence=0.7),
        ]
        rounds = round_results_from_records(records)
        assert len(rounds) == 3
        assert rounds[0].winner == "x"
        assert rounds[2].winner == "y"
        assert rounds[0].round_index == 0
        assert rounds[2].round_index == 2

    def test_skips_unresolved_records(self) -> None:
        records = [
            _FakeRecord(outcome="x", confidence=0.5),
            _FakeRecord(outcome=None, confidence=0.0),  # skipped
            _FakeRecord(outcome="x", confidence=0.6),
        ]
        rounds = round_results_from_records(records)
        assert len(rounds) == 2
        # Round indices renumbered from 0 in projected stream.
        assert rounds[0].round_index == 0
        assert rounds[1].round_index == 1

    def test_round_indices_override(self) -> None:
        records = [
            _FakeRecord(outcome="x", confidence=0.5),
            _FakeRecord(outcome="x", confidence=0.6),
        ]
        rounds = round_results_from_records(records, round_indices=[10, 20])
        assert rounds[0].round_index == 10
        assert rounds[1].round_index == 20

    def test_empty_records(self) -> None:
        assert round_results_from_records([]) == ()

# ---------------------------------------------------------------------------
# Module-level surface
# ---------------------------------------------------------------------------

def test_verdict_constant_lockstep() -> None:
    for v in ConvergenceVerdict:
        assert v.value in CONVERGENCE_VERDICTS
    assert len(CONVERGENCE_VERDICTS) == 5

def test_trajectory_immutable() -> None:
    t = ConvergenceTracker()
    rounds = _rounds(winners=["x", "x", "x"], confidences=[0.6, 0.7, 0.8])
    result = t.assess(rounds)
    with pytest.raises(AttributeError):
        result.verdict = ConvergenceVerdict.OSCILLATING  # type: ignore[misc]

def test_round_result_immutable() -> None:
    r = RoundResult(round_index=0, winner="x", confidence=0.5)
    with pytest.raises(AttributeError):
        r.winner = "y"  # type: ignore[misc]

def test_module_exports() -> None:
    from substrate.voting import (
        convergence_tracker as mod,
    )
    for name in (
        "CONVERGENCE_VERDICTS",
        "ConvergenceTracker",
        "ConvergenceTrajectory",
        "ConvergenceVerdict",
        "DEFAULT_DIVERGENCE_SLOPE_THRESHOLD",
        "DEFAULT_MIN_ROUNDS",
        "DEFAULT_OSCILLATION_THRESHOLD",
        "DEFAULT_STABILITY_THRESHOLD",
        "DEFAULT_STABLE_WINDOW_ROUNDS",
        "RoundResult",
        "round_results_from_records",
    ):
        assert name in mod.__all__, name

def test_trajectory_construct_directly() -> None:
    traj = ConvergenceTrajectory(
        verdict=ConvergenceVerdict.CONVERGED,
        current_winner="x",
        convergence_quality=1.0,
        winner_stability=1.0,
        oscillation_count=0,
        oscillation_rate=0.0,
        confidence_trend_slope=0.05,
        rounds_assessed=4,
        reasoning="manual",
    )
    assert traj.is_converged is True
