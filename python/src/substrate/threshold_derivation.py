"""ResistanceBand-derived threshold helpers.

When choosing thresholds (rate limits, ring sizes, batch sizes, retry
caps, queue depths, soft / hard quotas), this module derives them from
the substrate band rather than from ad-hoc multipliers. This is the
single source of truth for that derivation across consumers.

**Declare the quantity — RESISTANCE vs WORK — before deriving.** The two
have different bands, and conflating them inverts the model:

- **RESISTANCE** (imposed challenge / pull-back) calibrates in the
  ``1/3 … 1/φ²`` band — use the RESISTANCE positions (LOWER / TARGET /
  UPPER) for friction-type thresholds (retry caps, backpressure entry).
- **WORK** (the load a subsystem CARRIES — buffer capacity, processing
  rate, queue depth, steady-state quota) cruises the WORK ZONE
  ``1/φ² … 0.50`` — use the WORK positions (WORK_TARGET / WORK_CEILING).
  Deriving a WORK quantity from the resistance TARGET (~0.358)
  UNDER-provisions it by ~20%; ``0.45`` is the work zone, not a failure.

RESISTANCE reference points:

- **LOWER** (~``1/3``) — productive-band entry; below = under-loaded.
- **TARGET** (midpoint, ~``0.358``) — resistance-band steady-state (the
  imposed-challenge setpoint).
- **UPPER** (~``1/φ² ≈ 0.382``) — productive-band exit; above, the
  challenge eats into the maintained capacity.

WORK reference points (the sustainable cruise):

- **WORK_TARGET** (~``0.441``) — the work-zone midpoint; the steady-state
  a carried-load quantity should provision toward.
- **WORK_CEILING** (``0.50``) — work-zone top / half-period pivot; the
  ceiling of indefinitely-sustainable WORK (peaking above it is
  transient-only).

A capacity ``C`` is bound to threshold ``C × band_position``, so the
band's anchor flows mechanically into operational thresholds without
operators rolling their own multipliers. Whether an excursion above the
chosen position is an absorbed spike or accruing debt is a *temporal*
determination that belongs to the caller's ``SustainedLoadTracker``, not
to this static derivation.
"""
from __future__ import annotations

from enum import Enum
from typing import Final, Optional

from substrate.resistance_band import (
    DEFAULT_CONFIG,
    WORK_ZONE_UPPER,
    ResistanceBandAssessment,
    ResistanceBandConfig,
    assess,
)

class BandPosition(str, Enum):
    """Reference points for threshold derivation, keyed by quantity.

    RESISTANCE (imposed challenge): LOWER / TARGET / UPPER span 1/3 … 1/φ².
    WORK (carried load): WORK_TARGET / WORK_CEILING span 1/φ² … 0.50.
    Pick by the quantity you are deriving — deriving a WORK quantity from
    a RESISTANCE position under-provisions it.
    """

    # RESISTANCE positions — imposed-challenge setpoint (1/3 … 1/φ²)
    LOWER = "lower"
    TARGET = "target"
    UPPER = "upper"
    # WORK positions — the sustainable cruise (1/φ² … 0.50)
    WORK_TARGET = "work_target"
    WORK_CEILING = "work_ceiling"

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
    if position is BandPosition.WORK_CEILING:
        return WORK_ZONE_UPPER
    if position is BandPosition.WORK_TARGET:
        # work-zone midpoint: halfway between the resistance ceiling
        # (1/φ²) and the work-zone top (the 0.50 half-period pivot).
        return (cfg.upper_bound + WORK_ZONE_UPPER) / 2.0
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

def derive_work_target(
    capacity: float,
    *,
    config: Optional[ResistanceBandConfig] = None,
    min_threshold: int = DEFAULT_MIN_THRESHOLD,
) -> int:
    """Return the steady-state WORK provisioning (work-zone midpoint × capacity).

    Use for load a subsystem CARRIES — buffer capacity, queue depth,
    per-source rate budget. The sustainable cruise for WORK is the work
    zone (1/φ² … 0.50), so the steady-state target is its midpoint
    (~0.441 × capacity), NOT the resistance ``TARGET`` (~0.358). Deriving
    a WORK quantity from the resistance target under-provisions it.
    """
    return derive_threshold(
        capacity, position=BandPosition.WORK_TARGET,
        config=config, min_threshold=min_threshold,
    )

def derive_work_target_float(
    capacity: float,
    *,
    config: Optional[ResistanceBandConfig] = None,
) -> float:
    """Return the steady-state WORK target as a float (no rounding).

    The continuous-quantity companion of :func:`derive_work_target` — for
    rate budgets (requests/sec, frames/sec, bytes/sec) the system sustains.
    """
    return derive_threshold_float(
        capacity, position=BandPosition.WORK_TARGET, config=config,
    )

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
    "derive_work_target",
    "derive_work_target_float",
]
