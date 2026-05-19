"""Process-scope holder for the active budget verdict.

Substrate gates query the current mode without dependency-injection
plumbing. A service-level worker periodically polls system metrics,
builds a `PressureSignal`, calculates the verdict, and installs it via
`set_default_holder`.

Tests and unit-test fixtures use `install_default_holder` /
`reset_default_holder` so tests can pin a known mode.
"""
from __future__ import annotations

import threading
from typing import Optional

from substrate.performance_budget.budget_calculator import (
    BudgetCalculator,
    BudgetMode,
    BudgetVerdict,
    DEFAULT_BUDGET_CONFIG,
)
from substrate.performance_budget.pressure_signal import (
    PressureSignal,
)

class PerformanceBudgetHolder:
    """Thread-safe holder for the current `BudgetVerdict`."""

    def __init__(
        self,
        *,
        calculator: Optional[BudgetCalculator] = None,
    ) -> None:
        self._calculator = calculator or BudgetCalculator(
            config=DEFAULT_BUDGET_CONFIG,
        )
        self._lock = threading.Lock()
        # Start at FULL with zero composite pressure — safe-default
        # discipline. Gates running under this default behave as if
        # system pressure is nominal until the holder is updated.
        self._verdict = self._calculator.calculate(PressureSignal(
            cpu_utilization=0.0,
            memory_pressure=0.0,
            queue_depth_fraction=0.0,
            latency_p99_over_slo=0.0,
            concurrency_saturation=0.0,
        ))

    def update(self, signal: PressureSignal) -> BudgetVerdict:
        """Recompute the verdict from a fresh signal and store it atomically."""
        verdict = self._calculator.calculate(signal)
        with self._lock:
            self._verdict = verdict
        return verdict

    def current(self) -> BudgetVerdict:
        """Return the most recent verdict (atomic snapshot)."""
        with self._lock:
            return self._verdict

    def force(self, verdict: BudgetVerdict) -> None:
        """Install a pre-built verdict (test / debug entry point)."""
        with self._lock:
            self._verdict = verdict

# Process-scope default holder. Service runners install on startup.

_default_holder: Optional[PerformanceBudgetHolder] = None
_default_lock = threading.Lock()

def set_default_holder(holder: PerformanceBudgetHolder) -> None:
    """Install ``holder`` as the process-scope default."""
    global _default_holder  # noqa: PLW0603  # pylint: disable=global-statement
    with _default_lock:
        _default_holder = holder

def install_default_holder(
    *,
    calculator: Optional[BudgetCalculator] = None,
) -> PerformanceBudgetHolder:
    """Construct + install + return a fresh default holder."""
    holder = PerformanceBudgetHolder(calculator=calculator)
    set_default_holder(holder)
    return holder

def reset_default_holder() -> None:
    """Clear the process-scope default holder (test cleanup)."""
    global _default_holder  # noqa: PLW0603  # pylint: disable=global-statement
    with _default_lock:
        _default_holder = None

def _require_holder() -> PerformanceBudgetHolder:
    with _default_lock:
        if _default_holder is None:
            raise RuntimeError(
                "PerformanceBudgetHolder not installed; "
                "call install_default_holder() at service startup"
            )
        return _default_holder

def current_verdict() -> BudgetVerdict:
    """Return the current default holder's verdict."""
    return _require_holder().current()

def current_mode() -> BudgetMode:
    """Return the current default holder's mode (shortcut)."""
    return _require_holder().current().mode

__all__ = [
    "PerformanceBudgetHolder",
    "current_mode",
    "current_verdict",
    "install_default_holder",
    "reset_default_holder",
    "set_default_holder",
]
