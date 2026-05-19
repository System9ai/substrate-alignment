"""Substrate audit-trace primitive.

A pure-logic, hash-chained ledger of substrate-aware decisions. Each
:class:`SubstrateTraceRecord` captures one decision's substrate
context:

* the decision identifier and kind (caller-supplied semantic tags),
* the :class:`NetPotentialGainVerdict` from the NPG gate (if
  consulted),
* the :class:`ResistanceBandClassification` from the resistance band
  (if measured),
* a **summary** of the :class:`DriftPatternReport` (dominant pattern,
  composite confidence, pride-present flag, patterns detected),
* the harness :class:`InterceptKind` set that fired (if any),
* the final permitted/denied decision and short rationale.

Records are hash-chained: each record's ``prev_hash`` is the SHA-256
of the prior record's canonical form, and ``record_hash`` is the
SHA-256 of this record's canonical form (which itself includes
``prev_hash``). This gives tamper-evident audit at every scale per.

Pure logic
----------

* No DAO, no LLM, no network. The ledger is in-memory; callers who
  want durable storage persist :meth:`SubstrateTraceLedger.records`
  externally and pass them back into :meth:`from_records` to verify.
* All verdict types come from the prior-phase primitives (no
  re-creation of enums). This is the composition surface for the
  Tier-0 + Tier-1 work shipped previously.
* Deterministic. The same field values produce the same record hash;
  the canonical form is JSON with sorted keys and no whitespace.

Optional HMAC checkpointing
---------------------------

The ledger exposes :meth:`compute_checkpoint` so operators with an
HMAC key can publish substrate condition #2's HMAC checkpoint over a
range of records. The primitive itself does **not** carry the key
key custody is the operator's concern.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Final, List, Mapping, Optional, Tuple

from substrate.drift.drift_pattern_matcher import (
    DriftPattern,
    DriftPatternReport,
)
from substrate.harness import InterceptKind
from substrate.net_potential_gain_gate import (
    NetPotentialGainVerdict,
)
from substrate.resistance_band import (
    ResistanceBandClassification,
)

GENESIS_PREV_HASH: Final[str] = "0" * 64
_HASH_HEX_LEN: Final[int] = 64

@dataclass(frozen=True, slots=True)
class SubstrateTraceRecord:  # pylint: disable=too-many-instance-attributes
    """One substrate-aware decision's audit row.

    Optional ``actor_cell_id`` / ``actor_node_id`` fields make the
    the host application entity hierarchy explicit on each row (per substrate
    condition #3). When ``None`` (the legacy default), the fields are
    omitted from the canonical-dict so existing hash chains continue
    to verify; when set, they participate in the hash chain and are
    recoverable for cross-scale audit roll-up.
    """

    sequence: int
    epoch_seconds: int
    decision_id: str
    decision_kind: str
    permitted: bool
    rationale: str
    npg_verdict: Optional[NetPotentialGainVerdict]
    resistance_band: Optional[ResistanceBandClassification]
    sin_dominant: Optional[DriftPattern]
    sin_composite_confidence: float
    sin_pride_present: bool
    sin_kinds_detected: Tuple[DriftPattern, ...]
    harness_intercept_kinds: Tuple[InterceptKind, ...]
    prev_hash: str
    record_hash: str
    actor_cell_id: Optional[str] = None
    actor_node_id: Optional[str] = None

    def to_canonical_dict(self) -> dict[str, object]:
        """Return the canonical-form dict used for hashing.

        ``record_hash`` is excluded — it is the output of hashing this
        dict, so it cannot be a hash input. ``actor_cell_id`` and
        ``actor_node_id`` are included only when non-None so legacy
        records (without actor identity) keep their hashes.
        """
        payload: dict[str, object] = {
            "sequence": self.sequence,
            "epoch_seconds": self.epoch_seconds,
            "decision_id": self.decision_id,
            "decision_kind": self.decision_kind,
            "permitted": self.permitted,
            "rationale": self.rationale,
            "npg_verdict": (
                self.npg_verdict.value if self.npg_verdict else None
            ),
            "resistance_band": (
                self.resistance_band.value if self.resistance_band else None
            ),
            "sin_dominant": (
                self.sin_dominant.value if self.sin_dominant else None
            ),
            "sin_composite_confidence": self.sin_composite_confidence,
            "sin_pride_present": self.sin_pride_present,
            "sin_kinds_detected": [s.value for s in self.sin_kinds_detected],
            "harness_intercept_kinds": [
                k.value for k in self.harness_intercept_kinds
            ],
            "prev_hash": self.prev_hash,
        }
        if self.actor_cell_id is not None:
            payload["actor_cell_id"] = self.actor_cell_id
        if self.actor_node_id is not None:
            payload["actor_node_id"] = self.actor_node_id
        return payload

@dataclass(frozen=True, slots=True)
class LedgerVerification:
    """Outcome of :meth:`SubstrateTraceLedger.verify`."""

    ok: bool
    bad_sequence: Optional[int]
    reason: Optional[str]

@dataclass(frozen=True, slots=True)
class DriftPatternSummary:
    """Minimal substrate-trace projection of a :class:`DriftPatternReport`."""

    dominant_pattern: Optional[DriftPattern]
    composite_confidence: float
    amplifier_pattern_present: bool
    kinds_detected: Tuple[DriftPattern, ...]

    @classmethod
    def from_report(cls, report: DriftPatternReport) -> "DriftPatternSummary":
        """Project a full pattern report onto the audit-friendly summary."""
        return cls(
            dominant_pattern=report.dominant_pattern,
            composite_confidence=report.composite_confidence,
            amplifier_pattern_present=report.amplifier_pattern_present,
            kinds_detected=tuple(d.pattern for d in report.detections),
        )

def _canonical_bytes(payload: Mapping[str, object]) -> bytes:
    """JSON-serialize a canonical dict deterministically."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

def _hash_canonical(payload: Mapping[str, object]) -> str:
    """Return SHA-256 hex of the canonical bytes for ``payload``."""
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()

def _validate_hash_hex(value: str, name: str) -> None:
    if len(value) != _HASH_HEX_LEN:
        raise ValueError(f"{name} must be {_HASH_HEX_LEN} hex chars")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be hex") from exc

class SubstrateTraceLedger:
    """Append-only hash-chained ledger of substrate decisions."""

    def __init__(
        self,
        *,
        initial_records: Optional[Tuple[SubstrateTraceRecord, ...]] = None,
    ) -> None:
        self._records: List[SubstrateTraceRecord] = []
        if initial_records:
            for rec in initial_records:
                self._reattach(rec)

    @classmethod
    def from_records(
        cls,
        records: Tuple[SubstrateTraceRecord, ...],
    ) -> "SubstrateTraceLedger":
        """Build a ledger from a previously serialized record tuple.

        Does **not** re-verify the chain — call :meth:`verify` after.
        """
        ledger = cls()
        ledger._records.extend(records)  # pylint: disable=protected-access
        return ledger

    @property
    def length(self) -> int:
        """Number of records in the ledger."""
        return len(self._records)

    def records(self) -> Tuple[SubstrateTraceRecord, ...]:
        """Return all records as an immutable tuple."""
        return tuple(self._records)

    def last(self) -> Optional[SubstrateTraceRecord]:
        """Return the most-recent record (None if empty)."""
        return self._records[-1] if self._records else None

    def append(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
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
        """Append one substrate-aware decision to the ledger.

        ``actor_cell_id`` / ``actor_node_id`` (optional) make the
        the host application entity hierarchy explicit per substrate condition #3:
        the cell is the physical, replicable instance; the node is the
        logical, persistent face of the cell cluster. When omitted,
        the record carries no actor identity and the hash chain is
        identical to the legacy schema.
        """
        if not decision_id:
            raise ValueError("decision_id must be non-empty")
        if not decision_kind:
            raise ValueError("decision_kind must be non-empty")
        if epoch_seconds < 0:
            raise ValueError("epoch_seconds must be >= 0")
        if len(set(harness_intercept_kinds)) != len(harness_intercept_kinds):
            raise ValueError("harness_intercept_kinds must be unique")
        if actor_cell_id is not None and not actor_cell_id:
            raise ValueError("actor_cell_id must be non-empty when supplied")
        if actor_node_id is not None and not actor_node_id:
            raise ValueError("actor_node_id must be non-empty when supplied")

        summary = sin_summary or _empty_sin_summary()
        if not 0.0 <= summary.composite_confidence <= 1.0:
            raise ValueError("sin_composite_confidence must be in [0, 1]")
        if len(set(summary.kinds_detected)) != len(summary.kinds_detected):
            raise ValueError("sin_kinds_detected must be unique")

        prev_hash = (
            self._records[-1].record_hash
            if self._records
            else GENESIS_PREV_HASH
        )
        sequence = len(self._records)

        partial: dict[str, object] = {
            "sequence": sequence,
            "epoch_seconds": epoch_seconds,
            "decision_id": decision_id,
            "decision_kind": decision_kind,
            "permitted": permitted,
            "rationale": rationale,
            "npg_verdict": npg_verdict.value if npg_verdict else None,
            "resistance_band": (
                resistance_band.value if resistance_band else None
            ),
            "sin_dominant": (
                summary.dominant_pattern.value if summary.dominant_pattern else None
            ),
            "sin_composite_confidence": summary.composite_confidence,
            "sin_pride_present": summary.amplifier_pattern_present,
            "sin_kinds_detected": [s.value for s in summary.kinds_detected],
            "harness_intercept_kinds": [
                k.value for k in harness_intercept_kinds
            ],
            "prev_hash": prev_hash,
        }
        if actor_cell_id is not None:
            partial["actor_cell_id"] = actor_cell_id
        if actor_node_id is not None:
            partial["actor_node_id"] = actor_node_id
        record_hash = _hash_canonical(partial)

        record = SubstrateTraceRecord(
            sequence=sequence,
            epoch_seconds=epoch_seconds,
            decision_id=decision_id,
            decision_kind=decision_kind,
            permitted=permitted,
            rationale=rationale,
            npg_verdict=npg_verdict,
            resistance_band=resistance_band,
            sin_dominant=summary.dominant_pattern,
            sin_composite_confidence=summary.composite_confidence,
            sin_pride_present=summary.amplifier_pattern_present,
            sin_kinds_detected=tuple(summary.kinds_detected),
            harness_intercept_kinds=tuple(harness_intercept_kinds),
            prev_hash=prev_hash,
            record_hash=record_hash,
            actor_cell_id=actor_cell_id,
            actor_node_id=actor_node_id,
        )
        self._records.append(record)
        return record

    def verify(self) -> LedgerVerification:
        """Verify the hash chain end-to-end.

        Returns success on an empty ledger. On failure, surfaces the
        first sequence number that fails and a short reason. The
        ledger does not abort or mutate state on failure — operators
        decide how to remediate.
        """
        prev_hash = GENESIS_PREV_HASH
        for index, rec in enumerate(self._records):
            if rec.sequence != index:
                return LedgerVerification(
                    ok=False,
                    bad_sequence=index,
                    reason=(
                        f"sequence gap: record claims {rec.sequence}, "
                        f"expected {index}"
                    ),
                )
            if rec.prev_hash != prev_hash:
                return LedgerVerification(
                    ok=False,
                    bad_sequence=index,
                    reason="prev_hash mismatch with prior record",
                )
            expected = _hash_canonical(rec.to_canonical_dict())
            if rec.record_hash != expected:
                return LedgerVerification(
                    ok=False,
                    bad_sequence=index,
                    reason="record_hash does not match canonical body",
                )
            try:
                _validate_hash_hex(rec.record_hash, "record_hash")
            except ValueError as exc:
                return LedgerVerification(
                    ok=False, bad_sequence=index, reason=str(exc),
                )
            prev_hash = rec.record_hash
        return LedgerVerification(ok=True, bad_sequence=None, reason=None)

    def by_decision_kind(self, kind: str) -> Tuple[SubstrateTraceRecord, ...]:
        """Filter records by ``decision_kind`` tag."""
        return tuple(r for r in self._records if r.decision_kind == kind)

    def by_npg_verdict(
        self, verdict: NetPotentialGainVerdict,
    ) -> Tuple[SubstrateTraceRecord, ...]:
        """Filter records by NPG verdict."""
        return tuple(r for r in self._records if r.npg_verdict is verdict)

    def by_intercept_kind(
        self, kind: InterceptKind,
    ) -> Tuple[SubstrateTraceRecord, ...]:
        """Filter records that include a given harness intercept."""
        return tuple(
            r for r in self._records if kind in r.harness_intercept_kinds
        )

    def denied(self) -> Tuple[SubstrateTraceRecord, ...]:
        """Filter records where ``permitted is False``."""
        return tuple(r for r in self._records if not r.permitted)

    def compute_checkpoint(
        self,
        *,
        secret: bytes,
        start_sequence: int = 0,
        end_sequence_exclusive: Optional[int] = None,
    ) -> str:
        """HMAC-SHA256 checkpoint over ``record_hash`` values in a range.

        Per substrate condition #2 (HMAC checkpoints). Key custody is
        the operator's concern — the ledger only takes the bytes.
        """
        if not secret:
            raise ValueError("secret must be non-empty")
        end = (
            len(self._records)
            if end_sequence_exclusive is None
            else end_sequence_exclusive
        )
        if start_sequence < 0:
            raise ValueError("start_sequence must be >= 0")
        if end > len(self._records):
            raise ValueError(
                "end_sequence_exclusive exceeds ledger length"
            )
        if end <= start_sequence:
            raise ValueError(
                "end_sequence_exclusive must be > start_sequence"
            )
        mac = hmac.new(secret, digestmod=hashlib.sha256)
        for rec in self._records[start_sequence:end]:
            mac.update(rec.record_hash.encode("ascii"))
        return mac.hexdigest()

    def _reattach(self, rec: SubstrateTraceRecord) -> None:
        """Re-attach an externally-built record without recomputing."""
        self._records.append(rec)

def _empty_sin_summary() -> DriftPatternSummary:
    """Default summary used when caller did not run the pattern matcher."""
    return DriftPatternSummary(
        dominant_pattern=None,
        composite_confidence=0.0,
        amplifier_pattern_present=False,
        kinds_detected=(),
    )

__all__ = [
    "GENESIS_PREV_HASH",
    "LedgerVerification",
    "DriftPatternSummary",
    "SubstrateTraceLedger",
    "SubstrateTraceRecord",
]
