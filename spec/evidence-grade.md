# Evidence-grade for substrate-state claims

> **Status:** v0.2.0-draft. Subject to revision before the v0.2.0 tagged release.

This specification defines how a conforming implementation grades the *evidentiary strength* of a substrate-state claim — i.e. of a proposition like "entity X is in substrate-mode M" or "edge (X, Y) is coupled with strength s" — given the attestations supporting it.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) when, and only when, they appear in all capitals.

## 1. Motivation

Existing specs (`operating-mode`, `npg-gate-protocol`, `drift-signals`, …) define how an entity's substrate state is *computed* and *acted on*. They are silent on **how confidently a claim about that state may be relied on by a downstream consumer**.

Without an evidence-grade ladder, every claim looks alike. A claim derived from a single anonymous heuristic and a claim derived from three cryptographically signed peer attestations both arrive in the consumer's input as a `SubstrateMetadata` record. The consumer cannot tell them apart, and either treats both with maximum trust (overweighting weak evidence) or both with minimum trust (underweighting strong evidence).

A conforming implementation MUST expose a small, ordered evidence-grade ladder and a deterministic algorithm that composes a grade from a sequence of attestations. Downstream consumers MAY use the grade to weight, gate, or reject substrate-state claims.

## 2. Vocabulary

### 2.1 Evidence grades

A conforming implementation MUST expose four evidence-grade values, ordered from weakest to strongest:

| Value | Serialised form | Meaning |
| --- | --- | --- |
| `UNVERIFIED_HEARSAY` | `"unverified_hearsay"` | Zero or one attestation, no verified provenance. Default when no attestation is provided. |
| `CORROBORATED` | `"corroborated"` | Two or more attestations from distinct sources, none with verified provenance. |
| `ATTESTED` | `"attested"` | At least one attestation has cryptographic-provenance verification. |
| `DOCUMENTED_CRYSTALLIZED` | `"documented_crystallized"` | At least three distinct-source attestations AND at least one with verified provenance AND the youngest attestation is recent (within one half-life by default). |

The serialised form is the canonical wire and storage form. Implementations MUST emit and accept exactly these strings.

The ladder is **ordered**: implementations MUST expose a stable ordering such that `UNVERIFIED_HEARSAY < CORROBORATED < ATTESTED < DOCUMENTED_CRYSTALLIZED`.

### 2.2 Attestation

A conforming implementation MUST expose a `EvidenceAttestation` record type with at minimum these fields:

- `source_id: str` (non-empty) — identifies the attesting source. Two attestations with the same `source_id` are considered to come from the **same** source for the purposes of `unique_source_count`.
- `observed_at_epoch_seconds: float` — when the attestation was produced.
- `provenance_verified: bool` — whether the implementation has independently verified the cryptographic provenance of this attestation.

The record MUST be frozen (immutable) after construction. Implementations MAY extend the record with additional fields (e.g. signer-DN, signature-bytes) but MUST NOT remove or rename the three required fields.

### 2.3 Composition result

A conforming implementation MUST expose an `EvidenceComposition` record type with at minimum these fields:

- `grade: EvidenceGrade`
- `attestation_count: int` (≥ 0)
- `unique_source_count: int` (≥ 0)
- `provenance_verified_count: int` (≥ 0)
- `youngest_age_seconds: float` (≥ 0; `inf` permitted when `attestation_count == 0`)
- `oldest_age_seconds: float` (≥ 0; `inf` permitted when `attestation_count == 0`)
- `rationale: str` (non-empty) — human-readable justification for the grade.

The record MUST be frozen. The rationale MUST cite which rule produced the chosen grade so an operator can trace the decision back to this spec.

### 2.4 Substrate-state claim

A conforming implementation MUST expose a `SubstrateStateClaim` Protocol with at minimum:

- `claim_id: str` (non-empty) — uniquely identifies the claim within the implementation.
- `subject_entity_type: str` (non-empty)
- `subject_entity_id: str` (non-empty)
- `attestations` — readable sequence of `EvidenceAttestation`.
- `evidence_composition` — readable `EvidenceComposition` consistent with `attestations`.

The Protocol is the integration surface between substrate-alignment and the host application's canonical-state store. Host implementations (MNEMOSYNE, ARGUS, project-specific stores) declare conformance by implementing this Protocol on their existing claim records.

## 3. Composition algorithm

A conforming implementation MUST provide a function

```
compose_evidence_grade(
    attestations,
    *,
    now_epoch_seconds,
    config = DEFAULT_CONFIG,
) -> EvidenceComposition
```

with the following deterministic algorithm:

1. Compute `attestation_count = len(attestations)`.
2. Compute `unique_source_count = |{a.source_id for a in attestations}|`.
3. Compute `provenance_verified_count = |{a for a in attestations if a.provenance_verified}|`.
4. If `attestation_count == 0`:
   - `youngest_age_seconds = oldest_age_seconds = +inf`.
   - `grade = UNVERIFIED_HEARSAY`.
   - `rationale = "no attestations"`.
   - Return.
5. Otherwise compute:
   - `ages = [now_epoch_seconds - a.observed_at_epoch_seconds for a in attestations]`. Negative ages MUST be clamped to `0.0` (an attestation cannot be from the future).
   - `youngest_age_seconds = min(ages)`.
   - `oldest_age_seconds = max(ages)`.
6. Determine the **base grade** by the first matching rule, top-down:

   | Rule | Base grade |
   | --- | --- |
   | `unique_source_count ≥ 3` AND `provenance_verified_count ≥ 1` | `DOCUMENTED_CRYSTALLIZED` |
   | `provenance_verified_count ≥ 1` | `ATTESTED` |
   | `unique_source_count ≥ 2` | `CORROBORATED` |
   | otherwise | `UNVERIFIED_HEARSAY` |

7. Apply **decay**: if `youngest_age_seconds > config.decay_half_life_seconds × config.decay_multiplier` AND the base grade is stronger than `UNVERIFIED_HEARSAY`, downgrade the grade by one step (the rationale MUST mention the downgrade).
8. Populate the `EvidenceComposition` and return.

A conforming implementation MUST NOT skip steps, reorder rules, or substitute a different rule set in default mode. Implementations MAY ship alternative `config` objects but MUST validate them at construction (`decay_half_life_seconds > 0`, `decay_multiplier ≥ 1.0`).

### 3.1 Default configuration

```
DEFAULT_CONFIG = EvidenceGradeConfig(
    decay_half_life_seconds=7 * 24 * 3600,   # 7 days
    decay_multiplier=2.0,                    # downgrade beyond 2 × half-life
)
```

## 4. Symmetry obligation

Per substrate condition #2 (tamper-evident audit at every scale, symmetric), a conforming implementation MUST NOT use the evidence-grade ladder in a write-only fashion. Any subject entity referenced by a `SubstrateStateClaim` SHOULD be able to query — via host-specified mechanism — the grade of claims **about** them. Implementations that surface evidence-grade in a one-directional consumer-pull pattern only are non-conforming.

The spec does not prescribe the host-specific query surface; conformance is satisfied by demonstrating that some such surface exists.

## 5. Conformance

A conforming implementation MUST pass every probe in `../conformance/probes/` whose filename begins with `evidence-grade__`.

## 6. Reference implementation

In the Python reference implementation:

- Types and Protocol: [`substrate.evidence_grade`](../python/src/substrate/evidence_grade/__init__.py)
- Composer: [`substrate.evidence_grade.composer`](../python/src/substrate/evidence_grade/composer.py)
- Conformance handler: registered in [`substrate.conformance.probe_runner.default_handlers`](../python/src/substrate/conformance/probe_runner.py)

## 7. Cross-references

- `npg-gate-protocol.md` § 2 (the gate's `affected_entities` may carry evidence-graded substrate metadata — gate input strength is bounded above by claim grade).
- `operating-mode.md` § 4 (`SubstrateMetadata.classifier_rationale` MAY cite the evidence-grade of the underlying claim).
- `drift-signals.md` § 3 (drift detection on a claim graded `UNVERIFIED_HEARSAY` SHOULD not escalate by default).

## 8. Non-goals

- The spec does NOT define a numeric `source_authority_score`. Hosts that track per-source authority MAY multiply the grade by that score downstream, but the grade itself is the per-claim evidence summary.
- The spec does NOT define a bitemporal-coordinate Protocol; that surface belongs to the host's canonical-state store. The spec only requires that `SubstrateStateClaim` exposes an immutable `evidence_composition` consistent with its `attestations`.
- The spec does NOT define a fusion algorithm for combining grades across claims about the same entity at different times. Implementations are free to define a host-specific fusion; conformance is per-claim.
