"""Tests for PerformanceBudgetHolder (substrate)."""
from __future__ import annotations

import pytest

from substrate.performance_budget.budget_calculator import (
    BudgetMode,
)
from substrate.performance_budget.holder import (
    PerformanceBudgetHolder,
    current_mode,
    current_verdict,
    install_default_holder,
    reset_default_holder,
    set_default_holder,
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

class TestHolder:
    def test_default_starts_full(self) -> None:
        h = PerformanceBudgetHolder()
        assert h.current().mode is BudgetMode.FULL

    def test_update(self) -> None:
        h = PerformanceBudgetHolder()
        v = h.update(_signal(cpu=0.9))
        assert v.mode is BudgetMode.LEAN
        assert h.current().mode is BudgetMode.LEAN

    def test_force(self) -> None:
        h = PerformanceBudgetHolder()
        original = h.current()
        h.update(_signal(cpu=0.9))
        h.force(original)
        assert h.current().mode is BudgetMode.FULL

class TestDefaultHolder:
    def setup_method(self) -> None:
        reset_default_holder()

    def teardown_method(self) -> None:
        reset_default_holder()

    def test_uninstalled_raises(self) -> None:
        with pytest.raises(RuntimeError, match="not installed"):
            current_mode()

    def test_install_returns_holder(self) -> None:
        h = install_default_holder()
        assert isinstance(h, PerformanceBudgetHolder)
        assert current_mode() is BudgetMode.FULL

    def test_set_default(self) -> None:
        h = PerformanceBudgetHolder()
        h.update(_signal(cpu=0.99))
        set_default_holder(h)
        assert current_mode() is BudgetMode.EMERGENCY

    def test_current_verdict(self) -> None:
        install_default_holder()
        v = current_verdict()
        assert v.mode is BudgetMode.FULL
        assert v.composite_pressure == 0.0

    def test_reset(self) -> None:
        install_default_holder()
        reset_default_holder()
        with pytest.raises(RuntimeError):
            current_mode()
