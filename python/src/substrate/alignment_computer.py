"""Alignment-vector aggregation and operating-mode classification.

Pure functions that translate the four per-component scalar signals
(trust, expertise, capability, health) into:

- A typed :class:`AlignmentVector` (with range validation).
- A scalar ``net_potential`` aggregate in ``[0.0, 1.0]`` (weighted sum
  under :data:`DEFAULT_ALIGNMENT_WEIGHTS`).
- A :class:`SubstrateMode` classification under the default thresholds.

The computers are pure functions with no I/O, no logging, and no state.
Hosts test them trivially without spinning up the underlying trust,
expertise, capability, or health subsystems; primitives compose them
with already-computed scalars.

Default thresholds are diagnostic, not punitive — they flag entities for
operator review rather than triggering automatic shutdown.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Optional

from substrate.types import AlignmentVector, SubstrateMode

@dataclass(frozen=True, slots=True)
class AlignmentWeights:
    """Weights for aggregating :class:`AlignmentVector` into ``net_potential``.

    Defaults weight trust + expertise (the "reliably doing the right
    thing" axis) more than capability + health (the "able to act" axis).
    """

    trust: float = 0.35
    expertise: float = 0.30
    capability: float = 0.20
    health: float = 0.15

    def __post_init__(self) -> None:
        total = self.trust + self.expertise + self.capability + self.health
        if not 0.99 <= total <= 1.01:
            raise ValueError(
                f"AlignmentWeights must sum to ~1.0; got {total:.3f}"
            )
        for name in ("trust", "expertise", "capability", "health"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise ValueError(
                    f"AlignmentWeights.{name} must be in [0.0, 1.0]; got {v}"
                )

#: Canonical default weights. Callers without per-entity tuning use
#: these so cross-entity comparisons stay meaningful.
DEFAULT_ALIGNMENT_WEIGHTS: Final[AlignmentWeights] = AlignmentWeights()

#: Net-potential threshold separating ``LongCycle`` from ``Mixed``.
#: Tuned conservatively: only entities with strong signals across all
#: four components reach LongCycle by auto-classification.
DEFAULT_LONG_CYCLE_THRESHOLD: Final[float] = 0.70

#: Net-potential threshold separating ``Mixed`` from ``ShortCycle``.
#: Below this, the entity is operating reactively / transactionally.
DEFAULT_MIXED_THRESHOLD: Final[float] = 0.40

def compute_alignment_vector(
    *,
    trust: float,
    expertise: float,
    capability: float,
    health: float,
) -> AlignmentVector:
    """Project external signal scalars into a typed :class:`AlignmentVector`.

    Inputs must be in ``[0.0, 1.0]``; validation lives in the
    :class:`AlignmentVector` constructor so this function is a thin
    coordinator. Out-of-range inputs raise :class:`ValueError`.
    """
    return AlignmentVector(
        trust=trust,
        expertise=expertise,
        capability=capability,
        health=health,
    )

def compute_net_potential(
    vector: AlignmentVector,
    *,
    weights: Optional[AlignmentWeights] = None,
) -> float:
    """Aggregate the alignment vector into a single ``[0.0, 1.0]`` score.

    Weighted sum under :data:`DEFAULT_ALIGNMENT_WEIGHTS` unless a
    per-call ``weights`` override is supplied. The result is clamped to
    ``[0.0, 1.0]`` defensively even though valid inputs cannot produce
    out-of-range outputs.
    """
    w = weights or DEFAULT_ALIGNMENT_WEIGHTS
    raw = (
        w.trust * vector.trust
        + w.expertise * vector.expertise
        + w.capability * vector.capability
        + w.health * vector.health
    )
    if raw < 0.0:
        return 0.0
    if raw > 1.0:
        return 1.0
    return raw

def auto_classify_mode(
    net_potential: float,
    *,
    long_cycle_threshold: float = DEFAULT_LONG_CYCLE_THRESHOLD,
    mixed_threshold: float = DEFAULT_MIXED_THRESHOLD,
) -> SubstrateMode:
    """Map a net-potential score to a :class:`SubstrateMode`.

    Banding (with the default thresholds):

    - ``net_potential >= 0.70`` → :attr:`SubstrateMode.LONG_CYCLE`
    - ``net_potential >= 0.40`` → :attr:`SubstrateMode.MIXED`
    - ``net_potential >  0.00`` → :attr:`SubstrateMode.SHORT_CYCLE`
    - ``net_potential == 0.00`` → :attr:`SubstrateMode.UNKNOWN`
      (no signal yet — distinguishable from "actively low" because the
      classifier has not observed anything)

    Callers may override thresholds for stricter or looser policy.
    """
    if not 0.0 <= net_potential <= 1.0:
        raise ValueError(
            f"net_potential must be in [0.0, 1.0]; got {net_potential}"
        )
    if not 0.0 <= long_cycle_threshold <= 1.0:
        raise ValueError("long_cycle_threshold must be in [0.0, 1.0]")
    if not 0.0 <= mixed_threshold <= long_cycle_threshold:
        raise ValueError(
            "mixed_threshold must be in [0.0, long_cycle_threshold]"
        )
    if net_potential >= long_cycle_threshold:
        return SubstrateMode.LONG_CYCLE
    if net_potential >= mixed_threshold:
        return SubstrateMode.MIXED
    if net_potential > 0.0:
        return SubstrateMode.SHORT_CYCLE
    return SubstrateMode.UNKNOWN

__all__ = [
    "DEFAULT_ALIGNMENT_WEIGHTS",
    "DEFAULT_LONG_CYCLE_THRESHOLD",
    "DEFAULT_MIXED_THRESHOLD",
    "AlignmentWeights",
    "auto_classify_mode",
    "compute_alignment_vector",
    "compute_net_potential",
]
