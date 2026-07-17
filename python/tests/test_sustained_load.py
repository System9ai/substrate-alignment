"""Tests for substrate/sustained_load.py: sporadic-vs-sustained accounting."""
from __future__ import annotations

import pytest

from substrate.resistance_band import (
    DANGER_LINE,
    WORK_ZONE_UPPER,
)
from substrate.sustained_load import (
    GrowthStreakMonitor,
    LoadObservation,
    LoadTrend,
    SustainedLoadConfig,
    SustainedLoadTracker,
)


def _obs(t: int, util: float, *, pending: bool = False) -> LoadObservation:
    return LoadObservation(timestamp=t, utilization=util, work_pending=pending)


class TestObservationValidation:
    def test_rejects_out_of_range_utilization(self) -> None:
        with pytest.raises(ValueError):
            LoadObservation(timestamp=0, utilization=1.5)

    def test_rejects_negative_timestamp(self) -> None:
        with pytest.raises(ValueError):
            LoadObservation(timestamp=-1, utilization=0.4)

    def test_rejects_non_monotonic_timestamps(self) -> None:
        tracker = SustainedLoadTracker()
        tracker.observe(_obs(10, 0.4))
        with pytest.raises(ValueError):
            tracker.observe(_obs(5, 0.4))


class TestConfigValidation:
    def test_rejects_misordered_thresholds(self) -> None:
        with pytest.raises(ValueError):
            SustainedLoadConfig(spike_line=0.7, debt_line=0.6)

    def test_rejects_bad_alpha(self) -> None:
        with pytest.raises(ValueError):
            SustainedLoadConfig(ewma_alpha=0.0)


class TestSpikeVsSustained:
    def test_work_zone_is_nominal(self) -> None:
        tracker = SustainedLoadTracker()
        out = None
        for t, util in enumerate((0.40, 0.45, 0.48, 0.44)):
            out = tracker.observe(_obs(t, util))
        assert out is not None
        assert out.trend is LoadTrend.NOMINAL
        assert out.accrued_debt_units == 0.0

    def test_single_peak_is_spike(self) -> None:
        tracker = SustainedLoadTracker()
        tracker.observe(_obs(0, 0.42))
        out = tracker.observe(_obs(1, 0.55))
        assert out.trend is LoadTrend.SPIKE

    def test_sustained_peaking_is_strain(self) -> None:
        tracker = SustainedLoadTracker()
        out = None
        for t in range(6):
            out = tracker.observe(_obs(t, 0.58))
        assert out is not None
        assert out.trend is LoadTrend.SUSTAINED_STRAIN
        # Peaking sustained is strain, but below the debt line accrues
        # no debt units.
        assert out.accrued_debt_units == 0.0

    def test_sustained_in_warning_band_is_winded(self) -> None:
        # 0.64 ∈ (1/φ, 2/3): sustained = WINDED (the winded approach to
        # burnout), NOT debt; debt accrues only past the 2/3 line.
        tracker = SustainedLoadTracker()
        out = None
        for t in range(4):
            out = tracker.observe(_obs(t, 0.64))
        assert out is not None
        assert out.trend is LoadTrend.WINDED
        assert out.accrued_debt_units == 0.0

    def test_spike_decays_back_to_nominal(self) -> None:
        tracker = SustainedLoadTracker()
        tracker.observe(_obs(0, 0.55))
        out = None
        for t in range(1, 8):
            out = tracker.observe(_obs(t, 0.42))
        assert out is not None
        assert out.trend is LoadTrend.NOMINAL


class TestDebtAccrual:
    def test_sustained_above_debt_line_accrues_debt(self) -> None:
        tracker = SustainedLoadTracker()
        out = None
        for t in range(4):
            out = tracker.observe(_obs(t, 0.70))
        assert out is not None
        assert out.trend is LoadTrend.DEBT_ACCRUING
        # Accrual = (util - debt_line) per sustained observation; the
        # debt line is the uniform 2/3 (DANGER_LINE), not 1/φ.
        expected_per_obs = 0.70 - DANGER_LINE
        assert out.accrued_debt_units == pytest.approx(
            expected_per_obs * 2  # observations 3 and 4 (streak >= 3)
        )

    def test_brief_excursion_above_debt_line_is_not_debt(self) -> None:
        tracker = SustainedLoadTracker()
        tracker.observe(_obs(0, 0.45))
        out = tracker.observe(_obs(1, 0.70))
        assert out.trend is LoadTrend.SPIKE
        assert out.accrued_debt_units == 0.0

    def test_repay_floors_at_zero(self) -> None:
        tracker = SustainedLoadTracker()
        for t in range(4):
            tracker.observe(_obs(t, 0.75))
        assert tracker.accrued_debt_units > 0.0
        remaining = tracker.repay(1_000.0)
        assert remaining == 0.0

    def test_repay_rejects_negative(self) -> None:
        tracker = SustainedLoadTracker()
        with pytest.raises(ValueError):
            tracker.repay(-1.0)


class TestAvoidance:
    def test_bouncing_off_work_entry_with_work_pending(self) -> None:
        tracker = SustainedLoadTracker()
        out = None
        t = 0
        for _ in range(3):  # three approach→retreat cycles
            out = tracker.observe(_obs(t, 0.37, pending=True))
            t += 1
            out = tracker.observe(_obs(t, 0.20, pending=True))
            t += 1
        assert out is not None
        assert out.trend is LoadTrend.AVOIDANCE
        assert out.approach_retreat_cycles == 3

    def test_resting_without_pending_work_is_not_avoidance(self) -> None:
        tracker = SustainedLoadTracker()
        out = None
        t = 0
        for _ in range(4):
            out = tracker.observe(_obs(t, 0.37))
            t += 1
            out = tracker.observe(_obs(t, 0.20))
            t += 1
        assert out is not None
        assert out.trend is LoadTrend.NOMINAL
        assert out.approach_retreat_cycles == 0


class TestGrowthStreakMonitor:
    def test_phi_paced_growth_is_nominal(self) -> None:
        monitor = GrowthStreakMonitor()
        assert monitor.record_grow_step() is LoadTrend.NOMINAL
        monitor.record_maintain_step()
        assert monitor.record_grow_step() is LoadTrend.NOMINAL
        monitor.record_maintain_step()
        assert monitor.record_grow_step() is LoadTrend.NOMINAL

    def test_runaway_growth_streak_detected(self) -> None:
        monitor = GrowthStreakMonitor()
        assert monitor.record_grow_step() is LoadTrend.NOMINAL
        assert monitor.record_grow_step() is LoadTrend.NOMINAL
        assert monitor.record_grow_step() is LoadTrend.RUNAWAY_GROWTH

    def test_consolidation_resets_streak(self) -> None:
        monitor = GrowthStreakMonitor()
        monitor.record_grow_step()
        monitor.record_grow_step()
        monitor.record_maintain_step()
        assert monitor.record_grow_step() is LoadTrend.NOMINAL


class TestAnchors:
    def test_defaults_use_substrate_anchors(self) -> None:
        cfg = SustainedLoadConfig()
        assert cfg.spike_line == WORK_ZONE_UPPER
        assert cfg.debt_line == DANGER_LINE
