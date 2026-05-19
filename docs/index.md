# substrate-alignment documentation

substrate-alignment is an open standard, reference Python implementation, and machine-checkable conformance suite for primitives used in multi-entity agent systems. This documentation set explains the *concepts*; the [specifications](../spec/) define the *contract*; the [conformance probes](../conformance/) verify a given implementation against that contract.

Use this site to build intuition. Use `spec/` and `conformance/` to verify a claim.

## Contents

### Concepts

One markdown per primitive category. Each document explains the problem the primitive solves, the design choices, and links back to the relevant specification and source.

*Under construction. Populated alongside the bulk-port phase.*

Planned coverage:

- The substrate-aligned operating mode
- The net-potential-gain test (`NetPotentialGainGate`)
- The calibrated-resistance band (`ResistanceBand`)
- Drift signals and the drift-pattern matcher
- Runaway-power-prevention mechanisms
- The halt-and-escalate protocol
- Audit-chain types and the in-memory substrate ledger
- Pair-coupling and asymmetry-preservation primitives
- The four-options matrix for adversary reasoning

### Adoption guides

Recipes for wiring substrate-alignment primitives into common Python frameworks. *Under construction.*

- `NetPotentialGainGate` in a FastAPI permission flow
- `ResistanceBand` in a Redis-backed rate limiter
- Cancer-pattern / drift detection in a Celery worker
- `HaltAndEscalateProtocol` in a Temporal workflow

### Case studies

- [`case-studies/system9.md`](case-studies/) — the reference production deployment. *Under construction.*

## Quick links

- [Specifications](../spec/) — language-neutral interface contracts
- [Conformance probes](../conformance/) — machine-checkable behavioral tests
- [Python reference implementation](../python/) — `pip install substrate-alignment`
- [Project README](../README.md)
- [Contributing](../CONTRIBUTING.md)
- [Security policy](../SECURITY.md)
- [Changelog](../CHANGELOG.md)
