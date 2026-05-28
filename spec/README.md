# Specifications

Language-neutral specifications for substrate-alignment primitives. These documents are **normative**: any conforming implementation, in any language, must satisfy the behavior defined here.

The Python package under [`../python/`](../python/) is the *reference* implementation — the witness that the specifications are implementable. The [`../conformance/`](../conformance/) directory contains machine-checkable behavioral probes that any implementation can run to demonstrate conformance.

## Documents

| Document | Covers |
| --- | --- |
| [`conformance-criteria.md`](conformance-criteria.md) | What counts as a conforming implementation |
| [`operating-mode.md`](operating-mode.md) | Substrate-mode classifier, alignment vector, default thresholds |
| [`npg-gate-protocol.md`](npg-gate-protocol.md) | Net-potential-gain gate, the four verdicts, evaluation algorithm |
| [`drift-signals.md`](drift-signals.md) | Seven drift patterns, severity ordering, aggregation semantics |
| [`runaway-power-prevention.md`](runaway-power-prevention.md) | The six mechanisms that close known power-accumulation loopholes |
| [`four-options-matrix.md`](four-options-matrix.md) | Adversary-reasoning matrix: horizon × payoff × honesty × cooperation |
| [`evidence-grade.md`](evidence-grade.md) | Four-step evidence-grade ladder for substrate-state claims (v0.2.0-draft) |
| [`multi-scale.md`](multi-scale.md) | Pluggable `SubstrateScope` registry — defaults CELL/NODE/ORG (v0.3.0-draft) |

## Conventions

- Specifications use [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) / [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) requirement language (**MUST**, **SHOULD**, **MAY**, …) in all-caps.
- Each specification names the corresponding source module(s) in the Python reference implementation under "Reference implementation".
- Each specification declares which conformance probes (under `../conformance/probes/`) gate its conformance.
- Breaking changes to **MUST** clauses are major-version events under [SemVer](https://semver.org/spec/v2.0.0.html).

## How to read the specs

1. Start with [`conformance-criteria.md`](conformance-criteria.md) for the framing.
2. Read each numbered spec for the primitive you intend to implement.
3. Cross-reference the corresponding Python module (cited at the bottom of every spec) for an executable witness.
4. Run the probes that target your declared scope: `python -m substrate.conformance ../../conformance/probes/<spec>__*.yaml`.

## Stability

The specs are at `v0.1.0-draft`. Expect editorial revision (clarifications, typos) before the first tagged release. **MUST** clauses are stable in shape — they reflect behavior that the reference implementation already exhibits and that 2300+ unit tests pin down — but their wording may tighten.
