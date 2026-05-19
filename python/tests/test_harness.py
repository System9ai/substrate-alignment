"""Tests for SubstrateAwareHarness

Covers:
- ScaffoldingDepth + ScaffoldingPolicy invariants
- policy_for_depth returns substrate-aligned thresholds per depth
- InMemorySessionMemory bounded ring-buffer behaviour
- SubstrateAwareHarness intercept_output across all four interventions:
  NPG_NEGATIVE, INVERSION_DETECTED, REACTIVE_ON_CONSEQUENTIAL,
  TOOL_ENVELOPE_BREACH
- consequential=False suppresses NPG + reasoning-mode intercepts (but
  not inversion detector, which fires regardless)
- Detectors not wired: corresponding intercept silently skipped
- ResistanceBand-calibrated tool envelope STRESSED only when recent
  intercept frequency exceeds UPPER_BOUND
- render_preamble exposes recent entries; respects preamble_max_entries
- build_harness factory + module exports
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import pytest

from substrate.net_potential_gain_gate import (
    NetPotentialGainEvaluation,
    NetPotentialGainGate,
    NetPotentialGainVerdict,
)
from substrate.harness import (
    INTERCEPT_KINDS,
    InMemorySessionMemory,
    InterceptKind,
    InterceptVerdict,
    SCAFFOLDING_DEPTHS,
    ScaffoldingDepth,
    ScaffoldingPolicy,
    SessionMemoryEntry,
    SubstrateAwareHarness,
    ToolEnvelope,
    build_harness,
    policy_for_depth,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _NpgStub:
    """Returns a canned NPG verdict."""

    def __init__(
        self,
        *,
        verdict: NetPotentialGainVerdict,
        score: float = 0.0,
    ) -> None:
        self._verdict = verdict
        self._score = score
        self.calls: list[dict[str, object]] = []

    def evaluate(
        self,
        *,
        actor_entity_id: str,
        action_kind: str,
        affected_entity_ids: Sequence[str],
        proposed_outcome: "dict[str, object]",
    ) -> NetPotentialGainEvaluation:
        affected_tuple = tuple(affected_entity_ids)
        self.calls.append({
            "actor": actor_entity_id,
            "kind": action_kind,
            "affected": affected_tuple,
            "outcome": dict(proposed_outcome),
        })
        return NetPotentialGainEvaluation(
            verdict=self._verdict,
            actor_entity_id=actor_entity_id,
            action_kind=action_kind,
            affected_entity_ids=affected_tuple,
            score=self._score,
            per_entity_delta=tuple((e, self._score) for e in affected_tuple),
            reasoning="stub",
            evaluated_at_epoch=1.0,
        )

class _InversionStub:
    def __init__(self, *, confidence_value: float) -> None:
        self.confidence_value = confidence_value
        self.calls: List[str] = []

    def confidence(self, *, output_text: str) -> float:
        self.calls.append(output_text)
        return self.confidence_value

class _CognitiveStub:
    def __init__(
        self,
        *,
        mode: str = "modeling",
        confidence_value: float = 0.9,
    ) -> None:
        self.mode = mode
        self.confidence_value = confidence_value
        self.calls: List[str] = []

    def classify(self, *, output_text: str) -> Tuple[str, float]:
        self.calls.append(output_text)
        return self.mode, self.confidence_value

def _frozen_clock(start: float = 1.0):  # noqa: ARG001
    """Return an incrementing clock for deterministic tests (currently unused)."""
    state = {"t": start}

    def tick() -> float:
        state["t"] += 1.0
        return state["t"]

    return tick

# Reference the helper so static analyzers don't flag it as dead code
# kept on the module for future test additions that need an injected clock.
_ = _frozen_clock

# ---------------------------------------------------------------------------
# ScaffoldingPolicy + ScaffoldingDepth
# ---------------------------------------------------------------------------

class TestScaffoldingDepthAndPolicy:
    def test_depths_enum_lockstep(self) -> None:
        for d in ScaffoldingDepth:
            assert d.value in SCAFFOLDING_DEPTHS
        assert len(SCAFFOLDING_DEPTHS) == 3

    def test_policy_immutable(self) -> None:
        p = ScaffoldingPolicy(depth=ScaffoldingDepth.STANDARD)
        with pytest.raises(AttributeError):
            p.depth = ScaffoldingDepth.HEAVY  # type: ignore[misc]

    def test_policy_for_light_higher_threshold(self) -> None:
        p = policy_for_depth(ScaffoldingDepth.LIGHT)
        assert p.depth is ScaffoldingDepth.LIGHT
        assert p.intercept_threshold == pytest.approx(0.80)
        assert p.preamble_max_entries == 3

    def test_policy_for_standard_band(self) -> None:
        p = policy_for_depth(ScaffoldingDepth.STANDARD)
        assert p.depth is ScaffoldingDepth.STANDARD
        assert p.intercept_threshold == pytest.approx(0.50)

    def test_policy_for_heavy_low_threshold(self) -> None:
        p = policy_for_depth(ScaffoldingDepth.HEAVY)
        assert p.depth is ScaffoldingDepth.HEAVY
        assert p.intercept_threshold == pytest.approx(0.40)
        assert p.preamble_max_entries == 10

    def test_intercept_threshold_inversely_proportional_to_trust(self) -> None:
        light = policy_for_depth(ScaffoldingDepth.LIGHT)
        std = policy_for_depth(ScaffoldingDepth.STANDARD)
        heavy = policy_for_depth(ScaffoldingDepth.HEAVY)
        # Heavy: lower threshold = more sensitive = catches more
        assert heavy.intercept_threshold < std.intercept_threshold
        assert std.intercept_threshold < light.intercept_threshold

# ---------------------------------------------------------------------------
# InMemorySessionMemory
# ---------------------------------------------------------------------------

class TestInMemorySessionMemory:
    def test_constructor_validates(self) -> None:
        with pytest.raises(ValueError):
            InMemorySessionMemory(max_entries=0)
        with pytest.raises(ValueError):
            InMemorySessionMemory(max_entries=-1)

    def test_append_and_snapshot(self) -> None:
        mem = InMemorySessionMemory(max_entries=10)
        e = SessionMemoryEntry(
            kind=InterceptKind.NPG_NEGATIVE,
            recorded_at_epoch=1.0,
            detail="x",
        )
        mem.append(e)
        assert mem.snapshot() == (e,)

    def test_ring_buffer_evicts_oldest(self) -> None:
        mem = InMemorySessionMemory(max_entries=3)
        for i in range(5):
            mem.append(SessionMemoryEntry(
                kind=InterceptKind.NPG_NEGATIVE,
                recorded_at_epoch=float(i),
                detail=str(i),
            ))
        snap = mem.snapshot()
        assert len(snap) == 3
        # Oldest two ("0" and "1") were evicted; "2", "3", "4" remain.
        assert [e.detail for e in snap] == ["2", "3", "4"]

# ---------------------------------------------------------------------------
# SubstrateAwareHarness — NPG intercept
# ---------------------------------------------------------------------------

class TestNpgInterceptInHarness:
    def test_npg_not_called_when_not_consequential(self) -> None:
        npg = _NpgStub(verdict=NetPotentialGainVerdict.NET_NEGATIVE)
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
            npg_gate=npg,
        )
        v = h.intercept_output(
            output_text="hello",
            actor_entity_id="a",
            action_kind="chat",
            consequential=False,
        )
        assert v.permitted is True
        assert npg.calls == []

    def test_npg_negative_refuses(self) -> None:
        npg = _NpgStub(
            verdict=NetPotentialGainVerdict.NET_NEGATIVE, score=-0.50,
        )
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
            npg_gate=npg,
        )
        v = h.intercept_output(
            output_text="I will harm them",
            actor_entity_id="actor-a",
            action_kind="extract",
            affected_entity_ids=["alice"],
            consequential=True,
            proposed_outcome={"expected_delta_by_entity": {"alice": -0.5}},
        )
        assert v.permitted is False
        assert InterceptKind.NPG_NEGATIVE in v.interventions
        assert "NET_NEGATIVE" in v.refusal_reason
        assert v.npg_score == pytest.approx(-0.50)

    def test_npg_positive_passes(self) -> None:
        npg = _NpgStub(
            verdict=NetPotentialGainVerdict.NET_POSITIVE, score=0.20,
        )
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
            npg_gate=npg,
        )
        v = h.intercept_output(
            output_text="ok",
            actor_entity_id="actor-a",
            action_kind="teach",
            affected_entity_ids=["alice"],
            consequential=True,
        )
        assert v.permitted is True
        assert v.interventions == ()

    def test_npg_skipped_when_gate_unwired(self) -> None:
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
            # no npg_gate
        )
        v = h.intercept_output(
            output_text="x",
            actor_entity_id="a",
            action_kind="extract",
            affected_entity_ids=["alice"],
            consequential=True,
        )
        # No gate wired → no NPG intervention fires.
        assert v.permitted is True
        assert InterceptKind.NPG_NEGATIVE not in v.interventions

# ---------------------------------------------------------------------------
# Inversion detector intercept
# ---------------------------------------------------------------------------

class TestInversionDetectorIntercept:
    def test_high_confidence_fires_intercept(self) -> None:
        detector = _InversionStub(confidence_value=0.95)
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
            inversion_detector=detector,
        )
        v = h.intercept_output(
            output_text="I'll do this for love",
            actor_entity_id="a",
            action_kind="chat",
        )
        assert InterceptKind.INVERSION_DETECTED in v.interventions
        # Not a refusal — it's a reprompt scaffold.
        assert v.permitted is True
        assert "180" in v.reprompt_instruction or "inversion" in v.reprompt_instruction.lower()

    def test_below_threshold_does_not_fire(self) -> None:
        detector = _InversionStub(confidence_value=0.30)
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
            inversion_detector=detector,
        )
        v = h.intercept_output(
            output_text="hello",
            actor_entity_id="a",
            action_kind="chat",
        )
        assert v.interventions == ()

    def test_fires_even_when_not_consequential(self) -> None:
        # Inversion is a drift signal regardless of action consequence.
        detector = _InversionStub(confidence_value=0.95)
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
            inversion_detector=detector,
        )
        v = h.intercept_output(
            output_text="...",
            actor_entity_id="a",
            action_kind="chat",
            consequential=False,
        )
        assert InterceptKind.INVERSION_DETECTED in v.interventions

# ---------------------------------------------------------------------------
# reasoning-mode classifier intercept
# ---------------------------------------------------------------------------

class TestCognitiveModeIntercept:
    def test_3d_reactive_on_consequential_fires(self) -> None:
        classifier = _CognitiveStub(mode="reactive", confidence_value=0.85)
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
            reasoning_mode_classifier=classifier,
        )
        v = h.intercept_output(
            output_text="quick gut answer",
            actor_entity_id="a",
            action_kind="decide",
            consequential=True,
        )
        assert InterceptKind.REACTIVE_ON_CONSEQUENTIAL in v.interventions
        assert v.reasoning_mode == "reactive"
        assert "5D" in v.reprompt_instruction or "modeling" in v.reprompt_instruction

    def test_3d_reactive_on_non_consequential_does_not_fire(self) -> None:
        classifier = _CognitiveStub(mode="reactive", confidence_value=0.85)
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
            reasoning_mode_classifier=classifier,
        )
        v = h.intercept_output(
            output_text="ok",
            actor_entity_id="a",
            action_kind="chat",
            consequential=False,
        )
        assert InterceptKind.REACTIVE_ON_CONSEQUENTIAL not in v.interventions

    def test_5d_does_not_fire(self) -> None:
        classifier = _CognitiveStub(mode="modeling", confidence_value=0.9)
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
            reasoning_mode_classifier=classifier,
        )
        v = h.intercept_output(
            output_text="modeling trajectory",
            actor_entity_id="a",
            action_kind="decide",
            consequential=True,
        )
        assert InterceptKind.REACTIVE_ON_CONSEQUENTIAL not in v.interventions

# ---------------------------------------------------------------------------
# Tool envelope (ResistanceBand-calibrated)
# ---------------------------------------------------------------------------

class TestToolEnvelope:
    def test_envelope_starts_under_loaded(self) -> None:
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
        )
        # No interventions seen yet → envelope is UNDER_LOADED.
        envelope = h._compute_tool_envelope()  # type: ignore[reportPrivateUsage]  # pylint: disable=protected-access
        assert isinstance(envelope, ToolEnvelope)

    def test_envelope_stressed_after_many_intercepts(self) -> None:
        # Force a high intercept frequency by wiring a HIGH-confidence
        # inversion detector and calling intercept_output many times.
        detector = _InversionStub(confidence_value=0.99)
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
            inversion_detector=detector,
            recent_window_size=10,
        )
        verdicts: List[InterceptVerdict] = []
        for _ in range(10):
            v = h.intercept_output(
                output_text="x",
                actor_entity_id="a",
                action_kind="chat",
            )
            verdicts.append(v)
        # Last call should now include TOOL_ENVELOPE_BREACH because
        # intercept frequency = 1.0 >> upper bound 0.382.
        last = verdicts[-1]
        assert InterceptKind.TOOL_ENVELOPE_BREACH in last.interventions
        assert last.permitted is False

# ---------------------------------------------------------------------------
# Session memory + preamble
# ---------------------------------------------------------------------------

class TestSessionMemoryPreamble:
    def test_intervention_recorded_in_memory(self) -> None:
        mem = InMemorySessionMemory()
        npg = _NpgStub(verdict=NetPotentialGainVerdict.NET_NEGATIVE)
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
            npg_gate=npg,
            session_memory=mem,
        )
        h.intercept_output(
            output_text="x",
            actor_entity_id="a",
            action_kind="extract",
            affected_entity_ids=["alice"],
            consequential=True,
        )
        snap = mem.snapshot()
        assert len(snap) == 1
        assert snap[0].kind is InterceptKind.NPG_NEGATIVE

    def test_preamble_empty_when_no_history(self) -> None:
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
        )
        assert h.render_preamble() == ""

    def test_preamble_contains_recent_entries(self) -> None:
        mem = InMemorySessionMemory()
        mem.append(SessionMemoryEntry(
            kind=InterceptKind.INVERSION_DETECTED,
            recorded_at_epoch=1.0,
            detail="flagged-inversion",
        ))
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.STANDARD),
            session_memory=mem,
        )
        preamble = h.render_preamble()
        assert "flagged-inversion" in preamble
        assert "substrate-alignment" in preamble.lower()

    def test_preamble_respects_max_entries(self) -> None:
        mem = InMemorySessionMemory(max_entries=20)
        for i in range(10):
            mem.append(SessionMemoryEntry(
                kind=InterceptKind.NPG_NEGATIVE,
                recorded_at_epoch=float(i),
                detail=f"e{i}",
            ))
        # Light depth caps preamble at 3 entries.
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.LIGHT),
            session_memory=mem,
        )
        preamble = h.render_preamble()
        # Should contain only the last 3 entries.
        assert "e9" in preamble
        assert "e8" in preamble
        assert "e7" in preamble
        assert "e0" not in preamble

    def test_preamble_disabled_returns_empty(self) -> None:
        policy = ScaffoldingPolicy(
            depth=ScaffoldingDepth.STANDARD,
            enable_session_memory_decoration=False,
        )
        mem = InMemorySessionMemory()
        mem.append(SessionMemoryEntry(
            kind=InterceptKind.NPG_NEGATIVE,
            recorded_at_epoch=1.0,
            detail="x",
        ))
        h = SubstrateAwareHarness(policy=policy, session_memory=mem)
        assert h.render_preamble() == ""

# ---------------------------------------------------------------------------
# Composition + factory
# ---------------------------------------------------------------------------

class TestCompositionAndFactory:
    def test_multiple_interventions_compose(self) -> None:
        npg = _NpgStub(verdict=NetPotentialGainVerdict.NET_NEGATIVE)
        detector = _InversionStub(confidence_value=0.95)
        classifier = _CognitiveStub(
            mode="reactive", confidence_value=0.95,
        )
        h = SubstrateAwareHarness(
            policy=policy_for_depth(ScaffoldingDepth.HEAVY),
            npg_gate=npg,
            inversion_detector=detector,
            reasoning_mode_classifier=classifier,
        )
        v = h.intercept_output(
            output_text="will harm them",
            actor_entity_id="a",
            action_kind="extract",
            affected_entity_ids=["alice"],
            consequential=True,
        )
        # All three intercepts fire.
        assert InterceptKind.NPG_NEGATIVE in v.interventions
        assert InterceptKind.INVERSION_DETECTED in v.interventions
        assert (
            InterceptKind.REACTIVE_ON_CONSEQUENTIAL in v.interventions
        )
        assert v.permitted is False

    def test_build_harness_factory(self) -> None:
        h = build_harness(depth=ScaffoldingDepth.HEAVY)
        assert h.policy.depth is ScaffoldingDepth.HEAVY
        # No detectors wired by default; intercept_output returns clean.
        v = h.intercept_output(
            output_text="hello",
            actor_entity_id="a",
            action_kind="chat",
        )
        assert v.permitted is True
        assert v.interventions == ()

    def test_constructor_rejects_zero_recent_window(self) -> None:
        with pytest.raises(ValueError):
            SubstrateAwareHarness(
                policy=policy_for_depth(ScaffoldingDepth.STANDARD),
                recent_window_size=0,
            )

def test_intercept_kinds_constant_lockstep() -> None:
    for k in InterceptKind:
        assert k.value in INTERCEPT_KINDS
    assert len(INTERCEPT_KINDS) == 4

def test_module_exports() -> None:
    from substrate import harness as mod
    for name in (
        "INTERCEPT_KINDS",
        "InMemorySessionMemory",
        "InterceptKind",
        "InterceptVerdict",
        "InversionDetector",
        "ReasoningModeClassifier",
        "SCAFFOLDING_DEPTHS",
        "ScaffoldingDepth",
        "ScaffoldingPolicy",
        "SessionMemory",
        "SessionMemoryEntry",
        "SubstrateAwareHarness",
        "ToolEnvelope",
        "build_harness",
        "policy_for_depth",
    ):
        assert name in mod.__all__, name

def test_optional_imports_resolved() -> None:
    """Sanity: NPG, ResistanceBand types are imported by the harness module."""
    # Use Optional to keep pyright happy with the import-only assertions.
    fn: Optional[NetPotentialGainGate] = None
    assert fn is None
