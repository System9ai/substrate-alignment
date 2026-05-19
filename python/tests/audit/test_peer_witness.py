"""Tests for the symmetric-audit peer-witness ledger."""
from __future__ import annotations

import pytest

from substrate.audit.peer_witness import (
    GENESIS_PREV_HASH,
    PeerWitnessLedger,
    PeerWitnessRecord,
    quorum_witnessed,
)

_OK_HASH = "a" * 64
_OK_HASH_2 = "b" * 64

class TestAppend:
    def test_first_record_uses_genesis(self) -> None:
        ledger = PeerWitnessLedger()
        row = ledger.append(
            decision_id="d-1",
            primary_record_hash=_OK_HASH,
            witness_entity_id="peer-1",
            witnessed_at_epoch=1000,
        )
        assert row.sequence == 0
        assert row.prev_hash == GENESIS_PREV_HASH
        assert len(row.record_hash) == 64
        assert ledger.length == 1
        assert ledger.last() is row

    def test_second_record_chains(self) -> None:
        ledger = PeerWitnessLedger()
        r1 = ledger.append(
            decision_id="d-1",
            primary_record_hash=_OK_HASH,
            witness_entity_id="peer-1",
            witnessed_at_epoch=1000,
        )
        r2 = ledger.append(
            decision_id="d-1",
            primary_record_hash=_OK_HASH,
            witness_entity_id="peer-2",
            witnessed_at_epoch=1001,
        )
        assert r2.prev_hash == r1.record_hash
        assert r2.sequence == 1

    def test_attestation_passthrough(self) -> None:
        ledger = PeerWitnessLedger()
        row = ledger.append(
            decision_id="d-1",
            primary_record_hash=_OK_HASH,
            witness_entity_id="peer-1",
            witnessed_at_epoch=1000,
            attestation="sig:abc123",
        )
        assert row.attestation == "sig:abc123"

class TestValidation:
    def test_empty_decision_id(self) -> None:
        with pytest.raises(ValueError, match="decision_id"):
            PeerWitnessLedger().append(
                decision_id="",
                primary_record_hash=_OK_HASH,
                witness_entity_id="peer-1",
                witnessed_at_epoch=1000,
            )

    def test_empty_witness_id(self) -> None:
        with pytest.raises(ValueError, match="witness_entity_id"):
            PeerWitnessLedger().append(
                decision_id="d-1",
                primary_record_hash=_OK_HASH,
                witness_entity_id="",
                witnessed_at_epoch=1000,
            )

    def test_negative_epoch(self) -> None:
        with pytest.raises(ValueError, match="witnessed_at_epoch"):
            PeerWitnessLedger().append(
                decision_id="d-1",
                primary_record_hash=_OK_HASH,
                witness_entity_id="peer-1",
                witnessed_at_epoch=-1,
            )

    def test_bad_hash_length(self) -> None:
        with pytest.raises(ValueError, match="primary_record_hash"):
            PeerWitnessLedger().append(
                decision_id="d-1",
                primary_record_hash="abc",
                witness_entity_id="peer-1",
                witnessed_at_epoch=1000,
            )

    def test_bad_hash_chars(self) -> None:
        bad = "z" * 64
        with pytest.raises(ValueError, match="primary_record_hash"):
            PeerWitnessLedger().append(
                decision_id="d-1",
                primary_record_hash=bad,
                witness_entity_id="peer-1",
                witnessed_at_epoch=1000,
            )

    def test_duplicate_witness_rejected(self) -> None:
        ledger = PeerWitnessLedger()
        ledger.append(
            decision_id="d-1",
            primary_record_hash=_OK_HASH,
            witness_entity_id="peer-1",
            witnessed_at_epoch=1000,
        )
        with pytest.raises(ValueError, match="duplicate"):
            ledger.append(
                decision_id="d-1",
                primary_record_hash=_OK_HASH,
                witness_entity_id="peer-1",
                witnessed_at_epoch=2000,
            )

    def test_same_peer_different_decisions_allowed(self) -> None:
        ledger = PeerWitnessLedger()
        ledger.append(
            decision_id="d-1", primary_record_hash=_OK_HASH,
            witness_entity_id="peer-1", witnessed_at_epoch=1000,
        )
        ledger.append(
            decision_id="d-2", primary_record_hash=_OK_HASH_2,
            witness_entity_id="peer-1", witnessed_at_epoch=2000,
        )
        assert ledger.length == 2

class TestQueries:
    def test_witnesses_for(self) -> None:
        ledger = PeerWitnessLedger()
        ledger.append(
            decision_id="d-1", primary_record_hash=_OK_HASH,
            witness_entity_id="p1", witnessed_at_epoch=1,
        )
        ledger.append(
            decision_id="d-1", primary_record_hash=_OK_HASH,
            witness_entity_id="p2", witnessed_at_epoch=2,
        )
        ledger.append(
            decision_id="d-2", primary_record_hash=_OK_HASH_2,
            witness_entity_id="p1", witnessed_at_epoch=3,
        )
        d1 = ledger.witnesses_for("d-1")
        assert {r.witness_entity_id for r in d1} == {"p1", "p2"}
        assert len(ledger.witnesses_for("d-2")) == 1
        assert len(ledger.witnesses_for("missing")) == 0

    def test_witnesses_by(self) -> None:
        ledger = PeerWitnessLedger()
        ledger.append(
            decision_id="d-1", primary_record_hash=_OK_HASH,
            witness_entity_id="p1", witnessed_at_epoch=1,
        )
        ledger.append(
            decision_id="d-2", primary_record_hash=_OK_HASH_2,
            witness_entity_id="p1", witnessed_at_epoch=2,
        )
        ledger.append(
            decision_id="d-3", primary_record_hash=_OK_HASH,
            witness_entity_id="p2", witnessed_at_epoch=3,
        )
        p1 = ledger.witnesses_by("p1")
        assert {r.decision_id for r in p1} == {"d-1", "d-2"}
        assert len(ledger.witnesses_by("missing")) == 0

    def test_is_witnessed_by(self) -> None:
        ledger = PeerWitnessLedger()
        ledger.append(
            decision_id="d-1", primary_record_hash=_OK_HASH,
            witness_entity_id="p1", witnessed_at_epoch=1,
        )
        assert ledger.is_witnessed_by("d-1", "p1")
        assert not ledger.is_witnessed_by("d-1", "p2")
        assert not ledger.is_witnessed_by("missing", "p1")

class TestVerify:
    def test_empty_ledger_ok(self) -> None:
        v = PeerWitnessLedger().verify()
        assert v.ok
        assert v.bad_sequence is None

    def test_intact_chain_verifies(self) -> None:
        ledger = PeerWitnessLedger()
        for i, peer in enumerate(["p1", "p2", "p3"]):
            ledger.append(
                decision_id="d-1", primary_record_hash=_OK_HASH,
                witness_entity_id=peer, witnessed_at_epoch=i,
            )
        assert ledger.verify().ok

    def test_tampered_attestation_detected(self) -> None:
        ledger = PeerWitnessLedger()
        ledger.append(
            decision_id="d-1", primary_record_hash=_OK_HASH,
            witness_entity_id="p1", witnessed_at_epoch=1,
            attestation="original",
        )
        ledger.append(
            decision_id="d-1", primary_record_hash=_OK_HASH,
            witness_entity_id="p2", witnessed_at_epoch=2,
        )
        # Forge attestation on the first row.
        orig = ledger.records()[0]
        tampered = PeerWitnessRecord(
            sequence=orig.sequence, decision_id=orig.decision_id,
            primary_record_hash=orig.primary_record_hash,
            witness_entity_id=orig.witness_entity_id,
            witnessed_at_epoch=orig.witnessed_at_epoch,
            attestation="forged",  # changed
            prev_hash=orig.prev_hash,
            record_hash=orig.record_hash,  # unchanged on purpose
        )
        forged = PeerWitnessLedger.from_records(
            (tampered, ledger.records()[1]),
        )
        v = forged.verify()
        assert not v.ok
        assert v.bad_sequence == 0

    def test_from_records_round_trip(self) -> None:
        ledger = PeerWitnessLedger()
        ledger.append(
            decision_id="d-1", primary_record_hash=_OK_HASH,
            witness_entity_id="p1", witnessed_at_epoch=1,
        )
        ledger.append(
            decision_id="d-1", primary_record_hash=_OK_HASH,
            witness_entity_id="p2", witnessed_at_epoch=2,
        )
        rebuilt = PeerWitnessLedger.from_records(ledger.records())
        assert rebuilt.length == 2
        assert rebuilt.verify().ok

class TestQuorum:
    def test_quorum_met(self) -> None:
        ledger = PeerWitnessLedger()
        for peer in ("p1", "p2", "p3"):
            ledger.append(
                decision_id="d-1", primary_record_hash=_OK_HASH,
                witness_entity_id=peer, witnessed_at_epoch=1,
            )
        assert quorum_witnessed(ledger, "d-1", required_peers=3)
        assert quorum_witnessed(ledger, "d-1", required_peers=2)
        assert not quorum_witnessed(ledger, "d-1", required_peers=4)

    def test_zero_required_raises(self) -> None:
        with pytest.raises(ValueError):
            quorum_witnessed(PeerWitnessLedger(), "d-1", required_peers=0)

    def test_missing_decision_not_witnessed(self) -> None:
        assert not quorum_witnessed(
            PeerWitnessLedger(), "missing", required_peers=1,
        )
