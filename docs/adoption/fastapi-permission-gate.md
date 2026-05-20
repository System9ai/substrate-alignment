# Wiring the NPG gate into a FastAPI permission flow

This recipe shows how to wire the [net-potential-gain gate](../concepts/npg-gate.md) into a FastAPI application so every consequential endpoint routes its permission decision through the gate.

The pattern is small (~30 lines of glue), but pinning it down here means every FastAPI consumer of substrate-alignment ends up with the same wiring.

## What you need

- A FastAPI application.
- A `SubstrateMetadataStore` instance. The recipe assumes
  `InMemorySubstrateMetadataStore` for clarity; in production you would
  implement the Protocol against your persistence layer.
- An auth mechanism that resolves a request to an `actor: EntityRef`.

## Module layout

```
app/
├── main.py              # FastAPI application
├── deps.py              # Dependency-injection wiring (the substrate gate lives here)
└── routes/
    └── permissions.py   # Endpoints that consume the dependency
```

## The wiring

```python
# app/deps.py
from __future__ import annotations

from functools import lru_cache
from fastapi import Depends, HTTPException, status
from substrate import (
    DefaultNetPotentialGainGate, EntityRef,
    InMemorySubstrateMetadataStore, NetPotentialGainNegative,
    NetPotentialGainVerdict, RaiseOnNegativeGate,
    SubstrateMetadataStore,
)


@lru_cache(maxsize=1)
def get_store() -> SubstrateMetadataStore:
    """The Protocol-typed store. Swap this implementation in production."""
    return InMemorySubstrateMetadataStore()


@lru_cache(maxsize=1)
def get_gate() -> RaiseOnNegativeGate:
    """Single gate instance per process. RaiseOnNegativeGate refuses NEGATIVE."""
    return RaiseOnNegativeGate(
        inner=DefaultNetPotentialGainGate(metadata_store=get_store()),
    )


async def actor_from_request(...) -> EntityRef:
    """Your auth mechanism resolves the request to an EntityRef.

    Implementations are application-specific; e.g. JWT subject → user_id
    plus a constant entity_type.
    """
    ...
```

```python
# app/routes/permissions.py
from __future__ import annotations

from typing import Sequence
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from substrate import EntityRef, NetPotentialGainNegative, RaiseOnNegativeGate

from app.deps import actor_from_request, get_gate

router = APIRouter()


class GrantRequest(BaseModel):
    action_kind: str
    affected_entity_ids: Sequence[str]
    expected_delta_by_entity: dict[str, float] | None = None


@router.post("/permissions/grant")
async def grant(
    req: GrantRequest,
    actor: EntityRef = Depends(actor_from_request),
    gate: RaiseOnNegativeGate = Depends(get_gate),
) -> dict[str, str]:
    affected = [EntityRef("user", eid) for eid in req.affected_entity_ids]
    outcome = {}
    if req.expected_delta_by_entity is not None:
        outcome["expected_delta_by_entity"] = req.expected_delta_by_entity

    try:
        evaluation = gate.evaluate_or_raise(
            actor=actor,
            action_kind=req.action_kind,
            affected_entities=affected,
            proposed_outcome=outcome,
        )
    except NetPotentialGainNegative as exc:
        # Refused: surface the per-entity contributions so the caller can debug.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "reason": "net_potential_gain_negative",
                "score": exc.evaluation.score,
                "per_entity": [
                    {"entity_id": e.entity_id, "delta": d}
                    for e, d in exc.evaluation.per_entity_delta
                ],
                "reasoning": exc.evaluation.reasoning,
            },
        )

    if evaluation.verdict.value == "insufficient_data":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "insufficient_data",
                "missing_for": [e.entity_id for e in evaluation.missing_metadata_for],
                "reasoning": evaluation.reasoning,
            },
        )

    return {"verdict": evaluation.verdict.value}
```

## What this wiring buys

- Every endpoint that goes through `get_gate()` is on the same gate. There is no per-endpoint configuration drift.
- The gate's `INSUFFICIENT_DATA` verdict maps cleanly to `409 Conflict` ("retry with explicit deltas or seed the missing metadata"), distinct from `403 Forbidden` ("refused on negative net gain"). Clients can write differentiated retry logic.
- Swapping the storage backend is a one-line change in `get_store()` — the gate and the endpoints don't know about persistence.
- Tests construct a fresh `InMemorySubstrateMetadataStore`, seed the entities they exercise, and call the endpoint as usual.

## What this wiring deliberately does not do

- It does not couple the gate to FastAPI's middleware stack. Middleware-level gates create surprise refusals at unrelated endpoints; an explicit `Depends(get_gate)` keeps the surface honest.
- It does not auto-seed metadata for unrecognised entities. `INSUFFICIENT_DATA` is the conformant response; auto-seeding would silently default-to-permissive and contradict the [NPG specification](../../spec/npg-gate-protocol.md).
- It does not surface the gate's internals through the HTTP response when the verdict is positive. Audit-chain records are the operator surface for those.

## Testing

```python
# tests/routes/test_permissions.py
from fastapi.testclient import TestClient
from substrate import AlignmentVector, EntityRef, SubstrateMode

def test_grant_refuses_on_net_negative(client: TestClient, store) -> None:
    bob = EntityRef("user", "bob")
    store.upsert(
        bob,
        substrate_mode=SubstrateMode.MIXED,
        classifier="test", classifier_rationale="seed",
        alignment_vector=AlignmentVector(0.5, 0.5, 0.5, 0.5),
        net_potential=0.5,
    )
    response = client.post(
        "/permissions/grant",
        json={
            "action_kind": "extract",
            "affected_entity_ids": ["bob"],
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "net_potential_gain_negative"
```

Override `get_store` and `actor_from_request` in your test client's dependency overrides to inject the in-memory store and a synthetic actor.

## Production rollout

- Start by wiring `Depends(get_gate)` on a single endpoint and observing the verdict distribution.
- Add metadata-seeding for newly-created entities at create-time (the `INSUFFICIENT_DATA` rate is a leading indicator of seeding gaps).
- Once seeding is healthy, escalate `INSUFFICIENT_DATA` to a refusal-with-retry pattern on consequential endpoints.
- Wire the audit-chain ledger (mechanism 2) into the same flow so verdicts persist for operator review.
