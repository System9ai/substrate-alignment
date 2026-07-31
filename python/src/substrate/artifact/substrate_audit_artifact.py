"""Substrate audit artifact.

Portable, deterministically-serialized bundle wrapping a
:class:`SubstrateTraceLedger` with a manifest. The
artifact is the unit of substrate-audit exchange between cells, the
form in which audits flow to long-term observation storage, and the
shape extracted into this open-source repository.

Substrate-alignment
===================

Per substrate condition #2 ("tamper-evident audit at every scale
must be **symmetric** (every agent observes and is observed)"),
substrate audit chains must be portable so that peers can verify each
other's observations. A ledger held only on its producing cell is
asymmetric; an artifact exported from one cell and importable by
another is the operational form of symmetric audit.

Pure logic
==========

* No DAO, no LLM, no network. Serialization is canonical JSON.
* Honest uncertainty. The manifest fields are derived from the
  records, not from caller assertions; caller-supplied
  ``cell_id`` is the only externally-supplied field. The artifact's
  verification re-derives manifest fields from records on the
  receiving side and rejects mismatches.
* Round-trip determinism. ``json.dumps(..., sort_keys=True,
  separators=(",", ":"))`` plus typed enum-as-string serialization
  yields byte-identical output across processes, machines, and
  Python versions.
* Optional HMAC checkpoint per substrate condition #2's HMAC half.
  Key custody is the operator's concern; the artifact only carries
  the resulting checkpoint and the range it covers.
"""
from __future__ import annotations

import hmac
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Mapping, Optional, Tuple, TypeVar, cast

from substrate.audit.substrate_trace import (
    GENESIS_PREV_HASH,
    LedgerVerification,
    SubstrateTraceLedger,
    SubstrateTraceRecord,
)
from substrate.drift.drift_pattern_matcher import DriftPattern
from substrate.harness import InterceptKind
from substrate.net_potential_gain_gate import (
    NetPotentialGainVerdict,
)
from substrate.resistance_band import (
    ResistanceBandClassification,
)

ARTIFACT_FORMAT_VERSION: Final[str] = "1"
_HASH_HEX_LEN: Final[int] = 64
_E = TypeVar("_E", bound=Enum)

@dataclass(frozen=True, slots=True)
class SubstrateAuditManifest:  # pylint: disable=too-many-instance-attributes
    """Self-describing header for one substrate audit artifact."""

    format_version: str
    cell_id: str
    record_count: int
    earliest_epoch_seconds: Optional[int]
    latest_epoch_seconds: Optional[int]
    chain_head_hash: str
    hmac_checkpoint: Optional[str] = None
    hmac_checkpoint_start: Optional[int] = None
    hmac_checkpoint_end_exclusive: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.format_version:
            raise ValueError("format_version must be non-empty")
        if not self.cell_id:
            raise ValueError("cell_id must be non-empty")
        if self.record_count < 0:
            raise ValueError("record_count must be >= 0")
        if len(self.chain_head_hash) != _HASH_HEX_LEN:
            raise ValueError(
                f"chain_head_hash must be {_HASH_HEX_LEN} hex chars"
            )
        if (self.earliest_epoch_seconds is None) != (
            self.latest_epoch_seconds is None
        ):
            raise ValueError(
                "earliest_epoch_seconds and latest_epoch_seconds must "
                "both be present or both absent"
            )
        if (
            self.earliest_epoch_seconds is not None
            and self.latest_epoch_seconds is not None
            and self.earliest_epoch_seconds > self.latest_epoch_seconds
        ):
            raise ValueError(
                "earliest_epoch_seconds must be <= latest_epoch_seconds"
            )
        hmac_fields = (
            self.hmac_checkpoint,
            self.hmac_checkpoint_start,
            self.hmac_checkpoint_end_exclusive,
        )
        if not _all_none_or_all_set(hmac_fields):
            raise ValueError(
                "hmac_checkpoint, hmac_checkpoint_start, "
                "hmac_checkpoint_end_exclusive must be all set or all None"
            )

@dataclass(frozen=True, slots=True)
class ArtifactVerification:
    """Outcome of :meth:`SubstrateAuditArtifact.verify`."""

    ok: bool
    chain: LedgerVerification
    manifest_ok: bool
    hmac_ok: Optional[bool]
    reason: Optional[str]

@dataclass(frozen=True, slots=True)
class SubstrateAuditArtifact:
    """A manifest + records bundle, JSON-portable."""

    manifest: SubstrateAuditManifest
    records: Tuple[SubstrateTraceRecord, ...] = field(default_factory=tuple)

    # ---- constructors -----------------------------------------------

    @classmethod
    def from_ledger(
        cls,
        *,
        ledger: SubstrateTraceLedger,
        cell_id: str,
        hmac_secret: Optional[bytes] = None,
    ) -> "SubstrateAuditArtifact":
        """Package a ledger into an artifact (optional HMAC checkpoint)."""
        if not cell_id:
            raise ValueError("cell_id must be non-empty")
        records = ledger.records()
        manifest = cls._build_manifest(
            cell_id=cell_id,
            records=records,
            hmac_secret=hmac_secret,
            ledger=ledger,
        )
        return cls(manifest=manifest, records=records)

    @classmethod
    def from_json(cls, payload: str) -> "SubstrateAuditArtifact":
        """Deserialize a canonical-JSON payload into an artifact."""
        if not payload:
            raise ValueError("payload must be non-empty")
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON payload: {exc}") from exc
        if not isinstance(parsed, Mapping):
            raise ValueError("payload root must be a JSON object")
        parsed_map = cast("Mapping[str, object]", parsed)
        manifest_raw: object = parsed_map.get("manifest")
        records_raw: object = parsed_map.get("records")
        if not isinstance(manifest_raw, Mapping):
            raise ValueError("manifest must be a JSON object")
        if not isinstance(records_raw, list):
            raise ValueError("records must be a JSON array")
        manifest = _deserialize_manifest(cast("Mapping[str, object]", manifest_raw))
        records_list = cast("list[object]", records_raw)
        records = tuple(
            _deserialize_record(cast("Mapping[str, object]", r))
            for r in records_list
        )
        return cls(manifest=manifest, records=records)

    # ---- exports ----------------------------------------------------

    def to_json(self) -> str:
        """Serialize deterministically (sorted keys, no whitespace)."""
        return json.dumps(
            self._to_canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )

    def to_ledger(self) -> SubstrateTraceLedger:
        """Reconstruct a :class:`SubstrateTraceLedger` from the records."""
        return SubstrateTraceLedger.from_records(self.records)

    # ---- verification -----------------------------------------------

    def verify(
        self,
        *,
        hmac_secret: Optional[bytes] = None,
    ) -> ArtifactVerification:
        """Verify the artifact end-to-end.

        Checks:

        1. Inner record chain (:meth:`SubstrateTraceLedger.verify`).
        2. Manifest fields match the records (count, time range,
           chain head, format version).
        3. If a secret is supplied AND the manifest has an HMAC
           checkpoint, recompute and compare.
        """
        ledger = self.to_ledger()
        chain = ledger.verify()
        if not chain.ok:
            return ArtifactVerification(
                ok=False, chain=chain, manifest_ok=False,
                hmac_ok=None, reason="chain verification failed",
            )

        manifest_ok, manifest_reason = self._verify_manifest()
        if not manifest_ok:
            return ArtifactVerification(
                ok=False, chain=chain, manifest_ok=False,
                hmac_ok=None, reason=manifest_reason,
            )

        hmac_ok, hmac_reason = self._verify_hmac(ledger, hmac_secret)
        if hmac_ok is False:
            return ArtifactVerification(
                ok=False, chain=chain, manifest_ok=True,
                hmac_ok=False, reason=hmac_reason,
            )

        return ArtifactVerification(
            ok=True, chain=chain, manifest_ok=True,
            hmac_ok=hmac_ok, reason=None,
        )

    # ---- helpers ----------------------------------------------------

    def _to_canonical_dict(self) -> dict[str, object]:
        return {
            "manifest": _serialize_manifest(self.manifest),
            "records": [_serialize_record(r) for r in self.records],
        }

    def _verify_manifest(self) -> Tuple[bool, Optional[str]]:
        m = self.manifest
        if m.format_version != ARTIFACT_FORMAT_VERSION:
            return False, (
                f"unknown format_version {m.format_version!r}; "
                f"expected {ARTIFACT_FORMAT_VERSION!r}"
            )
        if m.record_count != len(self.records):
            return False, (
                f"manifest.record_count={m.record_count} does not "
                f"match len(records)={len(self.records)}"
            )
        expected_head = (
            self.records[-1].record_hash
            if self.records
            else GENESIS_PREV_HASH
        )
        if m.chain_head_hash != expected_head:
            return False, "chain_head_hash does not match last record"
        expected_range = _epoch_range(self.records)
        if (m.earliest_epoch_seconds, m.latest_epoch_seconds) != \
                expected_range:
            return False, (
                "manifest time range does not match records"
            )
        return True, None

    def _verify_hmac(
        self,
        ledger: SubstrateTraceLedger,
        secret: Optional[bytes],
    ) -> Tuple[Optional[bool], Optional[str]]:
        if self.manifest.hmac_checkpoint is None:
            return None, None
        if secret is None:
            return None, None
        assert self.manifest.hmac_checkpoint_start is not None
        assert self.manifest.hmac_checkpoint_end_exclusive is not None
        try:
            expected = ledger.compute_checkpoint(
                secret=secret,
                start_sequence=self.manifest.hmac_checkpoint_start,
                end_sequence_exclusive=(
                    self.manifest.hmac_checkpoint_end_exclusive
                ),
            )
        except ValueError as exc:
            return False, f"hmac recomputation failed: {exc}"
        if not hmac.compare_digest(expected, self.manifest.hmac_checkpoint):
            return False, "hmac checkpoint mismatch"
        return True, None

    @staticmethod
    def _build_manifest(
        *,
        cell_id: str,
        records: Tuple[SubstrateTraceRecord, ...],
        hmac_secret: Optional[bytes],
        ledger: SubstrateTraceLedger,
    ) -> SubstrateAuditManifest:
        earliest, latest = _epoch_range(records)
        head = records[-1].record_hash if records else GENESIS_PREV_HASH
        if hmac_secret is None or not records:
            return SubstrateAuditManifest(
                format_version=ARTIFACT_FORMAT_VERSION,
                cell_id=cell_id,
                record_count=len(records),
                earliest_epoch_seconds=earliest,
                latest_epoch_seconds=latest,
                chain_head_hash=head,
            )
        checkpoint = ledger.compute_checkpoint(secret=hmac_secret)
        return SubstrateAuditManifest(
            format_version=ARTIFACT_FORMAT_VERSION,
            cell_id=cell_id,
            record_count=len(records),
            earliest_epoch_seconds=earliest,
            latest_epoch_seconds=latest,
            chain_head_hash=head,
            hmac_checkpoint=checkpoint,
            hmac_checkpoint_start=0,
            hmac_checkpoint_end_exclusive=len(records),
        )

# -----------------------------
# Helpers
# -----------------------------

def _all_none_or_all_set(values: Tuple[object, ...]) -> bool:
    """Return True iff every value is None OR every value is non-None."""
    nones = sum(1 for v in values if v is None)
    return nones == 0 or nones == len(values)

def _epoch_range(
    records: Tuple[SubstrateTraceRecord, ...],
) -> Tuple[Optional[int], Optional[int]]:
    if not records:
        return None, None
    epochs = [r.epoch_seconds for r in records]
    return min(epochs), max(epochs)

def _serialize_manifest(m: SubstrateAuditManifest) -> dict[str, object]:
    out: dict[str, object] = {
        "format_version": m.format_version,
        "cell_id": m.cell_id,
        "record_count": m.record_count,
        "earliest_epoch_seconds": m.earliest_epoch_seconds,
        "latest_epoch_seconds": m.latest_epoch_seconds,
        "chain_head_hash": m.chain_head_hash,
    }
    if m.hmac_checkpoint is not None:
        out["hmac_checkpoint"] = m.hmac_checkpoint
        out["hmac_checkpoint_start"] = m.hmac_checkpoint_start
        out["hmac_checkpoint_end_exclusive"] = m.hmac_checkpoint_end_exclusive
    return out

def _serialize_record(r: SubstrateTraceRecord) -> dict[str, object]:
    canonical = r.to_canonical_dict()
    canonical["record_hash"] = r.record_hash
    return canonical

def _deserialize_manifest(
    raw: Mapping[str, object],
) -> SubstrateAuditManifest:
    try:
        return SubstrateAuditManifest(
            format_version=_required_str(raw, "format_version"),
            cell_id=_required_str(raw, "cell_id"),
            record_count=_required_int(raw, "record_count"),
            earliest_epoch_seconds=_optional_int(
                raw, "earliest_epoch_seconds",
            ),
            latest_epoch_seconds=_optional_int(
                raw, "latest_epoch_seconds",
            ),
            chain_head_hash=_required_str(raw, "chain_head_hash"),
            hmac_checkpoint=_optional_str(raw, "hmac_checkpoint"),
            hmac_checkpoint_start=_optional_int(
                raw, "hmac_checkpoint_start",
            ),
            hmac_checkpoint_end_exclusive=_optional_int(
                raw, "hmac_checkpoint_end_exclusive",
            ),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"manifest deserialize failed: {exc}") from exc

def _deserialize_record(
    raw: Mapping[str, object],
) -> SubstrateTraceRecord:
    try:
        return SubstrateTraceRecord(
            sequence=_required_int(raw, "sequence"),
            epoch_seconds=_required_int(raw, "epoch_seconds"),
            decision_id=_required_str(raw, "decision_id"),
            decision_kind=_required_str(raw, "decision_kind"),
            permitted=_required_bool(raw, "permitted"),
            rationale=_required_str(raw, "rationale"),
            npg_verdict=_optional_enum(
                raw, "npg_verdict", NetPotentialGainVerdict,
            ),
            resistance_band=_optional_enum(
                raw, "resistance_band", ResistanceBandClassification,
            ),
            sin_dominant=_optional_enum(raw, "sin_dominant", DriftPattern),
            sin_composite_confidence=_required_float(
                raw, "sin_composite_confidence",
            ),
            sin_pride_present=_required_bool(raw, "sin_pride_present"),
            sin_kinds_detected=_required_enum_tuple(
                raw, "sin_kinds_detected", DriftPattern,
            ),
            harness_intercept_kinds=_required_enum_tuple(
                raw, "harness_intercept_kinds", InterceptKind,
            ),
            prev_hash=_required_str(raw, "prev_hash"),
            record_hash=_required_str(raw, "record_hash"),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"record deserialize failed: {exc}") from exc

def _required_str(raw: Mapping[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str, got {type(value).__name__}")
    return value

def _required_int(raw: Mapping[str, object], key: str) -> int:
    value = raw[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be int, got {type(value).__name__}")
    return value

def _required_bool(raw: Mapping[str, object], key: str) -> bool:
    value = raw[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool, got {type(value).__name__}")
    return value

def _required_float(raw: Mapping[str, object], key: str) -> float:
    value = raw[key]
    if isinstance(value, bool):
        raise TypeError(f"{key} must be float, got bool")
    if not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be float, got {type(value).__name__}")
    return float(value)

def _optional_str(
    raw: Mapping[str, object], key: str,
) -> Optional[str]:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str or None")
    return value

def _optional_int(
    raw: Mapping[str, object], key: str,
) -> Optional[int]:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be int or None")
    return value

def _optional_enum(
    raw: Mapping[str, object], key: str, enum_cls: type[_E],
) -> Optional[_E]:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str or None")
    return enum_cls(value)

def _required_enum_tuple(
    raw: Mapping[str, object], key: str, enum_cls: type[_E],
) -> Tuple[_E, ...]:
    value = raw[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list")
    items = cast("list[object]", value)
    return tuple(enum_cls(v) for v in items)

__all__ = [
    "ARTIFACT_FORMAT_VERSION",
    "ArtifactVerification",
    "SubstrateAuditArtifact",
    "SubstrateAuditManifest",
]
