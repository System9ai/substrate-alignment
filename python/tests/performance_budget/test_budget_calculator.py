"""Tests for BudgetCalculator (substrate)."""
from __future__ import annotations

import pytest

from substrate.performance_budget.budget_calculator import (
    DEFAULT_BUDGET_CONFIG,
    BudgetCalculator,
    BudgetConfig,
    BudgetMode,
)
from substrate.performance_budget.pressure_signal import (
    PressureSignal,
)

def _signal(cpu: float = 0.0) -> PressureSignal:
    return PressureSignal(
        cpu_utilization=cpu,
        memory_pressure=0.0,
        queue_depth_fraction=0.0,
        latency_p99_over_slo=0.0,
        concurrency_saturation=0.0,
    )

class TestConfig:
    def test_defaults(self) -> None:
        c = BudgetConfig()
        assert c.full_overhead == 0.05
        assert c.emergency_overhead_max == 0.005

    @pytest.mark.parametrize(
        "kwargs,match",
        [
            ({"balanced_threshold": 0.9, "lean_threshold": 0.8}, "thresholds"),
            ({"emergency_threshold": 1.5}, "thresholds"),
            ({"full_overhead": -0.1}, "full_overhead"),
            (
                {
                    "balanced_overhead_min": 0.06,
                    "balanced_overhead_max": 0.05,
                },
                "balanced_overhead",
            ),
        ],
    )
    def test_bad(self, kwargs: dict[str, float], match: str) -> None:
        with pytest.raises(ValueError, match=match):
            BudgetConfig(**kwargs)

class TestCalculator:
    def setup_method(self) -> None:
        self.c = BudgetCalculator()

    def test_full_at_zero(self) -> None:
        v = self.c.calculate(_signal(cpu=0.0))
        assert v.mode is BudgetMode.FULL
        assert v.overhead_fraction == 0.05
        assert not v.caches_allowed
        assert not v.synchronous_gates_only_critical
        assert not v.emergency

    def test_full_at_threshold(self) -> None:
        v = self.c.calculate(_signal(cpu=0.5))
        assert v.mode is BudgetMode.FULL

    def test_balanced_low(self) -> None:
        v = self.c.calculate(_signal(cpu=0.51))
        assert v.mode is BudgetMode.BALANCED
        assert 0.02 < v.overhead_fraction <= 0.05
        assert v.caches_allowed

    def test_balanced_high(self) -> None:
        v = self.c.calculate(_signal(cpu=0.79))
        assert v.mode is BudgetMode.BALANCED
        assert v.overhead_fraction < 0.03

    def test_lean_low(self) -> None:
        v = self.c.calculate(_signal(cpu=0.81))
        assert v.mode is BudgetMode.LEAN
        assert v.synchronous_gates_only_critical
        assert 0.005 <= v.overhead_fraction < 0.02

    def test_lean_high(self) -> None:
        v = self.c.calculate(_signal(cpu=0.94))
        assert v.mode is BudgetMode.LEAN

    def test_emergency(self) -> None:
        v = self.c.calculate(_signal(cpu=0.99))
        assert v.mode is BudgetMode.EMERGENCY
        assert v.emergency
        assert v.synchronous_gates_only_critical
        assert v.overhead_fraction < 0.005

    def test_max_pressure(self) -> None:
        v = self.c.calculate(_signal(cpu=1.0))
        assert v.mode is BudgetMode.EMERGENCY
        assert v.overhead_fraction == 0.0

    def test_dominant_signal_in_verdict(self) -> None:
        v = self.c.calculate(PressureSignal(
            cpu_utilization=0.4,
            memory_pressure=0.85,
            queue_depth_fraction=0.0,
            latency_p99_over_slo=0.0,
            concurrency_saturation=0.0,
        ))
        assert v.dominant_signal == "memory_pressure"
        assert v.mode is BudgetMode.LEAN

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert DEFAULT_BUDGET_CONFIG.balanced_threshold == 0.5
