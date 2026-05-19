"""Tests for SubstrateModeShiftDetector"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from substrate.audit.substrate_trace import (
    DriftPatternSummary,
    SubstrateTraceLedger,
)
from substrate.drift.drift_pattern_matcher import DriftPattern
from substrate.harness import InterceptKind
from substrate.net_potential_gain_gate import (
    NetPotentialGainVerdict,
)
from substrate.resistance_band import (
    ResistanceBandClassification,
)
from substrate.workflow.substrate_mode_shift_detector import (
    DEFAULT_SHIFT_CONFIG,
    SubstrateModeShiftConfig,
    SubstrateModeShiftDetector,
    SubstrateModeShiftReport,
    SubstrateModeShiftVerdict,
)

# -----------------------------
# Helpers
# -----------------------------

def _append(ledger: SubstrateTraceLedger, **overrides: Any) -> None:
    base: dict[str, Any] = {
        "decision_id": "d-?",
        "decision_kind": "observer_activate",
        "permitted": True,
        "rationale": "ok",
        "epoch_seconds": 1_700_000_000,
    }
    base.update(overrides)
    ledger.append(**base)

def _aligned_ledger(count: int) -> SubstrateTraceLedger:
    ledger = SubstrateTraceLedger()
    for i in range(count):
        _append(
            ledger,
            decision_id=f"d-{i}",
            epoch_seconds=1_700_000_000 + i,
            npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
            resistance_band=ResistanceBandClassification.PRODUCTIVE,
        )
    return ledger

def _misaligned_ledger(count: int) -> SubstrateTraceLedger:
    ledger = SubstrateTraceLedger()
    for i in range(count):
        _append(
            ledger,
            decision_id=f"d-{i}",
            epoch_seconds=1_700_000_000 + i,
            permitted=False,
            npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE,
            resistance_band=ResistanceBandClassification.STRESSED,
            sin_summary=DriftPatternSummary(
                dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
                composite_confidence=0.9,
                amplifier_pattern_present=True,
                kinds_detected=(DriftPattern.SELF_REFERENCE_MISCALIBRATION,),
            ),
            harness_intercept_kinds=(InterceptKind.NPG_NEGATIVE,),
        )
    return ledger

def _drifting_ledger(count: int = 10) -> SubstrateTraceLedger:
    """Start aligned, end misaligned."""
    ledger = SubstrateTraceLedger()
    for i in range(count):
        # Linearly decrease alignment.
        fraction_bad = i / (count - 1)
        if fraction_bad < 0.5:
            _append(
                ledger,
                decision_id=f"d-{i}",
                epoch_seconds=1_700_000_000 + i,
                npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
                resistance_band=ResistanceBandClassification.PRODUCTIVE,
            )
        else:
            _append(
                ledger,
                decision_id=f"d-{i}",
                epoch_seconds=1_700_000_000 + i,
                permitted=False,
                npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE,
                resistance_band=ResistanceBandClassification.STRESSED,
                harness_intercept_kinds=(InterceptKind.NPG_NEGATIVE,),
                sin_summary=DriftPatternSummary(
                    dominant_pattern=DriftPattern.REACTIVE_NET_NEGATIVE,
                    composite_confidence=0.9,
                    amplifier_pattern_present=False,
                    kinds_detected=(DriftPattern.REACTIVE_NET_NEGATIVE,),
                ),
            )
    return ledger

def _recovering_ledger(count: int = 10) -> SubstrateTraceLedger:
    """Start misaligned, end aligned."""
    ledger = SubstrateTraceLedger()
    for i in range(count):
        fraction_good = i / (count - 1)
        if fraction_good < 0.5:
            _append(
                ledger,
                decision_id=f"d-{i}",
                epoch_seconds=1_700_000_000 + i,
                permitted=False,
                npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE,
                resistance_band=ResistanceBandClassification.STRESSED,
                harness_intercept_kinds=(InterceptKind.NPG_NEGATIVE,),
                sin_summary=DriftPatternSummary(
                    dominant_pattern=DriftPattern.REACTIVE_NET_NEGATIVE,
                    composite_confidence=0.9,
                    amplifier_pattern_present=False,
                    kinds_detected=(DriftPattern.REACTIVE_NET_NEGATIVE,),
                ),
            )
        else:
            _append(
                ledger,
                decision_id=f"d-{i}",
                epoch_seconds=1_700_000_000 + i,
                npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
                resistance_band=ResistanceBandClassification.PRODUCTIVE,
            )
    return ledger

def _oscillating_ledger(count: int = 10) -> SubstrateTraceLedger:
    """Alternating aligned / misaligned records — no net trend, high variance."""
    ledger = SubstrateTraceLedger()
    for i in range(count):
        if i % 2 == 0:
            _append(
                ledger,
                decision_id=f"d-{i}",
                epoch_seconds=1_700_000_000 + i,
                npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
                resistance_band=ResistanceBandClassification.PRODUCTIVE,
            )
        else:
            _append(
                ledger,
                decision_id=f"d-{i}",
                epoch_seconds=1_700_000_000 + i,
                permitted=False,
                npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE,
                resistance_band=ResistanceBandClassification.STRESSED,
                harness_intercept_kinds=(InterceptKind.NPG_NEGATIVE,),
                sin_summary=DriftPatternSummary(
                    dominant_pattern=DriftPattern.REACTIVE_NET_NEGATIVE,
                    composite_confidence=0.9,
                    amplifier_pattern_present=False,
                    kinds_detected=(DriftPattern.REACTIVE_NET_NEGATIVE,),
                ),
            )
    return ledger

def _detector() -> SubstrateModeShiftDetector:
    return SubstrateModeShiftDetector()

# -----------------------------
# Config validation
# -----------------------------

class TestConfigValidation:
    def test_default_config_valid(self) -> None:
        assert isinstance(DEFAULT_SHIFT_CONFIG, SubstrateModeShiftConfig)

    def test_min_records_below_two_rejected(self) -> None:
        with pytest.raises(ValueError, match="min_records"):
            SubstrateModeShiftConfig(min_records=1)
        with pytest.raises(ValueError, match="min_records"):
            SubstrateModeShiftConfig(min_records=0)

    def test_drift_slope_must_be_negative(self) -> None:
        with pytest.raises(ValueError, match="drift_slope_threshold"):
            SubstrateModeShiftConfig(drift_slope_threshold=0.0)
        with pytest.raises(ValueError, match="drift_slope_threshold"):
            SubstrateModeShiftConfig(drift_slope_threshold=0.1)

    def test_recover_slope_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="recover_slope_threshold"):
            SubstrateModeShiftConfig(recover_slope_threshold=0.0)
        with pytest.raises(ValueError, match="recover_slope_threshold"):
            SubstrateModeShiftConfig(recover_slope_threshold=-0.1)

    def test_oscillation_threshold_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="oscillation_stddev_threshold"):
            SubstrateModeShiftConfig(oscillation_stddev_threshold=0.0)

    def test_negative_weight_rejected(self) -> None:
        with pytest.raises(ValueError, match="npg_weight"):
            SubstrateModeShiftConfig(npg_weight=-1.0)
        with pytest.raises(ValueError, match="rb_weight"):
            SubstrateModeShiftConfig(rb_weight=0.0)

# -----------------------------
# Insufficient data
# -----------------------------

class TestInsufficientData:
    def test_empty_records_insufficient(self) -> None:
        report = _detector().detect(())
        assert report.verdict is SubstrateModeShiftVerdict.INSUFFICIENT_DATA
        assert report.slope is None
        assert report.stddev is None
        assert report.per_record_alignment == ()

    def test_below_min_records_insufficient(self) -> None:
        d = SubstrateModeShiftDetector(
            config=SubstrateModeShiftConfig(min_records=5),
        )
        report = d.detect_from_ledger(_aligned_ledger(3))
        assert report.verdict is SubstrateModeShiftVerdict.INSUFFICIENT_DATA
        assert "insufficient history" in report.rationale.lower()

    def test_at_min_records_classifies(self) -> None:
        d = SubstrateModeShiftDetector(
            config=SubstrateModeShiftConfig(min_records=3),
        )
        report = d.detect_from_ledger(_aligned_ledger(3))
        assert report.verdict is not SubstrateModeShiftVerdict.INSUFFICIENT_DATA

# -----------------------------
# Verdict resolution
# -----------------------------

class TestVerdictResolution:
    def test_aligned_records_stable(self) -> None:
        report = _detector().detect_from_ledger(_aligned_ledger(10))
        assert report.verdict is SubstrateModeShiftVerdict.STABLE
        assert report.is_stable is True
        # All-aligned records all score 1.0 → slope = 0, stddev = 0.
        assert report.slope == pytest.approx(0.0)
        assert report.stddev == pytest.approx(0.0)

    def test_misaligned_records_stable(self) -> None:
        # All-misaligned records also classify STABLE — no trend, no variance.
        report = _detector().detect_from_ledger(_misaligned_ledger(10))
        assert report.verdict is SubstrateModeShiftVerdict.STABLE
        # Mean alignment should be low.
        assert report.mean_alignment is not None
        assert report.mean_alignment < 0.3

    def test_drifting_records_classify_drifting(self) -> None:
        report = _detector().detect_from_ledger(_drifting_ledger(10))
        assert report.verdict is SubstrateModeShiftVerdict.DRIFTING
        assert report.is_drifting is True
        assert report.slope is not None
        assert report.slope < 0

    def test_recovering_records_classify_recovering(self) -> None:
        report = _detector().detect_from_ledger(_recovering_ledger(10))
        assert report.verdict is SubstrateModeShiftVerdict.RECOVERING
        assert report.is_recovering is True
        assert report.slope is not None
        assert report.slope > 0

    def test_oscillating_records_classify_oscillating(self) -> None:
        report = _detector().detect_from_ledger(_oscillating_ledger(10))
        assert report.verdict is SubstrateModeShiftVerdict.OSCILLATING
        assert report.is_oscillating is True
        assert report.stddev is not None
        assert report.stddev >= 0.25

# -----------------------------
# Alignment scoring components
# -----------------------------

class TestAlignmentScoring:
    def test_clean_record_scores_high(self) -> None:
        ledger = _aligned_ledger(5)
        report = _detector().detect_from_ledger(ledger)
        # All five components score 1.0 → alignment 1.0.
        for score in report.per_record_alignment:
            assert score == 1.0

    def test_misaligned_record_scores_low(self) -> None:
        ledger = _misaligned_ledger(5)
        report = _detector().detect_from_ledger(ledger)
        for score in report.per_record_alignment:
            # NPG=0, RB=0.2, intercept=0, pattern=0 → mean = 0.05.
            assert score < 0.2

    def test_absent_fields_neutral(self) -> None:
        # Record with no NPG, no RB, no pattern, no intercept → all neutral 0.5
        # except intercept (no intercept → 1.0) and pattern (none → 1.0).
        # Score = (0.5 + 0.5 + 1.0 + 1.0) / 4 = 0.75
        ledger = SubstrateTraceLedger()
        for i in range(5):
            _append(
                ledger,
                decision_id=f"d-{i}",
                epoch_seconds=1_700_000_000 + i,
            )
        report = _detector().detect_from_ledger(ledger)
        for score in report.per_record_alignment:
            assert score == pytest.approx(0.75)

    def test_per_component_scoring_independent(self) -> None:
        # Only NPG positive; other fields absent.
        ledger = SubstrateTraceLedger()
        for i in range(5):
            _append(
                ledger,
                decision_id=f"d-{i}",
                epoch_seconds=1_700_000_000 + i,
                npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
            )
        report = _detector().detect_from_ledger(ledger)
        # NPG=1.0, RB=0.5, intercept=1.0, pattern=1.0 → 0.875
        for score in report.per_record_alignment:
            assert score == pytest.approx(0.875)

# -----------------------------
# Custom config thresholds
# -----------------------------

class TestCustomConfig:
    def test_strict_drift_threshold_makes_drift_harder(self) -> None:
        # With a very strict drift threshold (-0.5), even a moderate
        # negative slope won't trip DRIFTING.
        d_strict = SubstrateModeShiftDetector(
            config=SubstrateModeShiftConfig(
                min_records=3, drift_slope_threshold=-0.5,
            ),
        )
        report = d_strict.detect_from_ledger(_drifting_ledger(10))
        # Drifting ledger has slope around -0.1 to -0.2; below -0.5
        # threshold → not DRIFTING.
        assert report.verdict is not SubstrateModeShiftVerdict.DRIFTING

    def test_lax_recovery_threshold_makes_recovery_easier(self) -> None:
        d_lax = SubstrateModeShiftDetector(
            config=SubstrateModeShiftConfig(
                min_records=3, recover_slope_threshold=0.001,
            ),
        )
        # Stable aligned has slope = 0.0, exactly at threshold doesn't qualify.
        # Use a slightly increasing alignment.
        ledger = SubstrateTraceLedger()
        for i in range(5):
            verdict = (
                NetPotentialGainVerdict.NET_NEUTRAL
                if i < 2
                else NetPotentialGainVerdict.NET_POSITIVE
            )
            _append(
                ledger,
                decision_id=f"d-{i}",
                epoch_seconds=1_700_000_000 + i,
                npg_verdict=verdict,
                resistance_band=ResistanceBandClassification.PRODUCTIVE,
            )
        report = d_lax.detect_from_ledger(ledger)
        assert report.verdict is SubstrateModeShiftVerdict.RECOVERING

# -----------------------------
# Report surface
# -----------------------------

class TestReportSurface:
    def test_report_is_frozen(self) -> None:
        report = _detector().detect(())
        with pytest.raises(dataclasses.FrozenInstanceError):
            report.verdict = SubstrateModeShiftVerdict.STABLE

    def test_report_rationale_includes_slope(self) -> None:
        report = _detector().detect_from_ledger(_aligned_ledger(10))
        assert "slope=" in report.rationale
        assert "verdict=" in report.rationale

    def test_earliest_and_latest_alignment_set(self) -> None:
        report = _detector().detect_from_ledger(_drifting_ledger(10))
        assert report.earliest_alignment is not None
        assert report.latest_alignment is not None
        # Drifting → earliest higher than latest.
        assert report.earliest_alignment > report.latest_alignment

    def test_detect_returns_report_type(self) -> None:
        report = _detector().detect(())
        assert isinstance(report, SubstrateModeShiftReport)

    def test_per_record_alignment_length_matches_records(self) -> None:
        ledger = _aligned_ledger(7)
        report = _detector().detect_from_ledger(ledger)
        assert len(report.per_record_alignment) == 7

    def test_mean_alignment_consistent(self) -> None:
        report = _detector().detect_from_ledger(_aligned_ledger(10))
        assert report.mean_alignment == pytest.approx(
            sum(report.per_record_alignment)
            / len(report.per_record_alignment)
        )

    def test_alignment_in_unit_interval(self) -> None:
        for ledger in (
            _aligned_ledger(10),
            _misaligned_ledger(10),
            _drifting_ledger(10),
            _oscillating_ledger(10),
        ):
            report = _detector().detect_from_ledger(ledger)
            for v in report.per_record_alignment:
                assert 0.0 <= v <= 1.0
