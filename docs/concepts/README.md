# Concepts

Engineering explanations of the substrate-alignment primitives. The normative behaviour lives in [`../../spec/`](../../spec/); these documents explain the *why* — the reasoning that was stripped from source under the federal-procurement test, and that readers expecting a "concepts" document expect to find here.

| Document | Primitive |
| --- | --- |
| [`operating-mode.md`](operating-mode.md) | The four-valued operating-mode classifier; alignment vector, weights, default thresholds, the `UNKNOWN` vs `SHORT_CYCLE` distinction. |
| [`npg-gate.md`](npg-gate.md) | The net-potential-gain gate; the four-verdict shape, the evaluation algorithm, why the neutral band exists, the default action-kind heuristics. |
| [`resistance-band.md`](resistance-band.md) | The productive-resistance band; derivation of the `1/3` and `1/φ²` anchors, why tighter-not-looser override discipline. |
| [`runaway-power-prevention.md`](runaway-power-prevention.md) | The six mechanisms taken together; threat model, how the mechanisms compose. |

Coming with later releases:

- `alignment-refresher.md` — folding signal-source updates into stored metadata.
- `audit-chain.md` — hash-chained audit ledger, peer-witness signing, cross-organisational coupling.
- `drift-signals.md` — the seven drift patterns, severity ordering, aggregation.
- `halt-and-escalate.md` — protocol states, trigger sources, resume discipline.
- `pair-coupling.md` — pair-coupling state machine, asymmetry-preservation gates.
- `four-options-matrix.md` — adversary-reasoning matrix, folk-theorem verification.

## How to read these

1. Each concept doc starts with the **engineering problem** the primitive solves.
2. The middle section explains the **shape** of the primitive (types, methods, key invariants).
3. The bottom names the **normative spec** and **conformance probes** that pin down the contract.

For runnable code, see [`../../python/examples/`](../../python/examples/). For integration recipes, see [`../adoption/`](../adoption/).
