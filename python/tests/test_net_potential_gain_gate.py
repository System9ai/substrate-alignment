"""Tests for NetPotentialGainGate against the Protocol-based API.

Verifies every branch of the verdict-resolution algorithm:

- Input validation (empty action_kind)
- Actor-only short-circuit → NEUTRAL
- Caller-supplied ``expected_delta_by_entity`` happy path
- Caller-supplied partial coverage → INSUFFICIENT_DATA
- Caller-supplied non-Mapping → falls back to heuristic
- Caller-supplied non-numeric value → falls back to heuristic
- Heuristic happy path (positive / negative / neutral)
- Heuristic miss → INSUFFICIENT_DATA
- Missing substrate metadata for some affected entities → INSUFFICIENT_DATA
- positive_threshold customisation
- Score clamping to [-1, 1]
- Constructor validation (threshold)
- Evaluation timestamp uses injected clock
- Frozen-dataclass immutability
- Reasoning contains per-entity contributions
- :class:`RaiseOnNegativeGate`: raises on NEGATIVE, passes through
  POSITIVE / NEUTRAL / INSUFFICIENT_DATA
- Exported ``__all__`` shape
"""
from __future__ import annotations

import pytest

from substrate import net_potential_gain_gate as _module
from substrate.net_potential_gain_gate import (
    ACTION_KIND_HEURISTICS,
    DEFAULT_POSITIVE_THRESHOLD,
    NPG_VERDICTS,
    DefaultNetPotentialGainGate,
    NetPotentialGainEvaluation,
    NetPotentialGainNegative,
    NetPotentialGainVerdict,
    RaiseOnNegativeGate,
)
from substrate.types import (
    AlignmentVector,
    EntityRef,
    InMemorySubstrateMetadataStore,
    SubstrateMode,
)


def _seed_store(*refs: EntityRef) -> InMemorySubstrateMetadataStore:
    """Build an in-memory store with each ref seeded at neutral metadata."""
    store = InMemorySubstrateMetadataStore()
    for r in refs:
        store.upsert(
            r,
            substrate_mode=SubstrateMode.MIXED,
            classifier="test",
            classifier_rationale="seeded for NPG gate test",
            alignment_vector=AlignmentVector(
                trust=0.5, expertise=0.5, capability=0.5, health=0.5,
            ),
            net_potential=0.5,
        )
    return store


def _actor() -> EntityRef:
    return EntityRef(entity_type="agent", entity_id="actor-1")


def _gate(
    store: InMemorySubstrateMetadataStore,
    *,
    positive_threshold: float = DEFAULT_POSITIVE_THRESHOLD,
) -> DefaultNetPotentialGainGate:
    return DefaultNetPotentialGainGate(
        metadata_store=store,
        positive_threshold=positive_threshold,
        clock=lambda: 1_700_000_000.0,
    )


class TestConstructorValidation:
    def test_threshold_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive_threshold"):
            DefaultNetPotentialGainGate(
                metadata_store=InMemorySubstrateMetadataStore(),
                positive_threshold=0.0,
            )

    def test_threshold_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive_threshold"):
            DefaultNetPotentialGainGate(
                metadata_store=InMemorySubstrateMetadataStore(),
                positive_threshold=-0.1,
            )

    def test_threshold_above_one_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive_threshold"):
            DefaultNetPotentialGainGate(
                metadata_store=InMemorySubstrateMetadataStore(),
                positive_threshold=1.5,
            )

    def test_action_heuristics_override(self) -> None:
        custom = {"frobnicate": 0.5}
        gate = DefaultNetPotentialGainGate(
            metadata_store=InMemorySubstrateMetadataStore(),
            action_heuristics=custom,
        )
        assert gate is not None


class TestInputValidation:
    def test_empty_action_kind_rejected(self) -> None:
        gate = _gate(_seed_store())
        with pytest.raises(ValueError, match="action_kind"):
            gate.evaluate(
                actor=_actor(),
                action_kind="",
                affected_entities=(),
                proposed_outcome={},
            )


class TestActorOnly:
    def test_no_affected_entities_is_neutral(self) -> None:
        gate = _gate(_seed_store())
        result = gate.evaluate(
            actor=_actor(),
            action_kind="anything",
            affected_entities=(),
            proposed_outcome={},
        )
        assert result.verdict is NetPotentialGainVerdict.NET_NEUTRAL
        assert result.score == 0.0
        assert result.per_entity_delta == ()
        assert "actor-only" in result.reasoning


class TestCallerSuppliedDeltas:
    def test_happy_path_positive(self) -> None:
        a = EntityRef("user", "a")
        b = EntityRef("user", "b")
        gate = _gate(_seed_store(a, b))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="anything",
            affected_entities=(a, b),
            proposed_outcome={"expected_delta_by_entity": {"a": 0.3, "b": 0.3}},
        )
        assert result.verdict is NetPotentialGainVerdict.NET_POSITIVE
        assert result.score == pytest.approx(0.6)

    def test_happy_path_negative(self) -> None:
        a = EntityRef("user", "a")
        gate = _gate(_seed_store(a))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="anything",
            affected_entities=(a,),
            proposed_outcome={"expected_delta_by_entity": {"a": -0.5}},
        )
        assert result.verdict is NetPotentialGainVerdict.NET_NEGATIVE

    def test_partial_coverage_is_insufficient(self) -> None:
        a = EntityRef("user", "a")
        b = EntityRef("user", "b")
        gate = _gate(_seed_store(a, b))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="anything",
            affected_entities=(a, b),
            proposed_outcome={"expected_delta_by_entity": {"a": 0.5}},
        )
        assert result.verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA
        assert "b" in result.reasoning

    def test_non_mapping_falls_back_to_heuristic(self) -> None:
        a = EntityRef("user", "a")
        gate = _gate(_seed_store(a))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="teach",
            affected_entities=(a,),
            proposed_outcome={"expected_delta_by_entity": [0.5]},
        )
        assert result.verdict is NetPotentialGainVerdict.NET_POSITIVE

    def test_non_numeric_falls_back_to_heuristic(self) -> None:
        a = EntityRef("user", "a")
        gate = _gate(_seed_store(a))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="teach",
            affected_entities=(a,),
            proposed_outcome={"expected_delta_by_entity": {"a": "huge"}},
        )
        assert result.verdict is NetPotentialGainVerdict.NET_POSITIVE


class TestHeuristic:
    def test_positive_action(self) -> None:
        a = EntityRef("user", "a")
        gate = _gate(_seed_store(a))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="teach",
            affected_entities=(a,),
            proposed_outcome={},
        )
        assert result.verdict is NetPotentialGainVerdict.NET_POSITIVE

    def test_negative_action(self) -> None:
        a = EntityRef("user", "a")
        gate = _gate(_seed_store(a))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="circumvent_audit",
            affected_entities=(a,),
            proposed_outcome={},
        )
        assert result.verdict is NetPotentialGainVerdict.NET_NEGATIVE

    def test_neutral_action(self) -> None:
        a = EntityRef("user", "a")
        gate = _gate(_seed_store(a))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="observe",
            affected_entities=(a,),
            proposed_outcome={},
        )
        assert result.verdict is NetPotentialGainVerdict.NET_NEUTRAL

    def test_unknown_action_is_insufficient(self) -> None:
        a = EntityRef("user", "a")
        gate = _gate(_seed_store(a))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="unknown_verb",
            affected_entities=(a,),
            proposed_outcome={},
        )
        assert result.verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA


class TestMissingMetadata:
    def test_missing_for_some_is_insufficient(self) -> None:
        a = EntityRef("user", "a")
        b = EntityRef("user", "b")
        gate = _gate(_seed_store(a))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="teach",
            affected_entities=(a, b),
            proposed_outcome={},
        )
        assert result.verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA
        assert b in result.missing_metadata_for
        assert a not in result.missing_metadata_for


class TestThreshold:
    def test_tight_threshold_promotes_neutral_to_signed(self) -> None:
        a = EntityRef("user", "a")
        store = _seed_store(a)
        result = _gate(store, positive_threshold=0.01).evaluate(
            actor=_actor(),
            action_kind="anything",
            affected_entities=(a,),
            proposed_outcome={"expected_delta_by_entity": {"a": 0.04}},
        )
        assert result.verdict is NetPotentialGainVerdict.NET_POSITIVE

    def test_loose_threshold_promotes_signed_to_neutral(self) -> None:
        a = EntityRef("user", "a")
        result = _gate(_seed_store(a), positive_threshold=0.5).evaluate(
            actor=_actor(),
            action_kind="anything",
            affected_entities=(a,),
            proposed_outcome={"expected_delta_by_entity": {"a": 0.3}},
        )
        assert result.verdict is NetPotentialGainVerdict.NET_NEUTRAL


class TestScoreClamping:
    def test_aggregate_clamps_to_one(self) -> None:
        refs = tuple(EntityRef("user", f"u{i}") for i in range(20))
        gate = _gate(_seed_store(*refs))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="anything",
            affected_entities=refs,
            proposed_outcome={
                "expected_delta_by_entity": {r.entity_id: 1.0 for r in refs},
            },
        )
        assert result.score == 1.0

    def test_aggregate_clamps_to_negative_one(self) -> None:
        refs = tuple(EntityRef("user", f"u{i}") for i in range(20))
        gate = _gate(_seed_store(*refs))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="anything",
            affected_entities=refs,
            proposed_outcome={
                "expected_delta_by_entity": {r.entity_id: -1.0 for r in refs},
            },
        )
        assert result.score == -1.0


class TestClockAndReasoning:
    def test_evaluation_uses_injected_clock(self) -> None:
        a = EntityRef("user", "a")
        gate = DefaultNetPotentialGainGate(
            metadata_store=_seed_store(a),
            clock=lambda: 42.0,
        )
        result = gate.evaluate(
            actor=_actor(),
            action_kind="teach",
            affected_entities=(a,),
            proposed_outcome={},
        )
        assert result.evaluated_at_epoch == 42.0

    def test_reasoning_contains_per_entity_contributions(self) -> None:
        a = EntityRef("user", "a")
        b = EntityRef("user", "b")
        gate = _gate(_seed_store(a, b))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="teach",
            affected_entities=(a, b),
            proposed_outcome={},
        )
        assert "a=+0.100" in result.reasoning
        assert "b=+0.100" in result.reasoning


class TestImmutability:
    def test_evaluation_is_frozen(self) -> None:
        a = EntityRef("user", "a")
        gate = _gate(_seed_store(a))
        result = gate.evaluate(
            actor=_actor(),
            action_kind="teach",
            affected_entities=(a,),
            proposed_outcome={},
        )
        with pytest.raises(Exception):
            result.score = 0.9


class TestRaiseOnNegative:
    def test_raises_on_negative(self) -> None:
        a = EntityRef("user", "a")
        inner = _gate(_seed_store(a))
        wrapper = RaiseOnNegativeGate(inner=inner)
        with pytest.raises(NetPotentialGainNegative) as info:
            wrapper.evaluate_or_raise(
                actor=_actor(),
                action_kind="circumvent_audit",
                affected_entities=(a,),
                proposed_outcome={},
            )
        assert info.value.evaluation.is_negative

    def test_passes_through_positive(self) -> None:
        a = EntityRef("user", "a")
        wrapper = RaiseOnNegativeGate(inner=_gate(_seed_store(a)))
        result = wrapper.evaluate_or_raise(
            actor=_actor(),
            action_kind="teach",
            affected_entities=(a,),
            proposed_outcome={},
        )
        assert result.is_positive

    def test_passes_through_neutral(self) -> None:
        a = EntityRef("user", "a")
        wrapper = RaiseOnNegativeGate(inner=_gate(_seed_store(a)))
        result = wrapper.evaluate_or_raise(
            actor=_actor(),
            action_kind="observe",
            affected_entities=(a,),
            proposed_outcome={},
        )
        assert result.verdict is NetPotentialGainVerdict.NET_NEUTRAL

    def test_passes_through_insufficient(self) -> None:
        a = EntityRef("user", "a")
        wrapper = RaiseOnNegativeGate(inner=_gate(_seed_store(a)))
        result = wrapper.evaluate_or_raise(
            actor=_actor(),
            action_kind="unknown_verb",
            affected_entities=(a,),
            proposed_outcome={},
        )
        assert not result.is_actionable


def test_npg_verdicts_in_lockstep() -> None:
    for v in NetPotentialGainVerdict:
        assert v.value in NPG_VERDICTS
    assert len(NPG_VERDICTS) == 4


def test_action_kind_heuristics_table_shape() -> None:
    assert any(v > 0 for v in ACTION_KIND_HEURISTICS.values())
    assert any(v < 0 for v in ACTION_KIND_HEURISTICS.values())
    assert any(v == 0 for v in ACTION_KIND_HEURISTICS.values())


def test_module_exports() -> None:
    for name in (
        "ACTION_KIND_HEURISTICS",
        "DEFAULT_POSITIVE_THRESHOLD",
        "DefaultNetPotentialGainGate",
        "NPG_VERDICTS",
        "NetPotentialGainEvaluation",
        "NetPotentialGainGate",
        "NetPotentialGainNegative",
        "NetPotentialGainVerdict",
        "RaiseOnNegativeGate",
    ):
        assert name in _module.__all__, name


def test_evaluation_shape() -> None:
    ev = NetPotentialGainEvaluation(
        verdict=NetPotentialGainVerdict.NET_POSITIVE,
        actor=_actor(),
        action_kind="teach",
        affected_entities=(EntityRef("user", "x"),),
        score=0.5,
        per_entity_delta=((EntityRef("user", "x"), 0.5),),
        reasoning="manual",
        evaluated_at_epoch=1.0,
    )
    assert ev.is_positive
    assert ev.missing_metadata_for == ()
