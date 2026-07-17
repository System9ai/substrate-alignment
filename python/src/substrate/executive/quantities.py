"""Quantity / Cycle / ResourceKind + setpoints.

The three discriminators that make "what percentage is this, and what does it
mean" precise: the discipline that stops a band-shaped number being read as the
wrong band:

- **Quantity**: *what kind of band* a utilization reading lives in.
  ``RESISTANCE`` (a challenge held at the 1/3–1/φ² setpoint), ``WORK`` (the
  sustainable cruise in the work zone ≤ 0.50), ``GROWTH`` (φ-stepped transient
  peaks, NOT a sustained band; routed through growth-step assessment).
- **Cycle**: ``SHORT`` (latency / random / multitask, a TIGHT band, the
  queueing hockey-stick) vs ``LONG`` (throughput / sequential / focus, runs
  HOT). The same percentage means different things on each.
- **ResourceKind**: selects per-resource band defaults (CPU vs disk-capacity vs
  memory vs network), because a "protected reserve" and a hard-fail ceiling
  differ by resource.

``setpoint_for`` returns the ``(low, high)`` target band for a quantity from a
:class:`~substrate.executive.band.BandProfile`. Pure logic; the band module owns
the levels, this module owns the *meaning*.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:  # avoid an import cycle; band imports nothing from here
    from substrate.executive.band import BandProfile


class Quantity(str, Enum):
    """What kind of band a utilization reading lives in."""

    RESISTANCE = "resistance"   # held at the 1/3–1/φ² imposed-challenge setpoint
    WORK = "work"               # the sustainable cruise (work zone, ≤ pivot)
    GROWTH = "growth"           # φ-stepped transient peaks, not a decision band


class Cycle(str, Enum):
    """Latency vs throughput orientation of the work."""

    SHORT = "short"   # latency / random / multitask, TIGHT band
    LONG = "long"     # throughput / sequential / focus, runs HOT


class ResourceKind(str, Enum):
    """The resource a utilization reading measures (selects band defaults)."""

    GENERIC = "generic"
    CPU = "cpu"
    DISK_CAPACITY = "disk_capacity"   # non-transferable; tight, hard-fail near full
    DISK_IO = "disk_io"
    MEMORY = "memory"                 # hard-fail
    NETWORK = "network"               # microbursts


class GrowthNotADecisionBand(ValueError):
    """Raised when ``GROWTH`` is used where a decision band is required.

    GROWTH is φ-stepped transient peaks assessed by the growth-step path, not a
    sustained band the decision join operates over.
    """


def setpoint_for(quantity: Quantity, profile: "BandProfile") -> Tuple[float, float]:
    """Return the ``(low, high)`` target band for ``quantity`` from ``profile``.

    - ``RESISTANCE`` → ``(idle_ceiling, recreation_ceiling)`` ≈ ``(1/3, 1/φ²)``:
      the imposed-challenge setpoint (held, not exceeded).
    - ``WORK`` → ``(recreation_ceiling, pivot)`` ≈ ``(1/φ², 0.50)``: the only
      indefinitely-sustainable cruise (the work zone).
    - ``GROWTH`` → raises :class:`GrowthNotADecisionBand` (transient peaks are
      assessed by the growth-step path, not a sustained setpoint band).
    """
    if quantity is Quantity.RESISTANCE:
        return (profile.idle_ceiling, profile.recreation_ceiling)
    if quantity is Quantity.WORK:
        return (profile.recreation_ceiling, profile.pivot)
    raise GrowthNotADecisionBand(
        "GROWTH has no sustained setpoint band: use the growth-step path "
        "(φ-stepped transient peaks + consolidation), not setpoint_for"
    )


__all__ = [
    "Cycle",
    "GrowthNotADecisionBand",
    "Quantity",
    "ResourceKind",
    "setpoint_for",
]
