"""Tests for RecursiveTransmissionPatternDetector (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.encapsulating_context.pull_signal import (
    ContextScale,
)
from substrate.state_layer.recursive_transmission_detector import (
    DEFAULT_TRANSMISSION_DETECTOR_CONFIG,
    RecursiveTransmissionPatternDetector,
    TransmissionDetectorConfig,
    TransmissionSample,
    TransmissionVerdict,
)

def _sample(
    *,
    kind: str = "drift-pattern-A",
    scale: ContextScale,
    at: float,
    triggered: bool = True,
) -> TransmissionSample:
    return TransmissionSample(
        signal_kind=kind,
        scale=scale,
        observed_at_seconds=at,
        triggered_by_prior=triggered,
    )

class TestSampleValidation:
    def test_round_trip(self) -> None:
        s = _sample(scale=ContextScale.NODE, at=0.0)
        assert s.scale is ContextScale.NODE

    def test_empty_kind(self) -> None:
        with pytest.raises(ValueError, match="signal_kind"):
            _sample(kind="", scale=ContextScale.NODE, at=0.0)

    def test_negative_time(self) -> None:
        with pytest.raises(ValueError, match="observed_at_seconds"):
            _sample(scale=ContextScale.NODE, at=-1.0)

class TestConfig:
    def test_defaults(self) -> None:
        c = TransmissionDetectorConfig()
        assert c.min_chain_length == 2

    def test_chain_length_floor(self) -> None:
        with pytest.raises(ValueError, match="min_chain_length"):
            TransmissionDetectorConfig(min_chain_length=1)

    def test_window_positive(self) -> None:
        with pytest.raises(
            ValueError, match="max_propagation_window_seconds",
        ):
            TransmissionDetectorConfig(
                max_propagation_window_seconds=0.0,
            )

class TestDetector:
    def setup_method(self) -> None:
        self.d = RecursiveTransmissionPatternDetector()

    def test_insufficient_data(self) -> None:
        out = self.d.detect(
            "drift-A",
            (_sample(kind="drift-A", scale=ContextScale.NODE, at=0.0),),
        )
        assert out.verdict is TransmissionVerdict.INSUFFICIENT_DATA

    def test_recursive_transmission(self) -> None:
        samples = (
            _sample(
                kind="drift-A", scale=ContextScale.NODE,
                at=0.0, triggered=False,
            ),
            _sample(
                kind="drift-A", scale=ContextScale.ORG,
                at=120.0, triggered=True,
            ),
            _sample(
                kind="drift-A", scale=ContextScale.CLUSTER,
                at=240.0, triggered=True,
            ),
        )
        out = self.d.detect("drift-A", samples)
        assert (
            out.verdict is TransmissionVerdict.RECURSIVE_TRANSMISSION
        )
        assert out.recursive
        assert out.chain_length == 3

    def test_no_pattern_window_exceeded(self) -> None:
        samples = (
            _sample(
                kind="drift-A", scale=ContextScale.NODE,
                at=0.0, triggered=False,
            ),
            _sample(
                kind="drift-A", scale=ContextScale.ORG,
                at=10000.0, triggered=True,
            ),
        )
        out = self.d.detect("drift-A", samples)
        assert out.verdict is TransmissionVerdict.NO_PATTERN

    def test_no_pattern_not_triggered(self) -> None:
        samples = (
            _sample(
                kind="drift-A", scale=ContextScale.NODE,
                at=0.0, triggered=False,
            ),
            _sample(
                kind="drift-A", scale=ContextScale.ORG,
                at=120.0, triggered=False,
            ),
        )
        out = self.d.detect("drift-A", samples)
        assert out.verdict is TransmissionVerdict.NO_PATTERN

    def test_no_pattern_not_ascending(self) -> None:
        samples = (
            _sample(
                kind="drift-A", scale=ContextScale.ORG,
                at=0.0, triggered=False,
            ),
            _sample(
                kind="drift-A", scale=ContextScale.NODE,
                at=120.0, triggered=True,
            ),
        )
        out = self.d.detect("drift-A", samples)
        assert out.verdict is TransmissionVerdict.NO_PATTERN

    def test_signal_kind_filter(self) -> None:
        samples = (
            _sample(
                kind="other", scale=ContextScale.NODE, at=0.0,
            ),
            _sample(
                kind="other", scale=ContextScale.ORG, at=120.0,
            ),
        )
        out = self.d.detect("drift-A", samples)
        assert out.verdict is TransmissionVerdict.INSUFFICIENT_DATA

    def test_empty_signal_kind_rejected(self) -> None:
        with pytest.raises(ValueError, match="signal_kind"):
            self.d.detect("", ())

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_TRANSMISSION_DETECTOR_CONFIG.min_chain_length == 2
        )
