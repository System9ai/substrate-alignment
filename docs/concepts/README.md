# Concepts

Engineering explanations of the substrate-alignment primitives. The normative behaviour lives in [`../../spec/`](../../spec/); these documents explain the *why* — the reasoning that was stripped from source under the federal-procurement test, and that readers expecting a "concepts" document expect to find here.

## Vocabulary primitives

| Document | Primitive |
| --- | --- |
| [`operating-mode.md`](operating-mode.md) | The four-valued operating-mode classifier; alignment vector, weights, default thresholds, the `UNKNOWN` vs `SHORT_CYCLE` distinction. |
| [`alignment-refresher.md`](alignment-refresher.md) | The component-merge coordinator: folding signal-source updates into stored metadata. |

## Decision-time primitives

| Document | Primitive |
| --- | --- |
| [`npg-gate.md`](npg-gate.md) | The net-potential-gain gate; the four-verdict shape, the evaluation algorithm, why the neutral band exists. |
| [`resistance-band.md`](resistance-band.md) | The productive-resistance band; derivation of the `1/3` and `1/φ²` anchors, tighter-not-looser discipline. |

## Observational primitives

| Document | Primitive |
| --- | --- |
| [`drift-signals.md`](drift-signals.md) | The seven drift patterns; severity ladder; aggregation discipline. |
| [`audit-chain.md`](audit-chain.md) | Hash-chained substrate-trace records; canonical bytes; peer-witness signing. |

## Response primitives

| Document | Primitive |
| --- | --- |
| [`halt-and-escalate.md`](halt-and-escalate.md) | The four states, six trigger reasons, resume discipline; the *only* automatic per-entity refusal surface. |
| [`pair-coupling.md`](pair-coupling.md) | The pair lifecycle state machine; three integrity gates; the explicit-close discipline. |

## Strategic primitives

| Document | Primitive |
| --- | --- |
| [`runaway-power-prevention.md`](runaway-power-prevention.md) | The six mechanisms taken together; threat model; how the mechanisms compose. |
| [`four-options-matrix.md`](four-options-matrix.md) | Adversary-reasoning matrix; horizon × payoff × honesty × cooperation; folk-theorem awareness rule. |

## How to read these

Each concept doc has the same shape:

1. **Engineering problem.** What the primitive solves, in one paragraph.
2. **Shape.** Types, methods, key invariants — enough to recognise the primitive in code.
3. **Why it is shaped this way.** The substrate-mathematical or design rationale; what alternatives were considered and rejected.
4. **Implementation.** A minimal code snippet exercising the primitive.
5. **Specification.** Pointers to the normative spec and the conformance probes that pin down the contract.

For runnable code, see [`../../python/examples/`](../../python/examples/). For integration recipes that wire primitives into common frameworks, see [`../adoption/`](../adoption/).
