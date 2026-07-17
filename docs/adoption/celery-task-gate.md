# Wrapping Celery tasks with the NPG gate

This recipe shows how to wire the [net-potential-gain gate](../concepts/npg-gate.md) into a Celery worker so every consequential task routes its decision through the gate before executing the task body. Task signatures don't change; the gating happens in a single decorator.

## What you need

- A Celery application configured against a broker.
- A `SubstrateMetadataStore` (this recipe uses `InMemorySubstrateMetadataStore` for clarity; production swaps in a Postgres / Redis implementation of the Protocol).
- A mapping from a task payload to an `actor: EntityRef` and a list of `affected_entities: list[EntityRef]`. This is application-specific.

## Module layout

```
app/
├── celery_app.py          # Celery app + the gating decorator
├── substrate_deps.py      # The substrate gate; constructed once per worker process
└── tasks/
    └── workflows.py       # The actual task functions, wrapped with @substrate_gate
```

## The wiring

```python
# app/substrate_deps.py
from __future__ import annotations

from functools import lru_cache

from substrate import (
    DefaultNetPotentialGainGate,
    InMemorySubstrateMetadataStore,
    RaiseOnNegativeGate,
    SubstrateMetadataStore,
)


@lru_cache(maxsize=1)
def get_store() -> SubstrateMetadataStore:
    """Per-worker-process store. Swap this in production."""
    return InMemorySubstrateMetadataStore()


@lru_cache(maxsize=1)
def get_gate() -> RaiseOnNegativeGate:
    """Per-worker-process gate. RaiseOnNegativeGate refuses NEGATIVE."""
    return RaiseOnNegativeGate(
        inner=DefaultNetPotentialGainGate(metadata_store=get_store()),
    )
```

```python
# app/celery_app.py
from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Sequence

from celery import Celery

from substrate import (
    EntityRef,
    NetPotentialGainNegative,
    NetPotentialGainVerdict,
)

from app.substrate_deps import get_gate

LOG = logging.getLogger(__name__)
app = Celery("app", broker="...", backend="...")


class GateRefused(RuntimeError):
    """Raised in-process when the gate refuses a task."""


def substrate_gate(
    *,
    action_kind: str,
    actor_resolver: Callable[..., EntityRef],
    affected_resolver: Callable[..., Sequence[EntityRef]],
    outcome_resolver: Callable[..., dict[str, Any]] = lambda *_a, **_kw: {},
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Wrap a Celery task with the NPG gate.

    The decorator evaluates the gate before the task body runs. On
    NET_POSITIVE / NET_NEUTRAL, the task body executes. On
    NET_NEGATIVE, the task is aborted and a structured refusal payload
    is returned so the caller can audit the refusal. On
    INSUFFICIENT_DATA, the task is also aborted (with a distinct payload
    so the caller can branch: "retry once the entity is seeded" vs.
    "refused outright").
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            gate = get_gate()
            actor = actor_resolver(*args, **kwargs)
            affected = tuple(affected_resolver(*args, **kwargs))
            outcome = outcome_resolver(*args, **kwargs)
            try:
                evaluation = gate.evaluate_or_raise(
                    actor=actor,
                    action_kind=action_kind,
                    affected_entities=affected,
                    proposed_outcome=outcome,
                )
            except NetPotentialGainNegative as exc:
                LOG.warning(
                    "substrate_gate refused task %s: score=%.3f reason=%s",
                    fn.__name__, exc.evaluation.score, exc.evaluation.reasoning,
                )
                return {
                    "status": "refused",
                    "reason": "net_potential_gain_negative",
                    "score": exc.evaluation.score,
                    "per_entity": [
                        {"entity_id": e.entity_id, "delta": d}
                        for e, d in exc.evaluation.per_entity_delta
                    ],
                }
            if evaluation.verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA:
                LOG.warning(
                    "substrate_gate insufficient for task %s; missing=%s",
                    fn.__name__,
                    [e.entity_id for e in evaluation.missing_metadata_for],
                )
                return {
                    "status": "insufficient_data",
                    "missing_for": [e.entity_id for e in evaluation.missing_metadata_for],
                }
            return fn(*args, **kwargs)

        return wrapper

    return decorator
```

```python
# app/tasks/workflows.py
from __future__ import annotations

from substrate import EntityRef
from app.celery_app import app, substrate_gate


@app.task
@substrate_gate(
    action_kind="teach",
    actor_resolver=lambda *_a, agent_id, **_kw: EntityRef("agent", agent_id),
    affected_resolver=lambda *_a, student_ids, **_kw: [
        EntityRef("user", sid) for sid in student_ids
    ],
)
def deliver_lesson(*, agent_id: str, student_ids: list[str], content: str) -> dict:
    # ... actual task body ...
    return {"status": "delivered", "students": len(student_ids)}
```

## What this wiring buys

- **Tasks remain idiomatic.** The Celery task signature looks like every other Celery task; the gating is transparent unless it refuses.
- **Per-task action_kind.** Each task declares the action vocabulary; the gate's heuristic table applies to the correct verb.
- **Structured refusals.** Refusals return a payload (status, score, per-entity contributions), so downstream pipelines branch on the result rather than catching an exception that loses context across the broker.
- **Per-worker gate caching.** The `lru_cache` on `get_gate()` keeps one gate instance per worker process; the store survives between tasks.

## What this wiring deliberately does not do

- **It does not retry on `INSUFFICIENT_DATA` automatically.** Auto-retry hides metadata-seeding gaps; the package's discipline is to surface them. The caller branches on the result.
- **It does not chain refusal-payload into another task.** If you want a refused task to spawn a "vetting" task, do so explicitly at the call site. Implicit chaining couples behaviours that should remain reviewable.
- **It does not couple to Celery's signal mechanism.** Signals fire too late (post-task-execution); the gate has to evaluate *before* the task body, so a decorator is the right shape.

## Testing

```python
# tests/test_gating.py
import pytest
from substrate import AlignmentVector, EntityRef, SubstrateMode

from app.substrate_deps import get_store


@pytest.fixture(autouse=True)
def clear_store():
    get_store().clear()    # InMemorySubstrateMetadataStore exposes .clear()
    yield


def test_deliver_lesson_refuses_when_metadata_missing(celery_app):
    from app.tasks.workflows import deliver_lesson
    result = deliver_lesson.apply(
        kwargs={"agent_id": "alice", "student_ids": ["bob"], "content": "..."},
    ).result
    assert result["status"] == "insufficient_data"
    assert result["missing_for"] == ["bob"]


def test_deliver_lesson_executes_when_metadata_present(celery_app):
    from app.tasks.workflows import deliver_lesson
    get_store().upsert(
        EntityRef("user", "bob"),
        substrate_mode=SubstrateMode.MIXED,
        classifier="test", classifier_rationale="seeded",
        alignment_vector=AlignmentVector(0.5, 0.5, 0.5, 0.5),
        net_potential=0.5,
    )
    get_store().upsert(
        EntityRef("agent", "alice"),
        substrate_mode=SubstrateMode.LONG_CYCLE,
        classifier="test", classifier_rationale="seeded",
        alignment_vector=AlignmentVector(0.8, 0.8, 0.8, 0.8),
        net_potential=0.8,
    )
    result = deliver_lesson.apply(
        kwargs={"agent_id": "alice", "student_ids": ["bob"], "content": "..."},
    ).result
    assert result["status"] == "delivered"
```

## See also

- [Concept: NPG gate](../concepts/npg-gate.md). The rationale for the four-verdict shape and the neutral band.
- [Spec: NPG gate Protocol](../../spec/npg-gate-protocol.md). The normative behaviour.
- [Example 01](../../python/examples/01_npg_gate.py). Runnable, framework-free demonstration of the gate.
- [FastAPI permission gate](fastapi-permission-gate.md). The synchronous, request-response variant of this pattern.
