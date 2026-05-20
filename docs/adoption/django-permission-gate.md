# Wiring the NPG gate into a Django view

This recipe is the Django counterpart to the [FastAPI permission-gate recipe](fastapi-permission-gate.md). The pattern is the same — every consequential view routes through a single [NPG gate](../concepts/npg-gate.md) — adapted to Django's class-based views and (optionally) Django REST framework's permission classes.

## What you need

- Django 4.2 or later.
- (Optional) Django REST framework, for the `BasePermission` variant.
- A `SubstrateMetadataStore` instance.
- An auth mechanism that resolves a request to an `actor: EntityRef` (Django's `request.user` is the typical source).

## Module layout

```
app/
├── substrate_deps.py     # store + gate, constructed once per process
├── permissions.py        # DRF BasePermission + a CBV mixin
└── views.py              # consequential views consuming the permission
```

## The shared dependencies

```python
# app/substrate_deps.py
from __future__ import annotations

from functools import lru_cache

from substrate import (
    DefaultNetPotentialGainGate, InMemorySubstrateMetadataStore,
    RaiseOnNegativeGate, SubstrateMetadataStore,
)


@lru_cache(maxsize=1)
def get_store() -> SubstrateMetadataStore:
    """Process-wide store. Swap for your persistent backend in production."""
    return InMemorySubstrateMetadataStore()


@lru_cache(maxsize=1)
def get_gate() -> RaiseOnNegativeGate:
    """Process-wide gate. RaiseOnNegativeGate raises on NEGATIVE verdicts."""
    return RaiseOnNegativeGate(
        inner=DefaultNetPotentialGainGate(metadata_store=get_store()),
    )
```

## Variant A — DRF `BasePermission`

```python
# app/permissions.py
from __future__ import annotations

from typing import Sequence

from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied, APIException
from rest_framework import status

from substrate import (
    EntityRef, NetPotentialGainNegative, NetPotentialGainVerdict,
)

from app.substrate_deps import get_gate


class InsufficientSubstrateData(APIException):
    """409 Conflict: gate returned INSUFFICIENT_DATA."""
    status_code = status.HTTP_409_CONFLICT
    default_code = "insufficient_substrate_data"


class SubstrateAligned(BasePermission):
    """DRF permission that routes the request through the NPG gate.

    Subclasses declare ``action_kind`` and the resolvers for actor +
    affected entities; the permission class wires the gate.
    """

    action_kind: str = "act"

    def resolve_actor(self, request) -> EntityRef:
        # request.user.entity_id should be supplied by your auth backend.
        return EntityRef(entity_type="user", entity_id=str(request.user.pk))

    def resolve_affected(self, request, view) -> Sequence[EntityRef]:
        # Override per-view to read affected ids from the request body / URL.
        return ()

    def resolve_outcome(self, request, view) -> dict:
        return {}

    def has_permission(self, request, view) -> bool:
        gate = get_gate()
        try:
            evaluation = gate.evaluate_or_raise(
                actor=self.resolve_actor(request),
                action_kind=self.action_kind,
                affected_entities=tuple(self.resolve_affected(request, view)),
                proposed_outcome=self.resolve_outcome(request, view),
            )
        except NetPotentialGainNegative as exc:
            # Raise the DRF exception so the view returns 403 with the
            # gate's per-entity contributions visible to the caller.
            raise PermissionDenied(detail={
                "reason": "net_potential_gain_negative",
                "score": exc.evaluation.score,
                "per_entity": [
                    {"entity_id": e.entity_id, "delta": d}
                    for e, d in exc.evaluation.per_entity_delta
                ],
                "reasoning": exc.evaluation.reasoning,
            }) from exc

        if evaluation.verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA:
            raise InsufficientSubstrateData(detail={
                "missing_for": [e.entity_id for e in evaluation.missing_metadata_for],
                "reasoning": evaluation.reasoning,
            })
        return True
```

```python
# app/views.py (DRF variant)
from __future__ import annotations

from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from substrate import EntityRef

from app.permissions import SubstrateAligned


class TeachLessonPermission(SubstrateAligned):
    action_kind = "teach"

    def resolve_affected(self, request, view):
        return [EntityRef("user", uid) for uid in request.data.get("student_ids", [])]


class TeachLessonView(GenericAPIView):
    permission_classes = [TeachLessonPermission]

    def post(self, request, *args, **kwargs):
        # Permission already ran the gate; if we got here, verdict is
        # NET_POSITIVE or NET_NEUTRAL.
        ...
        return Response({"status": "ok"})
```

## Variant B — class-based view mixin (no DRF dependency)

```python
# app/views_cbv.py
from __future__ import annotations

from django.http import JsonResponse
from django.views import View

from substrate import (
    EntityRef, NetPotentialGainNegative, NetPotentialGainVerdict,
)

from app.substrate_deps import get_gate


class SubstrateGatedView(View):
    """Class-based view mixin that gates ``dispatch`` via the NPG gate.

    Subclasses set ``action_kind`` and override the resolver methods.
    """

    action_kind: str = "act"

    def resolve_actor(self, request) -> EntityRef:
        return EntityRef(entity_type="user", entity_id=str(request.user.pk))

    def resolve_affected(self, request):
        return ()

    def resolve_outcome(self, request):
        return {}

    def dispatch(self, request, *args, **kwargs):
        gate = get_gate()
        try:
            evaluation = gate.evaluate_or_raise(
                actor=self.resolve_actor(request),
                action_kind=self.action_kind,
                affected_entities=tuple(self.resolve_affected(request)),
                proposed_outcome=self.resolve_outcome(request),
            )
        except NetPotentialGainNegative as exc:
            return JsonResponse(
                {
                    "reason": "net_potential_gain_negative",
                    "score": exc.evaluation.score,
                    "per_entity": [
                        {"entity_id": e.entity_id, "delta": d}
                        for e, d in exc.evaluation.per_entity_delta
                    ],
                    "reasoning": exc.evaluation.reasoning,
                },
                status=403,
            )
        if evaluation.verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA:
            return JsonResponse(
                {
                    "reason": "insufficient_substrate_data",
                    "missing_for": [e.entity_id for e in evaluation.missing_metadata_for],
                    "reasoning": evaluation.reasoning,
                },
                status=409,
            )
        return super().dispatch(request, *args, **kwargs)
```

```python
# app/views.py (CBV variant)
from app.views_cbv import SubstrateGatedView
from substrate import EntityRef


class TeachLessonView(SubstrateGatedView):
    action_kind = "teach"

    def resolve_affected(self, request):
        student_ids = request.POST.getlist("student_ids")
        return [EntityRef("user", sid) for sid in student_ids]

    def post(self, request, *args, **kwargs):
        ...
        from django.http import JsonResponse
        return JsonResponse({"status": "ok"})
```

## URL wiring

```python
# app/urls.py
from django.urls import path
from app.views import TeachLessonView

urlpatterns = [
    path("teach/", TeachLessonView.as_view(), name="teach-lesson"),
]
```

## HTTP code mapping (mirrors the FastAPI recipe)

| Verdict | HTTP status | Body shape |
| --- | --- | --- |
| `NET_POSITIVE` / `NET_NEUTRAL` | the view's normal response | unchanged |
| `NET_NEGATIVE` | **403 Forbidden** | `{reason, score, per_entity, reasoning}` |
| `INSUFFICIENT_DATA` | **409 Conflict** | `{reason, missing_for, reasoning}` |

The distinction matters: clients writing retry logic see `403` and stop, but see `409` and may retry after seeding the missing metadata. Collapsing the two into a single status would lose that signal.

## What this wiring buys

- **One gate, every view.** The decorator/mixin keeps view bodies focused; gating discipline lives in one place.
- **Two variants, same gate.** DRF projects get a `BasePermission`; vanilla-Django projects get a CBV mixin. Both are thin wrappers around the same `get_gate()`.
- **Structured refusals.** `403` and `409` carry the per-entity contributions so the frontend / API caller can render an actionable error instead of an opaque "forbidden".
- **Swap-in storage.** Changing `get_store()` to a Postgres-backed implementation (per the [SQLAlchemy recipe](sqlalchemy-metadata-store.md)) is one line.

## What this wiring deliberately does not do

- **It does not gate at the middleware level.** Middleware-level gating creates surprise refusals on unrelated endpoints; an explicit per-view permission is the honest surface.
- **It does not auto-seed metadata for unrecognised entities.** `INSUFFICIENT_DATA` surfaces the gap; auto-seeding would silently default-to-permissive and contradict the [NPG specification](../../spec/npg-gate-protocol.md).
- **It does not wrap Django's anonymous users.** Sub-class `SubstrateAligned` per route and decide how to handle anonymous access on a per-route basis; one global policy will not fit all consequential surfaces.

## Testing

```python
# tests/test_teach_view.py
import json

import pytest
from django.test import Client
from substrate import AlignmentVector, EntityRef, SubstrateMode

from app.substrate_deps import get_store


@pytest.fixture(autouse=True)
def clear_store():
    get_store().clear()
    yield


def test_teach_view_refuses_when_metadata_missing(client: Client, alice_user):
    client.force_login(alice_user)
    response = client.post("/teach/", {"student_ids": ["bob"]})
    assert response.status_code == 409
    assert json.loads(response.content)["reason"] == "insufficient_substrate_data"


def test_teach_view_proceeds_when_metadata_present(client: Client, alice_user):
    client.force_login(alice_user)
    for entity_id in ("alice", "bob"):
        get_store().upsert(
            EntityRef("user", entity_id),
            substrate_mode=SubstrateMode.MIXED,
            classifier="test", classifier_rationale="seeded",
            alignment_vector=AlignmentVector(0.5, 0.5, 0.5, 0.5),
            net_potential=0.5,
        )
    response = client.post("/teach/", {"student_ids": ["bob"]})
    assert response.status_code == 200
```

## See also

- [Concept: NPG gate](../concepts/npg-gate.md) — the four-verdict shape, the evaluation algorithm, why the neutral band exists.
- [Spec: NPG gate Protocol](../../spec/npg-gate-protocol.md) — the normative behaviour the recipe pins down.
- [FastAPI recipe](fastapi-permission-gate.md) — the synchronous, response-based variant of this pattern.
- [Celery recipe](celery-task-gate.md) — the asynchronous variant for tasks rather than HTTP endpoints.
- [Example 01](../../python/examples/01_npg_gate.py) — framework-free runnable demonstration.
