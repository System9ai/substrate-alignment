"""Tests for ExecutiveFunction.decide(): the join over NPG + load + cause."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import pytest

from substrate.executive.band import BandProfile
from substrate.executive.cause import (
    Cause,
    HallmarkReport,
)
from substrate.executive.executive_function import (
    Action,
    Disposition,
    ExecutiveFunction,
)
from substrate.executive.quantities import (
    GrowthNotADecisionBand,
    Quantity,
    ResourceKind,
)
from substrate.executive.scale import ExecutiveScale
from substrate.executive.temporal import LoadTrend
from substrate.executive.utilization_source import (
    CallableUtilizationSource,
)
from substrate.net_potential_gain_gate import (
    NetPotentialGainEvaluation,
    NetPotentialGainGate,
    NetPotentialGainVerdict,
)


# ── fakes for deterministic control of each axis ───────────────────────────


@dataclass
class _FakeTracker:  # pylint: disable=too-few-public-methods
    fixed: LoadTrend

    def observe(self, u: float, *, work_pending: bool = False) -> None:
        del u, work_pending

    def trend(self, *, profile: BandProfile) -> LoadTrend:
        del profile
        return self.fixed


@dataclass
class _FakeGate:  # pylint: disable=too-few-public-methods
    verdict: NetPotentialGainVerdict

    def evaluate(  # pylint: disable=unused-argument
        self, *, actor_entity_id: str, action_kind: str,
        affected_entity_ids: Sequence[str], proposed_outcome: Mapping[str, object],
    ) -> NetPotentialGainEvaluation:
        return NetPotentialGainEvaluation(
            verdict=self.verdict, actor_entity_id=actor_entity_id,
            action_kind=action_kind, affected_entity_ids=tuple(affected_entity_ids),
            score=0.0, per_entity_delta=(), reasoning="fake",
            evaluated_at_epoch=1.0,
        )


@dataclass
class _FakeHallmarks:  # pylint: disable=too-few-public-methods
    report: HallmarkReport

    def hallmarks(self, *, actor_entity_id: str, scale: ExecutiveScale) -> HallmarkReport:
        del actor_entity_id, scale
        return self.report


def _util(value: float) -> CallableUtilizationSource:
    return CallableUtilizationSource(lambda q, s, r, u: value)


def _decide(
    ef: ExecutiveFunction, *, u: float = 0.45,
    quantity: Quantity = Quantity.WORK,
):
    return ef.decide(
        actor_entity_id="agent:1", action_kind="test",
        quantity=quantity, scale=ExecutiveScale.CELL,
        utilization=_util(u), affected_entity_ids=["e1"],
        resource=ResourceKind.CPU,
    )


# ── the gate Protocol surface ──────────────────────────────────────────────


def test_implements_npg_gate_protocol() -> None:
    # Structural conformance: an ExecutiveFunction is usable wherever a
    # NetPotentialGainGate is expected (the Protocol is not @runtime_checkable,
    # so verify by use rather than isinstance).
    gate: NetPotentialGainGate = ExecutiveFunction(
        gate_chain=_FakeGate(NetPotentialGainVerdict.NET_POSITIVE)
    )
    ev = gate.evaluate(
        actor_entity_id="a", action_kind="k",
        affected_entity_ids=["e"], proposed_outcome={},
    )
    assert ev.verdict is NetPotentialGainVerdict.NET_POSITIVE


def test_evaluate_delegates() -> None:
    ef = ExecutiveFunction(gate_chain=_FakeGate(NetPotentialGainVerdict.NET_POSITIVE))
    ev = ef.evaluate(
        actor_entity_id="a", action_kind="k",
        affected_entity_ids=["e"], proposed_outcome={},
    )
    assert ev.verdict is NetPotentialGainVerdict.NET_POSITIVE


def test_evaluate_without_gate_raises() -> None:
    with pytest.raises(RuntimeError, match="gate_chain"):
        ExecutiveFunction().evaluate(
            actor_entity_id="a", action_kind="k",
            affected_entity_ids=[], proposed_outcome={},
        )


# ── decide(): GROWTH + the in-band happy path ──────────────────────────────


def test_growth_rejected_at_entry() -> None:
    ef = ExecutiveFunction()
    with pytest.raises(GrowthNotADecisionBand):
        _decide(ef, quantity=Quantity.GROWTH)


def test_in_band_npg_ok_proceeds() -> None:
    ef = ExecutiveFunction(
        gate_chain=_FakeGate(NetPotentialGainVerdict.NET_POSITIVE),
        tracker=_FakeTracker(LoadTrend.NOMINAL),
    )
    v = _decide(ef, u=0.45)  # in the WORK band (0.382..0.5)
    assert v.disposition is Disposition.PROCEED
    assert v.in_band is True
    assert v.actions == frozenset()


def test_owning_entity_defaults_to_actor() -> None:
    ef = ExecutiveFunction(tracker=_FakeTracker(LoadTrend.NOMINAL))
    v = _decide(ef)
    assert v.owning_entity_id == "agent:1"


# ── decide(): the disposition table (each branch) ──────────────────────────


def test_npg_negative_refuses() -> None:
    ef = ExecutiveFunction(
        gate_chain=_FakeGate(NetPotentialGainVerdict.NET_NEGATIVE),
        tracker=_FakeTracker(LoadTrend.NOMINAL),
    )
    v = _decide(ef)
    assert v.disposition is Disposition.REFUSE


def test_malice_refuses_with_siem() -> None:
    ef = ExecutiveFunction(
        gate_chain=_FakeGate(NetPotentialGainVerdict.NET_POSITIVE),
        tracker=_FakeTracker(LoadTrend.NOMINAL),
        hallmarks=_FakeHallmarks(HallmarkReport(evading_limits=True)),
    )
    v = _decide(ef)
    assert v.disposition is Disposition.REFUSE
    assert Action.SIEM in v.actions
    assert v.cause is Cause.MALICE


def test_debt_accruing_sheds_and_compensates() -> None:
    ef = ExecutiveFunction(
        gate_chain=_FakeGate(NetPotentialGainVerdict.NET_POSITIVE),
        tracker=_FakeTracker(LoadTrend.DEBT_ACCRUING),
    )
    v = _decide(ef, u=0.8)
    assert v.disposition is Disposition.SHED_AND_COMPENSATE
    assert Action.COMPENSATE in v.actions


def test_sustained_strain_defers() -> None:
    ef = ExecutiveFunction(
        gate_chain=_FakeGate(NetPotentialGainVerdict.NET_POSITIVE),
        tracker=_FakeTracker(LoadTrend.SUSTAINED_STRAIN),
    )
    v = _decide(ef, u=0.55)
    assert v.disposition is Disposition.DEFER


def test_spike_proceeds_with_warn() -> None:
    ef = ExecutiveFunction(
        gate_chain=_FakeGate(NetPotentialGainVerdict.NET_POSITIVE),
        tracker=_FakeTracker(LoadTrend.SPIKE),
    )
    v = _decide(ef, u=0.55)
    assert v.disposition is Disposition.PROCEED
    assert Action.WARN in v.actions


def test_insufficient_npg_is_accident_hold() -> None:
    ef = ExecutiveFunction(
        gate_chain=_FakeGate(NetPotentialGainVerdict.INSUFFICIENT_DATA),
        tracker=_FakeTracker(LoadTrend.NOMINAL),
    )
    v = _decide(ef)
    assert v.cause is Cause.ACCIDENT
    assert v.disposition is Disposition.HOLD


def test_out_of_band_unclassified_holds() -> None:
    # IDLE utilization, NOMINAL trend, npg ok, not in the WORK band → terminal.
    ef = ExecutiveFunction(
        gate_chain=_FakeGate(NetPotentialGainVerdict.NET_POSITIVE),
        tracker=_FakeTracker(LoadTrend.NOMINAL),
    )
    v = _decide(ef, u=0.2)
    assert v.in_band is False
    assert v.disposition is Disposition.HOLD
    assert v.audit_code == "executive_unclassified"


# ── the monotonicity invariant (the safety guarantee) ──────────────────────


@pytest.mark.parametrize("trend", list(LoadTrend))
def test_npg_negative_always_refuses_regardless_of_band(trend: LoadTrend) -> None:
    # The load axis can NEVER lift an NPG refusal; REFUSE on every trend.
    ef = ExecutiveFunction(
        gate_chain=_FakeGate(NetPotentialGainVerdict.NET_NEGATIVE),
        tracker=_FakeTracker(trend),
    )
    for u in (0.2, 0.45, 0.55, 0.8):
        assert _decide(ef, u=u).disposition is Disposition.REFUSE


def test_no_gate_chain_runs_band_only() -> None:
    # With no NPG axis, decide() still produces a load/cause verdict.
    ef = ExecutiveFunction(tracker=_FakeTracker(LoadTrend.NOMINAL))
    v = _decide(ef, u=0.45)
    assert v.npg is None
    assert v.disposition is Disposition.PROCEED
