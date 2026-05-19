"""Pure-logic adaptive budget calculator.

Maps a `PressureSignal` to a `BudgetMode` and overhead-fraction. The
modes flex from `FULL` (5% overhead, every gate synchronously) at low
pressure to `EMERGENCY` (<0.5% overhead, only halt-and-escalate
synchronous) at saturation.

| Pressure | Mode | Overhead range | Behavior |
|---|---|---|---|
| `≤ 0.5` | `FULL` | 5% | All gates sync; full audits; no caches |
| `0.5–0.8` | `BALANCED` | 2–5% | All gates sync; read-through caches |
| `0.8–0.95` | `LEAN` | 0.5–2% | Critical gates only; non-critical audits deferred |
| `> 0.95` | `EMERGENCY` | 0–0.5% | Only halt-and-escalate; others short-circuit |
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from substrate.performance_budget.pressure_signal import (
    PressureSignal,
)

class BudgetMode(str, Enum):
    """Four-state adaptive budget mode."""

    FULL = "full"
    BALANCED = "balanced"
    LEAN = "lean"
    EMERGENCY = "emergency"

@dataclass(frozen=True, slots=True)
class BudgetConfig:  # pylint: disable=too-many-instance-attributes
    """Operator-tunable thresholds + overhead caps."""

    balanced_threshold: float = 0.5
    lean_threshold: float = 0.8
    emergency_threshold: float = 0.95
    full_overhead: float = 0.05
    balanced_overhead_max: float = 0.05
    balanced_overhead_min: float = 0.02
    lean_overhead_max: float = 0.02
    lean_overhead_min: float = 0.005
    emergency_overhead_max: float = 0.005

    def __post_init__(self) -> None:
        if not (
            0.0
            < self.balanced_threshold
            < self.lean_threshold
            < self.emergency_threshold
            < 1.0
        ):
            raise ValueError(
                "thresholds must satisfy "
                "0 < balanced < lean < emergency < 1"
            )
        for name, value in (
            ("full_overhead", self.full_overhead),
            ("balanced_overhead_max", self.balanced_overhead_max),
            ("balanced_overhead_min", self.balanced_overhead_min),
            ("lean_overhead_max", self.lean_overhead_max),
            ("lean_overhead_min", self.lean_overhead_min),
            ("emergency_overhead_max", self.emergency_overhead_max),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.balanced_overhead_min > self.balanced_overhead_max:
            raise ValueError(
                "balanced_overhead_min cannot exceed balanced_overhead_max"
            )
        if self.lean_overhead_min > self.lean_overhead_max:
            raise ValueError(
                "lean_overhead_min cannot exceed lean_overhead_max"
            )

DEFAULT_BUDGET_CONFIG: Final[BudgetConfig] = BudgetConfig()

@dataclass(frozen=True, slots=True)
class BudgetVerdict:
    """Calculator output."""

    mode: BudgetMode
    overhead_fraction: float
    composite_pressure: float
    dominant_signal: str
    rationale: str

    @property
    def synchronous_gates_only_critical(self) -> bool:
        """True iff the mode allows only critical (NPG/halt) gates synchronously."""
        return self.mode in (BudgetMode.LEAN, BudgetMode.EMERGENCY)

    @property
    def emergency(self) -> bool:
        """True iff the mode is EMERGENCY (only halt-and-escalate)."""
        return self.mode is BudgetMode.EMERGENCY

    @property
    def caches_allowed(self) -> bool:
        """True iff gates may read-through caches (not FULL)."""
        return self.mode is not BudgetMode.FULL

class BudgetCalculator:  # pylint: disable=too-few-public-methods
    """Pure-logic adaptive budget calculator."""

    def __init__(
        self,
        *,
        config: BudgetConfig = DEFAULT_BUDGET_CONFIG,
    ) -> None:
        self._config = config

    def calculate(self, signal: PressureSignal) -> BudgetVerdict:
        """Map a pressure signal to a budget verdict."""
        cfg = self._config
        pressure = signal.composite_pressure
        if pressure <= cfg.balanced_threshold:
            mode = BudgetMode.FULL
            overhead = cfg.full_overhead
        elif pressure <= cfg.lean_threshold:
            mode = BudgetMode.BALANCED
            overhead = self._interp(
                pressure,
                lo=cfg.balanced_threshold,
                hi=cfg.lean_threshold,
                overhead_at_lo=cfg.balanced_overhead_max,
                overhead_at_hi=cfg.balanced_overhead_min,
            )
        elif pressure <= cfg.emergency_threshold:
            mode = BudgetMode.LEAN
            overhead = self._interp(
                pressure,
                lo=cfg.lean_threshold,
                hi=cfg.emergency_threshold,
                overhead_at_lo=cfg.lean_overhead_max,
                overhead_at_hi=cfg.lean_overhead_min,
            )
        else:
            mode = BudgetMode.EMERGENCY
            overhead = self._interp(
                pressure,
                lo=cfg.emergency_threshold,
                hi=1.0,
                overhead_at_lo=cfg.emergency_overhead_max,
                overhead_at_hi=0.0,
            )
        return BudgetVerdict(
            mode=mode,
            overhead_fraction=overhead,
            composite_pressure=pressure,
            dominant_signal=signal.dominant_signal,
            rationale=(
                f"pressure={pressure:.3f}; dominant="
                f"{signal.dominant_signal}; "
                f"mode={mode.value}; overhead={overhead:.4f}"
            ),
        )

    @staticmethod
    def _interp(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        pressure: float,
        *,
        lo: float,
        hi: float,
        overhead_at_lo: float,
        overhead_at_hi: float,
    ) -> float:
        if hi <= lo:
            return overhead_at_lo
        t = (pressure - lo) / (hi - lo)
        return overhead_at_lo + t * (overhead_at_hi - overhead_at_lo)

__all__ = [
    "BudgetCalculator",
    "BudgetConfig",
    "BudgetMode",
    "BudgetVerdict",
    "DEFAULT_BUDGET_CONFIG",
]
