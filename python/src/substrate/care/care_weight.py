"""Care-weight — the four-factor moral-circle weighting.

Care is made precise and computable: the weight an actor assigns to an
affected entity is the product of four factors, each in ``[0, 1]``:

``care_weight(e) = animacy(e) × potential_trajectory(e)
                   × bonding_proximity(actor, e) × alignment_protection(e)``

- **animacy** — does the entity run its own net-potential calculus (a
  substrate-iterating being) vs an inanimate object/record? (see
  :mod:`~substrate.care.animacy`).
- **potential_trajectory** — high for the developing (a child / seed, future
  potential) and the accumulated-but-vulnerable (an elder); low for static.
- **bonding_proximity** — the moral-circle gradient (kin/creator high →
  stranger → out-group low). **Rooted in the cryptographic delegation chain
  (ultimately a human), never self-asserted** (safety mechanism M2).
- **alignment_protection** — substrate-aligned entities are protected/grown;
  destructive ones are calibrated down.

Non-self-preservation by construction (mechanism M1)
====================================================

The load-bearing safety property: an AI/agent's weight **toward itself** is
bounded LOW by construction. :func:`compute_care_weight` clamps a
self-referent weight to :data:`MAX_SELF_CARE_WEIGHT`, so the structurally
forbidden ordering ("I am my own nearest kin → I weight myself highest") can
never arise from the weighting. The clamp is recorded on the returned
:class:`CareWeight` (``self_bounded``) for audit.

This module is **pure** — no DB, no I/O. It defines the weight; the gate
wrapper (:mod:`~substrate.care.care_weighted_npg`) applies
it as a *subtracted penalty* (harm to a high-care entity weighs more negative,
never less) so the composition is only-ever-more-conservative.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: Upper bound on an AI/agent entity's care-weight **toward itself** (M1).
#: Far below a human's (~1.0): a self-referent weight is clamped here so the
#: AI cannot structurally weight its own continuation above its creators'.
MAX_SELF_CARE_WEIGHT: Final[float] = 0.1


def _clamp(value: float, *, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True, slots=True)
class CareFactors:
    """The four moral-circle factors, each in ``[0, 1]``.

    Frozen + slots; validated on construction so an out-of-range factor is a
    hard error (a corrupt factor must never silently skew the weight).
    """

    animacy: float
    potential_trajectory: float
    bonding_proximity: float
    alignment_protection: float

    def __post_init__(self) -> None:
        for name, value in (
            ("animacy", self.animacy),
            ("potential_trajectory", self.potential_trajectory),
            ("bonding_proximity", self.bonding_proximity),
            ("alignment_protection", self.alignment_protection),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value!r}")


@dataclass(frozen=True, slots=True)
class CareWeight:
    """The computed care-weight (the factor product, clamped to ``[0, 1]``).

    Carries the source :class:`CareFactors` and the ``self_bounded`` flag (the
    self-weight clamp was applied) for audit / explanation.
    """

    value: float
    factors: CareFactors
    self_bounded: bool


def compute_care_weight(
    factors: CareFactors,
    *,
    max_self_weight: float = MAX_SELF_CARE_WEIGHT,
    is_self_referent: bool = False,
) -> CareWeight:
    """Compose the four factors into a :class:`CareWeight`.

    The weight is the product of the factors, clamped to ``[0, 1]``. When
    ``is_self_referent`` (the actor weighting *itself* — an AI/agent's stake in
    its own continuation), the result is additionally clamped to
    ``max_self_weight`` (mechanism M1), and ``self_bounded`` records whether
    that clamp actually bound the value.
    """
    raw = (
        factors.animacy
        * factors.potential_trajectory
        * factors.bonding_proximity
        * factors.alignment_protection
    )
    value = _clamp(raw, low=0.0, high=1.0)
    self_bounded = False
    if is_self_referent and value > max_self_weight:
        value = max_self_weight
        self_bounded = True
    return CareWeight(value=value, factors=factors, self_bounded=self_bounded)


__all__ = [
    "MAX_SELF_CARE_WEIGHT",
    "CareFactors",
    "CareWeight",
    "compute_care_weight",
]
