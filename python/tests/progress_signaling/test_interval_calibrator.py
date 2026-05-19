"""Tests for SubstrateAlignedIntervalCalibrator (Plan 3art 32)."""
from __future__ import annotations

import pytest

from substrate.progress_signaling.interval_calibrator import (
    DEFAULT_INTERVAL_CALIBRATOR_CONFIG,
    IntervalCalibratorConfig,
    SubstrateAlignedIntervalCalibrator,
)
from substrate.progress_signaling.signal import (
    SubstrateSignalType,
)
from substrate.resistance_band import (
    ResistanceBandClassification,
    assess,
)

class TestConfig:
    def test_defaults(self) -> None:
        c = IntervalCalibratorConfig()
        assert c.early_seconds == 180
        assert c.stressed_multiplier == 2.0

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("early_tier_cap", -1, "early_tier_cap"),
            ("early_seconds", 0, "early_seconds"),
            ("under_loaded_multiplier", 0.0, "under_loaded_multiplier"),
            ("under_loaded_multiplier", 1.5, "under_loaded_multiplier"),
            ("stressed_multiplier", 0.5, "stressed_multiplier"),
        ],
    )
    def test_bad(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            IntervalCalibratorConfig(**{field: value})

    def test_mid_must_exceed_early(self) -> None:
        with pytest.raises(ValueError, match="mid_tier_cap"):
            IntervalCalibratorConfig(early_tier_cap=5, mid_tier_cap=3)

class TestCalibration:
    def setup_method(self) -> None:
        self.c = SubstrateAlignedIntervalCalibrator()

    def test_early_tier_progress_marker(self) -> None:
        result = self.c.calibrate(
            signal_type=SubstrateSignalType.PROGRESS_MARKER,
            tier_index=0, resistance=assess(utilization=0.35),
        )
        # Early tier productive band → base 180s, multiplier 1.0
        assert result.target_seconds == 180

    def test_milestone_multiplier(self) -> None:
        result = self.c.calibrate(
            signal_type=SubstrateSignalType.MILESTONE,
            tier_index=0, resistance=assess(utilization=0.35),
        )
        # 180s * 12 = 2160s (36 min)
        assert result.target_seconds == 2160

    def test_mid_tier_seconds(self) -> None:
        result = self.c.calibrate(
            signal_type=SubstrateSignalType.PROGRESS_MARKER,
            tier_index=4, resistance=assess(utilization=0.35),
        )
        assert result.target_seconds == 1800

    def test_high_tier_seconds(self) -> None:
        result = self.c.calibrate(
            signal_type=SubstrateSignalType.PROGRESS_MARKER,
            tier_index=10, resistance=assess(utilization=0.35),
        )
        assert result.target_seconds == 14400

    def test_under_loaded_tightens(self) -> None:
        a = assess(utilization=0.1)
        assert a.classification is ResistanceBandClassification.UNDER_LOADED
        result = self.c.calibrate(
            signal_type=SubstrateSignalType.PROGRESS_MARKER,
            tier_index=0, resistance=a,
        )
        # 180 * 0.5 = 90s
        assert result.target_seconds == 90

    def test_stressed_expands(self) -> None:
        a = assess(utilization=0.9)
        assert a.classification is ResistanceBandClassification.STRESSED
        result = self.c.calibrate(
            signal_type=SubstrateSignalType.PROGRESS_MARKER,
            tier_index=0, resistance=a,
        )
        # 180 * 2.0 = 360s
        assert result.target_seconds == 360

    def test_bad_tier(self) -> None:
        with pytest.raises(ValueError, match="tier_index"):
            self.c.calibrate(
                signal_type=SubstrateSignalType.PROGRESS_MARKER,
                tier_index=-1, resistance=assess(utilization=0.35),
            )

    def test_consolidation_signal_long_interval(self) -> None:
        result = self.c.calibrate(
            signal_type=SubstrateSignalType.CONSOLIDATION,
            tier_index=0, resistance=assess(utilization=0.35),
        )
        # 180 * 72 = 12960s (3.6 hours)
        assert result.target_seconds == 12960

    def test_rationale_includes_classification(self) -> None:
        result = self.c.calibrate(
            signal_type=SubstrateSignalType.PROGRESS_MARKER,
            tier_index=0, resistance=assess(utilization=0.35),
        )
        assert "productive" in result.rationale.lower()

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_INTERVAL_CALIBRATOR_CONFIG.early_seconds == 180
        )
