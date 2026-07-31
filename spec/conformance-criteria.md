# Conformance criteria

> **Status:** v0.2.0-draft. The Python reference implementation under [`../python/`](../python/) is the witness for this specification.

This document defines what counts as a conforming implementation of substrate-alignment. It is the contract any language binding (Python, Rust, Go, TypeScript, …) must satisfy.

## Terminology

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) when, and only when, they appear in all capitals.

## Scope of conformance

A *conforming implementation* is a software artifact that, for some declared subset of the specifications, provides:

1. The behavior described in each `spec/*.md` document it declares.
2. Successful execution of every probe in [`../conformance/probes/`](../conformance/probes/) whose `spec` field matches a specification the implementation declares.

Implementations MAY add surface area beyond what is specified, provided no addition contradicts behavior defined here. Implementations MAY declare *partial conformance* (e.g. "implements `npg-gate-protocol.md` v1, does not yet implement `four-options-matrix.md`") by listing the implemented specs in their documentation.

A *fully conforming* implementation declares conformance with every specification in this directory.

## Required primitives

A *fully conforming* implementation MUST provide the following primitives, each with the behavior specified in the named document:

| Primitive | Specification | Reference module (Python) |
| --- | --- | --- |
| Operating-mode classification | [`operating-mode.md`](operating-mode.md) | [`substrate.alignment_computer`](../python/src/substrate/alignment_computer.py) |
| Net-potential-gain gate | [`npg-gate-protocol.md`](npg-gate-protocol.md) | [`substrate.net_potential_gain_gate`](../python/src/substrate/net_potential_gain_gate.py) |
| Drift signals | [`drift-signals.md`](drift-signals.md) | [`substrate.drift`](../python/src/substrate/drift/) |
| Runaway-power-prevention mechanisms (6) | [`runaway-power-prevention.md`](runaway-power-prevention.md) | (see each mechanism's row) |
| Four-options matrix | [`four-options-matrix.md`](four-options-matrix.md) | [`substrate.game_theory`](../python/src/substrate/game_theory/) |

## Conformance probes

A conforming implementation MUST pass every probe in `../conformance/probes/` marked `required: true` that targets a specification it claims to implement. Probes marked `required: false` are advisory: they document edge cases without gating conformance.

Each probe is a portable, declarative scenario file (YAML or JSON) consumed by a probe runner. The probe-runner protocol, how an implementation exposes itself to the conformance harness, is defined in [`../conformance/README.md`](../conformance/README.md).

The Python reference implementation ships a probe runner at [`substrate.conformance.probe_runner`](../python/src/substrate/conformance/probe_runner.py) that executes the YAML probes against the in-package primitives.

## Versioning

This specification follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

- Changes that strengthen or add a **MUST** clause are major-version events.
- Additions of new **OPTIONAL** or **SHOULD** clauses, or clarifications that do not change observable behavior, are minor-version events.
- Editorial corrections (typos, broken links) are patch-version events.

Each conformance probe declares the minimum specification version it requires via its metadata (`spec_version: ">=1.0"`).

## Witness rule

The Python reference implementation in this repository is the *witness* for this specification: it MUST pass every required probe. A divergence between the reference implementation and a required probe is a bug in the reference implementation, **not** in the specification, unless the probe's own documentation flags it as an open question.

The reference implementation thus provides three forms of evidence:

1. The behaviour itself (executable code).
2. A passing test suite (the engineering verification).
3. A passing probe suite (the conformance verification: what other implementations measure themselves against).

## Vendor self-attestation

A vendor demonstrating conformance publishes:

- The set of specifications their implementation targets.
- The probe-runner output (pass / fail per probe).
- The version of these specifications against which the run was performed.
- The version of their implementation.

The substrate-alignment maintainers do not certify implementations; the probes are the certification mechanism.

## Reporting issues

- Bugs in the reference implementation → repository [Issues](https://github.com/System9ai/substrate-alignment/issues).
- Ambiguity in a specification → repository [Discussions](https://github.com/System9ai/substrate-alignment/discussions), tagged `spec`.
- Security vulnerabilities → [SECURITY.md](../SECURITY.md). Do not open a public issue.
