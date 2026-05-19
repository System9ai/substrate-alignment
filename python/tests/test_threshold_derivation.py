"""Tests for the substrate threshold-derivation helpers."""
from __future__ import annotations

from math import sqrt

import pytest

from substrate.resistance_band import (
    LOWER_BOUND,
    UPPER_BOUND,
    ResistanceBandClassification,
    ResistanceBandConfig,
)
from substrate.threshold_derivation import (
    BandPosition,
    DEFAULT_MIN_THRESHOLD,
    assess_utilization,
    derive_batch_size,
    derive_hard_limit,
    derive_quota_pair,
    derive_retry_cap,
    derive_soft_limit,
    derive_target,
    derive_threshold,
    derive_threshold_float,
)


class TestDeriveThreshold:
    def test_target_at_band_midpoint(self) -> None:
        # capacity 1000 → band target ~0.358 → ~358
        result = derive_threshold(1000, position=BandPosition.TARGET)
        expected = int(1000 * ((LOWER_BOUND + UPPER_BOUND) / 2))
        assert result == expected

    def test_lower_at_lower_bound(self) -> None:
        result = derive_threshold(1000, position=BandPosition.LOWER)
        assert result == int(1000 * LOWER_BOUND)

    def test_upper_at_upper_bound(self) -> None:
        result = derive_threshold(1000, position=BandPosition.UPPER)
        assert result == int(1000 * UPPER_BOUND)

    def test_default_is_target(self) -> None:
        assert derive_threshold(1000) == derive_threshold(
            1000, position=BandPosition.TARGET,
        )

    def test_min_threshold_floors_small_capacity(self) -> None:
        # capacity 2 * lower_bound ≈ 0.67 → would round to 0, but floored to 1
        assert derive_threshold(2, position=BandPosition.LOWER) == 1

    def test_min_threshold_override(self) -> None:
        assert derive_threshold(2, position=BandPosition.LOWER, min_threshold=5) == 5

    def test_zero_capacity_returns_min(self) -> None:
        assert derive_threshold(0) == DEFAULT_MIN_THRESHOLD

    def test_negative_capacity_raises(self) -> None:
        with pytest.raises(ValueError, match="capacity"):
            derive_threshold(-1)


class TestDeriveThresholdFloat:
    def test_float_no_floor(self) -> None:
        # Floats do not get the min_threshold treatment.
        assert derive_threshold_float(0.0) == 0.0

    def test_target(self) -> None:
        capacity = 100.0
        midpoint = (LOWER_BOUND + UPPER_BOUND) / 2.0
        assert derive_threshold_float(capacity) == pytest.approx(
            capacity * midpoint,
        )

    def test_lower(self) -> None:
        assert derive_threshold_float(
            100.0, position=BandPosition.LOWER,
        ) == pytest.approx(100.0 * LOWER_BOUND)

    def test_negative_capacity_raises(self) -> None:
        with pytest.raises(ValueError):
            derive_threshold_float(-0.1)


class TestConvenienceHelpers:
    def test_soft_limit_is_lower(self) -> None:
        assert derive_soft_limit(1000) == derive_threshold(
            1000, position=BandPosition.LOWER,
        )

    def test_target_is_target(self) -> None:
        assert derive_target(1000) == derive_threshold(
            1000, position=BandPosition.TARGET,
        )

    def test_hard_limit_is_upper(self) -> None:
        assert derive_hard_limit(1000) == derive_threshold(
            1000, position=BandPosition.UPPER,
        )

    def test_quota_pair_ordering(self) -> None:
        soft, hard = derive_quota_pair(1000)
        assert soft <= hard
        assert soft == derive_soft_limit(1000)
        assert hard == derive_hard_limit(1000)

    def test_batch_size_uses_target(self) -> None:
        assert derive_batch_size(1000) == derive_threshold(
            1000, position=BandPosition.TARGET,
        )

    def test_retry_cap_uses_upper(self) -> None:
        assert derive_retry_cap(10) == derive_threshold(
            10, position=BandPosition.UPPER, min_threshold=1,
        )


class TestCustomConfig:
    def test_tighter_band(self) -> None:
        # ResistanceBandConfig allows only equal-or-tighter than the defaults.
        cfg = ResistanceBandConfig(lower_bound=0.34, upper_bound=0.37)
        result = derive_threshold(1000, config=cfg)
        midpoint = (0.34 + 0.37) / 2
        assert result == int(1000 * midpoint)

    def test_band_widening_rejected(self) -> None:
        # Wider than the defaults is rejected by the config itself.
        with pytest.raises(ValueError):
            ResistanceBandConfig(lower_bound=0.20, upper_bound=0.50)


class TestAssessUtilization:
    def test_below_band_under_loaded(self) -> None:
        a = assess_utilization(20.0, 100.0)
        assert a.classification is ResistanceBandClassification.UNDER_LOADED
        assert a.is_under_loaded

    def test_inside_band_productive(self) -> None:
        a = assess_utilization(36.0, 100.0)
        assert a.classification is ResistanceBandClassification.PRODUCTIVE

    def test_above_band_stressed(self) -> None:
        a = assess_utilization(80.0, 100.0)
        assert a.classification is ResistanceBandClassification.STRESSED
        assert a.is_stressed
        assert a.recommended_scaling_factor < 1.0

    def test_caps_at_capacity(self) -> None:
        # Over-utilisation is clamped to 1.0.
        a = assess_utilization(200.0, 100.0)
        assert a.utilization == 1.0

    def test_zero_capacity_raises(self) -> None:
        with pytest.raises(ValueError, match="capacity"):
            assess_utilization(1.0, 0.0)

    def test_negative_current_raises(self) -> None:
        with pytest.raises(ValueError, match="current"):
            assess_utilization(-1.0, 100.0)


class TestDefaultAnchors:
    """Lock the band's default anchors via test."""

    def test_lower_is_one_third(self) -> None:
        assert LOWER_BOUND == pytest.approx(1.0 / 3.0)

    def test_upper_is_phi_squared(self) -> None:
        # 1/φ² where φ = (1+√5)/2
        phi = (1 + sqrt(5)) / 2
        assert UPPER_BOUND == pytest.approx(1.0 / (phi * phi))
