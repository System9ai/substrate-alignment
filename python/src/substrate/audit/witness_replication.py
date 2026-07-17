"""Multi-cell witness replication coordinator.

Closes the *multi-cell witness propagation* v2 item from the
M-Substrate-1 grade. Replicates :class:`PeerWitnessRecord` rows
across cells:

1. **Publish**: when the local cell records a decision (via the
   :class:`SubstrateDecisionAuditor`), the coordinator forwards
   the self-witness row to peer cells via a pluggable transport.
2. **Receive**: when a peer cell submits a witness row, the
   coordinator verifies the attestation via
   :class:`MultiKeyWitnessVerifier` and appends the verified row
   to the local :class:`PeerWitnessLedger`.

Pure logic:

- No actual transport (HTTP/gRPC/sneakernet) lives here.
- The :class:`WitnessTransport` Protocol defines the contract;
  implementations live next to their transport (cell-to-cell HTTP
  in :mod:`witness_http_transport`, edge node gRPC in the Rust crate).
- All cryptographic verification routes through the existing
  signer + verifier.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Final, Optional, Protocol, Tuple

import logging
from substrate.audit.peer_witness import (
    PeerWitnessLedger,
    PeerWitnessRecord,
)
from substrate.audit.peer_witness_signer import (
    MultiKeyWitnessVerifier,
    WitnessPayload,
)

LOG = logging.getLogger(__name__)

class WitnessTransport(Protocol):  # pylint: disable=too-few-public-methods
    """Duck-typed transport for cell-to-cell witness publish.

    Implementations (HTTP, gRPC, sneakernet bundles) live next to
    their transport. The coordinator only sees this Protocol.
    """

    def publish(self, record: PeerWitnessRecord) -> None:
        """Forward one witness row to one or more peer cells."""
        ...  # pylint: disable=unnecessary-ellipsis

@dataclass(frozen=True, slots=True)
class ReplicationOutcome:
    """Outcome of one publish or receive call."""

    accepted: bool
    reason: str

    @classmethod
    def ok(cls, reason: str = "") -> "ReplicationOutcome":
        """Construct a successful outcome."""
        return cls(accepted=True, reason=reason)

    @classmethod
    def rejected(cls, reason: str) -> "ReplicationOutcome":
        """Construct a rejection outcome with a human-readable reason."""
        return cls(accepted=False, reason=reason)

#: Reasons emitted when a witness submission is rejected. Stable
#: strings so audit logs / dashboards can filter / aggregate.
REASON_DUPLICATE: Final[str] = "duplicate_witness_for_decision_and_peer"
REASON_UNKNOWN_PEER: Final[str] = "unknown_peer_no_verification_key"
REASON_BAD_SIGNATURE: Final[str] = "attestation_signature_verification_failed"
REASON_INVALID_PAYLOAD: Final[str] = "payload_field_validation_failed"

class WitnessReplicationCoordinator:
    """Publish local witnesses + receive + verify peer witnesses.

    Construction takes the local witness ledger + the verifier
    (which has the registry of known peer keys). Optionally a
    transport to publish to. Operators wire all three.
    """

    def __init__(
        self,
        *,
        local_ledger: PeerWitnessLedger,
        verifier: MultiKeyWitnessVerifier,
        transport: Optional[WitnessTransport] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._ledger = local_ledger
        self._verifier = verifier
        self._transport = transport
        # clock used for test injection; not load-bearing here.
        _ = clock

    @property
    def known_peers(self) -> frozenset[str]:
        """Peer entity IDs the verifier has keys for."""
        return self._verifier.known_peers()

    def publish_local(
        self, record: PeerWitnessRecord,
    ) -> ReplicationOutcome:
        """Forward a locally-recorded witness to peer cells.

        No-op (success) when no transport is wired. Transport
        failures are reported in the outcome but never raised.
        """
        if self._transport is None:
            return ReplicationOutcome.ok("no transport configured")
        try:
            self._transport.publish(record)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            LOG.warning(
                "witness publish failed decision=%s peer=%s: %s",
                record.decision_id, record.witness_entity_id, exc,
            )
            return ReplicationOutcome.rejected(f"transport_error:{exc}")
        return ReplicationOutcome.ok()

    def receive_peer_witness(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        decision_id: str,
        primary_record_hash: str,
        witness_entity_id: str,
        witnessed_at_epoch: int,
        attestation: str,
    ) -> ReplicationOutcome:
        """Verify + append a witness row from a peer cell.

        Rejects:
        - duplicate witnesses (same (decision_id, witness_entity_id))
        - unknown peers (no key in the verifier)
        - bad signatures
        - malformed payloads
        """
        try:
            payload = WitnessPayload(
                decision_id=decision_id,
                primary_record_hash=primary_record_hash,
                witness_entity_id=witness_entity_id,
                witnessed_at_epoch=witnessed_at_epoch,
            )
        except ValueError as exc:
            return ReplicationOutcome.rejected(
                f"{REASON_INVALID_PAYLOAD}:{exc}",
            )
        if witness_entity_id not in self._verifier.known_peers():
            return ReplicationOutcome.rejected(REASON_UNKNOWN_PEER)
        if not self._verifier.verify(payload, attestation):
            return ReplicationOutcome.rejected(REASON_BAD_SIGNATURE)
        # Dedupe BEFORE append; `PeerWitnessLedger.append` rejects
        # duplicates with ValueError; we want a typed outcome.
        if self._ledger.is_witnessed_by(decision_id, witness_entity_id):
            return ReplicationOutcome.rejected(REASON_DUPLICATE)
        self._ledger.append(
            decision_id=decision_id,
            primary_record_hash=primary_record_hash,
            witness_entity_id=witness_entity_id,
            witnessed_at_epoch=witnessed_at_epoch,
            attestation=attestation,
        )
        return ReplicationOutcome.ok()

    def witnesses_for(
        self, decision_id: str,
    ) -> Tuple[PeerWitnessRecord, ...]:
        """Convenience pass-through to the local ledger."""
        return self._ledger.witnesses_for(decision_id)

__all__ = [
    "REASON_BAD_SIGNATURE",
    "REASON_DUPLICATE",
    "REASON_INVALID_PAYLOAD",
    "REASON_UNKNOWN_PEER",
    "ReplicationOutcome",
    "WitnessReplicationCoordinator",
    "WitnessTransport",
]
