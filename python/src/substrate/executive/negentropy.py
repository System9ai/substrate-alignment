"""Negentropy / order metric — order-from-disorder, the emergence tell.

The substrate's central claim is *emergent order*: local iteration converges to
coherent structure (closed cycles, mode agreement) rather than scattering into
disorder. This module makes that mechanical and measurable.

* :func:`order_index` — the INSTANTANEOUS order in a distribution, ``1 -
  normalised Shannon entropy``. A distribution concentrated in one category
  (everything aligned) is maximally ordered (``1.0``); a uniform distribution
  (maximal disagreement) is maximally disordered (``0.0``). The mechanical inverse
  of entropy — no tuning, just information theory.
* :func:`negentropy` — order OVER TIME. Rising order is *emergence* (the
  negentropic direction); falling order is *decay* (entropy winning). The trend +
  its rate is the negentropy the system is producing or losing.

Feeds naturally from any substrate distribution — a mode distribution, a vote
tally, a zone distribution — sampled over a window.

Pure logic
==========

* No DAO, no LLM, no network. Deterministic.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import log2
from typing import Final, Sequence


def order_index(counts: Sequence[int]) -> float:
    """Instantaneous order of a distribution — ``1 - H/H_max`` in ``[0, 1]``.

    ``counts`` are the per-category frequencies (zero counts ignored). One
    populated category → maximal order (``1.0``); a uniform spread over ``N``
    categories → maximal disorder (``0.0``). Raises for an empty / all-zero
    distribution (no order is defined over nothing).
    """
    positive = [c for c in counts if c > 0]
    for c in counts:
        if c < 0:
            raise ValueError(f"counts must be >= 0; got {c!r}")
    total = sum(positive)
    if total == 0:
        raise ValueError("at least one positive count is required")
    n = len(positive)
    if n <= 1:
        return 1.0  # a single occupied category is perfectly ordered
    entropy = -sum(
        (c / total) * log2(c / total) for c in positive
    )
    return 1.0 - entropy / log2(n)


class NegentropyDirection(str, Enum):
    """Which way order is moving over the window."""

    EMERGING = "emerging"    # order rising — the substrate is self-organising
    STABLE = "stable"        # order holding
    DECAYING = "decaying"    # order falling — entropy winning


#: Below this absolute order-delta the change reads as noise, not a direction.
_ORDER_DEADBAND: Final[float] = 0.02


@dataclass(frozen=True, slots=True)
class NegentropyReport:
    """Order at the latest reading + its direction over the window."""

    current_order: float
    earlier_order: float
    order_delta: float
    direction: NegentropyDirection
    sample_count: int
    rationale: str


def negentropy(order_history: Sequence[float]) -> NegentropyReport:
    """Classify order's movement over a window of :func:`order_index` values.

    Compares the recent half's mean order to the earlier half's: rising past the
    dead-band is EMERGING (negentropic — order from disorder), falling is
    DECAYING, otherwise STABLE. A single reading is trivially STABLE.

    Raises for an empty history or an out-of-range order value.
    """
    if not order_history:
        raise ValueError("order_history must be non-empty")
    for v in order_history:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"order values must be in [0, 1]; got {v!r}")
    current = float(order_history[-1])
    if len(order_history) == 1:
        return NegentropyReport(
            current_order=current,
            earlier_order=current,
            order_delta=0.0,
            direction=NegentropyDirection.STABLE,
            sample_count=1,
            rationale=f"single reading order={current:.3f}; trend undefined → stable",
        )
    mid = len(order_history) // 2
    earlier = sum(order_history[:mid]) / mid
    recent = sum(order_history[mid:]) / (len(order_history) - mid)
    delta = recent - earlier
    if delta > _ORDER_DEADBAND:
        direction = NegentropyDirection.EMERGING
    elif delta < -_ORDER_DEADBAND:
        direction = NegentropyDirection.DECAYING
    else:
        direction = NegentropyDirection.STABLE
    rationale = (
        f"order {earlier:.3f}→{recent:.3f} (Δ{delta:+.3f}) over "
        f"{len(order_history)} readings → {direction.value}"
    )
    return NegentropyReport(
        current_order=current,
        earlier_order=earlier,
        order_delta=delta,
        direction=direction,
        sample_count=len(order_history),
        rationale=rationale,
    )


__all__ = [
    "NegentropyDirection",
    "NegentropyReport",
    "negentropy",
    "order_index",
]
