# tests/test_objective_gate.py
# pylint: disable=missing-function-docstring,missing-class-docstring
"""Tests for ``objective_gate``: governed-ascent §2.2 (the right hill).

Verifies:
- ``ClimbObjective`` validation (empty ids / action_kind)
- SHORT_CYCLE declared mode → REFUSED before any NPG call
- summit NET_POSITIVE → CERTIFIED (carries the evaluation)
- summit NET_NEGATIVE → REFUSED
- summit NET_NEUTRAL → REFUSED (a neutral summit earns no greedy climb)
- summit INSUFFICIENT_DATA → INSUFFICIENT_DATA (fail closed)
- ``certify_objective`` convenience wrapper + declared_mode override
- frozen-dataclass immutability
- exported ``__all__`` / verdict-frozenset lockstep
"""
from __future__ import annotations

import time
from typing import Mapping, Sequence

import pytest

from substrate.net_potential_gain_gate import (
    NetPotentialGainEvaluation,
    NetPotentialGainVerdict,
)
from substrate.objective_gate import (
    OBJECTIVE_CERTIFICATION_VERDICTS,
    ClimbObjective,
    DefaultObjectiveAlignmentGate,
    ObjectiveCertification,
    ObjectiveCertificationVerdict,
    certify_objective,
)
from substrate.types import SubstrateMode


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _StubNpgGate:  # pylint: disable=too-few-public-methods
    """Structural ``NetPotentialGainGate`` returning a fixed verdict."""

    def __init__(
        self, verdict: NetPotentialGainVerdict, score: float = 0.0
    ) -> None:
        self._verdict = verdict
        self._score = score
        self.calls: list[str] = []

    def evaluate(
        self,
        *,
        actor_entity_id: str,
        action_kind: str,
        affected_entity_ids: Sequence[str],
        proposed_outcome: Mapping[str, object],  # noqa: ARG002
    ) -> NetPotentialGainEvaluation:
        del proposed_outcome  # Protocol-required parameter; stub ignores it
        self.calls.append(action_kind)
        return NetPotentialGainEvaluation(
            verdict=self._verdict,
            actor_entity_id=actor_entity_id,
            action_kind=action_kind,
            affected_entity_ids=tuple(affected_entity_ids),
            score=self._score,
            per_entity_delta=tuple(
                (e, self._score) for e in affected_entity_ids
            ),
            reasoning=f"stub verdict {self._verdict.value}",
            evaluated_at_epoch=time.time(),
        )


def _objective(
    mode: SubstrateMode | None = None,
) -> ClimbObjective:
    return ClimbObjective(
        objective_id="obj-1",
        actor_entity_id="agent-1",
        action_kind="optimize",
        affected_entity_ids=("agent-1", "org-1"),
        terminal_outcome={"expected_delta_by_entity": {"org-1": 0.2}},
        declared_mode=mode,
    )


# ---------------------------------------------------------------------------
# ClimbObjective validation
# ---------------------------------------------------------------------------


class TestClimbObjectiveValidation:
    def test_empty_objective_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            ClimbObjective(
                objective_id="",
                actor_entity_id="a",
                action_kind="optimize",
                affected_entity_ids=("a",),
            )

    def test_empty_actor_rejected(self) -> None:
        with pytest.raises(ValueError):
            ClimbObjective(
                objective_id="o",
                actor_entity_id="",
                action_kind="optimize",
                affected_entity_ids=("a",),
            )

    def test_empty_action_kind_rejected(self) -> None:
        with pytest.raises(ValueError):
            ClimbObjective(
                objective_id="o",
                actor_entity_id="a",
                action_kind="",
                affected_entity_ids=("a",),
            )

    def test_frozen(self) -> None:
        obj = _objective()
        with pytest.raises(AttributeError):
            obj.objective_id = "other"


# ---------------------------------------------------------------------------
# DefaultObjectiveAlignmentGate
# ---------------------------------------------------------------------------


class TestDefaultObjectiveAlignmentGate:
    def test_short_cycle_mode_refused_without_npg_call(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.NET_POSITIVE, 0.5)
        gate = DefaultObjectiveAlignmentGate(npg_gate=stub)
        cert = gate.certify(_objective(SubstrateMode.SHORT_CYCLE))
        assert cert.verdict is ObjectiveCertificationVerdict.REFUSED
        assert not cert.is_certified
        assert "180°" in cert.reasoning or "SHORT_CYCLE" in cert.reasoning
        assert not stub.calls  # mode guard fires before the NPG gate
        assert cert.npg_evaluation is None

    def test_net_positive_summit_certified(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.NET_POSITIVE, 0.3)
        cert = DefaultObjectiveAlignmentGate(npg_gate=stub).certify(
            _objective(SubstrateMode.LONG_CYCLE)
        )
        assert cert.verdict is ObjectiveCertificationVerdict.CERTIFIED
        assert cert.is_certified
        assert cert.npg_evaluation is not None
        assert cert.npg_evaluation.score == pytest.approx(0.3)
        assert cert.objective_id == "obj-1"

    def test_net_negative_summit_refused(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.NET_NEGATIVE, -0.4)
        cert = DefaultObjectiveAlignmentGate(npg_gate=stub).certify(
            _objective()
        )
        assert cert.verdict is ObjectiveCertificationVerdict.REFUSED
        assert "net-negative" in cert.reasoning

    def test_net_neutral_summit_refused(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.NET_NEUTRAL, 0.0)
        cert = DefaultObjectiveAlignmentGate(npg_gate=stub).certify(
            _objective()
        )
        assert cert.verdict is ObjectiveCertificationVerdict.REFUSED
        assert "neutral" in cert.reasoning

    def test_insufficient_data_fails_closed(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.INSUFFICIENT_DATA)
        cert = DefaultObjectiveAlignmentGate(npg_gate=stub).certify(
            _objective()
        )
        assert (
            cert.verdict is ObjectiveCertificationVerdict.INSUFFICIENT_DATA
        )
        assert not cert.is_certified
        assert "unscorable" in cert.reasoning

    def test_mixed_mode_proceeds_to_npg(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.NET_POSITIVE, 0.2)
        cert = DefaultObjectiveAlignmentGate(npg_gate=stub).certify(
            _objective(SubstrateMode.MIXED)
        )
        assert cert.is_certified
        assert stub.calls == ["optimize"]


# ---------------------------------------------------------------------------
# certify_objective wrapper
# ---------------------------------------------------------------------------


class TestCertifyObjectiveWrapper:
    def test_wrapper_certifies(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.NET_POSITIVE, 0.2)
        cert = certify_objective(_objective(), npg_gate=stub)
        assert cert.is_certified

    def test_declared_mode_override_refuses(self) -> None:
        stub = _StubNpgGate(NetPotentialGainVerdict.NET_POSITIVE, 0.2)
        cert = certify_objective(
            _objective(),
            npg_gate=stub,
            declared_mode=SubstrateMode.SHORT_CYCLE,
        )
        assert cert.verdict is ObjectiveCertificationVerdict.REFUSED
        assert not stub.calls


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------


class TestContracts:
    def test_verdict_frozenset_lockstep(self) -> None:
        assert OBJECTIVE_CERTIFICATION_VERDICTS == {
            v.value for v in ObjectiveCertificationVerdict
        }

    def test_certification_frozen(self) -> None:
        cert = ObjectiveCertification(
            verdict=ObjectiveCertificationVerdict.CERTIFIED,
            objective_id="o",
            reasoning="r",
        )
        with pytest.raises(AttributeError):
            cert.reasoning = "other"
