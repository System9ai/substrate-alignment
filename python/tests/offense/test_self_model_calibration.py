"""Tests for SelfModelCalibrationTracker (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.offense.self_model_calibration import (
    DEFAULT_CALIBRATION_CONFIG,
    CalibrationConfig,
    CalibrationObservation,
    CalibrationVerdict,
    SelfModelCalibrationTracker,
)

def _obs(
    *,
    entity: str = "agent-1",
    cycle: int,
    declared: float,
    observed: float,
) -> CalibrationObservation:
    return CalibrationObservation(
        entity_id=entity,
        cycle_index=cycle,
        declared_substrate_state=declared,
        observed_substrate_state=observed,
    )

class TestObservationValidation:
    def test_round_trip(self) -> None:
        o = _obs(cycle=0, declared=0.5, observed=0.6)
        assert abs(o.divergence - 0.1) < 1e-9

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("entity", "", "entity_id"),
            ("cycle", -1, "cycle_index"),
            ("declared", 1.5, "declared_substrate_state"),
            ("observed", -0.1, "observed_substrate_state"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {
            "entity": "agent-1",
            "cycle": 0,
            "declared": 0.5,
            "observed": 0.5,
            field: value,
        }
        with pytest.raises(ValueError, match=match):
            _obs(**kwargs)

class TestConfig:
    def test_defaults(self) -> None:
        c = CalibrationConfig()
        assert c.window_size == 20

    def test_min_obs_cannot_exceed_window(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed"):
            CalibrationConfig(window_size=5, min_observations=10)

    def test_diverging_must_be_positive(self) -> None:
        with pytest.raises(
            ValueError, match="diverging_slope_threshold",
        ):
            CalibrationConfig(diverging_slope_threshold=0.0)

    def test_converging_must_be_negative(self) -> None:
        with pytest.raises(
            ValueError, match="converging_slope_threshold",
        ):
            CalibrationConfig(converging_slope_threshold=0.0)

class TestTracker:
    def setup_method(self) -> None:
        self.t = SelfModelCalibrationTracker(entity_id="agent-1")

    def test_insufficient_data(self) -> None:
        self.t.observe(_obs(cycle=0, declared=0.5, observed=0.6))
        v = self.t.verdict()
        assert v.verdict is CalibrationVerdict.INSUFFICIENT_DATA

    def test_converging(self) -> None:
        # divergence shrinking from 0.4 to 0.0
        for i, d in enumerate([0.4, 0.3, 0.2, 0.1, 0.0]):
            self.t.observe(_obs(
                cycle=i, declared=0.5, observed=0.5 + d,
            ))
        v = self.t.verdict()
        assert v.verdict is CalibrationVerdict.CONVERGING
        assert v.trend_slope < 0

    def test_diverging(self) -> None:
        # divergence growing from 0.0 to 0.4
        for i, d in enumerate([0.0, 0.1, 0.2, 0.3, 0.4]):
            self.t.observe(_obs(
                cycle=i, declared=0.5, observed=0.5 + d,
            ))
        v = self.t.verdict()
        assert v.verdict is CalibrationVerdict.DIVERGING
        assert v.diverging

    def test_diverging_via_high_current(self) -> None:
        for i, d in enumerate([0.45, 0.45, 0.45, 0.45, 0.45]):
            self.t.observe(_obs(
                cycle=i, declared=0.5, observed=0.5 + d,
            ))
        v = self.t.verdict()
        assert v.verdict is CalibrationVerdict.DIVERGING

    def test_steady(self) -> None:
        for i, d in enumerate([0.1, 0.11, 0.1, 0.09, 0.1]):
            self.t.observe(_obs(
                cycle=i, declared=0.5, observed=0.5 + d,
            ))
        v = self.t.verdict()
        assert v.verdict is CalibrationVerdict.STEADY

    def test_entity_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="does not match"):
            self.t.observe(_obs(
                entity="other", cycle=0, declared=0.5, observed=0.5,
            ))

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert DEFAULT_CALIBRATION_CONFIG.window_size == 20

    def test_tracker_requires_entity(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            SelfModelCalibrationTracker(entity_id="")
