"""Tests for the witness replication coordinator (J.3)."""
from __future__ import annotations

from substrate.audit.peer_witness import (
    PeerWitnessLedger,
    PeerWitnessRecord,
)
from substrate.audit.peer_witness_signer import (
    HmacWitnessSigner,
    MultiKeyWitnessVerifier,
    WitnessPayload,
)
from substrate.audit.witness_replication import (
    REASON_BAD_SIGNATURE,
    REASON_DUPLICATE,
    REASON_INVALID_PAYLOAD,
    REASON_UNKNOWN_PEER,
    ReplicationOutcome,
    WitnessReplicationCoordinator,
)

class _CapturingTransport:
    def __init__(self) -> None:
        self.published: list[PeerWitnessRecord] = []
        self._raise: Exception | None = None

    def will_raise(self, exc: Exception) -> None:
        self._raise = exc

    def publish(self, record: PeerWitnessRecord) -> None:
        if self._raise is not None:
            raise self._raise
        self.published.append(record)

_PRIMARY_HASH = "a" * 64

def _payload(
    *, decision_id: str = "d-1", witness: str = "cell-2",
    epoch: int = 1000,
) -> WitnessPayload:
    return WitnessPayload(
        decision_id=decision_id,
        primary_record_hash=_PRIMARY_HASH,
        witness_entity_id=witness,
        witnessed_at_epoch=epoch,
    )

def _coord(
    transport: object = None,
    *,
    peer_keys: dict[str, bytes] | None = None,
) -> WitnessReplicationCoordinator:
    return WitnessReplicationCoordinator(
        local_ledger=PeerWitnessLedger(),
        verifier=MultiKeyWitnessVerifier(
            peer_keys or {"cell-2": b"peer-key-2"},
        ),
        transport=transport,  # type: ignore[arg-type]
    )

class TestReplicationOutcome:
    def test_ok_factory(self) -> None:
        r = ReplicationOutcome.ok()
        assert r.accepted
        assert r.reason == ""

    def test_rejected_factory(self) -> None:
        r = ReplicationOutcome.rejected("reason")
        assert not r.accepted
        assert r.reason == "reason"

class TestPublishLocal:
    def test_no_transport_succeeds(self) -> None:
        coord = _coord(transport=None)
        ledger = PeerWitnessLedger()
        ledger.append(
            decision_id="d-1", primary_record_hash=_PRIMARY_HASH,
            witness_entity_id="cell-local", witnessed_at_epoch=1,
            attestation="att",
        )
        outcome = coord.publish_local(ledger.records()[0])
        assert outcome.accepted

    def test_with_transport_forwards(self) -> None:
        transport = _CapturingTransport()
        coord = _coord(transport=transport)
        ledger = PeerWitnessLedger()
        ledger.append(
            decision_id="d-1", primary_record_hash=_PRIMARY_HASH,
            witness_entity_id="cell-local", witnessed_at_epoch=1,
            attestation="att",
        )
        outcome = coord.publish_local(ledger.records()[0])
        assert outcome.accepted
        assert len(transport.published) == 1

    def test_transport_failure_reported(self) -> None:
        transport = _CapturingTransport()
        transport.will_raise(RuntimeError("transport down"))
        coord = _coord(transport=transport)
        ledger = PeerWitnessLedger()
        ledger.append(
            decision_id="d-1", primary_record_hash=_PRIMARY_HASH,
            witness_entity_id="cell-local", witnessed_at_epoch=1,
            attestation="att",
        )
        outcome = coord.publish_local(ledger.records()[0])
        assert not outcome.accepted
        assert "transport_error" in outcome.reason

class TestReceivePeerWitness:
    def test_valid_witness_appended(self) -> None:
        coord = _coord()
        signer = HmacWitnessSigner(b"peer-key-2")
        att = signer.sign(_payload())
        outcome = coord.receive_peer_witness(
            decision_id="d-1",
            primary_record_hash=_PRIMARY_HASH,
            witness_entity_id="cell-2",
            witnessed_at_epoch=1000,
            attestation=att,
        )
        assert outcome.accepted
        ws = coord.witnesses_for("d-1")
        assert len(ws) == 1
        assert ws[0].witness_entity_id == "cell-2"

    def test_unknown_peer_rejected(self) -> None:
        coord = _coord()
        signer = HmacWitnessSigner(b"unknown-key")
        att = signer.sign(_payload(witness="cell-mystery"))
        outcome = coord.receive_peer_witness(
            decision_id="d-1",
            primary_record_hash=_PRIMARY_HASH,
            witness_entity_id="cell-mystery",
            witnessed_at_epoch=1000,
            attestation=att,
        )
        assert not outcome.accepted
        assert outcome.reason == REASON_UNKNOWN_PEER

    def test_bad_signature_rejected(self) -> None:
        coord = _coord()
        outcome = coord.receive_peer_witness(
            decision_id="d-1",
            primary_record_hash=_PRIMARY_HASH,
            witness_entity_id="cell-2",
            witnessed_at_epoch=1000,
            attestation="hmac-sha256:" + "f" * 64,
        )
        assert not outcome.accepted
        assert outcome.reason == REASON_BAD_SIGNATURE

    def test_duplicate_rejected(self) -> None:
        coord = _coord()
        signer = HmacWitnessSigner(b"peer-key-2")
        att = signer.sign(_payload())
        # First time: accepted
        first = coord.receive_peer_witness(
            decision_id="d-1",
            primary_record_hash=_PRIMARY_HASH,
            witness_entity_id="cell-2",
            witnessed_at_epoch=1000,
            attestation=att,
        )
        assert first.accepted
        # Second time: duplicate rejected
        second = coord.receive_peer_witness(
            decision_id="d-1",
            primary_record_hash=_PRIMARY_HASH,
            witness_entity_id="cell-2",
            witnessed_at_epoch=1000,
            attestation=att,
        )
        assert not second.accepted
        assert second.reason == REASON_DUPLICATE

    def test_malformed_payload_rejected(self) -> None:
        coord = _coord()
        outcome = coord.receive_peer_witness(
            decision_id="",  # empty → invalid
            primary_record_hash=_PRIMARY_HASH,
            witness_entity_id="cell-2",
            witnessed_at_epoch=1000,
            attestation="hmac-sha256:" + "f" * 64,
        )
        assert not outcome.accepted
        assert REASON_INVALID_PAYLOAD in outcome.reason

    def test_short_hash_rejected_as_signature_fail(self) -> None:
        # primary_record_hash is opaque to validation here — only the
        # signature check catches mismatches.
        coord = _coord()
        signer = HmacWitnessSigner(b"peer-key-2")
        att = signer.sign(_payload())
        # Mutate hash → signature now invalid
        outcome = coord.receive_peer_witness(
            decision_id="d-1",
            primary_record_hash="b" * 64,
            witness_entity_id="cell-2",
            witnessed_at_epoch=1000,
            attestation=att,
        )
        assert not outcome.accepted
        assert outcome.reason == REASON_BAD_SIGNATURE

class TestQueryHelpers:
    def test_known_peers(self) -> None:
        coord = _coord(peer_keys={
            "cell-2": b"k2", "cell-3": b"k3",
        })
        assert coord.known_peers == frozenset({"cell-2", "cell-3"})

    def test_witnesses_for_empty(self) -> None:
        coord = _coord()
        assert coord.witnesses_for("missing") == ()
