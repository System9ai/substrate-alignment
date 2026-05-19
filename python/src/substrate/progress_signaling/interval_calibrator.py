"""Adaptive feedback-interval calibrator — Plan 3art 32.

Pure-logic calibrator that maps an entity's tier-consolidation position +
ResistanceBand classification to a recommended target interval between
signals. Composes with the shipped :class:`ResistanceBand` primitive.

Calibration band:
- Tier 0-2 (early): minor progress every 1-5 minutes; milestones every
  15-60 minutes.
- Tier 3-5 (mid): minor progress every 15-60 minutes; milestones every
  several hours.
- Tier 6+ (high): minor progress every hour-day; milestones every
  several days.
- UNDER_LOADED (below band): tighten temporarily.
- STRESSED (above band): expand temporarily.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Mapping

from substrate.progress_signaling.signal import (
    SubstrateSignalType,
)
from substrate.resistance_band import (
    ResistanceBandAssessment,
    ResistanceBandClassification,
)

#: Default per-tier-class targets for `PROGRESS_MARKER` signals (seconds).
_DEFAULT_TARGETS_BY_TIER_CLASS: Final[Mapping[str, int]] = {
    "early": 180, # 3 minutes
    "mid": 1800, # 30 minutes
    "high": 14400, # 4 hours
}

#: Multiplier applied to map PROGRESS_MARKER → MILESTONE → CONSOLIDATION.
_INTERVAL_MULTIPLIERS: Final[Mapping[SubstrateSignalType, float]] = {
    SubstrateSignalType.PROGRESS_MARKER: 1.0,
    SubstrateSignalType.MILESTONE: 12.0,
    SubstrateSignalType.CONSOLIDATION: 72.0,
    SubstrateSignalType.ACHIEVEMENT: 1.0,
    SubstrateSignalType.STREAK: 86400.0 / _DEFAULT_TARGETS_BY_TIER_CLASS["early"],
}

@dataclass(frozen=True, slots=True)
class IntervalCalibratorConfig:
    """Operator-tunable calibrator parameters."""

    early_tier_cap: int = 2
    mid_tier_cap: int = 5
    early_seconds: int = _DEFAULT_TARGETS_BY_TIER_CLASS["early"]
    mid_seconds: int = _DEFAULT_TARGETS_BY_TIER_CLASS["mid"]
    high_seconds: int = _DEFAULT_TARGETS_BY_TIER_CLASS["high"]
    under_loaded_multiplier: float = 0.5
    """Tighten intervals when the entity is under-loaded."""

    stressed_multiplier: float = 2.0
    """Expand intervals when the entity is stressed."""

    def __post_init__(self) -> None:
        if self.early_tier_cap < 0:
            raise ValueError("early_tier_cap must be >= 0")
        if self.mid_tier_cap <= self.early_tier_cap:
            raise ValueError(
                "mid_tier_cap must exceed early_tier_cap"
            )
        for name, value in (
            ("early_seconds", self.early_seconds),
            ("mid_seconds", self.mid_seconds),
            ("high_seconds", self.high_seconds),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be > 0")
        if not 0.0 < self.under_loaded_multiplier <= 1.0:
            raise ValueError(
                "under_loaded_multiplier must be in (0, 1]"
            )
        if self.stressed_multiplier < 1.0:
            raise ValueError(
                "stressed_multiplier must be >= 1.0 (stretches intervals)"
            )

DEFAULT_INTERVAL_CALIBRATOR_CONFIG: Final[IntervalCalibratorConfig] = (
    IntervalCalibratorConfig()
)

@dataclass(frozen=True, slots=True)
class SubstrateFeedbackInterval:
    """Per-signal-type calibrated target interval (seconds)."""

    signal_type: SubstrateSignalType
    target_seconds: int
    resistance_band_position: float
    tier_index: int
    rationale: str

class SubstrateAlignedIntervalCalibrator:  # pylint: disable=too-few-public-methods
    """Pure-logic interval calibrator (Plan 3art 32)."""

    def __init__(
        self,
        *,
        config: IntervalCalibratorConfig = (
            DEFAULT_INTERVAL_CALIBRATOR_CONFIG
        ),
    ) -> None:
        self._config = config

    def calibrate(
        self,
        *,
        signal_type: SubstrateSignalType,
        tier_index: int,
        resistance: ResistanceBandAssessment,
    ) -> SubstrateFeedbackInterval:
        """Return the calibrated target interval for the request."""
        if tier_index < 0:
            raise ValueError("tier_index must be >= 0")
        base_seconds = self._base_seconds_for_tier(tier_index)
        multiplier = _INTERVAL_MULTIPLIERS[signal_type]
        adjustment = self._resistance_adjustment(resistance)
        target_seconds = max(
            1, int(round(base_seconds * multiplier * adjustment)),
        )
        position = max(
            0.0, min(1.0, resistance.recommended_scaling_factor / 2.0),
        )
        rationale = (
            f"tier={tier_index} ({self._tier_class_name(tier_index)}); "
            f"base={base_seconds}s; multiplier={multiplier:.2f}; "
            f"resistance={resistance.classification.value} "
            f"adjustment={adjustment:.2f}"
        )
        return SubstrateFeedbackInterval(
            signal_type=signal_type,
            target_seconds=target_seconds,
            resistance_band_position=position,
            tier_index=tier_index,
            rationale=rationale,
        )

    def _base_seconds_for_tier(self, tier_index: int) -> int:
        cfg = self._config
        if tier_index <= cfg.early_tier_cap:
            return cfg.early_seconds
        if tier_index <= cfg.mid_tier_cap:
            return cfg.mid_seconds
        return cfg.high_seconds

    def _tier_class_name(self, tier_index: int) -> str:
        cfg = self._config
        if tier_index <= cfg.early_tier_cap:
            return "early"
        if tier_index <= cfg.mid_tier_cap:
            return "mid"
        return "high"

    def _resistance_adjustment(
        self, resistance: ResistanceBandAssessment,
    ) -> float:
        cfg = self._config
        match resistance.classification:
            case ResistanceBandClassification.UNDER_LOADED:
                return cfg.under_loaded_multiplier
            case ResistanceBandClassification.STRESSED:
                return cfg.stressed_multiplier
            case _:
                return 1.0

__all__ = [
    "DEFAULT_INTERVAL_CALIBRATOR_CONFIG",
    "IntervalCalibratorConfig",
    "SubstrateAlignedIntervalCalibrator",
    "SubstrateFeedbackInterval",
]
