"""Tests for PressureSignal (substrate)."""
from __future__ import annotations

import pytest

from substrate.performance_budget.pressure_signal import (
    PressureSignal,
)

def _signal(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    cpu: float = 0.0,
    mem: float = 0.0,
    queue: float = 0.0,
    latency: float = 0.0,
    concurrency: float = 0.0,
) -> PressureSignal:
    return PressureSignal(
        cpu_utilization=cpu,
        memory_pressure=mem,
        queue_depth_fraction=queue,
        latency_p99_over_slo=latency,
        concurrency_saturation=concurrency,
    )

class TestConstruction:
    def test_round_trip(self) -> None:
        s = _signal(cpu=0.4, mem=0.3)
        assert s.cpu_utilization == 0.4

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("cpu", 1.5, "cpu_utilization"),
            ("cpu", -0.1, "cpu_utilization"),
            ("mem", 1.5, "memory_pressure"),
            ("queue", -0.1, "queue_depth_fraction"),
            ("latency", 1.5, "latency_p99_over_slo"),
            ("concurrency", -0.1, "concurrency_saturation"),
        ],
    )
    def test_bad(self, field: str, value: float, match: str) -> None:
        kwargs: dict[str, float] = {field: value}
        with pytest.raises(ValueError, match=match):
            _signal(**kwargs)

class TestCompositePressure:
    def test_all_zero(self) -> None:
        assert _signal().composite_pressure == 0.0

    def test_max_wins(self) -> None:
        s = _signal(cpu=0.4, mem=0.7, queue=0.2)
        assert s.composite_pressure == 0.7

    def test_all_high(self) -> None:
        s = _signal(cpu=0.9, mem=0.9, queue=0.9, latency=0.9, concurrency=0.9)
        assert s.composite_pressure == 0.9

class TestDominantSignal:
    def test_cpu_dominant(self) -> None:
        s = _signal(cpu=0.9, mem=0.5)
        assert s.dominant_signal == "cpu_utilization"

    def test_mem_dominant(self) -> None:
        s = _signal(cpu=0.5, mem=0.9)
        assert s.dominant_signal == "memory_pressure"

    def test_queue_dominant(self) -> None:
        s = _signal(queue=0.9)
        assert s.dominant_signal == "queue_depth_fraction"

    def test_latency_dominant(self) -> None:
        s = _signal(latency=0.9)
        assert s.dominant_signal == "latency_p99_over_slo"

    def test_concurrency_dominant(self) -> None:
        s = _signal(concurrency=0.9)
        assert s.dominant_signal == "concurrency_saturation"
