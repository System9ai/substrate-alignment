# Specifications

Language-neutral specifications for substrate-alignment primitives. These documents are **normative**: any conforming implementation, in any language, must satisfy the behavior defined here.

The Python package under [`../python/`](../python/) is the *reference* implementation — the witness that the specifications are implementable. The [`../conformance/`](../conformance/) directory contains machine-checkable behavioral probes that any implementation can run to demonstrate conformance.

## Documents

| Document                                                       | Status        | Covers                                                      |
| -------------------------------------------------------------- | ------------- | ----------------------------------------------------------- |
| [`conformance-criteria.md`](conformance-criteria.md)           | Skeleton      | What counts as a conforming implementation                  |
| [`operating-mode.md`](operating-mode.md)                       | *Not yet written* | Substrate-aligned operating-mode rules                  |
| [`npg-gate-protocol.md`](npg-gate-protocol.md)                 | *Not yet written* | NetPotentialGainGate protocol interface                 |
| [`runaway-power-prevention.md`](runaway-power-prevention.md)   | *Not yet written* | The six runaway-power-prevention mechanisms             |
| [`drift-signals.md`](drift-signals.md)                         | *Not yet written* | Drift-signal definitions and aggregation                |
| [`four-options-matrix.md`](four-options-matrix.md)             | *Not yet written* | Adversary-reasoning matrix                              |

Documents marked *Not yet written* are populated during the specification phase of the project roadmap.

## Conventions

- Specifications use [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) / [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) requirement language (**MUST**, **SHOULD**, **MAY**, …) in all-caps.
- Each specification names the corresponding source module(s) in the Python reference implementation under "Reference implementation".
- Each specification lists its associated conformance probes under "Conformance" and links into `../conformance/probes/`.
- Breaking changes to **MUST** clauses are major-version events under [SemVer](https://semver.org/spec/v2.0.0.html).
