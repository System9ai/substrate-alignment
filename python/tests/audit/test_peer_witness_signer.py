"""Tests for HMAC-based peer-witness signer."""
from __future__ import annotations

import pytest

from substrate.audit.peer_witness_signer import (
    ATTESTATION_PREFIX,
    HMAC_ALGORITHM,
    HmacWitnessSigner,
    MultiKeyWitnessVerifier,
    WitnessPayload,
    canonical_bytes,
)

def _payload(
    *,
    decision_id: str = "d-1",
    primary_record_hash: str = "a" * 64,
    witness_entity_id: str = "cell-1",
    witnessed_at_epoch: int = 1000,
) -> WitnessPayload:
    return WitnessPayload(
        decision_id=decision_id,
        primary_record_hash=primary_record_hash,
        witness_entity_id=witness_entity_id,
        witnessed_at_epoch=witnessed_at_epoch,
    )

class TestWitnessPayloadValidation:
    def test_empty_decision_id_raises(self) -> None:
        with pytest.raises(ValueError, match="decision_id"):
            WitnessPayload(
                decision_id="", primary_record_hash="a" * 64,
                witness_entity_id="c1", witnessed_at_epoch=0,
            )

    def test_empty_primary_hash_raises(self) -> None:
        with pytest.raises(ValueError, match="primary_record_hash"):
            WitnessPayload(
                decision_id="d", primary_record_hash="",
                witness_entity_id="c1", witnessed_at_epoch=0,
            )

    def test_empty_witness_id_raises(self) -> None:
        with pytest.raises(ValueError, match="witness_entity_id"):
            WitnessPayload(
                decision_id="d", primary_record_hash="a" * 64,
                witness_entity_id="", witnessed_at_epoch=0,
            )

    def test_negative_epoch_raises(self) -> None:
        with pytest.raises(ValueError, match="witnessed_at_epoch"):
            WitnessPayload(
                decision_id="d", primary_record_hash="a" * 64,
                witness_entity_id="c1", witnessed_at_epoch=-1,
            )

class TestCanonicalBytes:
    def test_sorted_keys_no_whitespace(self) -> None:
        b = canonical_bytes(_payload())
        s = b.decode("utf-8")
        # No whitespace
        assert " " not in s
        # Sorted-key order: alphabetical
        idx_did = s.index("decision_id")
        idx_prim = s.index("primary_record_hash")
        idx_wid = s.index("witness_entity_id")
        idx_epoch = s.index("witnessed_at_epoch")
        assert idx_did < idx_prim < idx_wid < idx_epoch

    def test_deterministic(self) -> None:
        b1 = canonical_bytes(_payload())
        b2 = canonical_bytes(_payload())
        assert b1 == b2

    def test_distinct_payloads_distinct_bytes(self) -> None:
        b1 = canonical_bytes(_payload(decision_id="d-1"))
        b2 = canonical_bytes(_payload(decision_id="d-2"))
        assert b1 != b2

class TestHmacWitnessSigner:
    def test_empty_key_raises(self) -> None:
        with pytest.raises(ValueError, match="key"):
            HmacWitnessSigner(b"")

    def test_sign_returns_prefixed_hex(self) -> None:
        signer = HmacWitnessSigner(b"secret-key")
        attestation = signer.sign(_payload())
        assert attestation.startswith(ATTESTATION_PREFIX)
        digest = attestation[len(ATTESTATION_PREFIX):]
        assert len(digest) == 64
        # All hex
        bytes.fromhex(digest)

    def test_sign_deterministic(self) -> None:
        signer = HmacWitnessSigner(b"k")
        a1 = signer.sign(_payload())
        a2 = signer.sign(_payload())
        assert a1 == a2

    def test_sign_changes_with_payload(self) -> None:
        signer = HmacWitnessSigner(b"k")
        a1 = signer.sign(_payload(decision_id="d-1"))
        a2 = signer.sign(_payload(decision_id="d-2"))
        assert a1 != a2

    def test_sign_changes_with_key(self) -> None:
        a1 = HmacWitnessSigner(b"k1").sign(_payload())
        a2 = HmacWitnessSigner(b"k2").sign(_payload())
        assert a1 != a2

class TestVerify:
    def test_verify_correct_signature(self) -> None:
        signer = HmacWitnessSigner(b"k")
        att = signer.sign(_payload())
        assert signer.verify(_payload(), att)

    def test_verify_wrong_key_fails(self) -> None:
        att = HmacWitnessSigner(b"k1").sign(_payload())
        assert not HmacWitnessSigner(b"k2").verify(_payload(), att)

    def test_verify_tampered_payload_fails(self) -> None:
        signer = HmacWitnessSigner(b"k")
        att = signer.sign(_payload(decision_id="d-1"))
        # Verify with mutated payload
        assert not signer.verify(
            _payload(decision_id="d-2"), att,
        )

    def test_verify_wrong_prefix_fails(self) -> None:
        signer = HmacWitnessSigner(b"k")
        assert not signer.verify(_payload(), "bad-prefix:abc")

    def test_verify_short_hex_fails(self) -> None:
        signer = HmacWitnessSigner(b"k")
        assert not signer.verify(
            _payload(), f"{ATTESTATION_PREFIX}abc123",
        )

    def test_verify_non_hex_fails(self) -> None:
        signer = HmacWitnessSigner(b"k")
        assert not signer.verify(
            _payload(), f"{ATTESTATION_PREFIX}{'z' * 64}",
        )

    def test_verify_empty_attestation_fails(self) -> None:
        signer = HmacWitnessSigner(b"k")
        assert not signer.verify(_payload(), "")

class TestMultiKeyVerifier:
    def test_unknown_peer_rejected(self) -> None:
        verifier = MultiKeyWitnessVerifier({"cell-1": b"k1"})
        signer = HmacWitnessSigner(b"k2")
        att = signer.sign(_payload(witness_entity_id="cell-2"))
        # cell-2 not in registry → reject
        assert not verifier.verify(
            _payload(witness_entity_id="cell-2"), att,
        )

    def test_known_peer_with_correct_key_passes(self) -> None:
        signer = HmacWitnessSigner(b"k1")
        att = signer.sign(_payload(witness_entity_id="cell-1"))
        verifier = MultiKeyWitnessVerifier({"cell-1": b"k1"})
        assert verifier.verify(
            _payload(witness_entity_id="cell-1"), att,
        )

    def test_known_peer_wrong_key_fails(self) -> None:
        signer = HmacWitnessSigner(b"k1")
        att = signer.sign(_payload(witness_entity_id="cell-1"))
        verifier = MultiKeyWitnessVerifier({"cell-1": b"k2"})
        assert not verifier.verify(
            _payload(witness_entity_id="cell-1"), att,
        )

    def test_known_peers_returns_ids(self) -> None:
        verifier = MultiKeyWitnessVerifier({
            "cell-1": b"k1", "cell-2": b"k2",
        })
        assert verifier.known_peers() == frozenset({"cell-1", "cell-2"})

class TestKnownTestVector:
    """Lock the canonical-bytes wire format with a fixed vector.

    This vector must match the Rust counterpart's test fixture in
    ``the edge-node Rust witness binding``
    so signatures verify across implementations.
    """

    def test_canonical_bytes_known_vector(self) -> None:
        payload = WitnessPayload(
            decision_id="dec-42",
            primary_record_hash="a" * 64,
            witness_entity_id="cell-alpha",
            witnessed_at_epoch=1717180800,
        )
        b = canonical_bytes(payload)
        # The exact bytes; must match Rust output.
        assert b == (
            b'{"decision_id":"dec-42",'
            b'"primary_record_hash":"' + b"a" * 64 + b'",'
            b'"witness_entity_id":"cell-alpha",'
            b'"witnessed_at_epoch":1717180800}'
        )

    def test_hmac_known_vector(self) -> None:
        # Fixed key + payload → fixed HMAC.
        payload = WitnessPayload(
            decision_id="dec-42",
            primary_record_hash="a" * 64,
            witness_entity_id="cell-alpha",
            witnessed_at_epoch=1717180800,
        )
        signer = HmacWitnessSigner(b"test-key-32-bytes-for-cross-repo")
        attestation = signer.sign(payload)
        # The exact attestation; must match Rust output for the
        # same key + payload.
        assert attestation == (
            "hmac-sha256:"
            "2a82fa887b89b7c065d1e02e5efd67211fda465061f8c7f2070702fec0d36879"
        )

class TestConstants:
    def test_algorithm_constant(self) -> None:
        assert HMAC_ALGORITHM == "hmac-sha256"

    def test_prefix_constant(self) -> None:
        assert ATTESTATION_PREFIX == "hmac-sha256:"
