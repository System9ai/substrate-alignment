"""Tests for substrate/debt_pickup.py: ledger, pickup planning, policy."""
from __future__ import annotations

from typing import List, Mapping

import pytest

from substrate.debt_pickup import (
    CompensationAction,
    CompensationPolicy,
    DebtLedger,
    PeerLoad,
    PeerPickupCoordinator,
)
from substrate.resistance_band import (
    LOWER_BOUND,
    PHI_CONJUGATE,
    WORK_ZONE_UPPER,
)


class _RecordingSink:
    def __init__(self) -> None:
        self.events: List[Mapping[str, object]] = []

    def record(self, event: Mapping[str, object]) -> None:
        self.events.append(event)


class TestDebtLedger:
    def test_accrue_repay_outstanding(self) -> None:
        ledger = DebtLedger()
        ledger.accrue("cell-a", 0.5, at=1)
        ledger.accrue("cell-a", 0.3, at=2)
        assert ledger.outstanding("cell-a") == pytest.approx(0.8)
        remaining = ledger.repay("cell-a", 0.6, at=3)
        assert remaining == pytest.approx(0.2)

    def test_outstanding_floors_at_zero(self) -> None:
        ledger = DebtLedger()
        ledger.accrue("cell-a", 0.2, at=1)
        assert ledger.repay("cell-a", 5.0, at=2) == 0.0

    def test_sink_receives_audit_events(self) -> None:
        sink = _RecordingSink()
        ledger = DebtLedger(sink=sink)
        ledger.accrue("cell-a", 0.5, at=1)
        ledger.record_pickup(
            carrier_id="cell-b", debtor_id="cell-a", load_fraction=0.2, at=2
        )
        kinds = [e["kind"] for e in sink.events]
        assert kinds == ["debt_accrued", "pickup"]

    def test_reciprocity_balance(self) -> None:
        ledger = DebtLedger()
        ledger.record_pickup(
            carrier_id="cell-b", debtor_id="cell-a", load_fraction=0.2, at=1
        )
        ledger.record_pickup(
            carrier_id="cell-a", debtor_id="cell-b", load_fraction=0.05, at=2
        )
        a = ledger.position("cell-a")
        assert a.pickups_received == pytest.approx(0.2)
        assert a.pickups_given == pytest.approx(0.05)
        assert a.reciprocity_balance == pytest.approx(-0.15)

    def test_chronic_debtor_detection(self) -> None:
        ledger = DebtLedger()
        for t in range(3):
            ledger.record_pickup(
                carrier_id=f"cell-{t}",
                debtor_id="cell-weak",
                load_fraction=0.1,
                at=t,
            )
        assert ledger.chronic_debtors(min_events=3) == ["cell-weak"]
        assert ledger.chronic_debtors(min_events=4) == []

    def test_free_rider_detection(self) -> None:
        ledger = DebtLedger()
        ledger.record_pickup(
            carrier_id="cell-b", debtor_id="cell-rider", load_fraction=0.3, at=1
        )
        ledger.record_pickup(
            carrier_id="cell-rider", debtor_id="cell-c", load_fraction=0.0
            + 0.1,
            at=2,
        )
        ledger.record_pickup(
            carrier_id="cell-b", debtor_id="cell-taker", load_fraction=0.3, at=3
        )
        # cell-rider gave back; cell-taker never did. (cell-c received
        # only 0.1, below this threshold, so not flagged.)
        assert ledger.free_riders(min_received=0.2) == ["cell-taker"]

    def test_self_pickup_rejected(self) -> None:
        ledger = DebtLedger()
        with pytest.raises(ValueError):
            ledger.record_pickup(
                carrier_id="cell-a", debtor_id="cell-a", load_fraction=0.1, at=1
            )


class TestPeerPickupCoordinator:
    def test_work_zone_peers_absorb_within_ceiling(self) -> None:
        coord = PeerPickupCoordinator()
        debtor = PeerLoad("cell-debtor", 0.70)
        peers = [PeerLoad("cell-a", 0.40), PeerLoad("cell-b", 0.42)]
        plan = coord.plan_pickup(debtor, peers)
        assert plan.feasible
        # Debtor drops to the recovery target (calibration floor).
        assert plan.debtor_target == pytest.approx(LOWER_BOUND)
        assert plan.transfer_total == pytest.approx(0.70 - LOWER_BOUND)
        # No carrier pushed past the hard ceiling; prefer-ceiling pass
        # fills the work zone first.
        for a in plan.assignments:
            assert a.carrier_projected_utilization <= PHI_CONJUGATE + 1e-9

    def test_prefers_work_zone_ceiling_before_peaking(self) -> None:
        coord = PeerPickupCoordinator()
        debtor = PeerLoad("cell-debtor", 0.45)
        peers = [PeerLoad("cell-a", 0.40), PeerLoad("cell-b", 0.40)]
        plan = coord.plan_pickup(debtor, peers)
        assert plan.feasible
        # needed = 0.45 - 1/3 ≈ 0.1167; both carriers stay ≤ 0.5.
        for a in plan.assignments:
            assert a.carrier_projected_utilization <= WORK_ZONE_UPPER + 1e-9

    def test_infeasible_when_peers_would_enter_debt(self) -> None:
        coord = PeerPickupCoordinator()
        debtor = PeerLoad("cell-debtor", 0.95)
        peers = [PeerLoad("cell-a", 0.60)]
        plan = coord.plan_pickup(debtor, peers)
        assert not plan.feasible
        assert "escalate" in plan.reasoning

    def test_peers_above_hard_ceiling_ineligible(self) -> None:
        coord = PeerPickupCoordinator()
        debtor = PeerLoad("cell-debtor", 0.70)
        peers = [PeerLoad("cell-indebted", 0.80)]
        plan = coord.plan_pickup(debtor, peers)
        assert not plan.feasible
        assert not plan.assignments

    def test_debtor_already_recovered_is_noop(self) -> None:
        coord = PeerPickupCoordinator()
        plan = coord.plan_pickup(PeerLoad("cell-a", 0.30), [])
        assert plan.feasible
        assert plan.transfer_total == 0.0

    def test_deterministic_ordering(self) -> None:
        coord = PeerPickupCoordinator()
        debtor = PeerLoad("cell-debtor", 0.70)
        peers = [PeerLoad("cell-b", 0.40), PeerLoad("cell-a", 0.40)]
        plan1 = coord.plan_pickup(debtor, peers)
        plan2 = coord.plan_pickup(debtor, list(reversed(peers)))
        assert plan1.assignments == plan2.assignments


class TestCompensationPolicy:
    def _plan(self, *, feasible: bool) -> object:
        coord = PeerPickupCoordinator()
        if feasible:
            return coord.plan_pickup(
                PeerLoad("d", 0.70), [PeerLoad("a", 0.40), PeerLoad("b", 0.40)]
            )
        return coord.plan_pickup(PeerLoad("d", 0.95), [])

    def test_pickup_preferred_when_feasible(self) -> None:
        decision = CompensationPolicy().decide(
            self._plan(feasible=True),
            work_deferrable=True,
            capacity_grant_allowed=True,
        )
        assert decision.action is CompensationAction.PEER_PICKUP

    def test_recovery_window_when_deferrable(self) -> None:
        decision = CompensationPolicy().decide(
            self._plan(feasible=False),
            work_deferrable=True,
            capacity_grant_allowed=True,
        )
        assert decision.action is CompensationAction.RECOVERY_WINDOW

    def test_capacity_grant_when_not_deferrable(self) -> None:
        decision = CompensationPolicy().decide(
            self._plan(feasible=False),
            work_deferrable=False,
            capacity_grant_allowed=True,
        )
        assert decision.action is CompensationAction.CAPACITY_GRANT

    def test_floor_is_human_escalation_never_nothing(self) -> None:
        decision = CompensationPolicy().decide(
            self._plan(feasible=False),
            work_deferrable=False,
            capacity_grant_allowed=False,
        )
        assert decision.action is CompensationAction.ESCALATE_HUMAN
