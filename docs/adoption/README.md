# Adoption guides

Concrete integration recipes for common Python frameworks. Each guide is self-contained, names the primitive it wires in, and explains both what the recipe does *and* what it deliberately does not do.

| Guide | Primitive | Framework |
| --- | --- | --- |
| [`fastapi-permission-gate.md`](fastapi-permission-gate.md) | `NetPotentialGainGate` | FastAPI permission endpoints |
| [`redis-rate-limiter.md`](redis-rate-limiter.md) | `ResistanceBand` + threshold helpers | Redis-backed token-bucket rate limiter |
| [`celery-task-gate.md`](celery-task-gate.md) | `NetPotentialGainGate` | Celery worker task decorator |
| [`sqlalchemy-metadata-store.md`](sqlalchemy-metadata-store.md) | `SubstrateMetadataStore` Protocol | SQLAlchemy 2.x ORM model + upsert |

Coming with later releases:

- `temporal-workflow-halt.md` — wire the halt-and-escalate protocol into a Temporal workflow.
- `audit-chain-postgres.md` — back the substrate-trace ledger with a Postgres table; peer-witness signing across services.
- `django-permission-gate.md` — the Django equivalent of the FastAPI recipe.

## Pattern

Every recipe follows the same structure:

1. **What you need** — explicit prerequisites.
2. **Module layout** — where the wiring lives in the host application's package.
3. **The wiring** — the actual code, kept small and self-contained.
4. **What this wiring buys** — the properties the recipe pins down.
5. **What this wiring deliberately does not do** — the failure modes the recipe avoids (auto-permit on missing data, middleware-level gates, etc.).
6. **Testing** — fixtures and assertions for the recipe.

If you find a recipe doing more than is necessary to wire the primitive, that's a doc bug — open an issue.

## See also

- [`../concepts/`](../concepts/) — engineering explanation of each primitive.
- [`../../spec/`](../../spec/) — normative behaviour.
- [`../../python/examples/`](../../python/examples/) — minimal runnable snippets (no framework, single primitive).
