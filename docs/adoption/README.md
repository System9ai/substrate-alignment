# Adoption guides

Concrete integration recipes for common Python frameworks. Each guide is self-contained, names the primitive it wires in, and explains both what the recipe does *and* what it deliberately does not do.

| Guide | Primitive | Framework |
| --- | --- | --- |
| [`fastapi-permission-gate.md`](fastapi-permission-gate.md) | `NetPotentialGainGate` | FastAPI permission endpoints |
| [`django-permission-gate.md`](django-permission-gate.md) | `NetPotentialGainGate` | Django CBV + DRF permission class |
| [`celery-task-gate.md`](celery-task-gate.md) | `NetPotentialGainGate` | Celery worker task decorator |
| [`temporal-workflow-halt.md`](temporal-workflow-halt.md) | `HaltAndEscalateProtocol` | Temporal workflow with signal-driven resume |
| [`redis-rate-limiter.md`](redis-rate-limiter.md) | `ResistanceBand` + threshold helpers | Redis-backed token-bucket rate limiter |
| [`sqlalchemy-metadata-store.md`](sqlalchemy-metadata-store.md) | `SubstrateMetadataStore` Protocol | SQLAlchemy 2.x ORM model + upsert |
| [`audit-chain-postgres.md`](audit-chain-postgres.md) | `SubstrateTraceLedger` | Postgres-backed audit chain + peer-witness |

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
