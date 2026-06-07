"""Debt as a transferable obligation — ledger, pickup, reciprocity (layered zone model §2.4).

The founder's contract: sustained operation above the φ-conjugate debt
line creates a DEBT that the system must repay — "others pick up." The
work zone (0.38–0.50) IS the absorption capacity that makes transfer
possible (the same math as N+1 failover). Justice is reciprocity over
time: the ledger records who carried whom; chronic-debtor and
free-rider asymmetries surface as drift-signal feeds rather than being
silently absorbed.

Three primitives, all pure logic (no DAO, no clock; persistence rides
the pluggable :class:`LedgerSink`, audit-chained where the substrate
audit plane exists so peers can VERIFY the ledger — condition #2 is
symmetric, not write-only):

- :class:`DebtLedger` — accrual/repayment + pickup reciprocity records.
- :class:`PeerPickupCoordinator` — plans load transfers: debtor drops
  to actual rest (the pleasure zone), no carrier pushed past PEAKING,
  preferring carriers kept at or under the work-zone ceiling.
- :class:`CompensationPolicy` — ordered action selection:
  PEER_PICKUP → RECOVERY_WINDOW → CAPACITY_GRANT → ESCALATE_HUMAN.
  Refusing to compensate is itself a drift signal.

Per ``docs/concepts/resistance-band.md`` § "The layered zone model".
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Final, List, Mapping, Optional, Protocol, Sequence, Tuple

from substrate.resistance_band import (
    LOWER_BOUND,
    PHI_CONJUGATE,
    WORK_ZONE_UPPER,
    validate_utilization,
)


class CompensationAction(str, Enum):
    """Ordered compensation vocabulary (strongest-preference first)."""

    PEER_PICKUP = "peer_pickup"
    RECOVERY_WINDOW = "recovery_window"
    CAPACITY_GRANT = "capacity_grant"
    ESCALATE_HUMAN = "escalate_human"


#: All actions, lockstep with the enum.
COMPENSATION_ACTIONS: Final[frozenset[str]] = frozenset(
    a.value for a in CompensationAction
)


class LedgerSink(Protocol):  # pylint: disable=too-few-public-methods
    """Pluggable persistence/audit seam for ledger events.

    Production wires this to the substrate audit plane (hash-chained,
    peer-verifiable); tests use in-memory recorders. The ledger calls
    ``record`` with a flat, canonicalisable mapping.
    """

    def record(self, event: Mapping[str, object]) -> None:
        """Persist one ledger event."""


@dataclass(frozen=True, slots=True)
class DebtPosition:
    """One entity's current standing in the ledger."""

    entity_id: str
    outstanding_units: float
    lifetime_accrued: float
    lifetime_repaid: float
    pickups_given: float
    pickups_received: float

    @property
    def reciprocity_balance(self) -> float:
        """Given minus received — negative = net carried by others."""
        return self.pickups_given - self.pickups_received


class DebtLedger:
    """Per-entity debt accrual, repayment, and pickup reciprocity.

    All mutations take a caller-supplied ``at`` timestamp (no clock
    reads) and emit a sink event when a sink is configured.
    """

    def __init__(self, *, sink: Optional[LedgerSink] = None) -> None:
        self._sink = sink
        self._accrued: Dict[str, float] = {}
        self._repaid: Dict[str, float] = {}
        self._given: Dict[str, float] = {}
        self._received: Dict[str, float] = {}
        self._carry_events: List[Tuple[str, str, float, int]] = []

    @staticmethod
    def _validate_units(units: float) -> None:
        if not math.isfinite(units) or units <= 0.0:
            raise ValueError(
                f"units must be a finite float > 0; got {units!r}"
            )

    def _emit(self, event: Mapping[str, object]) -> None:
        if self._sink is not None:
            self._sink.record(event)

    def accrue(self, entity_id: str, units: float, *, at: int) -> None:
        """Record debt accrual for ``entity_id``."""
        if not entity_id:
            raise ValueError("entity_id must be non-empty")
        self._validate_units(units)
        self._accrued[entity_id] = self._accrued.get(entity_id, 0.0) + units
        self._emit(
            {
                "kind": "debt_accrued",
                "entity_id": entity_id,
                "units": units,
                "at": at,
            }
        )

    def repay(self, entity_id: str, units: float, *, at: int) -> float:
        """Record repayment; returns remaining outstanding units."""
        if not entity_id:
            raise ValueError("entity_id must be non-empty")
        self._validate_units(units)
        self._repaid[entity_id] = self._repaid.get(entity_id, 0.0) + units
        self._emit(
            {
                "kind": "debt_repaid",
                "entity_id": entity_id,
                "units": units,
                "at": at,
            }
        )
        return self.outstanding(entity_id)

    def record_pickup(
        self,
        *,
        carrier_id: str,
        debtor_id: str,
        load_fraction: float,
        at: int,
    ) -> None:
        """Record that ``carrier_id`` picked up load for ``debtor_id``."""
        if not carrier_id or not debtor_id:
            raise ValueError("carrier_id and debtor_id must be non-empty")
        if carrier_id == debtor_id:
            raise ValueError("an entity cannot pick up for itself")
        self._validate_units(load_fraction)
        self._given[carrier_id] = (
            self._given.get(carrier_id, 0.0) + load_fraction
        )
        self._received[debtor_id] = (
            self._received.get(debtor_id, 0.0) + load_fraction
        )
        self._carry_events.append((carrier_id, debtor_id, load_fraction, at))
        self._emit(
            {
                "kind": "pickup",
                "carrier_id": carrier_id,
                "debtor_id": debtor_id,
                "load_fraction": load_fraction,
                "at": at,
            }
        )

    def outstanding(self, entity_id: str) -> float:
        """Outstanding debt units (accrued − repaid, floored at zero)."""
        return max(
            0.0,
            self._accrued.get(entity_id, 0.0)
            - self._repaid.get(entity_id, 0.0),
        )

    def position(self, entity_id: str) -> DebtPosition:
        """Full standing for one entity."""
        return DebtPosition(
            entity_id=entity_id,
            outstanding_units=self.outstanding(entity_id),
            lifetime_accrued=self._accrued.get(entity_id, 0.0),
            lifetime_repaid=self._repaid.get(entity_id, 0.0),
            pickups_given=self._given.get(entity_id, 0.0),
            pickups_received=self._received.get(entity_id, 0.0),
        )

    def chronic_debtors(self, *, min_events: int = 3) -> List[str]:
        """Entities repeatedly carried — structural under-capacity.

        Drift-signal feed: propose grow-mode / rebalancing for these,
        not endless pickup.
        """
        counts: Dict[str, int] = {}
        for _, debtor_id, _, _ in self._carry_events:
            counts[debtor_id] = counts.get(debtor_id, 0) + 1
        return sorted(d for d, n in counts.items() if n >= min_events)

    def free_riders(self, *, min_received: float = 0.1) -> List[str]:
        """Entities that take pickup but never give — NPG inversion feed."""
        riders = []
        for entity_id, received in self._received.items():
            if received >= min_received and self._given.get(
                entity_id, 0.0
            ) <= 0.0:
                riders.append(entity_id)
        return sorted(riders)


@dataclass(frozen=True, slots=True)
class PeerLoad:
    """One peer's current utilisation in the shared bounded context."""

    entity_id: str
    utilization: float

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        validate_utilization(self.utilization)


@dataclass(frozen=True, slots=True)
class PickupAssignment:
    """One carrier's share of the transferred load."""

    carrier_id: str
    transfer_fraction: float
    carrier_projected_utilization: float


@dataclass(frozen=True, slots=True)
class PickupPlan:
    """Frozen result of pickup planning.

    ``feasible=False`` means no peer set satisfies the constraints —
    the policy escalates (capacity grant / human) rather than pushing
    a carrier into debt: pickup that creates new debt is not
    compensation, it is contagion.
    """

    debtor_id: str
    debtor_target: float
    transfer_total: float
    assignments: Tuple[PickupAssignment, ...]
    feasible: bool
    reasoning: str


class PeerPickupCoordinator:  # pylint: disable=too-few-public-methods
    """Plans load transfers from a debtor to work-zone peers.

    Pure planner: emits a :class:`PickupPlan`; executing transfers and
    recording them on the :class:`DebtLedger` is the caller's job.
    Real placement topology (shard affinity, erasure sets) may
    constrain which peers can actually receive a given load — callers
    pre-filter ``peers`` accordingly; uniform transferability is the
    default assumption, not a guarantee.
    """

    def __init__(
        self,
        *,
        recovery_target: float = LOWER_BOUND,
        prefer_ceiling: float = WORK_ZONE_UPPER,
        hard_ceiling: float = PHI_CONJUGATE,
    ) -> None:
        if not 0.0 <= recovery_target < prefer_ceiling <= hard_ceiling <= 1.0:
            raise ValueError(
                "must satisfy 0 <= recovery_target < prefer_ceiling <= "
                f"hard_ceiling <= 1; got {recovery_target!r}, "
                f"{prefer_ceiling!r}, {hard_ceiling!r}"
            )
        self._recovery_target = recovery_target
        self._prefer_ceiling = prefer_ceiling
        self._hard_ceiling = hard_ceiling

    def _fill(
        self,
        *,
        eligible: Sequence[PeerLoad],
        loads: Dict[str, float],
        assignments: Dict[str, float],
        needed: float,
    ) -> float:
        """Two-pass greedy fill; returns the untransferable remainder."""
        remaining = needed
        for ceiling in (self._prefer_ceiling, self._hard_ceiling):
            if remaining <= 1e-12:
                break
            for peer in eligible:
                if remaining <= 1e-12:
                    break
                headroom = ceiling - loads[peer.entity_id]
                if headroom <= 0.0:
                    continue
                take = min(headroom, remaining)
                loads[peer.entity_id] += take
                assignments[peer.entity_id] = (
                    assignments.get(peer.entity_id, 0.0) + take
                )
                remaining -= take
        return remaining

    def plan_pickup(
        self,
        debtor: PeerLoad,
        peers: Sequence[PeerLoad],
    ) -> PickupPlan:
        """Plan transfers so the debtor drops to the recovery target.

        Two passes: fill carriers to the work-zone ceiling first
        (preferred — nobody leaves the work zone), then to the hard
        ceiling (peaking — sporadic by definition, the plan itself is
        the decay path). Carriers above the hard ceiling are never
        eligible. Deterministic: most headroom first, entity_id
        tie-break.
        """
        transfer_needed = max(
            0.0, debtor.utilization - self._recovery_target
        )
        if transfer_needed == 0.0:
            return PickupPlan(
                debtor_id=debtor.entity_id,
                debtor_target=self._recovery_target,
                transfer_total=0.0,
                assignments=(),
                feasible=True,
                reasoning="debtor already at or below recovery target",
            )
        eligible = sorted(
            (
                p
                for p in peers
                if p.entity_id != debtor.entity_id
                and p.utilization < self._hard_ceiling
            ),
            key=lambda p: (
                -(self._hard_ceiling - p.utilization),
                p.entity_id,
            ),
        )
        loads: Dict[str, float] = {
            p.entity_id: p.utilization for p in eligible
        }
        assignments: Dict[str, float] = {}
        remaining = self._fill(
            eligible=eligible,
            loads=loads,
            assignments=assignments,
            needed=transfer_needed,
        )
        feasible = remaining <= 1e-12
        assignment_rows = tuple(
            PickupAssignment(
                carrier_id=entity_id,
                transfer_fraction=fraction,
                carrier_projected_utilization=loads[entity_id],
            )
            for entity_id, fraction in sorted(assignments.items())
        )
        transferred = transfer_needed - max(0.0, remaining)
        reasoning = (
            f"debtor={debtor.entity_id} util={debtor.utilization:.4f} "
            f"needed={transfer_needed:.4f} transferred={transferred:.4f} "
            f"carriers={len(assignment_rows)} feasible={feasible}"
            + ("" if feasible else " — escalate: pickup would create new debt")
        )
        return PickupPlan(
            debtor_id=debtor.entity_id,
            debtor_target=self._recovery_target,
            transfer_total=transferred,
            assignments=assignment_rows,
            feasible=feasible,
            reasoning=reasoning,
        )


@dataclass(frozen=True, slots=True)
class CompensationDecision:
    """The policy's chosen action plus the plan that informed it."""

    action: CompensationAction
    plan: PickupPlan
    reasoning: str


class CompensationPolicy:  # pylint: disable=too-few-public-methods
    """Ordered compensation selection (layered zone model §2.4).

    PEER_PICKUP when the plan is feasible; RECOVERY_WINDOW when the
    debtor can shed load unilaterally (work is deferrable);
    CAPACITY_GRANT when growth is permitted (φ-stepped, grow-mode);
    ESCALATE_HUMAN otherwise. The policy never returns "do nothing" —
    refusing to compensate is itself a drift signal, so the floor is
    human escalation.
    """

    def decide(
        self,
        plan: PickupPlan,
        *,
        work_deferrable: bool,
        capacity_grant_allowed: bool,
    ) -> CompensationDecision:
        """Select the compensation action for an accruing debtor."""
        if plan.feasible and plan.assignments:
            action = CompensationAction.PEER_PICKUP
            why = "peers absorb within work/peaking ceilings"
        elif work_deferrable:
            action = CompensationAction.RECOVERY_WINDOW
            why = "no peer capacity; work is deferrable — schedule recovery"
        elif capacity_grant_allowed:
            action = CompensationAction.CAPACITY_GRANT
            why = "no peer capacity, work not deferrable — grow (phi-stepped)"
        else:
            action = CompensationAction.ESCALATE_HUMAN
            why = "no compensation path available — human decision required"
        return CompensationDecision(
            action=action,
            plan=plan,
            reasoning=f"{action.value}: {why}",
        )


__all__ = [
    "COMPENSATION_ACTIONS",
    "CompensationAction",
    "CompensationDecision",
    "CompensationPolicy",
    "DebtLedger",
    "DebtPosition",
    "LedgerSink",
    "PeerLoad",
    "PeerPickupCoordinator",
    "PickupAssignment",
    "PickupPlan",
]
