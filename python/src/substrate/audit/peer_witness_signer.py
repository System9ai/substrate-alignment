"""HMAC-based peer-witness signer.

Closes the *peer signature cryptography* v2 item from the
M-Substrate-1 grade. Replaces the caller-supplied attestation
string in :class:`PeerWitnessRecord` with a real HMAC-SHA-256
signature over a canonical payload.

Canonical payload layout (must match the Rust edge node-side
implementation in ``the edge-node Rust witness binding``):

    JSON object with sorted keys, no whitespace, UTF-8 bytes:

    {
      "decision_id": "<str>",
      "primary_record_hash": "<64-hex sha256>",
      "witness_entity_id": "<str>",
      "witnessed_at_epoch": <int>
    }

The HMAC-SHA-256 hex digest of those bytes is the attestation
string. Receivers reconstruct the same canonical bytes and verify
with the peer's published key.

Pure logic:

- No DAO, no LLM, no network.
- Deterministic given (key, payload).
- Constant-time signature comparison (``hmac.compare_digest``).
"""
from __future__ import annotations

import hmac
import hashlib
import json
from dataclasses import dataclass
from typing import Final, Mapping

#: HMAC algorithm (SHA-256). Bumping this requires lock-step bump in
#: the Rust counterpart.
HMAC_ALGORITHM: Final[str] = "hmac-sha256"

#: Attestation prefix. Operators can identify the algorithm from
#: the leading bytes of the attestation string. The format is
#: ``"hmac-sha256:<hex-digest>"``.
ATTESTATION_PREFIX: Final[str] = "hmac-sha256:"

@dataclass(frozen=True, slots=True)
class WitnessPayload:
    """Canonical fields signed in a peer-witness attestation."""

    decision_id: str
    primary_record_hash: str
    witness_entity_id: str
    witnessed_at_epoch: int

    def __post_init__(self) -> None:
        if not self.decision_id:
            raise ValueError("decision_id must be non-empty")
        if not self.primary_record_hash:
            raise ValueError("primary_record_hash must be non-empty")
        if not self.witness_entity_id:
            raise ValueError("witness_entity_id must be non-empty")
        if self.witnessed_at_epoch < 0:
            raise ValueError("witnessed_at_epoch must be >= 0")

def canonical_bytes(payload: WitnessPayload) -> bytes:
    """Return the canonical bytes used for HMAC computation.

    JSON with sorted keys, no whitespace, UTF-8. This shape is
    cross-language stable; the Rust counterpart serialises with
    the same shape so signatures verify across implementations.
    """
    mapping: Mapping[str, object] = {
        "decision_id": payload.decision_id,
        "primary_record_hash": payload.primary_record_hash,
        "witness_entity_id": payload.witness_entity_id,
        "witnessed_at_epoch": payload.witnessed_at_epoch,
    }
    return json.dumps(
        mapping, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")

class HmacWitnessSigner:  # pylint: disable=too-few-public-methods
    """HMAC-SHA-256 signer for peer-witness attestations.

    Construction takes the local cell's HMAC key (bytes). The key
    is the shared secret across peer cells that recognize each
    other's attestations. Production wires the key from the
    existing cell crypto fabric (e.g., derived from the cell's
    KEK via HKDF); tests pass a fixed key.

    Same key + payload always yields the same attestation
    (deterministic + constant-time-comparable).
    """

    def __init__(self, key: bytes) -> None:
        if not key:
            raise ValueError("key must be non-empty bytes")
        self._key = bytes(key)

    def sign(self, payload: WitnessPayload) -> str:
        """Return the ``hmac-sha256:<hex>`` attestation string."""
        digest = hmac.new(
            self._key, canonical_bytes(payload), hashlib.sha256,
        ).hexdigest()
        return f"{ATTESTATION_PREFIX}{digest}"

    def verify(self, payload: WitnessPayload, attestation: str) -> bool:
        """Verify ``attestation`` over ``payload``.

        Returns False for malformed strings (wrong prefix, wrong
        hex length, non-hex characters). Uses constant-time
        comparison to avoid timing oracles.
        """
        if not attestation.startswith(ATTESTATION_PREFIX):
            return False
        provided = attestation[len(ATTESTATION_PREFIX):]
        # SHA-256 hex digest is 64 chars.
        if len(provided) != 64:
            return False
        try:
            provided_bytes = bytes.fromhex(provided)
        except ValueError:
            return False
        expected = hmac.new(
            self._key, canonical_bytes(payload), hashlib.sha256,
        ).digest()
        return hmac.compare_digest(provided_bytes, expected)

class MultiKeyWitnessVerifier:  # pylint: disable=too-few-public-methods
    """Verify attestations against a registry of peer keys.

    Operators maintain a ``{witness_entity_id: key_bytes}`` mapping
    (e.g., refreshed via the existing crypto fabric's key-distribution
    flow). When a witness arrives, the verifier looks up the peer's
    key + verifies with :class:`HmacWitnessSigner`.
    """

    def __init__(
        self,
        keys: Mapping[str, bytes],
    ) -> None:
        self._keys = {wid: bytes(k) for wid, k in keys.items() if k}

    def known_peers(self) -> frozenset[str]:
        """Return the witness-entity ids the verifier has keys for."""
        return frozenset(self._keys.keys())

    def verify(
        self, payload: WitnessPayload, attestation: str,
    ) -> bool:
        """Verify ``attestation`` was produced by the named peer.

        Returns False when the peer is unknown or the attestation
        is malformed / invalid.
        """
        key = self._keys.get(payload.witness_entity_id)
        if key is None:
            return False
        signer = HmacWitnessSigner(key)
        return signer.verify(payload, attestation)

__all__ = [
    "ATTESTATION_PREFIX",
    "HMAC_ALGORITHM",
    "HmacWitnessSigner",
    "MultiKeyWitnessVerifier",
    "WitnessPayload",
    "canonical_bytes",
]
