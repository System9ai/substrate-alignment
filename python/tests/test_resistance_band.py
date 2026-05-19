"""Tests for ResistanceBand — the productive-resistance band primitive.

Covers:
- Mathematical constants (PHI, PHI_SQUARED, LOWER_BOUND, UPPER_BOUND, TARGET)
- Default config matches the package anchors
- classify() across UNDER_LOADED / PRODUCTIVE / STRESSED including boundary inclusivity
- Out-of-range / NaN utilization rejected with ValueError
- assess() returns the full struct with correct distance + scaling
- recommend_scaling_factor edge case at utilization=0 returns finite scale-up
- Custom ResistanceBandConfig: tighter bounds accepted; bounds wider than defaults rejected
- ResistanceBandConfig invariants: lower < upper, in [0,1]
- ResistanceBandClassification / RESISTANCE_BAND_CLASSIFICATIONS lockstep
- Module __all__ exports
"""
from __future__ import annotations

import math

import pytest

from substrate import resistance_band as _resistance_band_module
from substrate.resistance_band import (
    DEFAULT_CONFIG,
    LOWER_BOUND,
    PHI,
    PHI_SQUARED,
    RESISTANCE_BAND_CLASSIFICATIONS,
    ResistanceBandAssessment,
    ResistanceBandClassification,
    ResistanceBandConfig,
    TARGET,
    UPPER_BOUND,
    assess,
    classify,
    recommend_scaling_factor,
)


# ---------------------------------------------------------------------------
# Mathematical constants
# ---------------------------------------------------------------------------


class TestMathematicalConstants:
    def test_phi_is_golden_ratio(self) -> None:
        assert PHI == pytest.approx((1.0 + math.sqrt(5.0)) / 2.0)
        assert PHI == pytest.approx(1.6180339887498949, rel=1e-12)

    def test_phi_squared_identity(self) -> None:
        # The defining property: φ² = φ + 1
        assert PHI_SQUARED == pytest.approx(PHI + 1.0, rel=1e-12)
        assert PHI_SQUARED == pytest.approx(2.6180339887498949, rel=1e-12)

    def test_lower_bound_is_one_third(self) -> None:
        assert LOWER_BOUND == pytest.approx(1.0 / 3.0, rel=1e-12)
        assert LOWER_BOUND == pytest.approx(0.3333333333333333, rel=1e-12)

    def test_upper_bound_is_one_over_phi_squared(self) -> None:
        assert UPPER_BOUND == pytest.approx(1.0 / PHI_SQUARED, rel=1e-12)
        # 1/φ² = 2 - φ (golden-ratio identity)
        assert UPPER_BOUND == pytest.approx(2.0 - PHI, rel=1e-12)
        assert UPPER_BOUND == pytest.approx(0.3819660112501051, rel=1e-12)

    def test_target_is_band_midpoint(self) -> None:
        assert TARGET == pytest.approx((LOWER_BOUND + UPPER_BOUND) / 2.0)
        assert LOWER_BOUND < TARGET < UPPER_BOUND

    def test_lower_strictly_less_than_upper(self) -> None:
        assert LOWER_BOUND < UPPER_BOUND


# ---------------------------------------------------------------------------
# ResistanceBandConfig validation
# ---------------------------------------------------------------------------


class TestResistanceBandConfigValidation:
    def test_default_config_uses_package_anchors(self) -> None:
        assert DEFAULT_CONFIG.lower_bound == LOWER_BOUND
        assert DEFAULT_CONFIG.upper_bound == UPPER_BOUND
        assert DEFAULT_CONFIG.target == TARGET

    def test_default_config_is_frozen(self) -> None:
        with pytest.raises(AttributeError):
            DEFAULT_CONFIG.lower_bound = 0.5

    def test_negative_lower_bound_rejected(self) -> None:
        with pytest.raises(ValueError):
            ResistanceBandConfig(lower_bound=-0.1, upper_bound=0.5)

    def test_upper_bound_above_one_rejected(self) -> None:
        with pytest.raises(ValueError):
            ResistanceBandConfig(lower_bound=0.3, upper_bound=1.5)

    def test_inverted_bounds_rejected(self) -> None:
        with pytest.raises(ValueError):
            ResistanceBandConfig(lower_bound=0.38, upper_bound=0.33)

    def test_equal_bounds_rejected(self) -> None:
        with pytest.raises(ValueError):
            ResistanceBandConfig(lower_bound=0.35, upper_bound=0.35)

    def test_tighter_bounds_accepted(self) -> None:
        # Tightening the band is allowed; widening beyond defaults is not.
        cfg = ResistanceBandConfig(lower_bound=0.34, upper_bound=0.37)
        assert cfg.lower_bound == pytest.approx(0.34)
        assert cfg.upper_bound == pytest.approx(0.37)
        assert cfg.target == pytest.approx(0.355)

    def test_lower_bound_looser_than_default_rejected(self) -> None:
        # Looser than 1/3 is rejected.
        with pytest.raises(ValueError):
            ResistanceBandConfig(lower_bound=0.20, upper_bound=0.37)

    def test_upper_bound_looser_than_default_rejected(self) -> None:
        # Looser than 1/φ² is rejected.
        with pytest.raises(ValueError):
            ResistanceBandConfig(lower_bound=0.34, upper_bound=0.50)


# ---------------------------------------------------------------------------
# classify()
# ---------------------------------------------------------------------------


class TestClassify:
    def test_under_loaded(self) -> None:
        assert (
            classify(0.20)
            is ResistanceBandClassification.UNDER_LOADED
        )

    def test_productive_at_target(self) -> None:
        assert classify(TARGET) is ResistanceBandClassification.PRODUCTIVE

    def test_productive_inclusive_at_lower_bound(self) -> None:
        assert (
            classify(LOWER_BOUND)
            is ResistanceBandClassification.PRODUCTIVE
        )

    def test_productive_inclusive_at_upper_bound(self) -> None:
        assert (
            classify(UPPER_BOUND)
            is ResistanceBandClassification.PRODUCTIVE
        )

    def test_stressed(self) -> None:
        assert classify(0.50) is ResistanceBandClassification.STRESSED

    def test_full_load_is_stressed(self) -> None:
        assert classify(1.0) is ResistanceBandClassification.STRESSED

    def test_zero_load_is_under_loaded(self) -> None:
        assert classify(0.0) is ResistanceBandClassification.UNDER_LOADED

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValueError):
            classify(-0.1)

    def test_above_unit_rejected(self) -> None:
        with pytest.raises(ValueError):
            classify(1.1)

    def test_nan_rejected(self) -> None:
        with pytest.raises(ValueError):
            classify(float("nan"))

    def test_inf_rejected(self) -> None:
        with pytest.raises(ValueError):
            classify(float("inf"))

    def test_custom_config_used(self) -> None:
        cfg = ResistanceBandConfig(lower_bound=0.34, upper_bound=0.36)
        # 0.35 is inside the custom band but not strictly at target
        assert (
            classify(0.35, config=cfg)
            is ResistanceBandClassification.PRODUCTIVE
        )
        # 0.337 is below the custom band's tighter lower bound
        assert (
            classify(0.337, config=cfg)
            is ResistanceBandClassification.UNDER_LOADED
        )
        # 0.37 is above the custom band's tighter upper bound
        assert (
            classify(0.37, config=cfg)
            is ResistanceBandClassification.STRESSED
        )


# ---------------------------------------------------------------------------
# assess()
# ---------------------------------------------------------------------------


class TestAssess:
    def test_productive_distance_is_zero(self) -> None:
        result = assess(TARGET)
        assert result.classification is ResistanceBandClassification.PRODUCTIVE
        assert result.distance_to_band == 0.0
        assert result.is_productive
        assert not result.is_under_loaded
        assert not result.is_stressed

    def test_under_loaded_distance_is_negative(self) -> None:
        result = assess(0.20)
        assert result.is_under_loaded
        assert result.distance_to_band < 0
        # Distance is (utilisation - lower_bound)
        assert result.distance_to_band == pytest.approx(0.20 - LOWER_BOUND)

    def test_stressed_distance_is_positive(self) -> None:
        result = assess(0.50)
        assert result.is_stressed
        assert result.distance_to_band > 0
        assert result.distance_to_band == pytest.approx(0.50 - UPPER_BOUND)

    def test_scaling_factor_at_target_is_one(self) -> None:
        result = assess(TARGET)
        assert result.recommended_scaling_factor == pytest.approx(1.0)

    def test_scaling_factor_below_target_is_above_one(self) -> None:
        # under-loaded → caller should INCREASE load (scale up)
        result = assess(0.20)
        assert result.recommended_scaling_factor > 1.0
        assert result.recommended_scaling_factor == pytest.approx(TARGET / 0.20)

    def test_scaling_factor_above_target_is_below_one(self) -> None:
        # stressed → caller should DECREASE load (scale down)
        result = assess(0.60)
        assert result.recommended_scaling_factor < 1.0
        assert result.recommended_scaling_factor == pytest.approx(TARGET / 0.60)

    def test_assessment_immutable(self) -> None:
        result = assess(TARGET)
        with pytest.raises(AttributeError):
            result.utilization = 0.99

    def test_assessment_carries_target(self) -> None:
        result = assess(0.5)
        assert result.target == pytest.approx(TARGET)

    def test_assessment_reasoning_contains_values(self) -> None:
        result = assess(0.50)
        assert "stressed" in result.reasoning
        assert "0.50" in result.reasoning

    def test_assessment_carries_config(self) -> None:
        cfg = ResistanceBandConfig(lower_bound=0.34, upper_bound=0.37)
        result = assess(0.36, config=cfg)
        assert result.config is cfg


# ---------------------------------------------------------------------------
# recommend_scaling_factor()
# ---------------------------------------------------------------------------


class TestRecommendScalingFactor:
    def test_at_target_returns_one(self) -> None:
        assert recommend_scaling_factor(TARGET) == pytest.approx(1.0)

    def test_under_returns_above_one(self) -> None:
        assert recommend_scaling_factor(0.20) > 1.0

    def test_over_returns_below_one(self) -> None:
        assert recommend_scaling_factor(0.80) < 1.0

    def test_zero_utilization_returns_finite_large(self) -> None:
        # No divide-by-zero — saturate to a large finite value.
        result = recommend_scaling_factor(0.0)
        assert math.isfinite(result)
        assert result > 1e3

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValueError):
            recommend_scaling_factor(-0.1)

    def test_above_unit_rejected(self) -> None:
        with pytest.raises(ValueError):
            recommend_scaling_factor(1.1)

    def test_custom_config_target_used(self) -> None:
        cfg = ResistanceBandConfig(lower_bound=0.34, upper_bound=0.36)
        factor = recommend_scaling_factor(cfg.target, config=cfg)
        assert factor == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Enum + module exports
# ---------------------------------------------------------------------------


def test_classification_constant_in_lockstep() -> None:
    for c in ResistanceBandClassification:
        assert c.value in RESISTANCE_BAND_CLASSIFICATIONS
    assert len(RESISTANCE_BAND_CLASSIFICATIONS) == 3


def test_classification_serialisable_as_string() -> None:
    # str-Enum invariant: each value is a string, comparable to its value.
    assert ResistanceBandClassification.PRODUCTIVE == "productive"
    assert ResistanceBandClassification.UNDER_LOADED == "under_loaded"
    assert ResistanceBandClassification.STRESSED == "stressed"


def test_module_exports() -> None:
    for name in (
        "DEFAULT_CONFIG", "LOWER_BOUND", "PHI", "PHI_SQUARED",
        "RESISTANCE_BAND_CLASSIFICATIONS", "ResistanceBandAssessment",
        "ResistanceBandClassification", "ResistanceBandConfig",
        "TARGET", "UPPER_BOUND",
        "assess", "classify", "recommend_scaling_factor",
    ):
        assert name in _resistance_band_module.__all__, name


def test_assessment_shape_constructable() -> None:
    ev = ResistanceBandAssessment(
        utilization=0.35,
        classification=ResistanceBandClassification.PRODUCTIVE,
        distance_to_band=0.0,
        target=TARGET,
        recommended_scaling_factor=1.0,
        reasoning="manual",
        config=DEFAULT_CONFIG,
    )
    assert ev.is_productive
    assert not ev.is_stressed
    assert not ev.is_under_loaded
