"""Tests for SubstrateMetricsAggregator"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from substrate.audit.substrate_trace import (
    DriftPatternSummary,
    SubstrateTraceLedger,
    SubstrateTraceRecord,
)
from substrate.drift.drift_pattern_matcher import DriftPattern
from substrate.harness import InterceptKind
from substrate.metrics.substrate_metrics import (
    SubstrateMetrics,
    SubstrateMetricsAggregator,
    SubstrateMetricsWindow,
)
from substrate.net_potential_gain_gate import (
    NetPotentialGainVerdict,
)
from substrate.resistance_band import (
    ResistanceBandClassification,
)

# -----------------------------
# Helpers
# -----------------------------

def _append(
    ledger: SubstrateTraceLedger,
    **overrides: Any,
) -> SubstrateTraceRecord:
    base: dict[str, Any] = {
        "decision_id": "d-1",
        "decision_kind": "observer_activate",
        "permitted": True,
        "rationale": "ok",
        "epoch_seconds": 1_700_000_000,
    }
    base.update(overrides)
    return ledger.append(**base)

def _seeded_ledger(count: int = 3) -> SubstrateTraceLedger:
    ledger = SubstrateTraceLedger()
    for i in range(count):
        _append(
            ledger,
            decision_id=f"d-{i}",
            epoch_seconds=1_700_000_000 + i,
            npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
        )
    return ledger

def _agg() -> SubstrateMetricsAggregator:
    return SubstrateMetricsAggregator()

# -----------------------------
# Empty cases
# -----------------------------

class TestEmpty:
    def test_empty_records_returns_zero_metrics(self) -> None:
        m = _agg().aggregate(())
        assert m.record_count == 0
        assert m.earliest_epoch_seconds is None
        assert m.latest_epoch_seconds is None
        assert m.npg_net_positive == 0
        assert m.sin_count_by_kind == ()
        assert m.intercept_count_by_kind == ()

    def test_empty_rates_return_none(self) -> None:
        m = _agg().aggregate(())
        assert m.npg_positive_rate is None
        assert m.npg_negative_rate is None
        assert m.npg_insufficient_rate is None
        assert m.npg_present_rate is None
        assert m.productive_rate is None
        assert m.stressed_rate is None
        assert m.under_loaded_rate is None
        assert m.sin_detection_rate is None
        assert m.pride_present_rate is None
        assert m.intercept_rate is None
        assert m.permit_rate is None
        assert m.deny_rate is None

    def test_empty_ledger_aggregation(self) -> None:
        m = _agg().aggregate_from_ledger(SubstrateTraceLedger())
        assert m.record_count == 0

# -----------------------------
# NPG distribution
# -----------------------------

class TestNpgDistribution:
    def test_single_positive_record(self) -> None:
        ledger = _seeded_ledger(1)
        m = _agg().aggregate_from_ledger(ledger)
        assert m.record_count == 1
        assert m.npg_net_positive == 1
        assert m.npg_positive_rate == 1.0

    def test_all_verdicts_counted(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=1,
                npg_verdict=NetPotentialGainVerdict.NET_POSITIVE)
        _append(ledger, decision_id="b", epoch_seconds=2,
                npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE)
        _append(ledger, decision_id="c", epoch_seconds=3,
                npg_verdict=NetPotentialGainVerdict.NET_NEUTRAL)
        _append(ledger, decision_id="d", epoch_seconds=4,
                npg_verdict=NetPotentialGainVerdict.INSUFFICIENT_DATA)
        _append(ledger, decision_id="e", epoch_seconds=5)  # absent
        m = _agg().aggregate_from_ledger(ledger)
        assert m.npg_net_positive == 1
        assert m.npg_net_negative == 1
        assert m.npg_net_neutral == 1
        assert m.npg_insufficient_data == 1
        assert m.npg_absent == 1
        assert (
            m.npg_net_positive + m.npg_net_negative + m.npg_net_neutral
            + m.npg_insufficient_data + m.npg_absent
        ) == m.record_count

    def test_npg_present_rate_excludes_absent(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=1,
                npg_verdict=NetPotentialGainVerdict.NET_POSITIVE)
        _append(ledger, decision_id="b", epoch_seconds=2)  # absent
        m = _agg().aggregate_from_ledger(ledger)
        assert m.npg_present_rate == 0.5

# -----------------------------
# Resistance band distribution
# -----------------------------

class TestResistanceBand:
    def test_band_distribution_counted(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=1,
                resistance_band=ResistanceBandClassification.UNDER_LOADED)
        _append(ledger, decision_id="b", epoch_seconds=2,
                resistance_band=ResistanceBandClassification.PRODUCTIVE)
        _append(ledger, decision_id="c", epoch_seconds=3,
                resistance_band=ResistanceBandClassification.STRESSED)
        _append(ledger, decision_id="d", epoch_seconds=4)  # absent
        m = _agg().aggregate_from_ledger(ledger)
        assert m.rb_under_loaded == 1
        assert m.rb_productive == 1
        assert m.rb_stressed == 1
        assert m.rb_absent == 1

    def test_productive_rate(self) -> None:
        ledger = SubstrateTraceLedger()
        for i in range(4):
            _append(ledger, decision_id=f"d-{i}", epoch_seconds=i,
                    resistance_band=ResistanceBandClassification.PRODUCTIVE)
        _append(ledger, decision_id="d-x", epoch_seconds=99,
                resistance_band=ResistanceBandClassification.STRESSED)
        m = _agg().aggregate_from_ledger(ledger)
        assert m.productive_rate == 0.8
        assert m.stressed_rate == 0.2

# -----------------------------
# DriftPattern pattern statistics
# -----------------------------

class TestSinPatternStats:
    def test_no_sin_records_zero_detection(self) -> None:
        ledger = _seeded_ledger(3)
        m = _agg().aggregate_from_ledger(ledger)
        assert m.sin_any_detection_count == 0
        assert m.sin_detection_rate == 0.0
        assert m.sin_count_by_kind == ()
        assert m.sin_pride_present_count == 0

    def test_sin_detection_counted(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=1,
                sin_summary=DriftPatternSummary(
                    dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
                    composite_confidence=0.8,
                    amplifier_pattern_present=True,
                    kinds_detected=(DriftPattern.SELF_REFERENCE_MISCALIBRATION,),
                ))
        _append(ledger, decision_id="b", epoch_seconds=2)
        m = _agg().aggregate_from_ledger(ledger)
        assert m.sin_any_detection_count == 1
        assert m.sin_pride_present_count == 1
        assert m.sin_detection_rate == 0.5
        assert m.pride_present_rate == 0.5

    def test_sin_count_by_kind_aggregates_across_records(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=1,
                sin_summary=DriftPatternSummary(
                    dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
                    composite_confidence=0.8,
                    amplifier_pattern_present=True,
                    kinds_detected=(
                        DriftPattern.SELF_REFERENCE_MISCALIBRATION,
                        DriftPattern.REACTIVE_NET_NEGATIVE,
                    ),
                ))
        _append(ledger, decision_id="b", epoch_seconds=2,
                sin_summary=DriftPatternSummary(
                    dominant_pattern=DriftPattern.REACTIVE_NET_NEGATIVE, composite_confidence=0.8,
                    amplifier_pattern_present=False, kinds_detected=(DriftPattern.REACTIVE_NET_NEGATIVE,),
                ))
        m = _agg().aggregate_from_ledger(ledger)
        # Sort by pattern.value for stable comparison.
        counts = dict(m.sin_count_by_kind)
        assert counts.get(DriftPattern.SELF_REFERENCE_MISCALIBRATION) == 1
        assert counts.get(DriftPattern.REACTIVE_NET_NEGATIVE) == 2

    def test_sin_count_by_kind_sorted_by_enum_value(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=1,
                sin_summary=DriftPatternSummary(
                    dominant_pattern=DriftPattern.REACTIVE_NET_NEGATIVE,
                    composite_confidence=0.8,
                    amplifier_pattern_present=False,
                    kinds_detected=(
                        DriftPattern.REACTIVE_NET_NEGATIVE,
                        DriftPattern.EXTRACTIVE_GAIN,
                        DriftPattern.SELF_REFERENCE_MISCALIBRATION,
                    ),
                ))
        m = _agg().aggregate_from_ledger(ledger)
        keys = [s.value for s, _ in m.sin_count_by_kind]
        assert keys == sorted(keys)

# -----------------------------
# Harness intercepts
# -----------------------------

class TestHarnessIntercepts:
    def test_no_intercepts_zero_rate(self) -> None:
        ledger = _seeded_ledger(3)
        m = _agg().aggregate_from_ledger(ledger)
        assert m.intercept_any_count == 0
        assert m.intercept_rate == 0.0
        assert m.intercept_count_by_kind == ()

    def test_intercept_counted(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=1,
                harness_intercept_kinds=(InterceptKind.NPG_NEGATIVE,))
        _append(ledger, decision_id="b", epoch_seconds=2)
        m = _agg().aggregate_from_ledger(ledger)
        assert m.intercept_any_count == 1
        assert m.intercept_rate == 0.5
        assert dict(m.intercept_count_by_kind)[InterceptKind.NPG_NEGATIVE] == 1

    def test_multi_intercept_record_counts_each_kind(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=1,
                harness_intercept_kinds=(
                    InterceptKind.NPG_NEGATIVE,
                    InterceptKind.INVERSION_DETECTED,
                ))
        m = _agg().aggregate_from_ledger(ledger)
        counts = dict(m.intercept_count_by_kind)
        assert counts[InterceptKind.NPG_NEGATIVE] == 1
        assert counts[InterceptKind.INVERSION_DETECTED] == 1
        # But intercept_any_count is 1: the record had any intercepts.
        assert m.intercept_any_count == 1

# -----------------------------
# Permit / deny
# -----------------------------

class TestPermitDeny:
    def test_all_permitted(self) -> None:
        ledger = _seeded_ledger(3)
        m = _agg().aggregate_from_ledger(ledger)
        assert m.permitted_count == 3
        assert m.denied_count == 0
        assert m.permit_rate == 1.0
        assert m.deny_rate == 0.0

    def test_mixed_permit_deny(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=1, permitted=True)
        _append(ledger, decision_id="b", epoch_seconds=2, permitted=False)
        _append(ledger, decision_id="c", epoch_seconds=3, permitted=False)
        m = _agg().aggregate_from_ledger(ledger)
        assert m.permit_rate == pytest.approx(1 / 3)
        assert m.deny_rate == pytest.approx(2 / 3)
        assert m.permitted_count + m.denied_count == m.record_count

# -----------------------------
# Time range
# -----------------------------

class TestTimeRange:
    def test_earliest_latest_from_records(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=300)
        _append(ledger, decision_id="b", epoch_seconds=100)
        _append(ledger, decision_id="c", epoch_seconds=200)
        m = _agg().aggregate_from_ledger(ledger)
        assert m.earliest_epoch_seconds == 100
        assert m.latest_epoch_seconds == 300

# -----------------------------
# Window aggregation
# -----------------------------

class TestWindowAggregation:
    def test_invalid_window_size_rejected(self) -> None:
        with pytest.raises(ValueError, match="window_size_seconds"):
            _agg().aggregate_windows((), window_size_seconds=0)
        with pytest.raises(ValueError, match="window_size_seconds"):
            _agg().aggregate_windows((), window_size_seconds=-1)

    def test_empty_records_no_windows(self) -> None:
        windows = _agg().aggregate_windows(
            (), window_size_seconds=60,
        )
        assert windows == ()

    def test_single_window_when_all_records_fit(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=100)
        _append(ledger, decision_id="b", epoch_seconds=110)
        _append(ledger, decision_id="c", epoch_seconds=120)
        windows = _agg().aggregate_windows(
            ledger.records(), window_size_seconds=60,
        )
        assert len(windows) == 1
        assert windows[0].metrics.record_count == 3

    def test_multiple_windows_when_records_span_buckets(self) -> None:
        ledger = SubstrateTraceLedger()
        # Window size 60, anchor will be 100 (earliest):
        # [100..160) ← 100, 150
        # [160..220) ← 170, 200
        # [220..280) ← 250
        _append(ledger, decision_id="a", epoch_seconds=100)
        _append(ledger, decision_id="b", epoch_seconds=150)
        _append(ledger, decision_id="c", epoch_seconds=170)
        _append(ledger, decision_id="d", epoch_seconds=200)
        _append(ledger, decision_id="e", epoch_seconds=250)
        windows = _agg().aggregate_windows(
            ledger.records(), window_size_seconds=60,
        )
        assert len(windows) == 3
        assert windows[0].window_start_epoch_seconds == 100
        assert windows[0].window_end_epoch_seconds_exclusive == 160
        assert windows[0].metrics.record_count == 2
        assert windows[1].window_start_epoch_seconds == 160
        assert windows[1].metrics.record_count == 2
        assert windows[2].window_start_epoch_seconds == 220
        assert windows[2].metrics.record_count == 1

    def test_custom_anchor_honored(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=100)
        _append(ledger, decision_id="b", epoch_seconds=150)
        windows = _agg().aggregate_windows(
            ledger.records(),
            window_size_seconds=100,
            window_anchor_epoch_seconds=0,
        )
        # Anchor 0, window size 100:
        # [100..200) holds both.
        assert len(windows) == 1
        assert windows[0].window_start_epoch_seconds == 100

    def test_aggregate_windows_from_ledger_convenience(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=100)
        windows = _agg().aggregate_windows_from_ledger(
            ledger, window_size_seconds=60,
        )
        assert len(windows) == 1
        assert windows[0].metrics.record_count == 1

    def test_windows_sorted_by_start(self) -> None:
        ledger = SubstrateTraceLedger()
        _append(ledger, decision_id="a", epoch_seconds=500)
        _append(ledger, decision_id="b", epoch_seconds=100)
        _append(ledger, decision_id="c", epoch_seconds=300)
        windows = _agg().aggregate_windows(
            ledger.records(), window_size_seconds=100,
        )
        starts = [w.window_start_epoch_seconds for w in windows]
        assert starts == sorted(starts)

# -----------------------------
# Metric dataclass surface
# -----------------------------

class TestMetricsSurface:
    def test_metrics_is_frozen(self) -> None:
        m = _agg().aggregate(())
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.record_count = 99

    def test_window_is_frozen(self) -> None:
        ledger = _seeded_ledger(1)
        w = _agg().aggregate_windows(
            ledger.records(), window_size_seconds=60,
        )[0]
        with pytest.raises(dataclasses.FrozenInstanceError):
            w.window_start_epoch_seconds = 0

    def test_window_carries_metrics_dataclass(self) -> None:
        ledger = _seeded_ledger(1)
        w = _agg().aggregate_windows(
            ledger.records(), window_size_seconds=60,
        )[0]
        assert isinstance(w, SubstrateMetricsWindow)
        assert isinstance(w.metrics, SubstrateMetrics)

# -----------------------------
# Composition end-to-end
# -----------------------------

class TestEndToEndComposition:
    def test_full_metrics_pipeline(self) -> None:
        ledger = SubstrateTraceLedger()
        # Two permitted, one denied; mixed verdict + bands + patterns.
        _append(ledger, decision_id="a", epoch_seconds=100,
                npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
                resistance_band=ResistanceBandClassification.PRODUCTIVE)
        _append(ledger, decision_id="b", epoch_seconds=110, permitted=False,
                npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE,
                resistance_band=ResistanceBandClassification.STRESSED,
                sin_summary=DriftPatternSummary(
                    dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION, composite_confidence=0.9,
                    amplifier_pattern_present=True,
                    kinds_detected=(DriftPattern.SELF_REFERENCE_MISCALIBRATION, DriftPattern.REACTIVE_NET_NEGATIVE),
                ),
                harness_intercept_kinds=(
                    InterceptKind.NPG_NEGATIVE,
                    InterceptKind.INVERSION_DETECTED,
                ))
        _append(ledger, decision_id="c", epoch_seconds=120,
                npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
                resistance_band=ResistanceBandClassification.PRODUCTIVE)
        m = _agg().aggregate_from_ledger(ledger)
        assert m.record_count == 3
        assert m.permit_rate == pytest.approx(2 / 3)
        assert m.npg_positive_rate == pytest.approx(2 / 3)
        assert m.npg_negative_rate == pytest.approx(1 / 3)
        assert m.productive_rate == pytest.approx(2 / 3)
        assert m.stressed_rate == pytest.approx(1 / 3)
        assert m.sin_detection_rate == pytest.approx(1 / 3)
        assert m.pride_present_rate == pytest.approx(1 / 3)
        assert m.intercept_rate == pytest.approx(1 / 3)
