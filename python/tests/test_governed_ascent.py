# tests/test_governed_ascent.py
# pylint: disable=missing-function-docstring,missing-class-docstring
"""Tests for ``governed_ascent`` — NPG-governed hill climbing (plan §2.1).

Verifies every termination path plus the consolidation contract:
- uncertified / unscorable objective → OBJECTIVE_UNCERTIFIED, zero steps
- happy climb to generator exhaustion → CONVERGED, steps + gain recorded
- epsilon convergence → CONVERGED, converging proposal NOT taken
- NET_NEGATIVE step → NET_NEGATIVE, prior steps preserved
- INSUFFICIENT_DATA step → INSUFFICIENT_DATA (fail closed)
- sustained debt-line load → DEBT_LIMIT
- growth streak without consolidation → RUNAWAY
- consecutive PEAKING/DEBT-zone excursions past budget → PEAKING_EXHAUSTED
- sporadic peak that decays → climb continues (sporadic ≠ sustained)
- step budget → MAX_STEPS
- consolidation sink invoked exactly once on EVERY exit path
- consolidation sink exceptions propagate (honest failure)
- ``proposal_digest`` determinism
- ``ClimbConfig`` validation; trajectory immutability; enum lockstep
"""
from __future__ import annotations

import time
from typing import Mapping, Optional, Sequence

import pytest

from substrate.governed_ascent import (
    CLIMB_TERMINATIONS,
    ClimbConfig,
    ClimbTermination,
    ClimbTrajectory,
    GovernedAscentLoop,
    StepProposal,
    proposal_digest,
)
from substrate.net_potential_gain_gate import (
    NetPotentialGainEvaluation,
    NetPotentialGainVerdict,
)
from substrate.objective_gate import (
    ClimbObjective,
    ObjectiveCertification,
    ObjectiveCertificationVerdict,
)
from substrate.resistance_band import ZoneClassification
from substrate.sustained_load import (
    LoadObservation,
    SustainedLoadTracker,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _ScriptedNpgGate:  # pylint: disable=too-few-public-methods
    """Returns scripted ``(verdict, score)`` pairs per call, in order.

    The last script entry repeats once the script is exhausted.
    """

    def __init__(
        self, script: Sequence[tuple[NetPotentialGainVerdict, float]]
    ) -> None:
        self._script = list(script)
        self.calls = 0

    def evaluate(
        self,
        *,
        actor_entity_id: str,
        action_kind: str,
        affected_entity_ids: Sequence[str],
        proposed_outcome: Mapping[str, object],
    ) -> NetPotentialGainEvaluation:
        del proposed_outcome  # Protocol-required parameter
        idx = min(self.calls, len(self._script) - 1)
        verdict, score = self._script[idx]
        self.calls += 1
        return NetPotentialGainEvaluation(
            verdict=verdict,
            actor_entity_id=actor_entity_id,
            action_kind=action_kind,
            affected_entity_ids=tuple(affected_entity_ids),
            score=score,
            per_entity_delta=tuple(
                (e, score) for e in affected_entity_ids
            ),
            reasoning=f"scripted {verdict.value} @ {score}",
            evaluated_at_epoch=time.time(),
        )


class _StubObjectiveGate:  # pylint: disable=too-few-public-methods
    """Returns a fixed certification verdict."""

    def __init__(
        self,
        verdict: ObjectiveCertificationVerdict = (
            ObjectiveCertificationVerdict.CERTIFIED
        ),
    ) -> None:
        self._verdict = verdict

    def certify(self, objective: ClimbObjective) -> ObjectiveCertification:
        return ObjectiveCertification(
            verdict=self._verdict,
            objective_id=objective.objective_id,
            reasoning=f"stub {self._verdict.value}",
        )


class _ConsolidationSpy:  # pylint: disable=too-few-public-methods
    """Records every trajectory the loop consolidates."""

    def __init__(self) -> None:
        self.trajectories: list[ClimbTrajectory] = []

    def __call__(self, trajectory: ClimbTrajectory) -> None:
        self.trajectories.append(trajectory)


def _objective() -> ClimbObjective:
    return ClimbObjective(
        objective_id="obj-1",
        actor_entity_id="agent-1",
        action_kind="optimize",
        affected_entity_ids=("agent-1",),
    )


def _proposal(grows: bool = False) -> StepProposal:
    return StepProposal(
        action_kind="optimize",
        affected_entity_ids=("agent-1",),
        proposed_outcome={"expected_delta_by_entity": {"agent-1": 0.1}},
        grows_capacity=grows,
    )


def _loop(
    *,
    npg_script: Sequence[tuple[NetPotentialGainVerdict, float]],
    spy: _ConsolidationSpy,
    objective_verdict: ObjectiveCertificationVerdict = (
        ObjectiveCertificationVerdict.CERTIFIED
    ),
    config: ClimbConfig = ClimbConfig(),
) -> GovernedAscentLoop:
    return GovernedAscentLoop(
        npg_gate=_ScriptedNpgGate(npg_script),
        objective_gate=_StubObjectiveGate(objective_verdict),
        load_tracker=SustainedLoadTracker(),
        on_consolidate=spy,
        config=config,
    )


def _steady_observer(utilization: float):
    def observe(step_index: int) -> LoadObservation:
        return LoadObservation(
            timestamp=step_index, utilization=utilization
        )

    return observe


_POSITIVE = (NetPotentialGainVerdict.NET_POSITIVE, 0.2)


# ---------------------------------------------------------------------------
# Objective certification path
# ---------------------------------------------------------------------------


class TestObjectiveCertification:
    def test_refused_objective_terminates_before_any_step(self) -> None:
        spy = _ConsolidationSpy()
        loop = _loop(
            npg_script=[_POSITIVE],
            spy=spy,
            objective_verdict=ObjectiveCertificationVerdict.REFUSED,
        )
        trajectory = loop.climb(
            objective=_objective(),
            step_generator=lambda i: _proposal(),
            load_observer=_steady_observer(0.45),
        )
        assert (
            trajectory.termination
            is ClimbTermination.OBJECTIVE_UNCERTIFIED
        )
        assert trajectory.step_count == 0
        assert trajectory.consolidation_emitted
        assert spy.trajectories == [trajectory]

    def test_insufficient_data_certification_fails_closed(self) -> None:
        spy = _ConsolidationSpy()
        loop = _loop(
            npg_script=[_POSITIVE],
            spy=spy,
            objective_verdict=(
                ObjectiveCertificationVerdict.INSUFFICIENT_DATA
            ),
        )
        trajectory = loop.climb(
            objective=_objective(),
            step_generator=lambda i: _proposal(),
            load_observer=_steady_observer(0.45),
        )
        assert (
            trajectory.termination
            is ClimbTermination.OBJECTIVE_UNCERTIFIED
        )
        assert "insufficient_data" in trajectory.terminal_reasoning


# ---------------------------------------------------------------------------
# Termination paths
# ---------------------------------------------------------------------------


class TestTerminations:
    def test_generator_exhaustion_converges(self) -> None:
        spy = _ConsolidationSpy()
        loop = _loop(npg_script=[_POSITIVE], spy=spy)

        def generator(step_index: int) -> Optional[StepProposal]:
            return _proposal() if step_index < 3 else None

        trajectory = loop.climb(
            objective=_objective(),
            step_generator=generator,
            load_observer=_steady_observer(0.45),
        )
        assert trajectory.termination is ClimbTermination.CONVERGED
        assert trajectory.reached_peak
        assert trajectory.step_count == 3
        assert trajectory.cumulative_gain == pytest.approx(0.6)
        assert all(
            s.zone is ZoneClassification.WORKING for s in trajectory.steps
        )

    def test_epsilon_convergence_does_not_take_the_step(self) -> None:
        spy = _ConsolidationSpy()
        script = [_POSITIVE, (NetPotentialGainVerdict.NET_POSITIVE, 0.0)]
        loop = _loop(npg_script=script, spy=spy)
        trajectory = loop.climb(
            objective=_objective(),
            step_generator=lambda i: _proposal(),
            load_observer=_steady_observer(0.45),
        )
        assert trajectory.termination is ClimbTermination.CONVERGED
        assert trajectory.step_count == 1  # the epsilon proposal not taken
        assert "the peak" in trajectory.terminal_reasoning

    def test_net_negative_step_refused_prior_steps_kept(self) -> None:
        spy = _ConsolidationSpy()
        script = [
            _POSITIVE,
            _POSITIVE,
            (NetPotentialGainVerdict.NET_NEGATIVE, -0.3),
        ]
        loop = _loop(npg_script=script, spy=spy)
        trajectory = loop.climb(
            objective=_objective(),
            step_generator=lambda i: _proposal(),
            load_observer=_steady_observer(0.45),
        )
        assert trajectory.termination is ClimbTermination.NET_NEGATIVE
        assert trajectory.step_count == 2
        assert trajectory.cumulative_gain == pytest.approx(0.4)

    def test_insufficient_data_step_stops(self) -> None:
        spy = _ConsolidationSpy()
        script = [
            _POSITIVE,
            (NetPotentialGainVerdict.INSUFFICIENT_DATA, 0.0),
        ]
        loop = _loop(npg_script=script, spy=spy)
        trajectory = loop.climb(
            objective=_objective(),
            step_generator=lambda i: _proposal(),
            load_observer=_steady_observer(0.45),
        )
        assert trajectory.termination is ClimbTermination.INSUFFICIENT_DATA
        assert trajectory.step_count == 1
        assert "unscorable" in trajectory.terminal_reasoning

    def test_sustained_debt_load_hits_debt_limit(self) -> None:
        spy = _ConsolidationSpy()
        loop = _loop(npg_script=[_POSITIVE], spy=spy)
        trajectory = loop.climb(
            objective=_objective(),
            step_generator=lambda i: _proposal(),
            load_observer=_steady_observer(0.70),  # past 2/3 every step
        )
        # Default sustain_count=3: the third consecutive above-debt
        # observation flips the trend to DEBT_ACCRUING.
        assert trajectory.termination is ClimbTermination.DEBT_LIMIT
        assert "2/3" in trajectory.terminal_reasoning

    def test_growth_streak_without_consolidation_is_runaway(self) -> None:
        spy = _ConsolidationSpy()
        loop = _loop(npg_script=[_POSITIVE], spy=spy)
        trajectory = loop.climb(
            objective=_objective(),
            step_generator=lambda i: _proposal(grows=True),
            load_observer=_steady_observer(0.45),
        )
        # Default max_growth_streak=2: the third consecutive grow step
        # exceeds the streak.
        assert trajectory.termination is ClimbTermination.RUNAWAY
        assert trajectory.step_count == 2
        assert "condition #6" in trajectory.terminal_reasoning

    def test_peaking_budget_exhausts(self) -> None:
        spy = _ConsolidationSpy()
        loop = _loop(npg_script=[_POSITIVE], spy=spy)
        trajectory = loop.climb(
            objective=_objective(),
            step_generator=lambda i: _proposal(),
            load_observer=_steady_observer(0.55),  # PEAKING zone every step
        )
        # max_consecutive_peaking=2 → the third consecutive excursion stops.
        assert trajectory.termination is ClimbTermination.PEAKING_EXHAUSTED
        assert trajectory.step_count == 2
        assert trajectory.peaking_steps == 3

    def test_warning_band_excursions_also_bounded(self) -> None:
        # The WARNING band (0.618, 2/3] is winded — counted with PEAKING
        # as a sporadic-only excursion: sustained 0.65 exhausts the budget
        # before it would ever accrue debt.
        spy = _ConsolidationSpy()
        loop = _loop(npg_script=[_POSITIVE], spy=spy)
        trajectory = loop.climb(
            objective=_objective(),
            step_generator=lambda i: _proposal(),
            load_observer=_steady_observer(0.65),  # WARNING zone every step
        )
        assert trajectory.termination is ClimbTermination.PEAKING_EXHAUSTED
        assert trajectory.step_count == 2
        assert trajectory.peaking_steps == 3

    def test_sporadic_peak_that_decays_continues(self) -> None:
        spy = _ConsolidationSpy()
        loop = _loop(npg_script=[_POSITIVE], spy=spy)
        pattern = {0: 0.55, 1: 0.45, 2: 0.55, 3: 0.45}

        def observer(step_index: int) -> LoadObservation:
            return LoadObservation(
                timestamp=step_index,
                utilization=pattern.get(step_index, 0.45),
            )

        def generator(step_index: int) -> Optional[StepProposal]:
            return _proposal() if step_index < 4 else None

        trajectory = loop.climb(
            objective=_objective(),
            step_generator=generator,
            load_observer=observer,
        )
        assert trajectory.termination is ClimbTermination.CONVERGED
        assert trajectory.step_count == 4
        assert trajectory.peaking_steps == 2  # sporadic, decayed each time

    def test_max_steps_budget(self) -> None:
        spy = _ConsolidationSpy()
        loop = _loop(
            npg_script=[_POSITIVE],
            spy=spy,
            config=ClimbConfig(max_steps=2),
        )
        trajectory = loop.climb(
            objective=_objective(),
            step_generator=lambda i: _proposal(),
            load_observer=_steady_observer(0.45),
        )
        assert trajectory.termination is ClimbTermination.MAX_STEPS
        assert trajectory.step_count == 2
        assert "consolidate before climbing further" in (
            trajectory.terminal_reasoning
        )


# ---------------------------------------------------------------------------
# Consolidation contract
# ---------------------------------------------------------------------------


class TestConsolidationContract:
    @pytest.mark.parametrize(
        "objective_verdict",
        [
            ObjectiveCertificationVerdict.CERTIFIED,
            ObjectiveCertificationVerdict.REFUSED,
            ObjectiveCertificationVerdict.INSUFFICIENT_DATA,
        ],
    )
    def test_every_exit_consolidates_exactly_once(
        self, objective_verdict: ObjectiveCertificationVerdict
    ) -> None:
        spy = _ConsolidationSpy()
        loop = _loop(
            npg_script=[_POSITIVE],
            spy=spy,
            objective_verdict=objective_verdict,
            config=ClimbConfig(max_steps=1),
        )
        trajectory = loop.climb(
            objective=_objective(),
            step_generator=lambda i: _proposal(),
            load_observer=_steady_observer(0.45),
        )
        assert len(spy.trajectories) == 1
        assert spy.trajectories[0] is trajectory
        assert trajectory.consolidation_emitted

    def test_consolidation_exception_propagates(self) -> None:
        def exploding_sink(trajectory: ClimbTrajectory) -> None:
            raise RuntimeError("sink failed")

        loop = GovernedAscentLoop(
            npg_gate=_ScriptedNpgGate([_POSITIVE]),
            objective_gate=_StubObjectiveGate(),
            load_tracker=SustainedLoadTracker(),
            on_consolidate=exploding_sink,
            config=ClimbConfig(max_steps=1),
        )
        with pytest.raises(RuntimeError, match="sink failed"):
            loop.climb(
                objective=_objective(),
                step_generator=lambda i: _proposal(),
                load_observer=_steady_observer(0.45),
            )


# ---------------------------------------------------------------------------
# Contracts & validation
# ---------------------------------------------------------------------------


class TestContracts:
    def test_termination_frozenset_lockstep(self) -> None:
        assert CLIMB_TERMINATIONS == {t.value for t in ClimbTermination}

    def test_config_validation(self) -> None:
        with pytest.raises(ValueError):
            ClimbConfig(max_steps=0)
        with pytest.raises(ValueError):
            ClimbConfig(convergence_epsilon=-1.0)
        with pytest.raises(ValueError):
            ClimbConfig(convergence_epsilon=float("nan"))
        with pytest.raises(ValueError):
            ClimbConfig(max_consecutive_peaking=0)

    def test_step_proposal_validation(self) -> None:
        with pytest.raises(ValueError):
            StepProposal(action_kind="", affected_entity_ids=("a",))

    def test_trajectory_frozen(self) -> None:
        spy = _ConsolidationSpy()
        loop = _loop(
            npg_script=[_POSITIVE], spy=spy, config=ClimbConfig(max_steps=1)
        )
        trajectory = loop.climb(
            objective=_objective(),
            step_generator=lambda i: _proposal(),
            load_observer=_steady_observer(0.45),
        )
        with pytest.raises(AttributeError):
            trajectory.cumulative_gain = 99.0

    def test_proposal_digest_deterministic_and_order_insensitive(
        self,
    ) -> None:
        digest_a = proposal_digest({"b": 2, "a": 1})
        digest_b = proposal_digest({"a": 1, "b": 2})
        assert digest_a == digest_b
        assert len(digest_a) == 12
        assert digest_a != proposal_digest({"a": 1, "b": 3})

    def test_step_records_carry_audit_vocabulary(self) -> None:
        spy = _ConsolidationSpy()
        loop = _loop(
            npg_script=[_POSITIVE], spy=spy, config=ClimbConfig(max_steps=1)
        )
        trajectory = loop.climb(
            objective=_objective(),
            step_generator=lambda i: _proposal(),
            load_observer=_steady_observer(0.45),
        )
        step = trajectory.steps[0]
        assert step.step_index == 0
        assert step.npg_verdict is NetPotentialGainVerdict.NET_POSITIVE
        assert step.zone is ZoneClassification.WORKING
        assert len(step.proposed_outcome_digest) == 12
        assert not step.grows_capacity
