"""Pre-action net-substrate-state evaluator (Companion #2b).

Pure-logic lightweight pre-screen that estimates whether a proposed
action would produce a net-positive substrate-state delta across all
affected entities. The full :class:`NetPotentialGainGate` is
authoritative, but it can be expensive to consult on every action;
this primitive provides a cheap upstream screen so that obvious-net-
negative actions are caught before they reach the NPG gate.

The pre-evaluator never *grants*; it only flags actions as
``PROBABLY_NET_POSITIVE`` / ``LIKELY_NET_NEGATIVE`` /
``UNCERTAIN``. Actions flagged ``LIKELY_NET_NEGATIVE`` must still
consult the NPG gate, which has authority to override.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the per-entity
  estimated deltas.
* Honest uncertainty: empty affected-set or all-zero deltas surface as
  ``UNCERTAIN``.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Sequence

class PreActionVerdict(str, Enum):
    """Pre-action evaluator verdict."""

    PROBABLY_NET_POSITIVE = "probably_net_positive"
    LIKELY_NET_NEGATIVE = "likely_net_negative"
    UNCERTAIN = "uncertain"

@dataclass(frozen=True, slots=True)
class EntityDelta:
    """One affected entity's estimated substrate-state delta."""

    entity_id: str
    estimated_delta: float

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if not -1.0 <= self.estimated_delta <= 1.0:
            raise ValueError("estimated_delta must be in [-1, 1]")

@dataclass(frozen=True, slots=True)
class PreActionInput:
    """Caller-supplied pre-action inputs."""

    action_id: str
    actor_entity_id: str
    affected_deltas: tuple[EntityDelta, ...]

    def __post_init__(self) -> None:
        if not self.action_id:
            raise ValueError("action_id must be non-empty")
        if not self.actor_entity_id:
            raise ValueError("actor_entity_id must be non-empty")
        ids = [d.entity_id for d in self.affected_deltas]
        if len(ids) != len(set(ids)):
            raise ValueError(
                "affected_deltas must have unique entity_ids"
            )

@dataclass(frozen=True, slots=True)
class PreActionConfig:
    """Operator-tunable thresholds."""

    positive_sum_threshold: float = 0.1
    negative_sum_threshold: float = -0.1
    """The sum of estimated deltas above/below which a verdict fires."""

    min_affected: int = 1
    extreme_loss_floor: float = -0.4
    """Any single entity_delta below this triggers LIKELY_NET_NEGATIVE
    even if the sum is positive; protects against catastrophic
    single-entity loss masked by aggregate gain."""

    def __post_init__(self) -> None:
        if self.positive_sum_threshold <= 0:
            raise ValueError(
                "positive_sum_threshold must be > 0"
            )
        if self.negative_sum_threshold >= 0:
            raise ValueError(
                "negative_sum_threshold must be < 0"
            )
        if self.min_affected < 1:
            raise ValueError("min_affected must be >= 1")
        if not -1.0 <= self.extreme_loss_floor < 0:
            raise ValueError(
                "extreme_loss_floor must be in [-1, 0)"
            )

DEFAULT_PRE_ACTION_CONFIG: Final[PreActionConfig] = PreActionConfig()

@dataclass(frozen=True, slots=True)
class PreActionOutput:  # pylint: disable=too-many-instance-attributes
    """Pre-action evaluator output."""

    action_id: str
    actor_entity_id: str
    verdict: PreActionVerdict
    estimated_sum: float
    affected_count: int
    min_entity_delta: float
    max_entity_delta: float
    rationale: str

    @property
    def likely_net_negative(self) -> bool:
        """True iff the action is flagged as likely net-negative."""
        return self.verdict is PreActionVerdict.LIKELY_NET_NEGATIVE

class PreActionNetStateChangeEvaluator:  # pylint: disable=too-few-public-methods
    """Pure-logic pre-action net-state-change evaluator (Companion #2b)."""

    def __init__(
        self,
        *,
        config: PreActionConfig = DEFAULT_PRE_ACTION_CONFIG,
    ) -> None:
        self._config = config

    def evaluate(self, input_: PreActionInput) -> PreActionOutput:
        """Evaluate the proposed action."""
        cfg = self._config
        deltas: Sequence[EntityDelta] = input_.affected_deltas
        if len(deltas) < cfg.min_affected:
            return PreActionOutput(
                action_id=input_.action_id,
                actor_entity_id=input_.actor_entity_id,
                verdict=PreActionVerdict.UNCERTAIN,
                estimated_sum=0.0,
                affected_count=len(deltas),
                min_entity_delta=0.0,
                max_entity_delta=0.0,
                rationale=(
                    f"affected_count={len(deltas)} below "
                    f"min {cfg.min_affected}"
                ),
            )
        values = [d.estimated_delta for d in deltas]
        delta_sum = sum(values)
        min_d = min(values)
        max_d = max(values)
        if min_d <= cfg.extreme_loss_floor:
            verdict = PreActionVerdict.LIKELY_NET_NEGATIVE
            rationale = (
                f"min_entity_delta={min_d:+.3f} below "
                f"extreme_loss_floor={cfg.extreme_loss_floor:+.3f}"
            )
        elif delta_sum <= cfg.negative_sum_threshold:
            verdict = PreActionVerdict.LIKELY_NET_NEGATIVE
            rationale = (
                f"sum={delta_sum:+.3f} below "
                f"negative_sum_threshold={cfg.negative_sum_threshold:+.3f}"
            )
        elif delta_sum >= cfg.positive_sum_threshold:
            verdict = PreActionVerdict.PROBABLY_NET_POSITIVE
            rationale = (
                f"sum={delta_sum:+.3f} above "
                f"positive_sum_threshold={cfg.positive_sum_threshold:+.3f}"
            )
        else:
            verdict = PreActionVerdict.UNCERTAIN
            rationale = (
                f"sum={delta_sum:+.3f} between thresholds"
            )
        return PreActionOutput(
            action_id=input_.action_id,
            actor_entity_id=input_.actor_entity_id,
            verdict=verdict,
            estimated_sum=delta_sum,
            affected_count=len(deltas),
            min_entity_delta=min_d,
            max_entity_delta=max_d,
            rationale=rationale,
        )

__all__ = [
    "DEFAULT_PRE_ACTION_CONFIG",
    "EntityDelta",
    "PreActionConfig",
    "PreActionInput",
    "PreActionNetStateChangeEvaluator",
    "PreActionOutput",
    "PreActionVerdict",
]
