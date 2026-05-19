"""ResistanceBand-derived threshold helpers.

When choosing thresholds (rate limits, ring sizes, batch sizes, retry
caps, queue depths, soft / hard quotas), this module derives them from
the productive-resistance band rather than from ad-hoc multipliers. This
is the single source of truth for that derivation across consumers.

Three reference points along the band:

- **LOWER** (~``1/3``) — the entry to the productive band. Below this
  the system is under-loaded.
- **TARGET** (midpoint, ~``0.358``) — closed-loop steady-state. The
  point the resistance band's recommended scaling factor walks toward.
- **UPPER** (~``1/φ² ≈ 0.382``) — the exit of the productive band.
  Above this the system is stressed and should shed load.

A capacity ``C`` is bound to threshold ``C × band_position``, so the
band's anchor flows mechanically into operational thresholds without
operators rolling their own multipliers.
"""
from __future__ import annotations

from enum import Enum
from typing import Final, Optional

from substrate.resistance_band import (
    DEFAULT_CONFIG,
    ResistanceBandAssessment,
    ResistanceBandConfig,
    assess,
)


class BandPosition(str, Enum):
    """Three reference points along the productive-resistance band."""

    LOWER = "lower"
    TARGET = "target"
    UPPER = "upper"


#: Default minimum threshold floor — derived thresholds never go below
#: this even when the input capacity is tiny. Prevents pathological
#: ``derive_threshold(capacity=1)`` cases from rounding to 0.
DEFAULT_MIN_THRESHOLD: Final[int] = 1


def _band_position(
    position: BandPosition,
    *,
    config: Optional[ResistanceBandConfig] = None,
) -> float:
    cfg = config or DEFAULT_CONFIG
    if position is BandPosition.LOWER:
        return cfg.lower_bound
    if position is BandPosition.UPPER:
        return cfg.upper_bound
    return cfg.target


def derive_threshold(
    capacity: float,
    *,
    position: BandPosition = BandPosition.TARGET,
    config: Optional[ResistanceBandConfig] = None,
    min_threshold: int = DEFAULT_MIN_THRESHOLD,
) -> int:
    """Return the band-aligned integer threshold for ``capacity``.

    The output is rounded *down* (floor) to an int — the productive
    band is the safe zone, so falling short of the multiplier is the
    conservative side. ``min_threshold`` floors trivial cases.
    """
    if capacity < 0:
        raise ValueError(f"capacity must be >= 0; got {capacity!r}")
    fraction = _band_position(position, config=config)
    value = int(capacity * fraction)
    return max(min_threshold, value)


def derive_threshold_float(
    capacity: float,
    *,
    position: BandPosition = BandPosition.TARGET,
    config: Optional[ResistanceBandConfig] = None,
) -> float:
    """Return the band-aligned float threshold (no rounding).

    Useful for rate limits (requests/sec), bytes-per-second budgets, or
    any continuous quantity. No minimum floor — the caller decides.
    """
    if capacity < 0:
        raise ValueError(f"capacity must be >= 0; got {capacity!r}")
    fraction = _band_position(position, config=config)
    return capacity * fraction


def derive_soft_limit(
    capacity: float,
    *,
    config: Optional[ResistanceBandConfig] = None,
) -> int:
    """Return the soft limit (productive-band lower bound × capacity)."""
    return derive_threshold(
        capacity, position=BandPosition.LOWER, config=config,
    )


def derive_target(
    capacity: float,
    *,
    config: Optional[ResistanceBandConfig] = None,
) -> int:
    """Return the closed-loop target (productive-band midpoint × capacity)."""
    return derive_threshold(
        capacity, position=BandPosition.TARGET, config=config,
    )


def derive_hard_limit(
    capacity: float,
    *,
    config: Optional[ResistanceBandConfig] = None,
) -> int:
    """Return the hard limit (productive-band upper bound × capacity)."""
    return derive_threshold(
        capacity, position=BandPosition.UPPER, config=config,
    )


def derive_quota_pair(
    capacity: float,
    *,
    config: Optional[ResistanceBandConfig] = None,
) -> tuple[int, int]:
    """Return ``(soft_limit, hard_limit)`` — the productive-band pair."""
    return (
        derive_soft_limit(capacity, config=config),
        derive_hard_limit(capacity, config=config),
    )


def derive_batch_size(
    max_batch: int,
    *,
    config: Optional[ResistanceBandConfig] = None,
    min_threshold: int = DEFAULT_MIN_THRESHOLD,
) -> int:
    """Return a band-aligned batch size from a maximum.

    Batch sizes ride the band target — small enough to leave room for
    backpressure-driven feedback, large enough to amortise overhead.
    """
    return derive_threshold(
        max_batch, position=BandPosition.TARGET,
        config=config, min_threshold=min_threshold,
    )


def derive_retry_cap(
    max_retries: int,
    *,
    config: Optional[ResistanceBandConfig] = None,
    min_threshold: int = 1,
) -> int:
    """Return a band-aligned retry cap.

    Retries cluster at the band's upper bound — generous when there is
    headroom (band target leaves room to escalate), constrained when
    capacity is tight.
    """
    return derive_threshold(
        max_retries, position=BandPosition.UPPER,
        config=config, min_threshold=min_threshold,
    )


def assess_utilization(
    current: float,
    capacity: float,
    *,
    config: Optional[ResistanceBandConfig] = None,
) -> ResistanceBandAssessment:
    """Compute a band assessment from absolute ``current/capacity`` values.

    Returns a :class:`ResistanceBandAssessment` carrying the
    classification and recommended scaling factor. Raises ``ValueError``
    when capacity is non-positive or current is negative.
    """
    if capacity <= 0:
        raise ValueError(f"capacity must be > 0; got {capacity!r}")
    if current < 0:
        raise ValueError(f"current must be >= 0; got {current!r}")
    utilization = min(1.0, current / capacity)
    return assess(utilization, config=config)


__all__ = [
    "BandPosition",
    "DEFAULT_MIN_THRESHOLD",
    "assess_utilization",
    "derive_batch_size",
    "derive_hard_limit",
    "derive_quota_pair",
    "derive_retry_cap",
    "derive_soft_limit",
    "derive_target",
    "derive_threshold",
    "derive_threshold_float",
]
