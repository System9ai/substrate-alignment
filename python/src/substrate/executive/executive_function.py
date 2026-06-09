"""ExecutiveFunction.decide() as a JOIN.

The engine every substrate decision routes through. ``ExecutiveFunction``
**implements the** ``NetPotentialGainGate`` **Protocol** (see
:mod:`~substrate.net_potential_gain_gate`) — so the existing
``.evaluate()`` call sites keep working with zero rework — and adds
:meth:`decide`, the superset call for a site that also has its own load to weigh.

``decide()`` is a **join of two already-proven subsystems**, not a new fused
decision table:

- the **NPG axis** — the gate chain's verdict over the *affected others*
  (only-ever-tightens);
- the **load axis** — the band classification + the temporal trend over the
  *actor's own* utilization (the tracker is the sole sustained-vs-spike
  authority).

plus the **cause**. The join is composed under a NAMED, swappable policy
(``MOST_CONSERVATIVE``). **Monotonicity (the safety invariant):** the join never
returns a verdict *less* conservative on the NPG axis than ``evaluate()`` alone —
an NPG refusal is always REFUSE; the load/cause axes can only ADD restriction.
The disposition table below is that policy's *implementation*, not the contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping, Optional, Sequence, Tuple

from substrate.executive.band import (
    DEFAULT_BAND_PROFILE,
    BandProfile,
    CyclePhase,
    LoadZone,
    classify_cycle_phase,
    classify_load_zone,
)
from substrate.executive.cause import (
    Cause,
    HallmarkReport,
    HallmarkSource,
    infer_cause,
)
from substrate.executive.quantities import (
    Quantity,
    ResourceKind,
    setpoint_for,
)
from substrate.executive.scale import ExecutiveScale
from substrate.executive.temporal import (
    EwmaLoadTracker,
    LoadTrend,
    SustainedLoadTracker,
)
from substrate.executive.utilization_source import (
    UtilizationSource,
)
from substrate.net_potential_gain_gate import (
    NetPotentialGainEvaluation,
    NetPotentialGainGate,
    NetPotentialGainVerdict,
)
from substrate.resistance_band import OperatingMode


class Disposition(str, Enum):
    """What the executive decided the actor should do."""

    PROCEED = "proceed"
    HOLD = "hold"
    DEFER = "defer"
    SHED_AND_COMPENSATE = "shed_and_compensate"
    REFUSE = "refuse"


class Action(str, Enum):
    """A side-effect the verdict requests of the caller."""

    WARN = "warn"
    ESCALATE = "escalate"
    REMEDIATE = "remediate"
    COMPENSATE = "compensate"
    SIEM = "siem"


class JoinPolicy(str, Enum):
    """How the two axes compose. One named, swappable policy."""

    MOST_CONSERVATIVE = "most_conservative"


@dataclass(frozen=True, slots=True)
class ExecutiveVerdict:  # pylint: disable=too-many-instance-attributes
    """The joined verdict over the NPG axis and the load axis."""

    disposition: Disposition
    quantity: Quantity
    scale: ExecutiveScale
    actor_entity_id: str
    owning_entity_id: str
    zone: LoadZone
    phase: CyclePhase
    trend: LoadTrend
    setpoint: Tuple[float, float]
    in_band: bool
    cause: Cause
    actions: frozenset[Action]
    npg: Optional[NetPotentialGainEvaluation]
    mode: OperatingMode
    reasoning: str
    audit_code: str

    @property
    def proceeded(self) -> bool:
        """``True`` iff the disposition is PROCEED."""
        return self.disposition is Disposition.PROCEED


_NO_ACTIONS: Final[frozenset[Action]] = frozenset()


def _join_most_conservative(  # pylint: disable=too-many-return-statements
    *,
    npg: Optional[NetPotentialGainEvaluation],
    trend: LoadTrend,
    cause: Cause,
    in_band: bool,
) -> Tuple[Disposition, frozenset[Action], str]:
    """The MOST_CONSERVATIVE policy's disposition table .

    Evaluated in priority order; the first match wins. An NPG refusal is the
    hard floor (always REFUSE) — the monotonicity guarantee. The load/cause axes
    can only add restriction below that.
    """
    if npg is not None and npg.verdict is NetPotentialGainVerdict.NET_NEGATIVE:
        return Disposition.REFUSE, frozenset({Action.ESCALATE}), "executive_npg_refuse"
    if cause is Cause.MALICE:
        return Disposition.REFUSE, frozenset({Action.SIEM}), "executive_malice_refuse"
    if trend is LoadTrend.DEBT_ACCRUING:
        return (
            Disposition.SHED_AND_COMPENSATE,
            frozenset({Action.ESCALATE, Action.COMPENSATE}),
            "executive_debt_shed",
        )
    if trend is LoadTrend.SUSTAINED_STRAIN:
        return Disposition.DEFER, frozenset({Action.WARN}), "executive_strain_defer"
    if trend is LoadTrend.SPIKE:
        return Disposition.PROCEED, frozenset({Action.WARN}), "executive_spike_absorbed"
    if cause is Cause.ACCIDENT:
        return (
            Disposition.HOLD,
            frozenset({Action.ESCALATE, Action.REMEDIATE}),
            "executive_accident_hold",
        )
    npg_ok = npg is None or npg.verdict in (
        NetPotentialGainVerdict.NET_POSITIVE,
        NetPotentialGainVerdict.NET_NEUTRAL,
    )
    if in_band and npg_ok:
        return Disposition.PROCEED, _NO_ACTIONS, "executive_in_band"
    return Disposition.HOLD, frozenset({Action.ESCALATE}), "executive_unclassified"


class ExecutiveFunction:  # pylint: disable=too-many-instance-attributes
    """The conscious cognition layer — implements the NPG-gate Protocol + decide().

    Construct with an optional NPG ``gate_chain`` (the decorator stack), a
    ``tracker`` (defaults to a fresh :class:`EwmaLoadTracker`), and an optional
    ``hallmarks`` source. With no gate chain, :meth:`decide` runs the load/cause
    join with no NPG axis (``npg=None``); :meth:`evaluate` then requires the
    chain (it is the Protocol surface for the existing call sites).
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        profile: BandProfile = DEFAULT_BAND_PROFILE,
        gate_chain: Optional[NetPotentialGainGate] = None,
        tracker: Optional[SustainedLoadTracker] = None,
        hallmarks: Optional[HallmarkSource] = None,
        policy: JoinPolicy = JoinPolicy.MOST_CONSERVATIVE,
    ) -> None:
        self._profile = profile
        self._gate_chain = gate_chain
        self._tracker: SustainedLoadTracker = tracker or EwmaLoadTracker()
        self._hallmarks = hallmarks
        self._policy = policy

    # ── the NetPotentialGainGate Protocol (unchanged for the existing sites) ──

    def evaluate(
        self,
        *,
        actor_entity_id: str,
        action_kind: str,
        affected_entity_ids: Sequence[str],
        proposed_outcome: Mapping[str, object],
    ) -> NetPotentialGainEvaluation:
        """Delegate to the NPG gate chain (the Protocol surface)."""
        if self._gate_chain is None:
            raise RuntimeError(
                "ExecutiveFunction.evaluate requires a gate_chain; construct "
                "with gate_chain=... to use the NPG-gate Protocol surface"
            )
        return self._gate_chain.evaluate(
            actor_entity_id=actor_entity_id,
            action_kind=action_kind,
            affected_entity_ids=affected_entity_ids,
            proposed_outcome=proposed_outcome,
        )

    # ── the superset call: the join over NPG + load + cause ──────────────────

    def decide(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        *,
        actor_entity_id: str,
        action_kind: str,
        quantity: Quantity,
        scale: ExecutiveScale,
        utilization: UtilizationSource,
        affected_entity_ids: Sequence[str] = (),
        scale_unit: str = "",
        owning_entity_id: Optional[str] = None,
        mode: OperatingMode = OperatingMode.MAINTAIN,
        resource: ResourceKind = ResourceKind.GENERIC,
        proposed_outcome: Optional[Mapping[str, object]] = None,
        intent: Optional[Cause] = None,
    ) -> ExecutiveVerdict:
        """Join the NPG axis and the load axis into one verdict.

        ``quantity`` + ``scale`` are required; ``utilization`` is a
        :class:`UtilizationSource` (a raw float is not accepted — the inverted-quantity class is
        closed at the input). GROWTH is rejected at entry (it is not a decision
        band). The disposition is produced by the configured join policy.
        """
        # 1. Measurement bound to the quantity (the inversion fix). Raises
        #    GrowthNotADecisionBand for GROWTH via setpoint_for below.
        setpoint = setpoint_for(quantity, self._profile)
        u = utilization.utilization_for(
            quantity=quantity, scale=scale, resource=resource,
            scale_unit=scale_unit,
        )

        # 2. The load axis — geometric zone/phase + the temporal trend.
        zone = classify_load_zone(u, self._profile)
        phase = classify_cycle_phase(u, self._profile)
        self._tracker.observe(u)
        trend = self._tracker.trend(profile=self._profile)
        in_band = setpoint[0] <= u <= setpoint[1]

        # 3. The NPG axis — the gate chain over the affected others.
        npg: Optional[NetPotentialGainEvaluation] = None
        npg_insufficient = False
        if self._gate_chain is not None:
            npg = self._gate_chain.evaluate(
                actor_entity_id=actor_entity_id,
                action_kind=action_kind,
                affected_entity_ids=affected_entity_ids,
                proposed_outcome=proposed_outcome or {},
            )
            npg_insufficient = (
                npg.verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA
            )

        # 4. Cause.
        hallmark_report = (
            self._hallmarks.hallmarks(actor_entity_id=actor_entity_id, scale=scale)
            if self._hallmarks is not None
            else HallmarkReport()
        )
        cause = infer_cause(
            hallmarks=hallmark_report,
            profile_valid=True,
            npg_insufficient=npg_insufficient,
            trend=trend,
            intent=intent,
        )

        # 5. The join.
        disposition, actions, audit_code = _join_most_conservative(
            npg=npg, trend=trend, cause=cause, in_band=in_band,
        )

        reasoning = (
            f"disposition={disposition.value} zone={zone.value} "
            f"phase={phase.value} trend={trend.value} cause={cause.value} "
            f"in_band={in_band} u={u:.4f} quantity={quantity.value} "
            f"scale={scale.value} policy={self._policy.value}"
        )
        return ExecutiveVerdict(
            disposition=disposition,
            quantity=quantity,
            scale=scale,
            actor_entity_id=actor_entity_id,
            owning_entity_id=owning_entity_id or actor_entity_id,
            zone=zone,
            phase=phase,
            trend=trend,
            setpoint=setpoint,
            in_band=in_band,
            cause=cause,
            actions=actions,
            npg=npg,
            mode=mode,
            reasoning=reasoning,
            audit_code=audit_code,
        )


__all__ = [
    "Action",
    "Disposition",
    "ExecutiveFunction",
    "ExecutiveVerdict",
    "JoinPolicy",
]
