# substrate-alignment documentation

substrate-alignment is an open standard, reference Python implementation, and machine-checkable conformance suite for primitives used in multi-entity agent systems. This documentation set explains the *concepts*; the [specifications](../spec/) define the *contract*; the [conformance probes](../conformance/) verify a given implementation against that contract.

Use this site to build intuition. Use `spec/` and `conformance/` to verify a claim.

## Where to start

New here? Read [`core-vs-extended.md`](core-vs-extended.md) first: it separates
the small **core** surface almost every integration uses from the **extended**
substrate-mechanical vocabulary, so you are not reading 170 modules to find the
9 that matter.

## Concepts

Engineering explanations of each primitive: why the design is shaped the way it is, what the load-bearing distinctions are, the underlying reasoning that the source code does not carry.

| Document | Primitive |
| --- | --- |
| [`concepts/operating-mode.md`](concepts/operating-mode.md) | Four-valued substrate-mode classifier; alignment vector and weights |
| [`concepts/npg-gate.md`](concepts/npg-gate.md) | Net-potential-gain gate; four verdicts; evaluation algorithm |
| [`concepts/resistance-band.md`](concepts/resistance-band.md) | Productive-resistance band; derivation of the `1/3` and `1/φ²` anchors |
| [`concepts/runaway-power-prevention.md`](concepts/runaway-power-prevention.md) | The six mechanisms; threat model; how the mechanisms compose |
| [`concepts/drift-signals.md`](concepts/drift-signals.md) | The seven drift patterns; pattern matching against observed behaviour |
| [`concepts/halt-and-escalate.md`](concepts/halt-and-escalate.md) | The halt-and-escalate protocol; when a primitive stops rather than proceeds |
| [`concepts/four-options-matrix.md`](concepts/four-options-matrix.md) | The four-options response matrix for a flagged action |
| [`concepts/pair-coupling.md`](concepts/pair-coupling.md) | Pair-coupling integrity; extraction monitoring between two entities |
| [`concepts/audit-chain.md`](concepts/audit-chain.md) | Hash-chained observation ledger; tamper-evidence |
| [`concepts/alignment-refresher.md`](concepts/alignment-refresher.md) | Periodic re-classification; keeping substrate metadata current |
| [`concepts/governed-ascent.md`](concepts/governed-ascent.md) | Hill climbing made substrate-aligned; certified, long-cycle-aware ascent |

See [`concepts/README.md`](concepts/README.md) for the full inventory.

## Adoption guides

Concrete integration recipes for common frameworks. Each guide is self-contained and explicit about what it deliberately does *not* do.

| Document | Recipe |
| --- | --- |
| [`adoption/fastapi-permission-gate.md`](adoption/fastapi-permission-gate.md) | Wire `NetPotentialGainGate` into a FastAPI permission endpoint |
| [`adoption/django-permission-gate.md`](adoption/django-permission-gate.md) | Gate a Django view/DRF permission through the NPG gate |
| [`adoption/redis-rate-limiter.md`](adoption/redis-rate-limiter.md) | Use `ResistanceBand` to derive token-bucket limits in Redis |
| [`adoption/celery-task-gate.md`](adoption/celery-task-gate.md) | Gate a Celery task before it runs |
| [`adoption/temporal-workflow-halt.md`](adoption/temporal-workflow-halt.md) | Apply the halt-and-escalate protocol inside a Temporal workflow |
| [`adoption/sqlalchemy-metadata-store.md`](adoption/sqlalchemy-metadata-store.md) | Implement `SubstrateMetadataStore` on SQLAlchemy |
| [`adoption/audit-chain-postgres.md`](adoption/audit-chain-postgres.md) | Persist the hash-chained audit ledger in Postgres |

See [`adoption/README.md`](adoption/README.md) for the pattern every recipe follows.

## Case studies

- [`case-studies/system9.md`](case-studies/system9.md): the anonymised reference production deployment.

## Orientation

- [Core vs extended](core-vs-extended.md): the surface you actually need.
- [Tutorial](tutorial.md): build your first governed system step by step.
- [Comparison](comparison.md): vs OPA, Cerbos, Guardrails AI, NeMo Guardrails.
- [FAQ](faq.md) · [Glossary](glossary.md) · [Preprint](preprint/preprint.md).

## Quick links

- [Specifications](../spec/): language-neutral interface contracts (nine normative documents)
- [Conformance probes](../conformance/): machine-checkable behavioural probes; the Python reference passes all 48 currently bundled
- [Python reference implementation](../python/): install from a local clone (`pip install -e python/`)
- [Runnable examples](../python/examples/): six self-contained snippets, one per primitive
- [Project README](../README.md)
- [Contributing](../CONTRIBUTING.md)
- [Security policy](../SECURITY.md)
- [Changelog](../CHANGELOG.md)

## Getting started

1. Read [`concepts/operating-mode.md`](concepts/operating-mode.md) and [`concepts/npg-gate.md`](concepts/npg-gate.md); these are the foundations the other primitives build on.
2. Run [`examples/01_npg_gate.py`](../python/examples/01_npg_gate.py) to see the gate's four verdicts in action.
3. Read the relevant adoption guide for the framework you're integrating with.
4. Implement the [`SubstrateMetadataStore` Protocol](../spec/operating-mode.md#4-persistence-shape) against your persistence layer. See [`examples/04_metadata_store.py`](../python/examples/04_metadata_store.py) for the pattern.
5. Run `python -m substrate.conformance --probes conformance/probes/` from the repository root to verify the reference implementation against its specs.
