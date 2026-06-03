"""Offense-response orchestrator — reflex gate ahead of deliberate handling.

Composes the offense-response sequence:

1. :class:`~substrate.offense.reflex_restraint_gate.ReflexRestraintGate`
   first — fast survival-reflex vs restraint.
2. If ``ACT_REACTIVE`` (genuine survival threat) the reactive action is
   permitted with no deliberation; if ``REFUSE_HARD_LIMIT`` it is
   refused.
3. Otherwise (``RESTRAIN`` / ``DE_ESCALATE`` / ``INSUFFICIENT_DATA``)
   the reflex is overridden and the event is routed into the
   **deliberate, multi-angle path**: the
   :class:`PreActionNetStateChangeEvaluator` ("think before you act"
   net-state check) and the
   :class:`~substrate.offense.handling_protocol.OffenseHandlingProtocol`
   (considered response: acknowledge / repair / escalate / dissolve).

This is the single composition point that wires the reflex gate ahead
of the existing offense-handling primitives.

Pure logic
==========

* No DAO, no LLM, no network — the orchestrator only **sequences**
  injected pure evaluators.
* The deliberate path runs **only** when the reflex is restrained; a
  survival-justified reactive action (or a hard-limit refusal) skips
  it.
* Frozen dataclasses with slots throughout; deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from substrate.offense.handling_protocol import (
    OffenseHandlingDecision,
    OffenseHandlingInput,
    OffenseHandlingProtocol,
    OffenseResponse,
)
from substrate.offense.pre_action_net_state_evaluator import (
    PreActionInput,
    PreActionNetStateChangeEvaluator,
    PreActionOutput,
)
from substrate.offense.reflex_restraint_gate import (
    ReflexRestraintGate,
    RestraintDecision,
    RestraintVerdict,
    ThreatAppraisal,
)


@dataclass(frozen=True, slots=True)
class OffenseResponsePlan:
    """The full offense-response plan for one triggering event.

    ``restraint`` is always present (the reflex-vs-restraint decision).
    When the reflex was overridden, ``deliberation_performed`` is
    ``True`` and ``pre_action`` / ``handling`` carry the deliberate
    multi-angle results; when the reactive action was survival-justified
    or hard-limit-refused, both are ``None``.
    """

    restraint: RestraintDecision
    deliberation_performed: bool
    pre_action: Optional[PreActionOutput]
    handling: Optional[OffenseHandlingDecision]
    rationale: str

    @property
    def is_reactive(self) -> bool:
        """True iff the fast reactive action was permitted (survival-level)."""
        return self.restraint.verdict is RestraintVerdict.ACT_REACTIVE

    @property
    def is_refused(self) -> bool:
        """True iff the reactive action was refused on a hard limit."""
        return self.restraint.verdict is RestraintVerdict.REFUSE_HARD_LIMIT

    @property
    def considered_response(self) -> Optional[OffenseResponse]:
        """The deliberate considered response, when deliberation ran."""
        return None if self.handling is None else self.handling.response


class OffenseResponseOrchestrator:  # pylint: disable=too-few-public-methods
    """Sequences the reflex gate ahead of the deliberate offense path.

    All three evaluators are injected (defaulting to the canonical
    pure-logic implementations) so call sites can tune thresholds and
    tests can substitute fakes.
    """

    def __init__(
        self,
        *,
        reflex_gate: Optional[ReflexRestraintGate] = None,
        pre_action_evaluator: Optional[
            PreActionNetStateChangeEvaluator
        ] = None,
        handling_protocol: Optional[OffenseHandlingProtocol] = None,
    ) -> None:
        self._reflex_gate = reflex_gate or ReflexRestraintGate()
        self._pre_action = (
            pre_action_evaluator or PreActionNetStateChangeEvaluator()
        )
        self._handling = handling_protocol or OffenseHandlingProtocol()

    def plan(
        self,
        *,
        appraisal: ThreatAppraisal,
        pre_action_input: PreActionInput,
        handling_input: OffenseHandlingInput,
    ) -> OffenseResponsePlan:
        """Produce the offense-response plan for one triggering event.

        ``appraisal`` drives the reflex gate; ``pre_action_input`` and
        ``handling_input`` drive the deliberate path used only when the
        reflex is restrained. All three must describe the same actor.
        """
        actor = appraisal.actor_entity_id
        if pre_action_input.actor_entity_id != actor:
            raise ValueError(
                "pre_action_input.actor_entity_id "
                f"{pre_action_input.actor_entity_id!r} != appraisal actor "
                f"{actor!r}"
            )
        if handling_input.actor_entity_id != actor:
            raise ValueError(
                "handling_input.actor_entity_id "
                f"{handling_input.actor_entity_id!r} != appraisal actor "
                f"{actor!r}"
            )

        restraint = self._reflex_gate.evaluate(appraisal)

        # Survival-justified reactive action or hard-limit refusal: the
        # deliberate path does not run.
        if restraint.verdict in (
            RestraintVerdict.ACT_REACTIVE,
            RestraintVerdict.REFUSE_HARD_LIMIT,
        ):
            return OffenseResponsePlan(
                restraint=restraint,
                deliberation_performed=False,
                pre_action=None,
                handling=None,
                rationale=(
                    f"reflex verdict={restraint.verdict.value}; "
                    "no deliberation (survival-justified or hard-limit refused)"
                ),
            )

        # Reflex restrained: route into the deliberate multi-angle path.
        pre_action = self._pre_action.evaluate(pre_action_input)
        handling = self._handling.handle(handling_input)
        return OffenseResponsePlan(
            restraint=restraint,
            deliberation_performed=True,
            pre_action=pre_action,
            handling=handling,
            rationale=(
                f"reflex verdict={restraint.verdict.value}; deliberated — "
                f"pre_action={pre_action.verdict.value}, "
                f"handling={handling.response.value}"
            ),
        )


__all__ = [
    "OffenseResponseOrchestrator",
    "OffenseResponsePlan",
]
