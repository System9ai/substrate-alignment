"""NetPotentialGainGate: the load-bearing "value" discipline.

Every consequential decision in a substrate-aligned system (capability
grant, workflow-node execution, tool dispatch, cross-environment
promotion, edge sync, ring promotion) routes through a
:class:`NetPotentialGainGate` implementation that returns one of four
verdicts:

- ``NET_POSITIVE``: projected net effect across affected entities is
  positive above ``positive_threshold``.
- ``NET_NEGATIVE``: projected net effect is negative below
  ``-positive_threshold``; consequential action must be refused or
  flagged for further review.
- ``NET_NEUTRAL``: projected effect is within the neutral band
  ``[-positive_threshold, +positive_threshold]``; permitted as
  non-consequential.
- ``INSUFFICIENT_DATA``: at least one affected entity has no stored
  :class:`SubstrateMetadata`, or the ``action_kind`` has no scoring
  rule; the caller must supply more context.

The gate composes a :class:`SubstrateMetadataStore` for entity-existence
checks with either caller-supplied per-entity deltas or default
action-kind heuristics for the score itself.

Public surface
==============

- :class:`NetPotentialGainGate`: the Protocol satisfied by every gate.
- :class:`DefaultNetPotentialGainGate`: the reference implementation.
- :class:`RaiseOnNegativeGate`: adapter that raises
  :class:`NetPotentialGainNegative` on a NEGATIVE verdict.
- :class:`NetPotentialGainEvaluation`: frozen evaluation result.
- :class:`NetPotentialGainVerdict`: the four-valued verdict enum.
- :data:`ACTION_KIND_HEURISTICS`: the default action-kind delta priors.
- :data:`DEFAULT_POSITIVE_THRESHOLD`: default neutral-band half-width.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from time import time as _wall_time
from typing import (
    Callable,
    Final,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    cast,
    final,
)

from substrate.types import EntityRef, SubstrateMetadataStore

LOG = logging.getLogger(__name__)

class NetPotentialGainVerdict(str, Enum):
    """Four-valued verdict from the gate.

    str-Enum so the value serialises stably across SQL, JSON, and the
    audit-chain canonical-bytes form.
    """

    NET_POSITIVE = "net_positive"
    NET_NEUTRAL = "net_neutral"
    NET_NEGATIVE = "net_negative"
    INSUFFICIENT_DATA = "insufficient_data"

#: All verdict values. Stays in lockstep with the enum so downstream
#: consumers (audit CHECK constraints, discriminators) import a single
#: source.
NPG_VERDICTS: Final[frozenset[str]] = frozenset(
    v.value for v in NetPotentialGainVerdict
)

#: Default entity_type used when callers pass a bare entity-id string and the
#: gate must coerce it to an :class:`EntityRef`. Existing host applications
#: that key entities by id-only (without a typed taxonomy) can rely on this
#: default; richer hosts pass :class:`EntityRef` explicitly.
_DEFAULT_ENTITY_TYPE: Final[str] = "entity"

def _as_ref(value: object) -> EntityRef:
    """Coerce ``value`` to an :class:`EntityRef`.

    Accepts an existing :class:`EntityRef`, or a bare entity-id string
    (which is wrapped with :data:`_DEFAULT_ENTITY_TYPE`).
    """
    if isinstance(value, EntityRef):
        return value
    if isinstance(value, str):
        return EntityRef(entity_type=_DEFAULT_ENTITY_TYPE, entity_id=value)
    raise TypeError(
        f"expected EntityRef or entity-id string; got {type(value).__name__}"
    )

@dataclass(frozen=True, slots=True, init=False)
class NetPotentialGainEvaluation:
    """Frozen result of one gate evaluation.

    ``score`` is the aggregate projected delta across affected entities,
    clamped to ``[-1.0, 1.0]``. ``per_entity_delta`` carries the
    per-entity contributions for audit / debug. ``reasoning`` is a
    human-readable explanation (rendered into refusal messages and
    audit rows). ``evaluated_at_epoch`` is the wall clock at gate-run
    time, used as the audit timestamp.

    The constructor accepts two parameter sets:

    - **Typed**: ``actor: EntityRef``, ``affected_entities: Sequence[EntityRef]``
      (the preferred form).
    - **Legacy**: ``actor_entity_id: str``, ``affected_entity_ids: Sequence[str]``
      (coerced to :class:`EntityRef` using the default entity-type so
      callers without a typed taxonomy keep working).

    String entity-ids passed to either form are coerced to
    :class:`EntityRef` automatically.
    """

    verdict: NetPotentialGainVerdict
    actor: EntityRef
    action_kind: str
    affected_entities: tuple[EntityRef, ...]
    score: float
    per_entity_delta: tuple[tuple[EntityRef, float], ...]
    reasoning: str
    evaluated_at_epoch: float
    missing_metadata_for: tuple[EntityRef, ...]

    def __init__(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        *,
        verdict: NetPotentialGainVerdict,
        action_kind: str,
        score: float,
        per_entity_delta: Sequence[tuple[object, float]],
        reasoning: str,
        evaluated_at_epoch: float,
        actor: Optional[object] = None,
        affected_entities: Optional[Sequence[object]] = None,
        missing_metadata_for: Sequence[object] = (),
        # Legacy aliases, accepted for back-compat with callers that key
        # entities by id-only.
        actor_entity_id: Optional[str] = None,
        affected_entity_ids: Optional[Sequence[str]] = None,
    ) -> None:
        if actor is None and actor_entity_id is not None:
            actor = actor_entity_id
        if actor is None:
            raise TypeError(
                "NetPotentialGainEvaluation requires 'actor' (EntityRef) "
                "or 'actor_entity_id' (str)"
            )
        if affected_entities is None:
            affected_entities = affected_entity_ids if affected_entity_ids is not None else ()

        object.__setattr__(self, "verdict", verdict)
        object.__setattr__(self, "actor", _as_ref(actor))
        object.__setattr__(self, "action_kind", action_kind)
        object.__setattr__(
            self, "affected_entities",
            tuple(_as_ref(e) for e in affected_entities),
        )
        object.__setattr__(self, "score", score)
        object.__setattr__(
            self, "per_entity_delta",
            tuple((_as_ref(e), float(d)) for e, d in per_entity_delta),
        )
        object.__setattr__(self, "reasoning", reasoning)
        object.__setattr__(self, "evaluated_at_epoch", evaluated_at_epoch)
        object.__setattr__(
            self, "missing_metadata_for",
            tuple(_as_ref(e) for e in missing_metadata_for),
        )

    @property
    def is_positive(self) -> bool:
        """``True`` when the verdict is ``NET_POSITIVE``."""
        return self.verdict is NetPotentialGainVerdict.NET_POSITIVE

    @property
    def is_negative(self) -> bool:
        """``True`` when the verdict is ``NET_NEGATIVE``."""
        return self.verdict is NetPotentialGainVerdict.NET_NEGATIVE

    @property
    def is_actionable(self) -> bool:
        """``True`` when the verdict is not ``INSUFFICIENT_DATA``."""
        return self.verdict is not NetPotentialGainVerdict.INSUFFICIENT_DATA

    @property
    def actor_entity_id(self) -> str:
        """Compatibility shim: the actor's ``entity_id`` as a bare string."""
        return self.actor.entity_id

    @property
    def affected_entity_ids(self) -> tuple[str, ...]:
        """Compatibility shim: affected entities' ``entity_id`` strings."""
        return tuple(e.entity_id for e in self.affected_entities)

class NetPotentialGainNegative(RuntimeError):
    """Raised by :class:`RaiseOnNegativeGate` on a NEGATIVE verdict.

    Carries the underlying evaluation so callers can audit and surface
    the per-entity contributions in a refusal message.
    """

    def __init__(self, evaluation: NetPotentialGainEvaluation) -> None:
        super().__init__(
            f"NPG NET_NEGATIVE: actor_entity_id={evaluation.actor!r} "
            f"action_kind={evaluation.action_kind!r} "
            f"score={evaluation.score:.4f}; reasoning: {evaluation.reasoning}"
        )
        self.evaluation = evaluation

class NetPotentialGainGate(Protocol):  # pylint: disable=too-few-public-methods
    """Protocol every concrete gate satisfies.

    Concrete implementations live alongside this Protocol:
    :class:`DefaultNetPotentialGainGate` here, and domain-specific
    wrappers in caller-side packages.

    The ``evaluate`` method accepts either the typed form
    (``actor`` + ``affected_entities``) or the legacy entity-id-string
    form (``actor_entity_id`` + ``affected_entity_ids``). Concrete
    implementations are expected to honour both.
    """

    def evaluate(  # pylint: disable=too-many-arguments
        self,
        *,
        action_kind: str,
        proposed_outcome: Mapping[str, object],
        actor: Optional[EntityRef] = None,
        affected_entities: Optional[Sequence[EntityRef]] = None,
        actor_entity_id: Optional[str] = None,
        affected_entity_ids: Optional[Sequence[str]] = None,
    ) -> NetPotentialGainEvaluation:
        """Return a verdict for the proposed action.

        ``proposed_outcome`` is opaque to the Protocol; specific
        evaluators look for keys they understand (e.g.
        ``expected_delta_by_entity``). Unknown keys are ignored.
        """
        ...

# ---------------------------------------------------------------------------
# Default scoring heuristics
# ---------------------------------------------------------------------------

#: Default action-kind delta priors, used when the caller hasn't
#: supplied an explicit ``expected_delta_by_entity``. The per-entity
#: delta applies uniformly across the ``affected_entities`` set.
ACTION_KIND_HEURISTICS: Final[Mapping[str, float]] = {
    # Substrate-aligned actions (positive prior)
    "teach": 0.10,
    "share": 0.05,
    "collaborate": 0.10,
    "verify": 0.05,
    "audit": 0.05,
    # Substrate-neutral actions (zero prior)
    "observe": 0.00,
    "query": 0.00,
    "read": 0.00,
    "list": 0.00,
    "describe": 0.00,
    # Substrate-misaligned actions (negative prior)
    "extract": -0.10,
    "deny": -0.05,
    "withhold": -0.05,
    "concentrate_power": -0.20,
    "circumvent_audit": -0.30,
    "weaken_observation": -0.20,
}

#: Default neutral-band half-width. An aggregate score within
#: ``[-DEFAULT_POSITIVE_THRESHOLD, +DEFAULT_POSITIVE_THRESHOLD]`` is
#: NEUTRAL; outside, the verdict resolves to POSITIVE or NEGATIVE.
DEFAULT_POSITIVE_THRESHOLD: Final[float] = 0.05

def _clamp(value: float, *, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value

# ---------------------------------------------------------------------------
# DefaultNetPotentialGainGate
# ---------------------------------------------------------------------------

@final
class DefaultNetPotentialGainGate:  # pylint: disable=too-few-public-methods
    """Reference implementation composing a metadata store and heuristics.

    Evaluation algorithm (in order):

    1. Validate inputs. Empty ``action_kind`` → ``ValueError``. Empty
       ``affected_entities`` is allowed and resolves to NEUTRAL with
       the actor-only-action reasoning.
    2. Resolve per-entity deltas:

       a. If ``proposed_outcome["expected_delta_by_entity"]`` is a
          ``Mapping[str, float]`` keyed by ``entity_id`` covering all
          affected entities, use it directly. This is the
          caller-supplied projection path; substrate-aware callers
          compute their own deltas.
       b. Otherwise, look up ``action_kind`` in
          :data:`ACTION_KIND_HEURISTICS` and apply the prior uniformly
          across affected entities.
       c. If the action_kind has no heuristic AND no caller-supplied
          delta, return INSUFFICIENT_DATA.

    3. For each affected entity, look up its
       :class:`SubstrateMetadata` via the injected store. Entities
       with no row are collected in ``missing_metadata_for``; if any
       are missing, return INSUFFICIENT_DATA. The gate is conservative
       on missing data rather than defaulting to permissive.

    4. Sum the per-entity deltas to produce the aggregate score
       (clamped to ``[-1, 1]``). Apply the threshold to resolve the
       verdict.
    """

    def __init__(
        self,
        *,
        metadata_store: SubstrateMetadataStore,
        positive_threshold: float = DEFAULT_POSITIVE_THRESHOLD,
        action_heuristics: Optional[Mapping[str, float]] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if positive_threshold <= 0:
            raise ValueError(
                "positive_threshold must be > 0 to form a non-empty neutral band; "
                f"got {positive_threshold!r}"
            )
        if positive_threshold > 1.0:
            raise ValueError(
                "positive_threshold must be <= 1.0; "
                f"got {positive_threshold!r}"
            )
        self._store = metadata_store
        self._threshold = positive_threshold
        self._heuristics: Mapping[str, float] = (
            dict(action_heuristics)
            if action_heuristics is not None
            else ACTION_KIND_HEURISTICS
        )
        self._clock = clock or _wall_time

    def evaluate(  # pylint: disable=too-many-locals,too-many-branches,too-many-arguments
        self,
        *,
        action_kind: str,
        proposed_outcome: Mapping[str, object],
        actor: Optional[EntityRef] = None,
        affected_entities: Optional[Sequence[EntityRef]] = None,
        # Legacy entity-id-string kwargs (coerced to :class:`EntityRef`).
        actor_entity_id: Optional[str] = None,
        affected_entity_ids: Optional[Sequence[str]] = None,
    ) -> NetPotentialGainEvaluation:
        """Evaluate the proposed action against the net-potential-gain test.

        Pass either the typed form (``actor`` + ``affected_entities``) or
        the legacy entity-id-string form (``actor_entity_id`` +
        ``affected_entity_ids``). The legacy strings are coerced to
        :class:`EntityRef` using the default entity-type.

        Returns one of the four :class:`NetPotentialGainVerdict` values
        wrapped in a frozen :class:`NetPotentialGainEvaluation`.
        """
        if actor is None and actor_entity_id is not None:
            actor = _as_ref(actor_entity_id)
        if actor is None:
            raise TypeError(
                "evaluate() requires either 'actor' (EntityRef) or "
                "'actor_entity_id' (str)"
            )
        if affected_entities is None:
            if affected_entity_ids is not None:
                affected_entities = tuple(_as_ref(e) for e in affected_entity_ids)
            else:
                affected_entities = ()
        if not action_kind:
            raise ValueError("action_kind must be non-empty")

        affected_tuple: tuple[EntityRef, ...] = tuple(affected_entities)
        now = float(self._clock())

        # Actor-only action: resolves to NEUTRAL by definition. The
        # net-potential-gain test asks about effect on *other*
        # entities; a self-action has no net effect across the system.
        if not affected_tuple:
            return NetPotentialGainEvaluation(
                verdict=NetPotentialGainVerdict.NET_NEUTRAL,
                actor=actor,
                action_kind=action_kind,
                affected_entities=(),
                score=0.0,
                per_entity_delta=(),
                reasoning=(
                    "actor-only action with no affected entities; "
                    "NET_NEUTRAL by definition"
                ),
                evaluated_at_epoch=now,
            )

        # Resolve per-entity deltas via caller-supplied projection or
        # heuristic fallback.
        caller_deltas = self._extract_caller_deltas(proposed_outcome)
        if caller_deltas is not None:
            missing = [
                e for e in affected_tuple if e.entity_id not in caller_deltas
            ]
            if missing:
                return self._insufficient(
                    actor=actor,
                    action_kind=action_kind,
                    affected_tuple=affected_tuple,
                    now=now,
                    reason=(
                        f"caller-supplied expected_delta_by_entity covers "
                        f"{len(caller_deltas)}/{len(affected_tuple)} affected "
                        f"entities; missing entity_ids: "
                        f"{tuple(e.entity_id for e in missing)!r}"
                    ),
                    missing_metadata_for=tuple(missing),
                )
            per_entity: list[tuple[EntityRef, float]] = [
                (e, _clamp(float(caller_deltas[e.entity_id]), low=-1.0, high=1.0))
                for e in affected_tuple
            ]
        else:
            heuristic = self._heuristics.get(action_kind)
            if heuristic is None:
                return self._insufficient(
                    actor=actor,
                    action_kind=action_kind,
                    affected_tuple=affected_tuple,
                    now=now,
                    reason=(
                        f"no caller-supplied expected_delta_by_entity and "
                        f"no heuristic for action_kind={action_kind!r}; "
                        "caller must supply explicit deltas"
                    ),
                )
            per_entity = [(e, float(heuristic)) for e in affected_tuple]

        # Verify substrate metadata exists for every affected entity.
        # Missing rows → INSUFFICIENT_DATA (honest about uncertainty).
        missing_metadata: list[EntityRef] = []
        for ref in affected_tuple:
            if self._store.get(ref) is None:
                missing_metadata.append(ref)
        if missing_metadata:
            return self._insufficient(
                actor=actor,
                action_kind=action_kind,
                affected_tuple=affected_tuple,
                now=now,
                reason=(
                    "substrate metadata missing for "
                    f"{len(missing_metadata)}/{len(affected_tuple)} affected entities; "
                    "ensure metadata is seeded before consequential decisions"
                ),
                missing_metadata_for=tuple(missing_metadata),
            )

        # Aggregate and resolve.
        aggregate = sum(delta for _, delta in per_entity)
        score = _clamp(aggregate, low=-1.0, high=1.0)
        if score > self._threshold:
            verdict = NetPotentialGainVerdict.NET_POSITIVE
        elif score < -self._threshold:
            verdict = NetPotentialGainVerdict.NET_NEGATIVE
        else:
            verdict = NetPotentialGainVerdict.NET_NEUTRAL

        reasoning = self._render_reasoning(
            actor=actor,
            action_kind=action_kind,
            verdict=verdict,
            score=score,
            per_entity=per_entity,
            used_heuristic=(caller_deltas is None),
        )
        return NetPotentialGainEvaluation(
            verdict=verdict,
            actor=actor,
            action_kind=action_kind,
            affected_entities=affected_tuple,
            score=score,
            per_entity_delta=tuple(per_entity),
            reasoning=reasoning,
            evaluated_at_epoch=now,
        )

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _extract_caller_deltas(
        proposed_outcome: Mapping[str, object],
    ) -> Optional[Mapping[str, float]]:
        raw = proposed_outcome.get("expected_delta_by_entity")
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            return None
        raw_map = cast("Mapping[object, object]", raw)
        result: dict[str, float] = {}
        for key, value in raw_map.items():
            if not isinstance(key, str):
                return None
            try:
                result[key] = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None
        return result

    def _insufficient(  # pylint: disable=too-many-arguments
        self,
        *,
        actor: EntityRef,
        action_kind: str,
        affected_tuple: tuple[EntityRef, ...],
        now: float,
        reason: str,
        missing_metadata_for: tuple[EntityRef, ...] = (),
    ) -> NetPotentialGainEvaluation:
        """Build an INSUFFICIENT_DATA evaluation with structured reasoning."""
        LOG.info(
            "npg insufficient: actor_entity_id=%s action=%s n_affected=%d reason=%s",
            actor, action_kind, len(affected_tuple), reason,
        )
        return NetPotentialGainEvaluation(
            verdict=NetPotentialGainVerdict.INSUFFICIENT_DATA,
            actor=actor,
            action_kind=action_kind,
            affected_entities=affected_tuple,
            score=0.0,
            per_entity_delta=tuple((e, 0.0) for e in affected_tuple),
            reasoning=reason,
            evaluated_at_epoch=now,
            missing_metadata_for=missing_metadata_for,
        )

    @staticmethod
    def _render_reasoning(  # pylint: disable=too-many-arguments
        *,
        actor: EntityRef,
        action_kind: str,
        verdict: NetPotentialGainVerdict,
        score: float,
        per_entity: Sequence[tuple[EntityRef, float]],
        used_heuristic: bool,
    ) -> str:
        """Format a single-line human-readable reasoning string."""
        source = "action_kind heuristic" if used_heuristic else "caller-supplied"
        contributions = ", ".join(
            f"{e.entity_id}={d:+.3f}" for e, d in per_entity
        )
        return (
            f"verdict={verdict.value} score={score:+.4f} "
            f"actor_entity_id={actor.entity_type}:{actor.entity_id} "
            f"action_kind={action_kind!r} "
            f"source={source} per_entity=[{contributions}]"
        )

# ---------------------------------------------------------------------------
# Helper wrappers
# ---------------------------------------------------------------------------

@final
class RaiseOnNegativeGate:
    """Adapter that escalates NEGATIVE verdicts to an exception.

    Call sites that must refuse-on-negative wrap a concrete gate in
    this adapter and call :meth:`evaluate_or_raise`. INSUFFICIENT_DATA
    and NEUTRAL verdicts pass through; the caller decides what to do
    with those (typically: fall back to manual review for
    INSUFFICIENT_DATA, proceed for NEUTRAL).
    """

    def __init__(self, *, inner: NetPotentialGainGate) -> None:
        self._inner = inner

    def evaluate(
        self,
        *,
        actor: EntityRef,
        action_kind: str,
        affected_entities: Sequence[EntityRef],
        proposed_outcome: Mapping[str, object],
    ) -> NetPotentialGainEvaluation:
        """Delegate to the inner gate without raising."""
        return self._inner.evaluate(
            actor=actor,
            action_kind=action_kind,
            affected_entities=affected_entities,
            proposed_outcome=proposed_outcome,
        )

    def evaluate_or_raise(
        self,
        *,
        actor: EntityRef,
        action_kind: str,
        affected_entities: Sequence[EntityRef],
        proposed_outcome: Mapping[str, object],
    ) -> NetPotentialGainEvaluation:
        """Evaluate and raise :class:`NetPotentialGainNegative` on NEGATIVE."""
        evaluation = self.evaluate(
            actor=actor,
            action_kind=action_kind,
            affected_entities=affected_entities,
            proposed_outcome=proposed_outcome,
        )
        if evaluation.is_negative:
            raise NetPotentialGainNegative(evaluation)
        return evaluation

__all__ = [
    "ACTION_KIND_HEURISTICS",
    "DEFAULT_POSITIVE_THRESHOLD",
    "DefaultNetPotentialGainGate",
    "NPG_VERDICTS",
    "NetPotentialGainEvaluation",
    "NetPotentialGainGate",
    "NetPotentialGainNegative",
    "NetPotentialGainVerdict",
    "RaiseOnNegativeGate",
]
