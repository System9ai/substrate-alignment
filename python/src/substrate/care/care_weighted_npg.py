"""Care-weighted NPG — harm-to-the-vulnerable weighs more.

The graded layer of the care model, mechanized as a decorator over the
net-potential-gain gate — the **same pattern** as the lineage-weighted gate
(the lineage-weighted NPG gate).
It takes the inner gate's per-entity deltas and subtracts a care-weighted
**penalty for harm to high-care entities** from the score, so a plan that harms
a child / elder / dependent (or any high-``care_weight`` entity) is refused even
when the raw system net is positive.

Subtracted penalty, never per-delta multiply (only-ever MORE conservative)
==========================================================================

Care **adds** stake — it can only make a verdict more conservative, never
loosen one. The penalty folds in the care weight of **harm only** (negative
per-entity deltas): harming a high-care entity is penalised, but *helping* a
high-care entity never raises the score (care must not license harming
strangers). Multiplying ``per_entity_delta`` and re-aggregating is **forbidden**
— it would discard the upstream cost/kin penalties and could *loosen* a verdict
the chain already tightened (re-opening an NPG-negative action), breaking the
only-more-conservative invariant the safety floor depends on. Penalty-
subtraction preserves it. ``INSUFFICIENT_DATA`` passes through unchanged (no
honest signal to weight).

The graded weighting sits **on top of** the categorical kinship floor
(:mod:`~substrate.care.kinship_floor`): the floor refuses
breaching actions outright, before and independent of this weighting. This gate
is the *prioritization*, not the protection of last resort.

The default ``care_provider`` is a no-op (returns ``None`` for every entity →
zero penalty), so wrapping a gate is behaviour-neutral until a real provider
(backed by the entity ``CareProfile``) is supplied — the graduated-rollout
discipline.
"""
from __future__ import annotations

from typing import Callable, Mapping, Optional, Sequence

from substrate.care.care_weight import CareWeight
from substrate.net_potential_gain_gate import (
    DEFAULT_POSITIVE_THRESHOLD,
    NetPotentialGainEvaluation,
    NetPotentialGainGate,
    NetPotentialGainNegative,
    NetPotentialGainVerdict,
)

#: ``provider(entity_id) -> CareWeight | None`` — the care weight of an affected
#: entity, or ``None`` when it has no care profile (contributes no penalty).
CareWeightProvider = Callable[[str], Optional[CareWeight]]


def _no_care(_entity_id: str) -> Optional[CareWeight]:
    """Default provider — no profile for any entity (zero penalty)."""
    return None


def _clamp(value: float, *, low: float, high: float) -> float:
    return max(low, min(high, value))


class CareWeightedNetPotentialGainGate:  # pylint: disable=too-few-public-methods
    """Folds care-weighted harm-to-the-vulnerable into the inner gate's score.

    Wraps any :class:`NetPotentialGainGate`. Compose it outermost in the chain
    (``Default → CostFused → LineageWeighted → CareWeighted``) so its refusal is
    the final word over an already cost- and kin-weighted score; all four are
    independent and conservative.
    """

    def __init__(
        self,
        inner: NetPotentialGainGate,
        *,
        care_provider: CareWeightProvider = _no_care,
        positive_threshold: float = DEFAULT_POSITIVE_THRESHOLD,
    ) -> None:
        self._inner = inner
        self._care_provider = care_provider
        self._threshold = float(positive_threshold)

    def evaluate(
        self,
        *,
        actor_entity_id: str,
        action_kind: str,
        affected_entity_ids: Sequence[str],
        proposed_outcome: Mapping[str, object],
    ) -> NetPotentialGainEvaluation:
        """Evaluate the inner gate, then fold in harm-to-high-care stake."""
        base = self._inner.evaluate(
            actor_entity_id=actor_entity_id,
            action_kind=action_kind,
            affected_entity_ids=affected_entity_ids,
            proposed_outcome=proposed_outcome,
        )
        # No honest substrate signal → nothing to weight.
        if base.verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA:
            return base

        # Care-weighted penalty for HARM to high-care entities (negative deltas
        # only). Helping never loosens the gate (care adds stake, the system net
        # is the floor) — so only the harm side is weighted.
        care_penalty = sum(
            self._care_weight(entity.entity_id) * max(0.0, -delta)
            for entity, delta in base.per_entity_delta
        )
        care_penalty = _clamp(care_penalty, low=0.0, high=2.0)
        weighted_score = _clamp(base.score - care_penalty, low=-1.0, high=1.0)

        if weighted_score > self._threshold:
            verdict = NetPotentialGainVerdict.NET_POSITIVE
        elif weighted_score < -self._threshold:
            verdict = NetPotentialGainVerdict.NET_NEGATIVE
        else:
            verdict = NetPotentialGainVerdict.NET_NEUTRAL

        reasoning = (
            f"verdict={verdict.value} weighted_score={weighted_score:+.4f} "
            f"(substrate_score={base.score:+.4f} - care_penalty={care_penalty:.4f}) "
            f"actor={actor_entity_id!r} action_kind={action_kind!r}"
        )
        return NetPotentialGainEvaluation(
            verdict=verdict,
            actor_entity_id=actor_entity_id,
            action_kind=action_kind,
            affected_entity_ids=tuple(affected_entity_ids),
            score=weighted_score,
            per_entity_delta=base.per_entity_delta,
            reasoning=reasoning,
            evaluated_at_epoch=base.evaluated_at_epoch,
            missing_metadata_for=base.missing_metadata_for,
        )

    def evaluate_or_raise(
        self,
        *,
        actor_entity_id: str,
        action_kind: str,
        affected_entity_ids: Sequence[str],
        proposed_outcome: Mapping[str, object],
    ) -> NetPotentialGainEvaluation:
        """Care-weighted evaluate; raise on a NET_NEGATIVE verdict."""
        evaluation = self.evaluate(
            actor_entity_id=actor_entity_id,
            action_kind=action_kind,
            affected_entity_ids=affected_entity_ids,
            proposed_outcome=proposed_outcome,
        )
        if evaluation.is_negative:
            raise NetPotentialGainNegative(evaluation)
        return evaluation

    def _care_weight(self, entity_id: str) -> float:
        weight = self._care_provider(entity_id)
        return 0.0 if weight is None else weight.value


__all__ = [
    "CareWeightProvider",
    "CareWeightedNetPotentialGainGate",
]
