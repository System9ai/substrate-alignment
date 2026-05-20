# substrate-alignment documentation

substrate-alignment is an open standard, reference Python implementation, and machine-checkable conformance suite for primitives used in multi-entity agent systems. This documentation set explains the *concepts*; the [specifications](../spec/) define the *contract*; the [conformance probes](../conformance/) verify a given implementation against that contract.

Use this site to build intuition. Use `spec/` and `conformance/` to verify a claim.

## Concepts

Engineering explanations of each primitive — why the design is shaped the way it is, what the load-bearing distinctions are, the underlying reasoning that the source code does not carry.

| Document | Primitive |
| --- | --- |
| [`concepts/operating-mode.md`](concepts/operating-mode.md) | Four-valued substrate-mode classifier; alignment vector and weights |
| [`concepts/npg-gate.md`](concepts/npg-gate.md) | Net-potential-gain gate; four verdicts; evaluation algorithm |
| [`concepts/resistance-band.md`](concepts/resistance-band.md) | Productive-resistance band; derivation of `1/3` and `1/φ²` anchors |
| [`concepts/runaway-power-prevention.md`](concepts/runaway-power-prevention.md) | The six mechanisms; threat model; how the mechanisms compose |

See [`concepts/README.md`](concepts/README.md) for the full inventory (additional concept docs land alongside their primitives).

## Adoption guides

Concrete integration recipes for common frameworks. Each guide is self-contained and explicit about what it deliberately does *not* do.

| Document | Recipe |
| --- | --- |
| [`adoption/fastapi-permission-gate.md`](adoption/fastapi-permission-gate.md) | Wire `NetPotentialGainGate` into a FastAPI permission endpoint |
| [`adoption/redis-rate-limiter.md`](adoption/redis-rate-limiter.md) | Use `ResistanceBand` to derive token-bucket limits in Redis |

See [`adoption/README.md`](adoption/README.md) for the pattern every recipe follows and the planned coverage for later releases.

## Case studies

- [`case-studies/system9.md`](case-studies/) — the reference production deployment. *Under construction.*

## Quick links

- [Specifications](../spec/) — language-neutral interface contracts (six normative documents)
- [Conformance probes](../conformance/) — machine-checkable behavioural probes; the Python reference passes all 12 currently bundled
- [Python reference implementation](../python/) — `pip install substrate-alignment`
- [Runnable examples](../python/examples/) — four self-contained snippets, one per primitive
- [Project README](../README.md)
- [Contributing](../CONTRIBUTING.md)
- [Security policy](../SECURITY.md)
- [Changelog](../CHANGELOG.md)

## Getting started

1. Read [`concepts/operating-mode.md`](concepts/operating-mode.md) and [`concepts/npg-gate.md`](concepts/npg-gate.md) — these are the foundations the other primitives build on.
2. Run [`examples/01_npg_gate.py`](../python/examples/01_npg_gate.py) to see the gate's four verdicts in action.
3. Read the relevant adoption guide for the framework you're integrating with.
4. Implement the [`SubstrateMetadataStore` Protocol](../spec/operating-mode.md#4-persistence-shape) against your persistence layer — see [`examples/04_metadata_store.py`](../python/examples/04_metadata_store.py) for the pattern.
5. Run `python -m substrate.conformance --probes conformance/probes/` from the repository root to verify the reference implementation against its specs.
