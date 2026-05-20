# Backing the substrate-trace ledger with Postgres

This recipe shows how to persist the [substrate audit chain](../concepts/audit-chain.md) — the hash-chained record of consequential decisions — to a Postgres table. The pattern keeps the package's hash-continuity invariants intact across writes and across processes, and provides the cross-organisational peer-witness pattern.

The package ships an in-memory `SubstrateTraceLedger`; the recipe below wraps it in a Postgres-backed writer + reader pair so the chain survives process restarts and replicates cross-org.

## What you need

- Postgres 12 or later.
- SQLAlchemy 2.x (the recipe uses the 2.0 ORM API).
- A migration tool — Alembic if you don't already have one.

## Schema

```sql
CREATE TABLE substrate_trace_record (
    sequence              BIGINT      PRIMARY KEY,
    epoch_seconds         BIGINT      NOT NULL,
    decision_id           TEXT        NOT NULL,
    decision_kind         TEXT        NOT NULL,
    permitted             BOOLEAN     NOT NULL,
    rationale             TEXT        NOT NULL,
    npg_verdict           TEXT,
    resistance_band       TEXT,
    sin_summary_json      JSONB,
    harness_intercept_kinds TEXT[]    NOT NULL DEFAULT '{}',
    actor_cell_id         TEXT,
    actor_node_id         TEXT,
    previous_hash         CHAR(64)    NOT NULL,
    record_hash           CHAR(64)    NOT NULL UNIQUE,
    CONSTRAINT ck_sequence_nonneg CHECK (sequence >= 0),
    CONSTRAINT ck_decision_id_nonempty CHECK (length(decision_id) > 0),
    CONSTRAINT ck_decision_kind_nonempty CHECK (length(decision_kind) > 0),
    CONSTRAINT ck_record_hash_hex CHECK (record_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_previous_hash_hex CHECK (previous_hash ~ '^[0-9a-f]{64}$')
);

-- Index for cross-org peer-witness replication: peers reconstruct
-- chains by chasing record_hash backward through previous_hash.
CREATE INDEX ix_substrate_trace_record_previous_hash
    ON substrate_trace_record (previous_hash);

-- Index for operator surfaces ("show the most recent N decisions").
CREATE INDEX ix_substrate_trace_record_epoch_seconds
    ON substrate_trace_record (epoch_seconds DESC);
```

`sequence` is the primary key because it is monotonic and unique within the chain; `record_hash` is uniqued because chain forks would manifest as a non-unique hash. The CHECK constraints catch malformed rows (e.g., from manual database edits or backfill jobs that bypass the application layer).

## The writer

```python
# app/audit/postgres_ledger.py
from __future__ import annotations

import json
from typing import Optional, Tuple

from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from substrate.audit.substrate_trace import (
    DriftPatternSummary,
    SubstrateTraceLedger,
    SubstrateTraceRecord,
)
from substrate import NetPotentialGainVerdict, ResistanceBandClassification
from substrate.harness import InterceptKind

# In your project this is the SQLAlchemy ORM model corresponding to the
# substrate_trace_record table above; sketched here for clarity.
from app.models.audit import SubstrateTraceRecordRow


class PostgresSubstrateTraceLedger:
    """Postgres-backed audit ledger preserving the package's hash continuity.

    Wraps :class:`SubstrateTraceLedger` so the package's append + hash
    logic stays canonical; the wrapper persists each appended record
    in the same transaction.
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def _hydrate(self) -> SubstrateTraceLedger:
        """Reconstruct an in-memory ledger from the persisted rows.

        Reads every row in sequence order and re-attaches it to a fresh
        in-memory ledger. ``SubstrateTraceLedger.from_records`` performs
        the hash-continuity check during attachment, so an inconsistent
        chain refuses to hydrate.
        """
        with self._session_factory() as session:
            rows = session.execute(
                select(SubstrateTraceRecordRow).order_by(
                    SubstrateTraceRecordRow.sequence,
                )
            ).scalars().all()
        records = tuple(_row_to_record(r) for r in rows)
        return SubstrateTraceLedger.from_records(records)

    def append(  # pylint: disable=too-many-arguments
        self,
        *,
        decision_id: str,
        decision_kind: str,
        permitted: bool,
        rationale: str,
        epoch_seconds: int,
        npg_verdict: Optional[NetPotentialGainVerdict] = None,
        resistance_band: Optional[ResistanceBandClassification] = None,
        sin_summary: Optional[DriftPatternSummary] = None,
        harness_intercept_kinds: Tuple[InterceptKind, ...] = (),
        actor_cell_id: Optional[str] = None,
        actor_node_id: Optional[str] = None,
    ) -> SubstrateTraceRecord:
        """Append one record. The package computes the hash; we persist it."""
        # The package's ledger handles the canonical-bytes computation,
        # the previous_hash linkage, and the record_hash. We re-hydrate
        # so the append starts from the chain's true head, then persist
        # only the new tail.
        in_memory = self._hydrate()
        record = in_memory.append(
            decision_id=decision_id,
            decision_kind=decision_kind,
            permitted=permitted,
            rationale=rationale,
            epoch_seconds=epoch_seconds,
            npg_verdict=npg_verdict,
            resistance_band=resistance_band,
            sin_summary=sin_summary,
            harness_intercept_kinds=harness_intercept_kinds,
            actor_cell_id=actor_cell_id,
            actor_node_id=actor_node_id,
        )
        with self._session_factory() as session:
            session.add(_record_to_row(record))
            session.commit()
        return record

    def verify(self) -> bool:
        """Re-hydrate and assert end-to-end hash continuity."""
        verification = self._hydrate().verify()
        return verification.ok

    def head_hash(self) -> Optional[str]:
        """Return the record_hash of the current tail (for peer-witness)."""
        with self._session_factory() as session:
            row = session.execute(
                select(SubstrateTraceRecordRow)
                .order_by(SubstrateTraceRecordRow.sequence.desc())
                .limit(1)
            ).scalar_one_or_none()
        return row.record_hash if row else None
```

## Concurrent writers

The naive append above re-hydrates the whole chain on each call. That's correct but slow at high write rate. For a busy ledger, layer one of:

### 1. Append-only Postgres advisory lock

```python
def append(self, **kwargs):
    with self._session_factory() as session:
        # Postgres advisory lock keyed to the chain identity; serialises
        # appends without blocking unrelated transactions.
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": 7747})
        head = session.execute(
            select(SubstrateTraceRecordRow)
            .order_by(SubstrateTraceRecordRow.sequence.desc()).limit(1)
        ).scalar_one_or_none()
        # Construct the new record using head.record_hash as previous_hash;
        # do the canonical-bytes computation manually, persist, commit.
        # See the package's SubstrateTraceLedger.append source for the
        # exact serialisation.
        ...
```

The advisory lock is per-chain (the integer `7747` is a chain identifier — pick yours). Multiple chains in the same database use disjoint lock keys; the package's hash-continuity invariant holds per-chain regardless.

### 2. Single writer per chain via partitioning

For very high throughput, partition the ledger by entity (`actor_node_id`) and run one writer per partition. Hash-continuity holds per partition; cross-partition queries union the partitions at read time.

## Cross-organisational peer-witness

The audit chain becomes cross-organisationally meaningful through peer-witness signing (see [`docs/concepts/audit-chain.md`](../concepts/audit-chain.md)). The pattern, in Postgres:

```sql
CREATE TABLE peer_witness_attestation (
    id              BIGSERIAL PRIMARY KEY,
    witnessed_hash  CHAR(64)  NOT NULL REFERENCES substrate_trace_record(record_hash),
    witness_id      TEXT      NOT NULL,
    signature       BYTEA     NOT NULL,
    signed_at       BIGINT    NOT NULL,
    UNIQUE (witnessed_hash, witness_id)
);

CREATE INDEX ix_peer_witness_attestation_witnessed_hash
    ON peer_witness_attestation (witnessed_hash);
```

The witness side:

```python
from substrate.audit.peer_witness_signer import sign_head

def witness(other_org_head_hash: str, our_secret: bytes) -> bytes:
    """Witness another org's head hash with our key material."""
    signature = sign_head(other_org_head_hash, our_secret)
    # Persist the attestation locally; replicate it back to the
    # witnessed org so they have evidence both sides hold the same head.
    return signature
```

Any third party can independently fetch both ledgers and the attestation row and verify that the witnessed hash matches the chain's head at the time of attestation.

## What this wiring buys

- **Hash continuity survives process restarts.** Re-hydrating from rows runs the package's `verify()` chain walk; a row mutated in place by hand surfaces as `verification.ok == False`.
- **Postgres CHECK constraints catch malformed rows.** The hex-format constraints on `record_hash` and `previous_hash` reject ingest jobs that bypass the application layer.
- **The same package code runs both in-memory and Postgres-backed.** The package's `SubstrateTraceLedger` is the canonical implementation; the wrapper persists it. Other-language implementations can read the same Postgres rows and re-derive hashes using the canonical-bytes specification.
- **Peer-witness scales horizontally.** Each org runs its own ledger; attestations replicate at the row level; verification is local.

## What this wiring deliberately does not do

- **It does not implement delete or update on `substrate_trace_record`.** The chain is append-only; corrections append a *new* record that references the original by `decision_id`. Implementing UPDATE would break the chain's audit-meaningful property.
- **It does not auto-checkpoint.** The package's `compute_checkpoint(...)` produces signed checkpoints for very-long chains; this recipe leaves checkpointing to host operators (typically a cron task that runs `ledger.compute_checkpoint()` and persists the result).
- **It does not synchronise the chain across processes via Postgres LISTEN/NOTIFY.** That's an integration step a busy deployment may need; the recipe stays focused on the persistence shape, not the replication topology.

## Testing

```python
# tests/audit/test_postgres_ledger.py
def test_chain_continuity_across_restarts(session_factory) -> None:
    ledger = PostgresSubstrateTraceLedger(session_factory)
    r1 = ledger.append(
        decision_id="d1", decision_kind="test", permitted=True,
        rationale="first", epoch_seconds=1_700_000_000,
    )
    r2 = ledger.append(
        decision_id="d2", decision_kind="test", permitted=True,
        rationale="second", epoch_seconds=1_700_000_001,
    )
    # Discard the writer; reconstruct from rows alone.
    ledger2 = PostgresSubstrateTraceLedger(session_factory)
    assert ledger2.verify()
    assert ledger2.head_hash() == r2.record_hash
    assert r2.previous_hash == r1.record_hash
```

## See also

- [Concept: audit chain](../concepts/audit-chain.md) — hash-chained records, canonical bytes, peer-witness signing.
- [Spec: runaway-power-prevention mechanism 2](../../spec/runaway-power-prevention.md) — normative behaviour.
- [`sqlalchemy-metadata-store.md`](sqlalchemy-metadata-store.md) — companion recipe for the `SubstrateMetadataStore` Protocol.
- [Example 05](../../python/examples/05_halt_and_escalate.py) — halt protocol + in-memory audit ledger end-to-end.
