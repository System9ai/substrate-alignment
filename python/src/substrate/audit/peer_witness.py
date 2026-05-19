"""Symmetric audit-chain extension — peer-witness ledger.

The primary :class:`SubstrateTraceLedger` records what an actor
*decided*. Substrate condition #2 (tamper-evident audit at every scale)
explicitly requires that audit is **symmetric**:

    Every agent observes and is observed — not write-only.

This module ships the *observed-by-peers* side. For every decision
recorded in the primary ledger, peers may attach a peer-witness row
attesting they observed the decision. Witness rows form their own
SHA-256 hash chain so tampering with a peer's testimony is detectable
just like tampering with the primary chain.

Pure logic:

- No DAO, no LLM, no network. Persistence is the caller's concern.
- Hash chain canonical form: deterministic JSON with sorted keys.
- Witness attestation is a caller-supplied opaque string (e.g., a
  detached signature, HMAC, or "co-signed at <epoch>" marker). The
  ledger does not interpret it.

Composition:

- A peer-witness row CITES the primary record by ``decision_id`` and
  ``primary_record_hash`` — binding makes substituting the primary
  record detectable at verify time.
- :meth:`PeerWitnessLedger.witnesses_for` returns the witness rows
  for one decision; :meth:`PeerWitnessLedger.witnesses_by` returns
  rows for one peer entity. The bidirectional index is what makes
  the audit *symmetric*.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final, List, Mapping, Optional, Tuple

GENESIS_PREV_HASH: Final[str] = "0" * 64
_HASH_HEX_LEN: Final[int] = 64

@dataclass(frozen=True, slots=True)
class PeerWitnessRecord:  # pylint: disable=too-many-instance-attributes
    """One peer entity's attestation that they observed a decision."""

    sequence: int
    decision_id: str
    primary_record_hash: str
    witness_entity_id: str
    witnessed_at_epoch: int
    attestation: str
    prev_hash: str
    record_hash: str

    def to_canonical_dict(self) -> dict[str, object]:
        """Canonical-form dict used for hashing (record_hash excluded)."""
        return {
            "sequence": self.sequence,
            "decision_id": self.decision_id,
            "primary_record_hash": self.primary_record_hash,
            "witness_entity_id": self.witness_entity_id,
            "witnessed_at_epoch": self.witnessed_at_epoch,
            "attestation": self.attestation,
            "prev_hash": self.prev_hash,
        }

@dataclass(frozen=True, slots=True)
class WitnessLedgerVerification:
    """Outcome of :meth:`PeerWitnessLedger.verify`."""

    ok: bool
    bad_sequence: Optional[int]
    reason: Optional[str]

def _canonical_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

def _hash_canonical(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()

def _validate_hash_hex(value: str, name: str) -> None:
    if len(value) != _HASH_HEX_LEN:
        raise ValueError(f"{name} must be {_HASH_HEX_LEN} hex chars")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be hex") from exc

class PeerWitnessLedger:
    """Append-only hash-chained ledger of peer witness attestations."""

    def __init__(
        self,
        *,
        initial_records: Optional[Tuple[PeerWitnessRecord, ...]] = None,
    ) -> None:
        self._records: List[PeerWitnessRecord] = []
        if initial_records:
            self._records.extend(initial_records)

    @classmethod
    def from_records(
        cls,
        records: Tuple[PeerWitnessRecord, ...],
    ) -> "PeerWitnessLedger":
        """Build a ledger from previously serialized rows (does not re-verify)."""
        return cls(initial_records=records)

    @property
    def length(self) -> int:
        """Number of witness rows."""
        return len(self._records)

    def records(self) -> Tuple[PeerWitnessRecord, ...]:
        """Return all witness rows as an immutable tuple."""
        return tuple(self._records)

    def last(self) -> Optional[PeerWitnessRecord]:
        """Most-recent witness row (None if empty)."""
        return self._records[-1] if self._records else None

    def append(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        decision_id: str,
        primary_record_hash: str,
        witness_entity_id: str,
        witnessed_at_epoch: int,
        attestation: str = "",
    ) -> PeerWitnessRecord:
        """Append one peer-witness attestation.

        Validates inputs (non-empty IDs, hex hash). Forbids two witnesses
        from the same entity on the same decision — substrate-aligned
        audit attribution is per-entity, per-decision.
        """
        if not decision_id:
            raise ValueError("decision_id must be non-empty")
        if not witness_entity_id:
            raise ValueError("witness_entity_id must be non-empty")
        if witnessed_at_epoch < 0:
            raise ValueError("witnessed_at_epoch must be >= 0")
        _validate_hash_hex(primary_record_hash, "primary_record_hash")
        for existing in self._records:
            if (
                existing.decision_id == decision_id
                and existing.witness_entity_id == witness_entity_id
            ):
                raise ValueError(
                    f"duplicate witness: entity {witness_entity_id!r} "
                    f"already attested decision {decision_id!r}"
                )
        prev_hash = (
            self._records[-1].record_hash
            if self._records else GENESIS_PREV_HASH
        )
        sequence = len(self._records)
        unhashed: dict[str, object] = {
            "sequence": sequence,
            "decision_id": decision_id,
            "primary_record_hash": primary_record_hash,
            "witness_entity_id": witness_entity_id,
            "witnessed_at_epoch": witnessed_at_epoch,
            "attestation": attestation,
            "prev_hash": prev_hash,
        }
        record_hash = _hash_canonical(unhashed)
        row = PeerWitnessRecord(
            sequence=sequence,
            decision_id=decision_id,
            primary_record_hash=primary_record_hash,
            witness_entity_id=witness_entity_id,
            witnessed_at_epoch=witnessed_at_epoch,
            attestation=attestation,
            prev_hash=prev_hash,
            record_hash=record_hash,
        )
        self._records.append(row)
        return row

    def witnesses_for(
        self, decision_id: str,
    ) -> Tuple[PeerWitnessRecord, ...]:
        """All witness rows for a single decision (in append order)."""
        return tuple(r for r in self._records if r.decision_id == decision_id)

    def witnesses_by(
        self, witness_entity_id: str,
    ) -> Tuple[PeerWitnessRecord, ...]:
        """All witness rows authored by a single peer entity."""
        return tuple(
            r for r in self._records
            if r.witness_entity_id == witness_entity_id
        )

    def is_witnessed_by(
        self, decision_id: str, witness_entity_id: str,
    ) -> bool:
        """True iff this peer has attested this decision."""
        return any(
            r.decision_id == decision_id
            and r.witness_entity_id == witness_entity_id
            for r in self._records
        )

    def verify(self) -> WitnessLedgerVerification:
        """Verify hash chain integrity end-to-end."""
        expected_prev = GENESIS_PREV_HASH
        for idx, row in enumerate(self._records):
            if row.sequence != idx:
                return WitnessLedgerVerification(
                    ok=False, bad_sequence=idx,
                    reason=f"sequence drift: expected {idx}, got {row.sequence}",
                )
            if row.prev_hash != expected_prev:
                return WitnessLedgerVerification(
                    ok=False, bad_sequence=row.sequence,
                    reason="prev_hash mismatch",
                )
            recomputed = _hash_canonical(row.to_canonical_dict())
            if recomputed != row.record_hash:
                return WitnessLedgerVerification(
                    ok=False, bad_sequence=row.sequence,
                    reason="record_hash mismatch",
                )
            expected_prev = row.record_hash
        return WitnessLedgerVerification(
            ok=True, bad_sequence=None, reason=None,
        )

def quorum_witnessed(
    ledger: PeerWitnessLedger,
    decision_id: str,
    required_peers: int,
) -> bool:
    """Return True iff ``decision_id`` has ≥ ``required_peers`` distinct witnesses.

    Substrate-aligned symmetric-audit predicate: a decision is
    "quorum-witnessed" when at least *N* distinct peer entities have
    attested it. Caller chooses *N* (typically derived from the
    productive-resistance band via [[threshold_derivation]]).
    """
    if required_peers < 1:
        raise ValueError("required_peers must be >= 1")
    witnesses = ledger.witnesses_for(decision_id)
    distinct_peers = {r.witness_entity_id for r in witnesses}
    return len(distinct_peers) >= required_peers

__all__ = [
    "GENESIS_PREV_HASH",
    "PeerWitnessLedger",
    "PeerWitnessRecord",
    "WitnessLedgerVerification",
    "quorum_witnessed",
]
