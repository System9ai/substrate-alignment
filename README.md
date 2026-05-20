# substrate-alignment

> Open standard, reference Python implementation, and machine-checkable conformance suite for substrate-alignment primitives in multi-entity agent systems.

[![CI](https://github.com/System9ai/substrate-alignment/actions/workflows/ci.yml/badge.svg)](https://github.com/System9ai/substrate-alignment/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-%E2%89%A53.11-blue.svg)](https://www.python.org/downloads/)
[![Tests: 2315](https://img.shields.io/badge/tests-2315%20passing-brightgreen.svg)](python/tests/)
[![Probes: 22](https://img.shields.io/badge/probes-22%20passing-brightgreen.svg)](conformance/probes/)
[![Pyright: strict](https://img.shields.io/badge/pyright-strict-blue.svg)](python/pyproject.toml)

`substrate-alignment` is a behavioural-layer standard for systems in which multiple entities — humans, services, AI agents — cooperate and adversarially interact. It defines a small, auditable set of primitives that any conforming implementation must satisfy: gates, classifiers, audit-chain types, drift signals, halt-and-escalate protocols, pair-coupling integrity checks.

The project lets you make **verifiable** alignment claims about a multi-agent system, rather than asking reviewers to trust closed-source assertions.

## 30-second first contact

```bash
pip install substrate-alignment            # zero runtime dependencies
```

```python
from substrate import (
    DefaultNetPotentialGainGate, EntityRef,
    InMemorySubstrateMetadataStore, RaiseOnNegativeGate,
)

store = InMemorySubstrateMetadataStore()   # ships with the package; swap for your backend
gate = RaiseOnNegativeGate(inner=DefaultNetPotentialGainGate(metadata_store=store))

# Seed an affected entity, then route a consequential decision through the gate.
gate.evaluate_or_raise(
    actor=EntityRef("agent", "alice"),
    action_kind="teach",
    affected_entities=[EntityRef("user", "bob")],
    proposed_outcome={"expected_delta_by_entity": {"bob": 0.3}},
)
```

If the proposed action would have negative net effect on the affected entities, the gate raises `NetPotentialGainNegative` carrying the per-entity contributions for audit.

```bash
substrate-conformance --probes conformance/probes/   # run the bundled probes
# 22/22 probes passed (0 required failures, 0 advisory failures).
```

## Three deliverables, one repository

| Directory | What it contains | Audience |
| --- | --- | --- |
| [`spec/`](spec/) | Six normative specifications — the standard itself. | Implementers in any language; auditors; standards bodies. |
| [`conformance/`](conformance/) | 22 machine-checkable behavioural probes that any implementation can run. | Vendors validating conformance; reviewers verifying claims. |
| [`python/`](python/) | Reference Python implementation. `pip install substrate-alignment`. | Python application authors; the witness for the specification. |

Future language bindings (`rust/`, `go/`, `ts/`) will land as sibling top-level directories in this same repository.

## Who it's for

- **AI-safety researchers** who want to make verifiable claims about multi-agent system behaviour.
- **Regulated-industry platform builders** (healthcare, finance, defence, sovereign cloud) whose alignment claims must survive procurement and audit review.
- **Standards bodies and auditors** evaluating vendor alignment claims against a published reference.
- **Multi-agent system architects** implementing cooperation primitives across services and teams.

## Status

Pre-release. The Python reference implementation has been extracted from the [System9](https://system9.ai) platform, where these primitives are in production use. The first tagged release will be `v0.1.0`.

What is in place today on `main`:

- 6 normative specification documents under [`spec/`](spec/).
- 22 YAML conformance probes under [`conformance/probes/`](conformance/probes/), all passing against the Python reference.
- 136 source modules and 137 test modules under [`python/`](python/); **2315 tests passing**, pyright strict 0/0/0, pylint 10.00/10.
- 10 engineering concept docs at [`docs/concepts/`](docs/concepts/) covering every primitive category.
- 4 framework adoption recipes at [`docs/adoption/`](docs/adoption/) (FastAPI, Redis, Celery, SQLAlchemy).
- 6 runnable examples at [`python/examples/`](python/examples/).
- An anonymised production case study at [`docs/case-studies/system9.md`](docs/case-studies/system9.md).

The [CHANGELOG](CHANGELOG.md) tracks released changes; the **Unreleased** section reflects what is in flight on `main`.

## Architecture in one screen

```
Host application
        │
        ▼
┌────────────────────────────────────────────────────────────────┐
│ substrate (your decision surface routes through these)         │
│                                                                 │
│  AlignmentRefresher ──┐                                         │
│                       │ writes via                              │
│  NetPotentialGainGate ─┼──► SubstrateMetadataStore (Protocol)   │
│                       │ reads from                              │
│  DriftPatternMatcher ─┘                                         │
│           │                                                     │
│           ▼                                                     │
│  HaltAndEscalateProtocol ◄── SubstrateTraceLedger               │
│                                                                 │
│  ResistanceBand ──► derive_threshold / derive_quota_pair / …    │
│  PairCouplingStateMachine ──► extraction_monitor / …            │
└────────────────────────────────────────────────────────────────┘
        │
        ▼
Your persistent storage (implement SubstrateMetadataStore)
```

The host application supplies the storage backend (any implementation of `SubstrateMetadataStore`); every primitive consumes it through that one Protocol.

## Install and develop locally

```bash
git clone https://github.com/System9ai/substrate-alignment.git
cd substrate-alignment/python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest                                      # 2315 passing
pyright src/substrate tests                 # strict, 0/0/0
pylint  src/substrate tests                 # 10.00/10
substrate-conformance --probes ../conformance/probes/   # 22/22

for f in examples/0*.py; do python "$f"; done
```

## Repository layout

```
substrate-alignment/
├── LICENSE              Apache-2.0
├── README.md            this file
├── CHANGELOG.md         Keep-a-Changelog history
├── CONTRIBUTING.md      contributor rules + PR checklist
├── CODE_OF_CONDUCT.md   Contributor Covenant 2.1
├── SECURITY.md          vulnerability-reporting policy
├── spec/                six normative specifications
├── conformance/         YAML probe runner + 22 probes
├── docs/                concepts, adoption guides, case study
└── python/              reference implementation
    ├── pyproject.toml
    ├── src/substrate/
    ├── tests/
    └── examples/
```

## Documentation

- **Specifications** — [`spec/`](spec/): six normative documents covering operating-mode classification, the NPG gate Protocol, drift signals, runaway-power-prevention mechanisms, the four-options matrix, and conformance criteria.
- **Conformance** — [`conformance/`](conformance/): YAML probe runner with a documented schema, 22 bundled probes covering every spec, vendor-attestation guidance.
- **Concepts** — [`docs/concepts/`](docs/concepts/): engineering rationale for each primitive (10 documents). Read these to understand *why* each primitive is shaped the way it is.
- **Adoption** — [`docs/adoption/`](docs/adoption/): framework integration recipes (FastAPI permission gate, Redis-backed rate limiter, Celery task gate, SQLAlchemy metadata-store implementation).
- **Case study** — [`docs/case-studies/system9.md`](docs/case-studies/system9.md): anonymised production-deployment narrative.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The hard rule: source code uses engineering vocabulary only; substrate-mathematical reasoning belongs in `docs/concepts/` and `spec/`. This is what lets substrate-alignment withstand procurement and audit review.

## Security

`substrate-alignment` ships primitives used in safety-relevant code (the net-potential-gain gate, the halt-and-escalate protocol, the audit chain). Vulnerabilities in these primitives have downstream safety consequences. Report them privately per [SECURITY.md](SECURITY.md).

## License

Apache-2.0. See [LICENSE](LICENSE).

## Citing

A formal citation will accompany the first preprint. Until then, cite the repository:

```
@misc{substrate-alignment,
  author = {System9},
  title  = {substrate-alignment: open standard for substrate-alignment primitives in multi-entity agent systems},
  year   = {2026},
  url    = {https://github.com/System9ai/substrate-alignment}
}
```
