"""Adaptive substrate performance-budget primitive.

Substrate-aligned adaptive policy: at low system pressure, full
deliberative gates run synchronously with no cache shortcuts; at high
pressure, only critical gates (NPG, halt-and-escalate) stay synchronous
and non-critical audits defer to a background queue.

This is itself a substrate-aligned design — ResistanceBand-style
adaptive: low load → full deliberative; high load → reactive-mode
fast-path with audit catch-up.
"""
from substrate.performance_budget.budget_calculator import (
    DEFAULT_BUDGET_CONFIG,
    BudgetCalculator,
    BudgetConfig,
    BudgetMode,
    BudgetVerdict,
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

__all__ = [
    "BudgetCalculator",
    "BudgetConfig",
    "BudgetMode",
    "BudgetVerdict",
    "DEFAULT_BUDGET_CONFIG",
    "PerformanceBudgetHolder",
    "PressureSignal",
    "current_mode",
    "current_verdict",
    "install_default_holder",
    "reset_default_holder",
    "set_default_holder",
]
