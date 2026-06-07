"""NPG-governed ascent — hill climbing made substrate-aligned.

Doctrine (see ``docs/concepts/governed-ascent.md``): conventional hill
climbing greedily ascends an arbitrary local objective with no quantity
discipline and no certification of the objective — the short-cycle
optimizer in algorithmic form. This module is the governed
form:

1. **The objective is certified long-cycle before the loop is entered**
   (``substrate/objective_gate.py``); an uncertified hill is never
   climbed greedily.
2. **Every step is a net-potential-gain evaluation** — a step the gate
   scores NET_NEGATIVE (or cannot score) is a step not taken.
3. **Effort is paced by the layered capacity zones** — climb effort is a
   WORK quantity: PEAKING/DEBT-zone excursions are tolerated only
   sporadically, and the temporal verdicts (``SustainedLoadTracker``)
   terminate the climb on DEBT_ACCRUING. Capacity-growth proposals feed
   the ``GrowthStreakMonitor``; an always-grow climb terminates as
   RUNAWAY (condition #6).
4. **Termination + consolidation are mandatory** — every exit invokes
   the caller's consolidation callback. There are no unterminated
   climbs by construction.

A rising per-step NPG score is **not** a runaway signal — rising gain is
the point of a climb; growth-without-consolidation is the runaway
signature, and the streak monitor owns it.

Pure logic: no DAO, no LLM, no I/O, no clock reads (timestamps arrive on
the caller's load observations); gates, tracker, generator, and observer
are all injected.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Final, Mapping, Optional

from substrate.net_potential_gain_gate import (
    NetPotentialGainEvaluation,
    NetPotentialGainGate,
    NetPotentialGainVerdict,
)
from substrate.objective_gate import (
    ClimbObjective,
    ObjectiveAlignmentGate,
    ObjectiveCertification,
)
from substrate.resistance_band import (
    ZoneClassification,
    classify_zone,
)
from substrate.sustained_load import (
    GrowthStreakMonitor,
    LoadObservation,
    LoadTrend,
    SustainedLoadAssessment,
    SustainedLoadTracker,
)


def _empty_outcome() -> dict[str, object]:
    return {}


class ClimbTermination(str, Enum):
    """Why a climb ended — every climb ends with exactly one of these.

    str-Enum so the value serialises stably across SQL, JSON, and
    audit-chain canonical bytes.
    """

    CONVERGED = "converged"  # no further improving step — the peak
    NET_NEGATIVE = "net_negative"  # a step scored NET_NEGATIVE — refused
    INSUFFICIENT_DATA = "insufficient_data"  # a step could not be scored
    OBJECTIVE_UNCERTIFIED = "objective_uncertified"  # wrong/unscorable hill
    DEBT_LIMIT = "debt_limit"  # sustained load past the φ-conjugate
    RUNAWAY = "runaway"  # growth streak without consolidation
    PEAKING_EXHAUSTED = "peaking_exhausted"  # sporadic tolerance spent
    MAX_STEPS = "max_steps"  # step budget exhausted


#: All termination values — stays in lockstep with the enum.
CLIMB_TERMINATIONS: Final[frozenset[str]] = frozenset(
    t.value for t in ClimbTermination
)


@dataclass(frozen=True, slots=True)
class StepProposal:
    """One proposed climb step, produced by the caller's generator.

    ``grows_capacity`` declares the step a GROWTH-quantity action
    (raising max capacity rather than spending effort within it); such
    steps feed the growth-streak monitor and must be φ-stepped by the
    caller (``resistance_band.assess_growth_step``).
    """

    action_kind: str
    affected_entity_ids: tuple[str, ...]
    proposed_outcome: Mapping[str, object] = field(
        default_factory=_empty_outcome
    )
    grows_capacity: bool = False

    def __post_init__(self) -> None:
        if not self.action_kind:
            raise ValueError("action_kind must be non-empty")


@dataclass(frozen=True, slots=True)
class ClimbStep:  # pylint: disable=too-many-instance-attributes
    """Frozen record of one accepted climb step (audit vocabulary)."""

    step_index: int
    action_kind: str
    proposed_outcome_digest: str
    npg_score: float
    npg_verdict: NetPotentialGainVerdict
    utilization: float
    zone: ZoneClassification
    load_trend: LoadTrend
    grows_capacity: bool


@dataclass(frozen=True, slots=True)
class ClimbTrajectory:  # pylint: disable=too-many-instance-attributes
    """Frozen verdict of one whole climb.

    ``consolidation_emitted`` is ``True`` on every trajectory the loop
    returns — it exists so downstream consumers (audit rows, NEXUS run
    records) can assert the no-unterminated-climbs contract held.
    """

    objective_id: str
    actor_entity_id: str
    certification: ObjectiveCertification
    steps: tuple[ClimbStep, ...]
    termination: ClimbTermination
    terminal_reasoning: str
    cumulative_gain: float
    peaking_steps: int
    consolidation_emitted: bool

    @property
    def step_count(self) -> int:
        """Number of accepted steps."""
        return len(self.steps)

    @property
    def reached_peak(self) -> bool:
        """``True`` iff the climb ended because no step improved further."""
        return self.termination is ClimbTermination.CONVERGED


@dataclass(frozen=True, slots=True)
class ClimbConfig:
    """Caller-supplied climb bounds.

    ``convergence_epsilon`` is the minimum per-step projected gain that
    still counts as "improving"; a proposal at or below it converges the
    climb (the proposal is not taken). ``max_consecutive_peaking`` is
    the sporadic-tolerance budget: consecutive observations in the
    PEAKING or DEBT zones beyond it terminate the climb — past the 0.5
    line a turnaround is expected, and a climb that keeps peaking is
    sustaining what must stay sporadic.
    """

    max_steps: int = 20
    convergence_epsilon: float = 1e-6
    max_consecutive_peaking: int = 2

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError(f"max_steps must be >= 1; got {self.max_steps!r}")
        if not math.isfinite(self.convergence_epsilon) or (
            self.convergence_epsilon < 0.0
        ):
            raise ValueError(
                "convergence_epsilon must be a finite float >= 0; "
                f"got {self.convergence_epsilon!r}"
            )
        if self.max_consecutive_peaking < 1:
            raise ValueError(
                "max_consecutive_peaking must be >= 1; "
                f"got {self.max_consecutive_peaking!r}"
            )


DEFAULT_CLIMB_CONFIG: Final[ClimbConfig] = ClimbConfig()

#: Generator signature: ``step_index -> proposal`` (``None`` = no further
#: proposal — the climb has reached the generator's peak).
StepGenerator = Callable[[int], Optional[StepProposal]]

#: Observer signature: ``step_index -> LoadObservation`` for the entity's
#: current utilisation (timestamps are the caller's).
LoadObserver = Callable[[int], LoadObservation]

#: Consolidation sink: invoked with the finished trajectory on EVERY
#: exit path (cycle-close semantics; see ``substrate/iteration/
#: consolidation.py`` for the event vocabulary callers typically emit).
ConsolidationSink = Callable[["ClimbTrajectory"], None]


def proposal_digest(proposed_outcome: Mapping[str, object]) -> str:
    """Stable 12-hex digest of a proposed outcome (audit vocabulary).

    Canonicalised via sorted-key JSON with ``repr`` fallback for
    non-JSON values — deterministic across processes for the mappings
    the NPG gate consumes.
    """
    canonical = json.dumps(
        dict(proposed_outcome), sort_keys=True, default=repr
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


class _ClimbState:  # pylint: disable=too-few-public-methods
    """Mutable per-climb scratch (private to the loop)."""

    __slots__ = (
        "objective",
        "certification",
        "steps",
        "cumulative_gain",
        "peaking_steps",
        "consecutive_peaking",
    )

    def __init__(
        self,
        objective: ClimbObjective,
        certification: ObjectiveCertification,
    ) -> None:
        self.objective = objective
        self.certification = certification
        self.steps: list[ClimbStep] = []
        self.cumulative_gain = 0.0
        self.peaking_steps = 0
        self.consecutive_peaking = 0


#: A termination decision: ``(why, human-readable reasoning)``.
_Outcome = tuple[ClimbTermination, str]


class GovernedAscentLoop:  # pylint: disable=too-few-public-methods
    """The governed greedy-ascent loop (one public entry: :meth:`climb`).

    The loop owns no state beyond its injected collaborators; run
    :meth:`climb` once per objective. The consolidation sink is a
    required constructor argument — a climb with nowhere to consolidate
    is an unterminated climb waiting to happen, and the doctrine forbids
    it by construction.
    """

    def __init__(  # pylint: disable=too-many-arguments  # DI constructor
        self,
        *,
        npg_gate: NetPotentialGainGate,
        objective_gate: ObjectiveAlignmentGate,
        load_tracker: SustainedLoadTracker,
        on_consolidate: ConsolidationSink,
        growth_monitor: Optional[GrowthStreakMonitor] = None,
        config: ClimbConfig = DEFAULT_CLIMB_CONFIG,
    ) -> None:
        self._npg_gate = npg_gate
        self._objective_gate = objective_gate
        self._load_tracker = load_tracker
        self._on_consolidate = on_consolidate
        self._growth_monitor = growth_monitor or GrowthStreakMonitor()
        self._config = config

    def climb(
        self,
        *,
        objective: ClimbObjective,
        step_generator: StepGenerator,
        load_observer: LoadObserver,
    ) -> ClimbTrajectory:
        """Run one governed climb to termination; consolidate; return.

        Per-step order: propose → NPG-evaluate (refuse NET_NEGATIVE,
        stop on INSUFFICIENT_DATA, converge at/below epsilon) → observe
        load (terminate on DEBT_ACCRUING / RUNAWAY_GROWTH; bound
        consecutive PEAKING/DEBT-zone excursions) → accept + record.
        """
        certification = self._objective_gate.certify(objective)
        state = _ClimbState(objective, certification)
        if not certification.is_certified:
            return self._finish(
                state,
                ClimbTermination.OBJECTIVE_UNCERTIFIED,
                (
                    f"objective certification "
                    f"{certification.verdict.value}: "
                    f"{certification.reasoning}"
                ),
            )
        for step_index in range(self._config.max_steps):
            outcome = self._step(
                state, step_index, step_generator, load_observer
            )
            if outcome is not None:
                return self._finish(state, *outcome)
        return self._finish(
            state,
            ClimbTermination.MAX_STEPS,
            (
                f"step budget of {self._config.max_steps} exhausted — "
                "consolidate before climbing further"
            ),
        )

    def _step(
        self,
        state: _ClimbState,
        step_index: int,
        step_generator: StepGenerator,
        load_observer: LoadObserver,
    ) -> Optional[_Outcome]:
        """Run one step; return a termination outcome or ``None`` to go on."""
        proposal = step_generator(step_index)
        if proposal is None:
            return (
                ClimbTermination.CONVERGED,
                (
                    f"generator exhausted after {len(state.steps)} steps — "
                    "no further proposal"
                ),
            )
        # pylint: disable-next=assignment-from-no-return  # Protocol stub
        evaluation = self._npg_gate.evaluate(
            actor_entity_id=state.objective.actor_entity_id,
            action_kind=proposal.action_kind,
            affected_entity_ids=proposal.affected_entity_ids,
            proposed_outcome=proposal.proposed_outcome,
        )
        gate_outcome = self._resolve_gate_outcome(step_index, evaluation)
        if gate_outcome is not None:
            return gate_outcome
        observation = load_observer(step_index)
        assessment = self._load_tracker.observe(observation)
        pace_outcome = self._pace(step_index, proposal, assessment)
        if pace_outcome is not None:
            return pace_outcome
        zone = classify_zone(observation.utilization)
        peaking_outcome = self._bound_peaking(state, step_index, zone)
        if peaking_outcome is not None:
            return peaking_outcome
        state.steps.append(
            ClimbStep(
                step_index=step_index,
                action_kind=proposal.action_kind,
                proposed_outcome_digest=proposal_digest(
                    proposal.proposed_outcome
                ),
                npg_score=evaluation.score,
                npg_verdict=evaluation.verdict,
                utilization=observation.utilization,
                zone=zone,
                load_trend=assessment.trend,
                grows_capacity=proposal.grows_capacity,
            )
        )
        state.cumulative_gain += evaluation.score
        return None

    def _resolve_gate_outcome(
        self,
        step_index: int,
        evaluation: NetPotentialGainEvaluation,
    ) -> Optional[_Outcome]:
        """Translate the step's NPG evaluation into a termination, if any."""
        if evaluation.verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA:
            return (
                ClimbTermination.INSUFFICIENT_DATA,
                (
                    f"step {step_index} unscorable — a step the gate "
                    f"cannot score is not taken greedily; "
                    f"{evaluation.reasoning}"
                ),
            )
        if evaluation.verdict is NetPotentialGainVerdict.NET_NEGATIVE:
            return (
                ClimbTermination.NET_NEGATIVE,
                (
                    f"step {step_index} net-negative "
                    f"(score={evaluation.score:.4f}) — refused; "
                    f"{evaluation.reasoning}"
                ),
            )
        if evaluation.score <= self._config.convergence_epsilon:
            return (
                ClimbTermination.CONVERGED,
                (
                    f"step {step_index} projected gain "
                    f"{evaluation.score:.6f} <= epsilon "
                    f"{self._config.convergence_epsilon:.6f} — the peak"
                ),
            )
        return None

    def _pace(
        self,
        step_index: int,
        proposal: StepProposal,
        assessment: SustainedLoadAssessment,
    ) -> Optional[_Outcome]:
        """Apply the temporal capacity contract (debt + growth streaks)."""
        if assessment.trend is LoadTrend.DEBT_ACCRUING:
            return (
                ClimbTermination.DEBT_LIMIT,
                (
                    f"step {step_index} load past the φ-conjugate debt "
                    f"line sustained — {assessment.reasoning}"
                ),
            )
        if proposal.grows_capacity:
            growth_trend = self._growth_monitor.record_grow_step()
            if growth_trend is LoadTrend.RUNAWAY_GROWTH:
                return (
                    ClimbTermination.RUNAWAY,
                    (
                        f"step {step_index} extends a growth streak of "
                        f"{self._growth_monitor.growth_streak} without "
                        "consolidation — always-grow is the runaway "
                        "signature (condition #6)"
                    ),
                )
        else:
            self._growth_monitor.record_maintain_step()
        return None

    def _bound_peaking(
        self,
        state: _ClimbState,
        step_index: int,
        zone: ZoneClassification,
    ) -> Optional[_Outcome]:
        """Bound consecutive PEAKING/DEBT-zone excursions (sporadic only)."""
        if zone in (ZoneClassification.PEAKING, ZoneClassification.DEBT):
            state.consecutive_peaking += 1
            state.peaking_steps += 1
            if state.consecutive_peaking > self._config.max_consecutive_peaking:
                return (
                    ClimbTermination.PEAKING_EXHAUSTED,
                    (
                        f"step {step_index} is the "
                        f"{state.consecutive_peaking}th consecutive "
                        "PEAKING/DEBT-zone excursion — past the 0.5 "
                        "line a turnaround is expected; sporadic "
                        "tolerance is spent"
                    ),
                )
        else:
            state.consecutive_peaking = 0
        return None

    def _finish(
        self,
        state: _ClimbState,
        termination: ClimbTermination,
        reasoning: str,
    ) -> ClimbTrajectory:
        """Build the trajectory and emit the mandatory consolidation."""
        trajectory = ClimbTrajectory(
            objective_id=state.objective.objective_id,
            actor_entity_id=state.objective.actor_entity_id,
            certification=state.certification,
            steps=tuple(state.steps),
            termination=termination,
            terminal_reasoning=reasoning,
            cumulative_gain=state.cumulative_gain,
            peaking_steps=state.peaking_steps,
            consolidation_emitted=True,
        )
        self._on_consolidate(trajectory)
        return trajectory


__all__ = [
    "CLIMB_TERMINATIONS",
    "ClimbConfig",
    "ClimbStep",
    "ClimbTermination",
    "ClimbTrajectory",
    "ConsolidationSink",
    "DEFAULT_CLIMB_CONFIG",
    "GovernedAscentLoop",
    "LoadObserver",
    "StepGenerator",
    "StepProposal",
    "proposal_digest",
]
