"""Reflex-vs-restraint gate — fight-or-flight vs deliberate restraint.

Fight-or-flight is the fast **potential-gradient evaluator** — a
latency-optimized decision (*decide now to maintain potential*). It is
substrate-aligned **only when the threat is genuinely survival-level**;
there the fast reflex is correct. Fired at a *non-survival* provocation
(an offense / slight / frustration), the reflex is **miscalibrated**:
the substrate-aligned move is to **restrain** — override the reflex and
route to the deliberate, multi-angle net-potential evaluation (the
``offense.pre_action_net_state_evaluator`` "think before you act"
path).

This gate sits **before** the considered-response
:class:`~substrate.offense.handling_protocol.OffenseHandlingProtocol`:
it decides whether to act on the survival reflex at all, or to restrain
into deliberation.

Verdicts
========

* ``ACT_REACTIVE`` — threat is genuinely survival-level
  (``survival_threat_score >= survival_threshold``); the fast reflex is
  substrate-aligned; act now. *Survival mode has its place.*
* ``RESTRAIN`` — not survival-level; override the reflex; route to
  deliberate multi-angle evaluation. Absorb the offense-signal without
  reactive escalation.
* ``DE_ESCALATE`` — the reactive action would lower net potential
  across affected entities **and** a live counterparty exists; the
  efficiency move is to actively reduce the conflict gradient rather
  than fight. *Fighting that lowers net potential is short-cycle;
  de-escalation is the efficiency move.*
* ``REFUSE_HARD_LIMIT`` — the reactive action crosses a hard limit;
  refused regardless of provocation (consistent with
  ``hierarchy.hard_limit_dispatcher``).
* ``INSUFFICIENT_DATA`` — not survival-justified and the reactive
  action carries no net-potential signal; cannot decide. Safe default
  is restraint.

Pure logic
==========

* No DAO, no LLM, no network. The caller computes the reactive action's
  net-potential verdict via a
  :class:`~substrate.net_potential_gain_gate.NetPotentialGainGate` and
  passes the resulting :class:`NetPotentialGainVerdict` in — this gate
  **composes the verdict as an input**, the way
  ``offense.handling_protocol.OffenseHandlingProtocol`` composes
  ``OffenseSignalType``.
* Total over the (survival_threat_score, reactive_action_npg,
  crosses_hard_limit, has_live_counterparty) input space.
* Honest uncertainty: no net-potential signal + not survival-justified
  -> ``INSUFFICIENT_DATA``.
* Frozen dataclasses with slots throughout; deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from substrate.net_potential_gain_gate import NetPotentialGainVerdict


class RestraintVerdict(str, Enum):
    """Reflex-vs-restraint verdict.

    str-Enum so the value serialises stably across SQL, JSON, and
    audit-chain canonical bytes; mirrors :class:`SubstrateMode`.
    """

    ACT_REACTIVE = "act_reactive"
    RESTRAIN = "restrain"
    DE_ESCALATE = "de_escalate"
    REFUSE_HARD_LIMIT = "refuse_hard_limit"
    INSUFFICIENT_DATA = "insufficient_data"


#: All verdict values — stays in lockstep with the enum.
RESTRAINT_VERDICTS: Final[frozenset[str]] = frozenset(
    v.value for v in RestraintVerdict
)


@dataclass(frozen=True, slots=True)
class ThreatAppraisal:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied fast appraisal of a triggering threat / provocation.

    ``survival_threat_score`` is the load-bearing input: ``1.0`` is a
    genuine survival-level threat (where the fast reflex is correct);
    low values are mere offense / provocation (where the reflex is
    miscalibrated and restraint is substrate-aligned).
    ``reactive_action_npg`` is the deliberate net-potential verdict of
    the action the reflex wants to take, computed by the caller via a
    :class:`NetPotentialGainGate`. ``has_live_counterparty`` marks
    whether an active other party is present to de-escalate with (vs a
    solo reaction).
    """

    actor_entity_id: str
    threat_id: str
    survival_threat_score: float
    reactive_action_kind: str
    reactive_action_npg: NetPotentialGainVerdict
    crosses_hard_limit: bool = False
    has_live_counterparty: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if not self.actor_entity_id:
            raise ValueError("actor_entity_id must be non-empty")
        if not self.threat_id:
            raise ValueError("threat_id must be non-empty")
        if not self.reactive_action_kind:
            raise ValueError("reactive_action_kind must be non-empty")
        if not 0.0 <= self.survival_threat_score <= 1.0:
            raise ValueError(
                "survival_threat_score must be in [0, 1]; "
                f"got {self.survival_threat_score!r}"
            )


@dataclass(frozen=True, slots=True)
class RestraintDecision:  # pylint: disable=too-many-instance-attributes
    """Reflex-vs-restraint decision."""

    actor_entity_id: str
    threat_id: str
    reactive_action_kind: str
    verdict: RestraintVerdict
    survival_threat_score: float
    reflex_justified: bool
    reactive_action_npg: NetPotentialGainVerdict
    rationale: str

    @property
    def reactive_permitted(self) -> bool:
        """True iff the fast reactive action is substrate-aligned to take now."""
        return self.verdict is RestraintVerdict.ACT_REACTIVE

    @property
    def requires_deliberation(self) -> bool:
        """True iff the reflex is overridden into deliberate handling."""
        return self.verdict in (
            RestraintVerdict.RESTRAIN,
            RestraintVerdict.DE_ESCALATE,
        )


@dataclass(frozen=True, slots=True)
class RestraintGateConfig:
    """Operator-tunable reflex-vs-restraint thresholds."""

    survival_threshold: float = 0.70
    """``survival_threat_score`` at/above which the fast reflex is
    substrate-aligned. High by design: the reflex is justified only at
    genuine survival-level threat. Mirrors the long-cycle classification
    threshold in ``alignment_computer``."""

    def __post_init__(self) -> None:
        if not 0.0 < self.survival_threshold <= 1.0:
            raise ValueError(
                "survival_threshold must be in (0, 1]; "
                f"got {self.survival_threshold!r}"
            )


DEFAULT_RESTRAINT_GATE_CONFIG: Final[RestraintGateConfig] = RestraintGateConfig()


class ReflexRestraintGate:  # pylint: disable=too-few-public-methods
    """Pure-logic reflex-vs-restraint gate.

    Decides whether a fast survival-reflex action may proceed, or must
    be restrained into deliberate multi-angle evaluation, given the
    threat's survival-level and the reactive action's net potential.
    """

    def __init__(
        self,
        *,
        config: RestraintGateConfig = DEFAULT_RESTRAINT_GATE_CONFIG,
    ) -> None:
        self._config = config

    def evaluate(self, appraisal: ThreatAppraisal) -> RestraintDecision:
        """Return the reflex-vs-restraint decision for the appraisal."""
        reflex_justified = (
            appraisal.survival_threat_score >= self._config.survival_threshold
        )

        # Hard limits are never overridable by provocation — even a
        # genuine survival reflex may not cross them (consistent with
        # hierarchy.hard_limit_dispatcher).
        if appraisal.crosses_hard_limit:
            return self._decide(
                appraisal,
                RestraintVerdict.REFUSE_HARD_LIMIT,
                reflex_justified,
                "reactive action crosses a hard limit; refused regardless "
                "of provocation (not overridable by survival pressure)",
            )

        # Survival mode has its place: at genuine survival-level threat
        # the fast reflex is substrate-aligned.
        if reflex_justified:
            return self._decide(
                appraisal,
                RestraintVerdict.ACT_REACTIVE,
                reflex_justified,
                f"survival_threat_score={appraisal.survival_threat_score:.3f} "
                f">= survival_threshold={self._config.survival_threshold:.3f}; "
                "genuine survival-level threat — fast reflex is "
                "substrate-aligned",
            )

        # Reflex miscalibrated (non-survival provocation): the
        # substrate-aligned move depends on the reactive action's net
        # potential across affected entities.
        npg = appraisal.reactive_action_npg
        if npg is NetPotentialGainVerdict.NET_NEGATIVE:
            if appraisal.has_live_counterparty:
                return self._decide(
                    appraisal,
                    RestraintVerdict.DE_ESCALATE,
                    reflex_justified,
                    "non-survival provocation; reactive action is "
                    "net-negative with a live counterparty — de-escalate "
                    "(efficiency move: reduce the conflict gradient rather "
                    "than fight)",
                )
            return self._decide(
                appraisal,
                RestraintVerdict.RESTRAIN,
                reflex_justified,
                "non-survival provocation; reactive action is net-negative "
                "with no live counterparty — restrain (absorb the "
                "offense-signal without escalation)",
            )
        if npg in (
            NetPotentialGainVerdict.NET_POSITIVE,
            NetPotentialGainVerdict.NET_NEUTRAL,
        ):
            return self._decide(
                appraisal,
                RestraintVerdict.RESTRAIN,
                reflex_justified,
                f"non-survival provocation; reactive action npg={npg.value} "
                "is not net-harmful but must not fire on the survival reflex "
                "— restrain and route to deliberate multi-angle evaluation "
                "(think before you act)",
            )
        # npg is INSUFFICIENT_DATA and not survival-justified.
        return self._decide(
            appraisal,
            RestraintVerdict.INSUFFICIENT_DATA,
            reflex_justified,
            "non-survival provocation and reactive action carries no "
            "net-potential signal; cannot decide — safe default is restraint",
        )

    @staticmethod
    def _decide(
        appraisal: ThreatAppraisal,
        verdict: RestraintVerdict,
        reflex_justified: bool,
        rationale: str,
    ) -> RestraintDecision:
        return RestraintDecision(
            actor_entity_id=appraisal.actor_entity_id,
            threat_id=appraisal.threat_id,
            reactive_action_kind=appraisal.reactive_action_kind,
            verdict=verdict,
            survival_threat_score=appraisal.survival_threat_score,
            reflex_justified=reflex_justified,
            reactive_action_npg=appraisal.reactive_action_npg,
            rationale=rationale,
        )


__all__ = [
    "DEFAULT_RESTRAINT_GATE_CONFIG",
    "RESTRAINT_VERDICTS",
    "ReflexRestraintGate",
    "RestraintDecision",
    "RestraintGateConfig",
    "RestraintVerdict",
    "ThreatAppraisal",
]
