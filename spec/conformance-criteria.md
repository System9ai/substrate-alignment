# Conformance criteria

This document defines what counts as a conforming implementation of substrate-alignment. It is the contract any language binding (Python, Rust, Go, TypeScript, …) must satisfy.

> **Status:** skeleton. Sections currently marked *TBD* will be populated as each primitive is specified. The Python reference implementation under [`../python/`](../python/) is the witness for this specification.

## Terminology

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) when, and only when, they appear in all capitals.

## Scope of conformance

A *conforming implementation* is a software artifact that, for some declared subset of the specifications, provides:

1. The behavior described in the named `spec/*.md` documents.
2. Successful execution of every conformance probe in `../conformance/probes/` whose specification it claims to implement.

Implementations MAY add surface area beyond what is specified, provided no such addition contradicts behavior defined here. Implementations MAY declare partial conformance — e.g. "implements `npg-gate-protocol.md` v1, does not yet implement `four-options-matrix.md`" — by listing the specs implemented in their documentation.

## Required primitives

A *fully conforming* implementation MUST provide the following primitives, each with the behavior specified in the named document:

| Primitive                            | Specification                                                  | Reference module (Python)                                                                                                          |
| ------------------------------------ | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Substrate operating-mode classification | [`operating-mode.md`](operating-mode.md) *(TBD)*           | *TBD*                                                                                                                              |
| NetPotentialGainGate protocol        | [`npg-gate-protocol.md`](npg-gate-protocol.md) *(TBD)*         | *TBD*                                                                                                                              |
| Runaway-power-prevention mechanisms  | [`runaway-power-prevention.md`](runaway-power-prevention.md) *(TBD)* | *TBD*                                                                                                                        |
| Drift signals                        | [`drift-signals.md`](drift-signals.md) *(TBD)*                 | *TBD*                                                                                                                              |
| Four-options matrix                  | [`four-options-matrix.md`](four-options-matrix.md) *(TBD)*     | *TBD*                                                                                                                              |

## Conformance probes

A conforming implementation MUST pass every probe in `../conformance/probes/` marked `required: true` that targets a specification it claims to implement. Probes marked `required: false` are advisory: they document edge cases without gating conformance.

The probe-runner protocol — how an implementation exposes itself to the conformance harness — is defined in [`../conformance/README.md`](../conformance/README.md).

## Versioning

This specification follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

- Changes that strengthen a **MUST** clause, or add a new one, are **major-version** events.
- Additions of new **OPTIONAL** clauses, or clarifications of existing ones that do not change observable behavior, are **minor-version** events.
- Editorial corrections (typos, broken links) are **patch-version** events.

Each conformance probe declares the minimum specification version it requires via its metadata.

## The reference implementation as witness

The Python reference implementation in this repository is the witness for this specification: it MUST pass every required probe. A divergence between the reference implementation and a required probe is a bug in the reference implementation, not in the specification, unless the probe's own documentation flags it as an open question.
