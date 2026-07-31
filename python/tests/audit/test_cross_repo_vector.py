"""Cross-repo canonical-bytes test vector.

Locks the wire-format contract between:

- `substrate.audit.peer_witness_signer` (Python)
- `the edge-node Rust witness binding` (Rust)

Both implementations independently produce the same HMAC-SHA-256
attestation over the same canonical payload + key. Any drift between
the two test vectors here and the Rust ``cross_repo_payload`` /
``hmac_matches_python_vector`` tests means the wire format diverged
and witnesses will no longer verify across the cell ↔ edge node
boundary.
"""
from __future__ import annotations

from substrate.audit.peer_witness_signer import (
    HmacWitnessSigner,
    WitnessPayload,
    canonical_bytes,
)

#: Fixed payload; must match `cross_repo_payload()` in the Rust
#: counterpart.
_PAYLOAD = WitnessPayload(
    decision_id="dec-42",
    primary_record_hash="a" * 64,
    witness_entity_id="cell-alpha",
    witnessed_at_epoch=1_717_180_800,
)

#: Fixed key; must match the Rust counterpart's key bytes.
_KEY = b"test-key-32-bytes-for-cross-repo"

#: Expected canonical-bytes string (UTF-8 encoded).
_EXPECTED_BYTES = (
    b'{"decision_id":"dec-42",'
    b'"primary_record_hash":"' + b"a" * 64 + b'",'
    b'"witness_entity_id":"cell-alpha",'
    b'"witnessed_at_epoch":1717180800}'
)

#: Expected HMAC attestation. Both Python and Rust produce this.
_EXPECTED_ATTESTATION = (
    "hmac-sha256:"
    "2a82fa887b89b7c065d1e02e5efd67211fda465061f8c7f2070702fec0d36879"
)

class TestCrossRepoVector:
    def test_canonical_bytes_match(self) -> None:
        assert canonical_bytes(_PAYLOAD) == _EXPECTED_BYTES

    def test_hmac_matches(self) -> None:
        signer = HmacWitnessSigner(_KEY)
        assert signer.sign(_PAYLOAD) == _EXPECTED_ATTESTATION

    def test_attestation_self_verifies(self) -> None:
        signer = HmacWitnessSigner(_KEY)
        assert signer.verify(_PAYLOAD, _EXPECTED_ATTESTATION)
