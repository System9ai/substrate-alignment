# Audit chain

The audit chain is the package's *evidence* surface. Every consequential decision — NPG gate verdict, refusal, escalation, drift detection — appends an immutable hash-chained record that any peer entity can verify.

The audit chain is not a logging facility. It is a *coupling* facility: records become evidence other entities can attest to via peer-witness signing, making the ledger tamper-evident *across organisational boundaries*, not just internally.

This document explains the ledger's invariants and how the peer-witness layer extends them to cross-organisational coupling. The normative behaviour lives in [`spec/runaway-power-prevention.md`](../../spec/runaway-power-prevention.md) as mechanism 2.

## The substrate-trace record

Each record carries (at minimum):

| Field | Purpose |
| --- | --- |
| `sequence` | The record's position in the ledger; monotonic non-negative integer. |
| `epoch_seconds` | Wall-clock timestamp; allows operators to align with external events. |
| `decision_id` | Caller-supplied identifier for the decision being recorded. |
| `decision_kind` | A discriminator (`npg_gate`, `capability_grant`, `halt_escalate`, …). |
| `permitted` | Whether the decision permitted the action. |
| `rationale` | Human-readable explanation from the decision surface. |
| `npg_verdict` | The NPG gate verdict (if a gate fired). |
| `resistance_band` | The resistance-band classification (if relevant). |
| `sin_summary` | The drift-pattern summary (if a drift detection fired). |
| `previous_hash` | Hash of the prior record (or genesis-hash for the first record). |
| `record_hash` | Hash of this record's canonical bytes. |

The `(previous_hash, record_hash)` pair is what makes the chain tamper-evident: changing any field in any record changes that record's `record_hash`, which breaks the next record's `previous_hash` reference, which `ledger.verify()` detects.

## Canonical bytes

Each record's hash is computed over a **canonical** byte representation — sorted keys, no whitespace, stable null encoding. The canonical-bytes function is not internal to the Python implementation; it is part of the specification, so other-language implementations can recompute hashes and verify the chain.

This is the property that lets a peer-witness signer in another runtime (a Rust witness daemon at the edge, a TypeScript verifier in a browser, an auditor's Go tool) re-derive and attest to the same hashes the Python reference computed.

## Verification

`SubstrateTraceLedger.verify()` returns a `LedgerVerification` carrying:

- `ok: bool` — whether the chain is intact end-to-end.
- `bad_sequence: int | None` — the sequence number where verification first failed (if any).
- `reason: str | None` — what specifically went wrong.

The verifier walks the chain from genesis, recomputing each record's hash and comparing against the next record's `previous_hash`. Any divergence — record tampered with, sequence number out of order, hash recomputation disagreement — surfaces as `ok=False` with the offending sequence.

Verification is **stateless across calls**. Two callers verifying the same ledger always agree.

## Peer-witness signing

The audit chain becomes cross-organisationally meaningful through peer-witness signing. The pattern:

1. Entity A's ledger produces a `head_hash` (the hash of the most recent record).
2. Entity A asks entity B to *witness* the head — B independently re-derives the canonical bytes and signs the resulting hash with its own key.
3. The signature lands as a witness attestation in B's ledger (and is replicated back to A).
4. Now any third party can independently verify both A's chain and B's attestation, and conclude either "both ledgers are consistent" or "they diverged".

Peer-witness signing is what turns "A says they ran the gate" into "A and B both have evidence the gate ran with this outcome at this time". The single ledger is auditable; the cross-witnessed ledger is also non-repudiable.

The package ships:

- `substrate.audit.peer_witness` — the witness data type.
- `substrate.audit.peer_witness_signer` — HMAC-based signer (pure logic; host applications swap in their key-management layer).
- `substrate.audit.witness_replication` — replication semantics.

## Append semantics

Append is strictly forward-only. The ledger:

- Computes `previous_hash` from the current head (or genesis).
- Computes the canonical bytes of the new record.
- Computes the `record_hash`.
- Appends; returns the new record.

There is no `update` operation, no `delete`, no "set the previous hash to something else". An entity that wants to correct a prior decision appends a new record that references the original. This is the property that makes the chain audit-meaningful: the historical record is what was decided at the time, not what we wish had been decided.

## Implementation

```python
from substrate.audit.substrate_trace import SubstrateTraceLedger
from substrate import NetPotentialGainVerdict, ResistanceBandClassification

ledger = SubstrateTraceLedger()
ledger.append(
    decision_id="grant-1",
    decision_kind="capability_grant",
    permitted=True,
    rationale="NPG positive; trust >= threshold; no drift",
    epoch_seconds=1_700_000_000,
    npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
    resistance_band=ResistanceBandClassification.PRODUCTIVE,
)

verification = ledger.verify()
verification.ok                    # True
ledger.length                      # 1
ledger.last().record_hash          # the head hash
```

## Specification

The normative definition lives at [`spec/runaway-power-prevention.md`](../../spec/runaway-power-prevention.md) as mechanism 2. Conformance probes are at `conformance/probes/runaway-power-prevention__mech-2__*.yaml`.
