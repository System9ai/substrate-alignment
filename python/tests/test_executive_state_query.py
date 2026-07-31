"""Tests for the unified entity-state query, 'how are you doing?' (G51)."""
from __future__ import annotations

import pytest

from substrate.executive.band import WORK_LEVELS
from substrate.executive.state_query import (
    EffortState,
    EnergyState,
    StateObservation,
    TrajectoryDirection,
    integrate_state,
)


def _obs(*pairs: tuple[float, bool]) -> list[StateObservation]:
    return [StateObservation(u, wp) for u, wp in pairs]


class TestStateObservationValidation:
    def test_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="utilization"):
            StateObservation(1.5)


class TestIntegrateState:
    def test_empty_history_returns_none(self) -> None:
        assert integrate_state("e", []) is None

    def test_empty_entity_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            integrate_state("", [StateObservation(0.44)])

    def test_engaged_worker(self) -> None:
        r = integrate_state("alice", [StateObservation(u) for u in (0.44, 0.45, 0.43, 0.46)])
        assert r is not None
        assert r.energy is EnergyState.ENGAGED
        assert r.effort is EffortState.WORKING
        assert r.dominant_zone in WORK_LEVELS

    def test_slacking_is_avoidance_while_work_pending(self) -> None:
        # Idle, but with work pending the whole time → the avoidance trend.
        r = integrate_state(
            "bob", _obs((0.2, True), (0.18, True), (0.22, True), (0.19, True), (0.21, True)),
        )
        assert r is not None
        assert r.effort is EffortState.SLACKING
        assert r.energy is EnergyState.DEPLETED
        assert r.sustained is True

    def test_resting_is_idle_with_nothing_pending(self) -> None:
        r = integrate_state("zoe", [StateObservation(0.2) for _ in range(4)])
        assert r is not None
        assert r.effort is EffortState.RESTING

    def test_burning_out_is_sustained_danger(self) -> None:
        r = integrate_state("carol", [StateObservation(u) for u in (0.8, 0.82, 0.79, 0.81, 0.83, 0.8)])
        assert r is not None
        assert r.energy is EnergyState.STRAINED
        assert r.effort is EffortState.OVEREXERTING
        assert r.sustained is True

    def test_recovering_trajectory(self) -> None:
        # Climbing down from danger toward the work zone → moving toward health.
        r = integrate_state("dave", [StateObservation(u) for u in (0.85, 0.75, 0.6, 0.5, 0.45)])
        assert r is not None
        assert r.trajectory is TrajectoryDirection.RECOVERING

    def test_deteriorating_trajectory(self) -> None:
        # Sinking from the work zone toward idle → away from health.
        r = integrate_state("erin", [StateObservation(u) for u in (0.45, 0.4, 0.3, 0.2, 0.1)])
        assert r is not None
        assert r.trajectory is TrajectoryDirection.DETERIORATING

    def test_transient_peak_is_a_good_push(self) -> None:
        # A single excursion into peaking after work-zone readings = PEAKING, not strained.
        r = integrate_state("finn", [StateObservation(u) for u in (0.44, 0.45, 0.46, 0.6)])
        assert r is not None
        assert r.energy is EnergyState.PEAKING
        assert r.sustained is False

    def test_summary_is_human_readable(self) -> None:
        r = integrate_state("g", [StateObservation(0.44), StateObservation(0.45)])
        assert r is not None
        assert "is" in r.summary and "g" in r.summary
