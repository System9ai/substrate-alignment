"""Composite pressure-signal value type for the adaptive performance budget.

A `PressureSignal` carries five normalized signals (CPU, memory, queue
depth, p99 latency, concurrency saturation) each in `[0, 1]`. The
composite pressure score is the **maximum** of the normalized signals
— worst-case wins, conservatively. This biases toward defending the
critical-path gates under any one source of pressure.
"""
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class PressureSignal:
    """Caller-supplied pressure signal."""

    cpu_utilization: float
    """CPU utilization, normalized to ``[0, 1]``."""

    memory_pressure: float
    """Memory pressure, normalized to ``[0, 1]``."""

    queue_depth_fraction: float
    """Request queue depth divided by capacity, in ``[0, 1]``."""

    latency_p99_over_slo: float
    """P99 latency divided by SLO, in ``[0, 1]`` where 1.0 means SLO breached."""

    concurrency_saturation: float
    """Active workers / max workers, in ``[0, 1]``."""

    def __post_init__(self) -> None:
        for name, value in (
            ("cpu_utilization", self.cpu_utilization),
            ("memory_pressure", self.memory_pressure),
            ("queue_depth_fraction", self.queue_depth_fraction),
            ("latency_p99_over_slo", self.latency_p99_over_slo),
            ("concurrency_saturation", self.concurrency_saturation),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]; got {value!r}")

    @property
    def composite_pressure(self) -> float:
        """Worst-case pressure in ``[0, 1]`` — max of normalized signals."""
        return max(
            self.cpu_utilization,
            self.memory_pressure,
            self.queue_depth_fraction,
            self.latency_p99_over_slo,
            self.concurrency_saturation,
        )

    @property
    def dominant_signal(self) -> str:
        """Name of the signal currently driving the composite pressure."""
        signals = {
            "cpu_utilization": self.cpu_utilization,
            "memory_pressure": self.memory_pressure,
            "queue_depth_fraction": self.queue_depth_fraction,
            "latency_p99_over_slo": self.latency_p99_over_slo,
            "concurrency_saturation": self.concurrency_saturation,
        }
        return max(signals.items(), key=lambda kv: kv[1])[0]

__all__ = ["PressureSignal"]
