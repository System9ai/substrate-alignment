"""SustainedLoadTracker — the temporal authority.

Levels are geometric; *consequences* are temporal. The band classifier
(:mod:`~substrate.executive.band`) says only *where* a
reading sits. **This module is the sole authority for SPIKE-vs-SUSTAINED** — so
the pivot and the damage/debt are fired by *duration*, and a transient spike
never triggers them. One source of levels (the profile), one authority for
sustained-vs-spike (this tracker): no desync possible (there is deliberately no
``spike_tolerance`` on the profile).

It reuses the established :class:`~substrate.sustained_load.LoadTrend`
vocabulary (no shadow enum), but applies the **corrected** thresholds: strain is
sustained above the *work-zone* (``> pivot`` = 0.50), debt is sustained in
*DANGER* (``> danger_line`` = 2/3) — not the older 1/φ debt line. The thresholds
come from the :class:`BandProfile` passed to :meth:`trend`, never from a local
constant.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Final, Optional, Protocol, final, runtime_checkable

from substrate.executive.band import (
    DEFAULT_BAND_PROFILE,
    BandProfile,
)
from substrate.sustained_load import LoadTrend

#: Default EWMA smoothing factor (matches the established tracker).
DEFAULT_EWMA_ALPHA: Final[float] = 0.3
#: Default consecutive-breach count that constitutes "sustained" vs a spike.
DEFAULT_SUSTAIN_COUNT: Final[int] = 3


@runtime_checkable
class SustainedLoadTracker(Protocol):
    """The temporal-verdict contract (.

    ``observe`` feeds one reading; ``trend`` returns the temporal verdict at the
    profile's levels (EWMA + consecutive-breach). A concrete tracker is the only
    thing allowed to declare SPIKE vs SUSTAINED.
    """

    def observe(self, u: float, *, work_pending: bool = False) -> None:
        """Feed one utilization reading (optionally flagged work-pending)."""
        ...  # pylint: disable=unnecessary-ellipsis

    def trend(self, *, profile: BandProfile = DEFAULT_BAND_PROFILE) -> LoadTrend:
        """Return the temporal verdict at ``profile``'s levels."""
        ...  # pylint: disable=unnecessary-ellipsis


@final
class EwmaLoadTracker:
    """EWMA + consecutive-breach tracker — the canonical temporal authority.

    Keeps an EWMA (for smoothing) plus a bounded window of the most recent
    readings; :meth:`trend` derives SPIKE vs SUSTAINED from that window relative
    to the supplied profile. ``sustain_count`` consecutive readings above a level
    constitute "sustained"; a single excursion above the pivot is a SPIKE
    (absorbed, expected to decay).
    """

    def __init__(
        self,
        *,
        alpha: float = DEFAULT_EWMA_ALPHA,
        sustain_count: int = DEFAULT_SUSTAIN_COUNT,
    ) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError(f"alpha must be in (0, 1]; got {alpha!r}")
        if sustain_count < 1:
            raise ValueError(f"sustain_count must be >= 1; got {sustain_count!r}")
        self._alpha = alpha
        self._sustain_count = sustain_count
        self._ewma: Optional[float] = None
        self._window: Deque[float] = deque(maxlen=sustain_count)
        self._last: Optional[float] = None
        self._work_pending = False

    def observe(self, u: float, *, work_pending: bool = False) -> None:
        """Feed one reading; update the EWMA + the recent-reading window."""
        self._ewma = (
            u if self._ewma is None
            else self._alpha * u + (1.0 - self._alpha) * self._ewma
        )
        self._window.append(u)
        self._last = u
        self._work_pending = work_pending

    @property
    def ewma(self) -> Optional[float]:
        """The current EWMA (``None`` before the first observation)."""
        return self._ewma

    def trend(
        self, *, profile: BandProfile = DEFAULT_BAND_PROFILE
    ) -> LoadTrend:
        """Return the temporal verdict at ``profile``'s levels.

        - ``DEBT_ACCRUING`` — ``sustain_count`` consecutive readings sustained in
          DANGER (``> danger_line``): damage, compensation owed.
        - ``SUSTAINED_STRAIN`` — sustained above the work zone (``> pivot``):
          debt accruing, back off to the cruise.
        - ``SPIKE`` — a transient excursion above the pivot that has NOT
          persisted: absorbed, expected to decay.
        - ``AVOIDANCE`` — work pending but the entity sits below the work-entry
          threshold (bouncing off it).
        - ``NOMINAL`` — in the sustainable cruise.
        """
        if self._last is None:
            return LoadTrend.NOMINAL
        full = len(self._window) >= self._sustain_count
        if full and all(u > profile.danger_line for u in self._window):
            return LoadTrend.DEBT_ACCRUING
        if full and all(u > profile.pivot for u in self._window):
            return LoadTrend.SUSTAINED_STRAIN
        if self._last > profile.pivot:
            return LoadTrend.SPIKE
        if self._work_pending and self._last < profile.idle_ceiling:
            return LoadTrend.AVOIDANCE
        return LoadTrend.NOMINAL


__all__ = [
    "DEFAULT_EWMA_ALPHA",
    "DEFAULT_SUSTAIN_COUNT",
    "EwmaLoadTracker",
    "LoadTrend",
    "SustainedLoadTracker",
]
