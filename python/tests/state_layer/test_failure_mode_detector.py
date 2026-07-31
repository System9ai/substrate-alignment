"""Tests for StateLayerFailureModeDetector (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.state_layer.failure_mode_detector import (
    DEFAULT_FAILURE_MODE_DETECTOR_CONFIG,
    FailureModeDetectorConfig,
    FailureModeFeatures,
    StateLayerFailureMode,
    StateLayerFailureModeDetector,
)

def _features(
    *,
    entity: str = "agent-1",
    capacity: float = 0.5,
    partitions: int = 5,
    corruption: bool = False,
    divergence: float = 0.1,
) -> FailureModeFeatures:
    return FailureModeFeatures(
        entity_id=entity,
        capacity_utilization=capacity,
        partition_count=partitions,
        corruption_flag=corruption,
        calibration_divergence=divergence,
    )

class TestFeatureValidation:
    def test_round_trip(self) -> None:
        f = _features()
        assert f.entity_id == "agent-1"

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("entity", "", "entity_id"),
            ("capacity", 1.5, "capacity_utilization"),
            ("partitions", -1, "partition_count"),
            ("divergence", 1.5, "calibration_divergence"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _features(**kwargs)

class TestConfig:
    def test_defaults(self) -> None:
        c = FailureModeDetectorConfig()
        assert c.saturation_threshold == 0.9

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("saturation_threshold", 0.0, "saturation_threshold"),
            (
                "fragmentation_partition_threshold", 1,
                "fragmentation_partition_threshold",
            ),
            (
                "decoherence_divergence_threshold", 0.0,
                "decoherence_divergence_threshold",
            ),
        ],
    )
    def test_bad_values(
        self, field: str, value: float, match: str,
    ) -> None:
        with pytest.raises(ValueError, match=match):
            FailureModeDetectorConfig(**{field: value})

class TestDetector:
    def setup_method(self) -> None:
        self.d = StateLayerFailureModeDetector()

    def test_corruption_dominates(self) -> None:
        d = self.d.detect(_features(
            corruption=True, capacity=0.99, divergence=0.99,
        ))
        assert d.mode is StateLayerFailureMode.CORRUPTION
        assert d.failed

    def test_decoherence(self) -> None:
        d = self.d.detect(_features(divergence=0.5))
        assert d.mode is StateLayerFailureMode.DECOHERENCE

    def test_saturation(self) -> None:
        d = self.d.detect(_features(capacity=0.95))
        assert d.mode is StateLayerFailureMode.SATURATION

    def test_fragmentation(self) -> None:
        d = self.d.detect(_features(partitions=50))
        assert d.mode is StateLayerFailureMode.FRAGMENTATION

    def test_none(self) -> None:
        d = self.d.detect(_features())
        assert d.mode is StateLayerFailureMode.NONE
        assert not d.failed

    def test_decoherence_before_saturation(self) -> None:
        # Both fire; decoherence ranks higher
        d = self.d.detect(_features(capacity=0.95, divergence=0.5))
        assert d.mode is StateLayerFailureMode.DECOHERENCE

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_FAILURE_MODE_DETECTOR_CONFIG.saturation_threshold
            == 0.9
        )
