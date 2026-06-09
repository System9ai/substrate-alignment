"""UtilizationSource — bind the measurement to the quantity.

The P0 invariant that actually kills the literal-bypass disease at its root.
``decide()`` takes a ``UtilizationSource``, NOT a raw float — so each
``(quantity, scale, resource, scale_unit)`` maps to exactly ONE sanctioned
metric. Requiring a ``quantity`` label alone only *relabels* the inversion (a
RESISTANCE-derived number passed under ``quantity=WORK``); binding the
*measurement* to the quantity at the input boundary is what closes the class. A
raw float is permitted only behind an ``# executive-bypass: <metric>`` directive.

This module defines the Protocol + a callable-backed concrete source. Pure logic.
"""
from __future__ import annotations

from typing import Callable, Protocol, final, runtime_checkable

from substrate.executive.quantities import (
    Quantity,
    ResourceKind,
)
from substrate.executive.scale import ExecutiveScale

#: ``fn(quantity, scale, resource, scale_unit) -> utilization`` in ``[0, 1]``.
UtilizationFn = Callable[[Quantity, ExecutiveScale, ResourceKind, str], float]


@runtime_checkable
class UtilizationSource(Protocol):  # pylint: disable=too-few-public-methods
    """The sanctioned-metric boundary: one metric per (quantity, scale, resource)."""

    def utilization_for(
        self,
        *,
        quantity: Quantity,
        scale: ExecutiveScale,
        resource: ResourceKind,
        scale_unit: str,
    ) -> float:
        """Return the utilization for the bound metric (clamped to ``[0, 1]``)."""
        ...  # pylint: disable=unnecessary-ellipsis


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@final
class CallableUtilizationSource:  # pylint: disable=too-few-public-methods
    """A :class:`UtilizationSource` backed by a callable.

    Wraps a function that resolves ``(quantity, scale, resource, scale_unit)`` to
    a raw utilization; the result is clamped to ``[0, 1]`` at the boundary so a
    misbehaving metric cannot inject an out-of-range reading.
    """

    def __init__(self, fn: UtilizationFn) -> None:
        self._fn = fn

    def utilization_for(
        self,
        *,
        quantity: Quantity,
        scale: ExecutiveScale,
        resource: ResourceKind,
        scale_unit: str,
    ) -> float:
        """Resolve + clamp the bound metric."""
        return _clamp01(float(self._fn(quantity, scale, resource, scale_unit)))


__all__ = [
    "CallableUtilizationSource",
    "UtilizationFn",
    "UtilizationSource",
]
