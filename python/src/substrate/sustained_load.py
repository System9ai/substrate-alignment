"""SustainedLoadTracker — sporadic-vs-sustained accounting (layered zone model §2.3).

The pure band classifiers (``resistance_band.classify_zone``) are
instantaneous; the capacity contract is temporal: a PEAKING excursion
is tolerable **sporadically** and must decay; sustained operation
above the ``2/3`` debt line accrues **compensation debt** (sustained
in the 0.618–2/3 WARNING band reads as WINDED — the approach to
burnout, not yet debt); and an entity that repeatedly approaches the
work-entry
threshold and retreats while work is pending is **avoiding** ("we
don't want to bounce off 38%").

This module is the temporal half: a windowed tracker that turns a
stream of utilisation observations into trend verdicts plus accrued
debt units. Signals feed interpretation — the tracker never blocks;
compensation planning lives in ``substrate/debt_pickup.py`` and mode
governance in the caller.

Pure logic: no DAO, no clock reads (callers supply timestamps), frozen
dataclasses with slots. Per
``docs/concepts/resistance-band.md`` § "Sporadic vs sustained".
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Final, Optional

from substrate.resistance_band import (
    DANGER_LINE,
    LOWER_BOUND,
    PHI_CONJUGATE,
    UPPER_BOUND,
    WORK_ZONE_UPPER,
    validate_utilization,
)


class LoadTrend(str, Enum):
    """Temporal verdicts over the observation window."""

    NOMINAL = "nominal"
    SPIKE = "spike"
    SUSTAINED_STRAIN = "sustained_strain"
    WINDED = "winded"
    DEBT_ACCRUING = "debt_accruing"
    AVOIDANCE = "avoidance"
    RUNAWAY_GROWTH = "runaway_growth"


#: All trends, lockstep with the enum (CHECK-constraint contract).
LOAD_TRENDS: Final[frozenset[str]] = frozenset(t.value for t in LoadTrend)


@dataclass(frozen=True, slots=True)
class LoadObservation:
    """One utilisation sample. ``work_pending`` feeds avoidance detection."""

    timestamp: int
    utilization: float
    work_pending: bool = False

    def __post_init__(self) -> None:
        if self.timestamp < 0:
            raise ValueError(f"timestamp must be >= 0; got {self.timestamp!r}")
        validate_utilization(self.utilization)


@dataclass(frozen=True, slots=True)
class SustainedLoadAssessment:
    """Frozen result of one ``observe()`` call."""

    trend: LoadTrend
    ewma: float
    accrued_debt_units: float
    consecutive_above_debt_line: int
    approach_retreat_cycles: int
    reasoning: str


@dataclass(frozen=True, slots=True)
class SustainedLoadConfig:  # pylint: disable=too-many-instance-attributes
    """Tunable tracker thresholds — anchors default to the substrate values.

    ``sustain_count`` is how many consecutive observations constitute
    "sustained" (vs a sporadic spike). ``avoidance_cycles`` is how many
    approach→retreat cycles with work pending constitute avoidance.
    ``consolidation_gap`` is how many MAINTAIN-mode steps must separate
    grow steps before the growth streak resets (anti-runaway,
    condition #6).
    """

    window: int = 12
    ewma_alpha: float = 0.3
    work_entry: float = UPPER_BOUND
    spike_line: float = WORK_ZONE_UPPER
    warning_line: float = PHI_CONJUGATE
    debt_line: float = DANGER_LINE
    sustain_count: int = 3
    avoidance_cycles: int = 3
    avoidance_retreat_below: float = LOWER_BOUND
    max_growth_streak: int = 2
    consolidation_gap: int = 1

    def __post_init__(self) -> None:
        if self.window < 2:
            raise ValueError(f"window must be >= 2; got {self.window!r}")
        if not 0.0 < self.ewma_alpha <= 1.0:
            raise ValueError(
                f"ewma_alpha must be in (0, 1]; got {self.ewma_alpha!r}"
            )
        if not (
            0.0
            < self.avoidance_retreat_below
            <= self.work_entry
            < self.spike_line
            < self.warning_line
            < self.debt_line
            <= 1.0
        ):
            raise ValueError(
                "thresholds must satisfy 0 < retreat <= work_entry < "
                "spike_line < warning_line < debt_line <= 1; got "
                f"retreat={self.avoidance_retreat_below!r} "
                f"work_entry={self.work_entry!r} "
                f"spike={self.spike_line!r} warning={self.warning_line!r} "
                f"debt={self.debt_line!r}"
            )
        if self.sustain_count < 1:
            raise ValueError(
                f"sustain_count must be >= 1; got {self.sustain_count!r}"
            )
        if self.avoidance_cycles < 1:
            raise ValueError(
                f"avoidance_cycles must be >= 1; "
                f"got {self.avoidance_cycles!r}"
            )
        if self.max_growth_streak < 1:
            raise ValueError(
                f"max_growth_streak must be >= 1; "
                f"got {self.max_growth_streak!r}"
            )
        if self.consolidation_gap < 1:
            raise ValueError(
                f"consolidation_gap must be >= 1; "
                f"got {self.consolidation_gap!r}"
            )


DEFAULT_SUSTAINED_LOAD_CONFIG: Final[SustainedLoadConfig] = (
    SustainedLoadConfig()
)


class SustainedLoadTracker:  # pylint: disable=too-many-instance-attributes
    """Windowed temporal tracker for one bounded context.

    One tracker per entity per bounded context (cell CPU, queue depth,
    token window, …). Debt units accrue as ``(utilization - debt_line)``
    per sustained observation above the line — magnitude × duration in
    observation units; repayment is recorded via :meth:`repay` (the
    compensation planner decides when).
    """

    def __init__(
        self,
        *,
        config: SustainedLoadConfig = DEFAULT_SUSTAINED_LOAD_CONFIG,
    ) -> None:
        self._config = config
        self._observations: Deque[LoadObservation] = deque(
            maxlen=config.window
        )
        self._ewma: Optional[float] = None
        self._consecutive_above_debt = 0
        self._accrued_debt_units = 0.0
        self._approach_retreat_cycles = 0
        self._approached = False
        self._last_timestamp: Optional[int] = None

    @property
    def accrued_debt_units(self) -> float:
        """Outstanding debt units (accrued − repaid, floored at zero)."""
        return self._accrued_debt_units

    def repay(self, units: float) -> float:
        """Record debt repayment; returns the remaining outstanding units."""
        if units < 0.0 or not math.isfinite(units):
            raise ValueError(
                f"units must be a finite float >= 0; got {units!r}"
            )
        self._accrued_debt_units = max(0.0, self._accrued_debt_units - units)
        return self._accrued_debt_units

    def observe(self, obs: LoadObservation) -> SustainedLoadAssessment:
        """Ingest one observation and return the temporal assessment."""
        if (
            self._last_timestamp is not None
            and obs.timestamp < self._last_timestamp
        ):
            raise ValueError(
                f"timestamps must be monotonic; got {obs.timestamp!r} "
                f"after {self._last_timestamp!r}"
            )
        cfg = self._config
        self._last_timestamp = obs.timestamp
        self._observations.append(obs)
        self._ewma = (
            obs.utilization
            if self._ewma is None
            else cfg.ewma_alpha * obs.utilization
            + (1.0 - cfg.ewma_alpha) * self._ewma
        )
        self._track_debt(obs)
        self._track_avoidance(obs)
        trend = self._resolve_trend(obs)
        reasoning = (
            f"util={obs.utilization:.4f} ewma={self._ewma:.4f} "
            f"trend={trend.value} debt_units="
            f"{self._accrued_debt_units:.4f} "
            f"above_debt_streak={self._consecutive_above_debt} "
            f"avoidance_cycles={self._approach_retreat_cycles}"
        )
        return SustainedLoadAssessment(
            trend=trend,
            ewma=self._ewma,
            accrued_debt_units=self._accrued_debt_units,
            consecutive_above_debt_line=self._consecutive_above_debt,
            approach_retreat_cycles=self._approach_retreat_cycles,
            reasoning=reasoning,
        )

    def _track_debt(self, obs: LoadObservation) -> None:
        cfg = self._config
        if obs.utilization > cfg.debt_line:
            self._consecutive_above_debt += 1
            if self._consecutive_above_debt >= cfg.sustain_count:
                self._accrued_debt_units += obs.utilization - cfg.debt_line
        else:
            self._consecutive_above_debt = 0

    def _track_avoidance(self, obs: LoadObservation) -> None:
        cfg = self._config
        if obs.utilization >= cfg.work_entry - 0.03:
            # Reached the approach margin of the work-entry threshold.
            self._approached = True
        elif (
            self._approached
            and obs.utilization < cfg.avoidance_retreat_below
        ):
            # Retreated all the way below the calibration floor after
            # approaching — count a bounce iff work was pending.
            if obs.work_pending:
                self._approach_retreat_cycles += 1
            self._approached = False

    def _resolve_trend(self, obs: LoadObservation) -> LoadTrend:
        cfg = self._config
        assert self._ewma is not None  # set in observe()
        if (
            self._consecutive_above_debt >= cfg.sustain_count
            or self._accrued_debt_units > 0.0
        ):
            return LoadTrend.DEBT_ACCRUING
        if self._ewma > cfg.spike_line:
            recent = list(self._observations)[-cfg.sustain_count :]
            if len(recent) >= cfg.sustain_count:
                # Sustained in the WARNING band (winded — past the
                # φ-conjugate, not yet past the 2/3 debt line) is distinct
                # from strain sustained merely past the 0.5 pivot.
                if all(o.utilization > cfg.warning_line for o in recent):
                    return LoadTrend.WINDED
                if all(o.utilization > cfg.spike_line for o in recent):
                    return LoadTrend.SUSTAINED_STRAIN
        if obs.utilization > cfg.spike_line:
            return LoadTrend.SPIKE
        if self._approach_retreat_cycles >= cfg.avoidance_cycles:
            return LoadTrend.AVOIDANCE
        return LoadTrend.NOMINAL


class GrowthStreakMonitor:
    """Anti-runaway growth-desire detector (layered zone model §2.5, condition #6).

    Tracks grow-vs-consolidate steps for one entity. More than
    ``max_growth_streak`` consecutive grow steps without at least
    ``consolidation_gap`` maintain steps between them emits
    RUNAWAY_GROWTH — growth must be a deliberate, gated transition from
    maintain, never a standing posture.
    """

    def __init__(
        self,
        *,
        config: SustainedLoadConfig = DEFAULT_SUSTAINED_LOAD_CONFIG,
    ) -> None:
        self._config = config
        self._growth_streak = 0
        self._consolidation_run = 0

    @property
    def growth_streak(self) -> int:
        """Consecutive grow steps without sufficient consolidation."""
        return self._growth_streak

    def record_grow_step(self) -> LoadTrend:
        """Record one capacity-growth step; returns the trend verdict."""
        if self._consolidation_run >= self._config.consolidation_gap:
            self._growth_streak = 0
        self._consolidation_run = 0
        self._growth_streak += 1
        if self._growth_streak > self._config.max_growth_streak:
            return LoadTrend.RUNAWAY_GROWTH
        return LoadTrend.NOMINAL

    def record_maintain_step(self) -> None:
        """Record one maintain/consolidation step."""
        self._consolidation_run += 1


__all__ = [
    "DEFAULT_SUSTAINED_LOAD_CONFIG",
    "GrowthStreakMonitor",
    "LOAD_TRENDS",
    "LoadObservation",
    "LoadTrend",
    "SustainedLoadAssessment",
    "SustainedLoadConfig",
    "SustainedLoadTracker",
]
