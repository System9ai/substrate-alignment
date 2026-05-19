# substrate-alignment

> Open standard, reference Python implementation, and machine-checkable conformance suite for substrate-alignment primitives in multi-entity agent systems.

[![CI](https://github.com/System9ai/substrate-alignment/actions/workflows/ci.yml/badge.svg)](https://github.com/System9ai/substrate-alignment/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-%E2%89%A53.11-blue.svg)](https://www.python.org/downloads/)

substrate-alignment is a behavioral-layer standard for systems in which multiple entities — humans, services, and AI agents — cooperate and adversarially interact. It defines a small, auditable set of primitives that any conforming implementation must satisfy: gates, classifiers, audit-chain types, drift signals, and halt-and-escalate protocols.

The project lets you make **verifiable** alignment claims about a multi-agent system, rather than asking reviewers to trust closed-source assertions.

## Three deliverables, one repository

| Directory | What it contains | Audience |
| --------- | ---------------- | -------- |
| [`spec/`](spec/) | Language-neutral specifications — the standard itself. | Implementers in any language; auditors; standards bodies. |
| [`conformance/`](conformance/) | Machine-checkable behavioral probes that any implementation can run. | Vendors validating conformance; reviewers verifying claims. |
| [`python/`](python/) | Reference Python implementation. `pip install substrate-alignment`. | Python application authors; the witness for the specification. |

Future language bindings (`rust/`, `go/`, `ts/`) will land as sibling top-level directories in this same repository.

## Who it's for

- **AI-safety researchers** who want to make verifiable claims about multi-agent system behavior.
- **Regulated-industry platform builders** (healthcare, finance, defence, sovereign cloud) whose alignment claims must survive procurement and audit review.
- **Standards bodies and auditors** evaluating vendor alignment claims against a published reference.
- **Multi-agent system architects** implementing cooperation primitives across services and teams.

## Status

Pre-release. The repository scaffold is in place; the reference Python implementation is being extracted from the [System9](https://system9.ai) platform, where these primitives are in production use. First tagged release: `v0.1.0`.

The [CHANGELOG](CHANGELOG.md) tracks released changes; the **Unreleased** section reflects what is in flight on `main`.

## Install

```bash
pip install substrate-alignment
```

The package installs as the top-level module `substrate`:

```python
import substrate

print(substrate.__version__)
```

For development against a local checkout:

```bash
git clone https://github.com/System9ai/substrate-alignment.git
cd substrate-alignment/python
pip install -e ".[dev]"
```

## Repository layout

```
substrate-alignment/
├── LICENSE              Apache-2.0
├── README.md            this file
├── CHANGELOG.md         Keep-a-Changelog history
├── CONTRIBUTING.md      contributor rules and PR checklist
├── CODE_OF_CONDUCT.md   Contributor Covenant 2.1
├── SECURITY.md          vulnerability-reporting policy
├── spec/                language-neutral specifications
├── conformance/         vendor-runnable behavioral probes
├── docs/                concepts, adoption guides, case studies
└── python/              reference Python implementation
    ├── pyproject.toml
    ├── src/substrate/
    ├── tests/
    └── examples/
```

## Quick start

The Python package exposes a small, stable surface of primitives. As they are ported, they become importable from the top-level `substrate` module:

```python
from substrate import NetPotentialGainGate, ResistanceBand, SubstrateMode
```

See [`python/examples/`](python/examples/) for end-to-end snippets and [`docs/adoption/`](docs/adoption/) for integration recipes (FastAPI permission flows, Redis-backed rate limiters, Celery workers, Temporal workflows).

## Documentation

- **Concepts** — [`docs/concepts/`](docs/concepts/): substrate conditions, drift signals, runaway-power-prevention mechanisms.
- **Specifications** — [`spec/`](spec/): language-neutral interface contracts and conformance criteria.
- **Conformance** — [`conformance/`](conformance/): machine-checkable behavioral probes.
- **Adoption** — [`docs/adoption/`](docs/adoption/): framework integration recipes.
- **Case study** — [`docs/case-studies/system9.md`](docs/case-studies/): production deployment narrative.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The hard rule: source code uses engineering vocabulary only; substrate-mathematical reasoning belongs in `docs/concepts/` and `spec/`. This is what lets substrate-alignment withstand procurement and audit review.

## Security

substrate-alignment ships primitives used in safety-relevant code (the net-potential-gain gate and halt-and-escalate protocol, among others). Vulnerabilities in these primitives have downstream safety consequences. Report them privately per [SECURITY.md](SECURITY.md).

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
