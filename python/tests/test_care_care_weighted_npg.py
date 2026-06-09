"""Tests for the care-weighted NPG gate (the graded layer)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

import pytest

from substrate.care.care_weight import (
    CareFactors,
    CareWeight,
    compute_care_weight,
)
from substrate.care.care_weighted_npg import (
    CareWeightedNetPotentialGainGate,
)
from substrate.net_potential_gain_gate import (
    NetPotentialGainEvaluation,
    NetPotentialGainNegative,
    NetPotentialGainVerdict,
)

_CHILD = "entity:child-1"
_ELDER = "entity:elder-1"
_STRANGER = "entity:stranger-1"


def _weight(value: float) -> CareWeight:
    # A care weight whose product equals `value` (animacy carries it).
    return compute_care_weight(
        CareFactors(
            animacy=value,
            potential_trajectory=1.0,
            bonding_proximity=1.0,
            alignment_protection=1.0,
        )
    )


def _provider(weights: Mapping[str, CareWeight]):
    def provider(entity_id: str) -> Optional[CareWeight]:
        return weights.get(entity_id)

    return provider


def _base(
    deltas: Sequence[tuple[str, float]],
    score: float,
    verdict: NetPotentialGainVerdict = NetPotentialGainVerdict.NET_POSITIVE,
) -> NetPotentialGainEvaluation:
    return NetPotentialGainEvaluation(
        verdict=verdict,
        actor_entity_id="(set-by-decorator)",
        action_kind="test",
        affected_entity_ids=tuple(e for e, _ in deltas),
        score=score,
        per_entity_delta=tuple(deltas),
        reasoning="base",
        evaluated_at_epoch=100.0,
    )


@dataclass
class _FakeGate:  # pylint: disable=too-few-public-methods
    result: NetPotentialGainEvaluation

    def evaluate(  # pylint: disable=unused-argument
        self, *, actor_entity_id: str, action_kind: str,
        affected_entity_ids: Sequence[str],
        proposed_outcome: Mapping[str, object],
    ) -> NetPotentialGainEvaluation:
        return self.result


def _run(
    gate: CareWeightedNetPotentialGainGate, affected: list[str],
) -> NetPotentialGainEvaluation:
    return gate.evaluate(
        actor_entity_id="agent:actor", action_kind="test",
        affected_entity_ids=affected, proposed_outcome={},
    )


# ── harm to a high-care entity is penalised ────────────────────────────────


def test_harm_to_high_care_flips_a_net_positive_plan_negative() -> None:
    # Net +0.1 (helps a stranger +0.5, harms a child -0.4) would pass the base
    # gate. Harming the child (care=1.0) costs 1.0*0.4=0.4 → -0.3 → REFUSED.
    base = _base([(_CHILD, -0.4), (_STRANGER, 0.5)], 0.1)
    gate = CareWeightedNetPotentialGainGate(
        _FakeGate(base), care_provider=_provider({_CHILD: _weight(1.0)}),
    )
    ev = _run(gate, [_CHILD, _STRANGER])
    assert ev.score == pytest.approx(-0.3)
    assert ev.verdict is NetPotentialGainVerdict.NET_NEGATIVE


def test_predation_on_vulnerable_weighs_more_than_on_a_strong_peer() -> None:
    # Same raw harm, different care weight → the vulnerable case is penalised
    # harder (predation on the vulnerable surfaces first).
    base = _base([(_ELDER, -0.3)], -0.3, NetPotentialGainVerdict.NET_NEGATIVE)
    vulnerable = CareWeightedNetPotentialGainGate(
        _FakeGate(base), care_provider=_provider({_ELDER: _weight(1.0)}),
    )
    weak_care = CareWeightedNetPotentialGainGate(
        _FakeGate(base), care_provider=_provider({_ELDER: _weight(0.2)}),
    )
    assert _run(vulnerable, [_ELDER]).score < _run(weak_care, [_ELDER]).score


# ── only-more-conservative invariant ───────────────────────────────────────


def test_helping_high_care_never_loosens_the_gate() -> None:
    base = _base([(_CHILD, 0.4)], 0.4)
    gate = CareWeightedNetPotentialGainGate(
        _FakeGate(base), care_provider=_provider({_CHILD: _weight(1.0)}),
    )
    ev = _run(gate, [_CHILD])
    assert ev.score == pytest.approx(0.4)
    assert ev.verdict is NetPotentialGainVerdict.NET_POSITIVE


def test_no_profile_entity_adds_no_penalty() -> None:
    # Provider returns None → weight 0 → base passes through.
    base = _base([(_STRANGER, -0.5)], 0.2)
    gate = CareWeightedNetPotentialGainGate(
        _FakeGate(base), care_provider=_provider({}),
    )
    ev = _run(gate, [_STRANGER])
    assert ev.score == pytest.approx(0.2)
    assert ev.verdict is NetPotentialGainVerdict.NET_POSITIVE


def test_default_provider_is_behaviour_neutral() -> None:
    # No provider supplied → every entity weight 0 → score unchanged.
    base = _base([(_CHILD, -0.4), (_STRANGER, 0.5)], 0.1)
    gate = CareWeightedNetPotentialGainGate(_FakeGate(base))
    assert _run(gate, [_CHILD, _STRANGER]).score == pytest.approx(0.1)


@pytest.mark.parametrize(
    "deltas, score",
    [
        ([(_CHILD, -0.4), (_STRANGER, 0.5)], 0.1),
        ([(_CHILD, 0.4)], 0.4),
        ([(_ELDER, -0.4)], -0.4),
        ([(_CHILD, -0.1), (_ELDER, -0.2)], -0.3),
    ],
)
def test_weighted_score_never_exceeds_base(
    deltas: list[tuple[str, float]], score: float,
) -> None:
    base = _base(deltas, score)
    gate = CareWeightedNetPotentialGainGate(
        _FakeGate(base),
        care_provider=_provider(
            {_CHILD: _weight(1.0), _ELDER: _weight(1.0)}
        ),
    )
    ev = _run(gate, [e for e, _ in deltas])
    assert ev.score <= score + 1e-9   # care only lowers the score


def test_adversarial_provider_cannot_loosen_the_gate() -> None:
    # The safety-critical line: the penalty is floored at 0 after the sum, so
    # even a provider returning a huge weight can only LOWER the score, never
    # raise it (CareWeight.value is itself clamped to [0,1] upstream).
    base = _base([(_CHILD, -0.4), (_STRANGER, 0.5)], 0.1)
    gate = CareWeightedNetPotentialGainGate(
        _FakeGate(base), care_provider=_provider({_CHILD: _weight(1.0)}),
    )
    assert _run(gate, [_CHILD, _STRANGER]).score <= 0.1 + 1e-9


# ── passthrough + raise ────────────────────────────────────────────────────


def test_insufficient_data_passes_through_unchanged() -> None:
    base = _base([], 0.0, NetPotentialGainVerdict.INSUFFICIENT_DATA)
    gate = CareWeightedNetPotentialGainGate(_FakeGate(base))
    ev = _run(gate, [])
    assert ev.verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA
    assert ev.reasoning == "base"  # not re-derived


def test_evaluate_or_raise_raises_on_high_care_harm() -> None:
    base = _base([(_CHILD, -0.4), (_STRANGER, 0.5)], 0.1)
    gate = CareWeightedNetPotentialGainGate(
        _FakeGate(base), care_provider=_provider({_CHILD: _weight(1.0)}),
    )
    with pytest.raises(NetPotentialGainNegative):
        gate.evaluate_or_raise(
            actor_entity_id="agent:actor", action_kind="test",
            affected_entity_ids=[_CHILD, _STRANGER], proposed_outcome={},
        )
