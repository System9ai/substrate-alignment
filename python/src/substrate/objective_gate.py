"""Objective certification — "is this the right hill?" (governed ascent).

Doctrine: conventional hill climbing greedily ascends an arbitrary local
objective; a greedy ascent is substrate-aligned only when the **basin is
certified** — when the local objective is a faithful restriction of net
potential gain. This module certifies the hill itself (the summit, not
the steps): per-step evaluation belongs to the loop in
``substrate/governed_ascent.py``; this gate answers the prior question
every conventional hill climber skips.

Fail-closed by construction: an objective the gate cannot score is an
objective that is **not climbed greedily** — ``INSUFFICIENT_DATA`` never
silently certifies. Pure logic: no I/O, no clock reads; the NPG gate is
injected. See ``docs/concepts/governed-ascent.md``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Mapping, Optional, Protocol

from substrate.net_potential_gain_gate import (
    NetPotentialGainEvaluation,
    NetPotentialGainGate,
    NetPotentialGainVerdict,
)
from substrate.types import SubstrateMode


def _empty_outcome() -> dict[str, object]:
    return {}


class ObjectiveCertificationVerdict(str, Enum):
    """Three-valued certification verdict for a climb objective.

    str-Enum so the value serialises stably across SQL, JSON, and
    audit-chain canonical bytes (same contract as
    :class:`NetPotentialGainVerdict`).
    """

    CERTIFIED = "certified"
    REFUSED = "refused"
    INSUFFICIENT_DATA = "insufficient_data"


#: All certification verdicts — stays in lockstep with the enum.
OBJECTIVE_CERTIFICATION_VERDICTS: Final[frozenset[str]] = frozenset(
    v.value for v in ObjectiveCertificationVerdict
)


@dataclass(frozen=True, slots=True)
class ClimbObjective:
    """Descriptor of the hill — the terminal outcome, not a step.

    ``terminal_outcome`` is the summit the climb is aiming at, in the
    same opaque-mapping vocabulary the NPG gate evaluates
    (``expected_delta_by_entity`` and friends). ``declared_mode`` is the
    actor's substrate mode when the caller knows it; ``None`` means
    unknown and is acceptable — mode is an additional check, not a
    requirement.
    """

    objective_id: str
    actor_entity_id: str
    action_kind: str
    affected_entity_ids: tuple[str, ...]
    terminal_outcome: Mapping[str, object] = field(
        default_factory=_empty_outcome
    )
    declared_mode: Optional[SubstrateMode] = None

    def __post_init__(self) -> None:
        if not self.objective_id:
            raise ValueError("objective_id must be non-empty")
        if not self.actor_entity_id:
            raise ValueError("actor_entity_id must be non-empty")
        if not self.action_kind:
            raise ValueError("action_kind must be non-empty")


@dataclass(frozen=True, slots=True)
class ObjectiveCertification:
    """Frozen result of one objective certification.

    Carries the underlying summit NPG evaluation (when one was run) so
    refusals can surface per-entity contributions in audit rows.
    """

    verdict: ObjectiveCertificationVerdict
    objective_id: str
    reasoning: str
    npg_evaluation: Optional[NetPotentialGainEvaluation] = None

    @property
    def is_certified(self) -> bool:
        """``True`` iff the verdict is CERTIFIED."""
        return self.verdict is ObjectiveCertificationVerdict.CERTIFIED


class ObjectiveAlignmentGate(Protocol):  # pylint: disable=too-few-public-methods
    """Protocol every concrete objective gate satisfies."""

    def certify(self, objective: ClimbObjective) -> ObjectiveCertification:
        """Certify (or refuse) the climb objective.

        Implementations MUST be fail-closed: when the objective cannot
        be scored, return ``INSUFFICIENT_DATA`` — never ``CERTIFIED``.
        """
        ...  # pylint: disable=unnecessary-ellipsis


@dataclass(frozen=True, slots=True)
class DefaultObjectiveAlignmentGate:
    """Fail-closed default: NPG-evaluate the summit; consult declared mode.

    Decision order:

    1. ``declared_mode is SHORT_CYCLE`` → REFUSED. Short-cycle
       mode-selection cannot certify its own hill — the 180° inversion
       is precisely a short-cycle evaluator presenting its local
       gradient as value.
    2. Summit NPG evaluation (the *terminal* proposed outcome, via the
       injected gate): ``NET_NEGATIVE`` → REFUSED; ``INSUFFICIENT_DATA``
       → INSUFFICIENT_DATA (fail closed); ``NET_NEUTRAL`` → REFUSED — a
       neutral summit does not justify spending work-zone effort on a
       greedy climb (value = net potential gain); ``NET_POSITIVE`` →
       CERTIFIED.
    """

    npg_gate: NetPotentialGainGate

    def certify(self, objective: ClimbObjective) -> ObjectiveCertification:
        """Certify the hill per the decision order above."""
        if objective.declared_mode is SubstrateMode.SHORT_CYCLE:
            return ObjectiveCertification(
                verdict=ObjectiveCertificationVerdict.REFUSED,
                objective_id=objective.objective_id,
                reasoning=(
                    "actor declared SHORT_CYCLE: short-cycle mode-selection "
                    "cannot certify its own hill (180° inversion guard)"
                ),
            )
        # pylint: disable-next=assignment-from-no-return  # Protocol stub
        evaluation = self.npg_gate.evaluate(
            action_kind=objective.action_kind,
            proposed_outcome=objective.terminal_outcome,
            actor_entity_id=objective.actor_entity_id,
            affected_entity_ids=objective.affected_entity_ids,
        )
        if evaluation.verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA:
            return ObjectiveCertification(
                verdict=ObjectiveCertificationVerdict.INSUFFICIENT_DATA,
                objective_id=objective.objective_id,
                reasoning=(
                    "summit NPG evaluation returned INSUFFICIENT_DATA — an "
                    f"unscorable hill is not climbed greedily; "
                    f"{evaluation.reasoning}"
                ),
                npg_evaluation=evaluation,
            )
        if evaluation.verdict is NetPotentialGainVerdict.NET_NEGATIVE:
            return ObjectiveCertification(
                verdict=ObjectiveCertificationVerdict.REFUSED,
                objective_id=objective.objective_id,
                reasoning=(
                    f"summit is net-negative (score={evaluation.score:.4f}): "
                    f"{evaluation.reasoning}"
                ),
                npg_evaluation=evaluation,
            )
        if evaluation.verdict is NetPotentialGainVerdict.NET_NEUTRAL:
            return ObjectiveCertification(
                verdict=ObjectiveCertificationVerdict.REFUSED,
                objective_id=objective.objective_id,
                reasoning=(
                    f"summit is net-neutral (score={evaluation.score:.4f}): "
                    "a neutral summit does not justify spending work-zone "
                    "effort on a greedy climb"
                ),
                npg_evaluation=evaluation,
            )
        return ObjectiveCertification(
            verdict=ObjectiveCertificationVerdict.CERTIFIED,
            objective_id=objective.objective_id,
            reasoning=(
                f"summit is net-positive (score={evaluation.score:.4f}): "
                f"{evaluation.reasoning}"
            ),
            npg_evaluation=evaluation,
        )


def certify_objective(
    objective: ClimbObjective,
    *,
    npg_gate: NetPotentialGainGate,
    declared_mode: Optional[SubstrateMode] = None,
) -> ObjectiveCertification:
    """Convenience wrapper: certify ``objective`` with the default gate.

    ``declared_mode``, when given, overrides the objective's own
    ``declared_mode`` (callers often resolve the actor's mode after
    constructing the objective).
    """
    if declared_mode is not None and declared_mode is not objective.declared_mode:
        objective = ClimbObjective(
            objective_id=objective.objective_id,
            actor_entity_id=objective.actor_entity_id,
            action_kind=objective.action_kind,
            affected_entity_ids=objective.affected_entity_ids,
            terminal_outcome=objective.terminal_outcome,
            declared_mode=declared_mode,
        )
    return DefaultObjectiveAlignmentGate(npg_gate=npg_gate).certify(objective)


__all__ = [
    "OBJECTIVE_CERTIFICATION_VERDICTS",
    "ClimbObjective",
    "DefaultObjectiveAlignmentGate",
    "ObjectiveAlignmentGate",
    "ObjectiveCertification",
    "ObjectiveCertificationVerdict",
    "certify_objective",
]
