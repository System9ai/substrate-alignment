"""Tests for SubstrateAuditArtifact"""
from __future__ import annotations

import dataclasses
import json

import pytest

from substrate.artifact.substrate_audit_artifact import (
    ARTIFACT_FORMAT_VERSION,
    ArtifactVerification,
    SubstrateAuditArtifact,
    SubstrateAuditManifest,
)
from substrate.audit.substrate_trace import (
    GENESIS_PREV_HASH,
    DriftPatternSummary,
    SubstrateTraceLedger,
)
from substrate.drift.drift_pattern_matcher import DriftPattern
from substrate.harness import InterceptKind
from substrate.net_potential_gain_gate import (
    NetPotentialGainVerdict,
)
from substrate.resistance_band import (
    ResistanceBandClassification,
)

# -----------------------------
# Helpers
# -----------------------------

def _seeded_ledger(count: int = 3) -> SubstrateTraceLedger:
    ledger = SubstrateTraceLedger()
    for i in range(count):
        ledger.append(
            decision_id=f"d-{i}",
            decision_kind="observer_activate",
            permitted=True,
            rationale=f"r{i}",
            epoch_seconds=1_700_000_000 + i,
            npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
        )
    return ledger

def _full_ledger() -> SubstrateTraceLedger:
    ledger = SubstrateTraceLedger()
    ledger.append(
        decision_id="d-1",
        decision_kind="mcp_tool_dispatch",
        permitted=False,
        rationale="NPG negative",
        epoch_seconds=1_700_000_000,
        npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE,
        resistance_band=ResistanceBandClassification.STRESSED,
        sin_summary=DriftPatternSummary(
            dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
            composite_confidence=0.85,
            amplifier_pattern_present=True,
            kinds_detected=(DriftPattern.SELF_REFERENCE_MISCALIBRATION, DriftPattern.REACTIVE_NET_NEGATIVE),
        ),
        harness_intercept_kinds=(
            InterceptKind.NPG_NEGATIVE,
            InterceptKind.INVERSION_DETECTED,
        ),
    )
    ledger.append(
        decision_id="d-2",
        decision_kind="observer_activate",
        permitted=True,
        rationale="clean",
        epoch_seconds=1_700_000_500,
        npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
    )
    return ledger

# -----------------------------
# Manifest validation
# -----------------------------

class TestManifestValidation:
    def _ok(self) -> dict[str, object]:
        return {
            "format_version": ARTIFACT_FORMAT_VERSION,
            "cell_id": "cell-1",
            "record_count": 0,
            "earliest_epoch_seconds": None,
            "latest_epoch_seconds": None,
            "chain_head_hash": GENESIS_PREV_HASH,
        }

    def test_empty_format_version_rejected(self) -> None:
        args = self._ok()
        args["format_version"] = ""
        with pytest.raises(ValueError, match="format_version"):
            SubstrateAuditManifest(**args)

    def test_empty_cell_id_rejected(self) -> None:
        args = self._ok()
        args["cell_id"] = ""
        with pytest.raises(ValueError, match="cell_id"):
            SubstrateAuditManifest(**args)

    def test_negative_record_count_rejected(self) -> None:
        args = self._ok()
        args["record_count"] = -1
        with pytest.raises(ValueError, match="record_count"):
            SubstrateAuditManifest(**args)

    def test_short_chain_head_hash_rejected(self) -> None:
        args = self._ok()
        args["chain_head_hash"] = "deadbeef"
        with pytest.raises(ValueError, match="chain_head_hash"):
            SubstrateAuditManifest(**args)

    def test_epoch_one_set_one_none_rejected(self) -> None:
        args = self._ok()
        args["earliest_epoch_seconds"] = 0
        # latest still None: mismatch.
        with pytest.raises(ValueError, match="earliest_epoch_seconds"):
            SubstrateAuditManifest(**args)

    def test_epoch_earliest_after_latest_rejected(self) -> None:
        args = self._ok()
        args["earliest_epoch_seconds"] = 200
        args["latest_epoch_seconds"] = 100
        with pytest.raises(ValueError, match="earliest_epoch_seconds"):
            SubstrateAuditManifest(**args)

    def test_hmac_partial_rejected(self) -> None:
        args = self._ok()
        args["hmac_checkpoint"] = "a" * 64
        # hmac_start + end still None: partial set rejected.
        with pytest.raises(ValueError, match="hmac"):
            SubstrateAuditManifest(**args)

# -----------------------------
# from_ledger constructor
# -----------------------------

class TestFromLedger:
    def test_basic_packaging(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-A",
        )
        assert art.manifest.cell_id == "cell-A"
        assert art.manifest.record_count == 3
        assert art.manifest.format_version == ARTIFACT_FORMAT_VERSION
        assert len(art.records) == 3

    def test_empty_ledger_packaging(self) -> None:
        ledger = SubstrateTraceLedger()
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-X",
        )
        assert art.manifest.record_count == 0
        assert art.records == ()
        assert art.manifest.chain_head_hash == GENESIS_PREV_HASH
        assert art.manifest.earliest_epoch_seconds is None
        assert art.manifest.latest_epoch_seconds is None

    def test_empty_cell_id_rejected(self) -> None:
        ledger = _seeded_ledger(1)
        with pytest.raises(ValueError, match="cell_id"):
            SubstrateAuditArtifact.from_ledger(
                ledger=ledger, cell_id="",
            )

    def test_chain_head_matches_last_record(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        assert art.manifest.chain_head_hash == \
            ledger.records()[-1].record_hash

    def test_epoch_range_min_max(self) -> None:
        ledger = SubstrateTraceLedger()
        ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=100,
        )
        ledger.append(
            decision_id="d-2", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=500,
        )
        ledger.append(
            decision_id="d-3", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=300,
        )
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        assert art.manifest.earliest_epoch_seconds == 100
        assert art.manifest.latest_epoch_seconds == 500

# -----------------------------
# HMAC packaging
# -----------------------------

class TestHmacPackaging:
    def test_hmac_set_when_secret_provided(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1", hmac_secret=b"secret-key",
        )
        assert art.manifest.hmac_checkpoint is not None
        assert len(art.manifest.hmac_checkpoint) == 64
        assert art.manifest.hmac_checkpoint_start == 0
        assert art.manifest.hmac_checkpoint_end_exclusive == 3

    def test_hmac_absent_when_no_secret(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        assert art.manifest.hmac_checkpoint is None
        assert art.manifest.hmac_checkpoint_start is None
        assert art.manifest.hmac_checkpoint_end_exclusive is None

    def test_hmac_absent_when_empty_ledger_even_with_secret(self) -> None:
        ledger = SubstrateTraceLedger()
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1", hmac_secret=b"k",
        )
        # No records → no checkpoint to compute.
        assert art.manifest.hmac_checkpoint is None

# -----------------------------
# JSON round-trip
# -----------------------------

class TestJsonRoundTrip:
    def test_round_trip_basic(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        payload = art.to_json()
        rebuilt = SubstrateAuditArtifact.from_json(payload)
        assert rebuilt == art

    def test_round_trip_with_full_context(self) -> None:
        ledger = _full_ledger()
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-X", hmac_secret=b"sec",
        )
        payload = art.to_json()
        rebuilt = SubstrateAuditArtifact.from_json(payload)
        assert rebuilt == art

    def test_round_trip_empty_ledger(self) -> None:
        ledger = SubstrateTraceLedger()
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        payload = art.to_json()
        rebuilt = SubstrateAuditArtifact.from_json(payload)
        assert rebuilt == art

    def test_json_is_deterministic(self) -> None:
        ledger_a = _seeded_ledger(3)
        ledger_b = _seeded_ledger(3)
        a = SubstrateAuditArtifact.from_ledger(
            ledger=ledger_a, cell_id="cell-1",
        )
        b = SubstrateAuditArtifact.from_ledger(
            ledger=ledger_b, cell_id="cell-1",
        )
        assert a.to_json() == b.to_json()

    def test_json_format_is_sorted_compact(self) -> None:
        ledger = _seeded_ledger(1)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        payload = art.to_json()
        # Compact: no whitespace after separators.
        assert ", " not in payload
        assert ": " not in payload
        # Valid JSON.
        parsed = json.loads(payload)
        assert "manifest" in parsed
        assert "records" in parsed

    def test_records_preserve_record_hash(self) -> None:
        ledger = _seeded_ledger(2)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        payload = art.to_json()
        parsed = json.loads(payload)
        records = parsed["records"]
        assert all("record_hash" in r for r in records)

# -----------------------------
# JSON validation errors
# -----------------------------

class TestJsonValidation:
    def test_empty_payload_rejected(self) -> None:
        with pytest.raises(ValueError, match="payload"):
            SubstrateAuditArtifact.from_json("")

    def test_invalid_json_rejected(self) -> None:
        with pytest.raises(ValueError, match="JSON"):
            SubstrateAuditArtifact.from_json("not-json{")

    def test_non_object_root_rejected(self) -> None:
        with pytest.raises(ValueError, match="object"):
            SubstrateAuditArtifact.from_json("[]")

    def test_missing_manifest_rejected(self) -> None:
        with pytest.raises(ValueError, match="manifest"):
            SubstrateAuditArtifact.from_json('{"records": []}')

    def test_records_not_list_rejected(self) -> None:
        with pytest.raises(ValueError, match="records"):
            SubstrateAuditArtifact.from_json(
                '{"manifest": {}, "records": "not-a-list"}'
            )

    def test_malformed_record_field_rejected(self) -> None:
        # Build a valid artifact then corrupt one field type.
        ledger = _seeded_ledger(1)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        parsed = json.loads(art.to_json())
        parsed["records"][0]["sequence"] = "not-an-int"
        with pytest.raises(ValueError, match="record"):
            SubstrateAuditArtifact.from_json(json.dumps(parsed))

# -----------------------------
# to_ledger reconstruction
# -----------------------------

class TestToLedger:
    def test_reconstruct_ledger_verifies_clean(self) -> None:
        original = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=original, cell_id="cell-1",
        )
        rebuilt = art.to_ledger()
        assert rebuilt.verify().ok is True
        assert rebuilt.records() == original.records()

    def test_reconstruct_full_context_ledger(self) -> None:
        original = _full_ledger()
        art = SubstrateAuditArtifact.from_ledger(
            ledger=original, cell_id="cell-X", hmac_secret=b"k",
        )
        rebuilt = art.to_ledger()
        assert rebuilt.verify().ok is True
        assert rebuilt.records() == original.records()

# -----------------------------
# Verification: clean and tampered
# -----------------------------

class TestArtifactVerification:
    def test_clean_artifact_verifies(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        result = art.verify()
        assert result.ok is True
        assert result.chain.ok is True
        assert result.manifest_ok is True
        assert result.hmac_ok is None  # no secret supplied
        assert result.reason is None

    def test_empty_artifact_verifies(self) -> None:
        ledger = SubstrateTraceLedger()
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        result = art.verify()
        assert result.ok is True

    def test_tampered_record_field_detected(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        # Tamper with the first record's rationale.
        tampered_records = (
            dataclasses.replace(art.records[0], rationale="tampered"),
            *art.records[1:],
        )
        tampered = SubstrateAuditArtifact(
            manifest=art.manifest, records=tampered_records,
        )
        result = tampered.verify()
        assert result.ok is False
        assert result.chain.ok is False

    def test_manifest_record_count_mismatch_detected(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        bad_manifest = dataclasses.replace(art.manifest, record_count=99)
        bad = SubstrateAuditArtifact(
            manifest=bad_manifest, records=art.records,
        )
        result = bad.verify()
        assert result.ok is False
        assert result.manifest_ok is False
        assert result.reason is not None
        assert "record_count" in result.reason

    def test_manifest_wrong_format_version_detected(self) -> None:
        ledger = _seeded_ledger(1)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        bad_manifest = dataclasses.replace(
            art.manifest, format_version="999",
        )
        bad = SubstrateAuditArtifact(
            manifest=bad_manifest, records=art.records,
        )
        result = bad.verify()
        assert result.ok is False
        assert result.reason is not None
        assert "format_version" in result.reason

    def test_manifest_wrong_chain_head_detected(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        bad_manifest = dataclasses.replace(
            art.manifest, chain_head_hash="a" * 64,
        )
        bad = SubstrateAuditArtifact(
            manifest=bad_manifest, records=art.records,
        )
        result = bad.verify()
        assert result.ok is False
        assert result.reason is not None
        assert "chain_head_hash" in result.reason

    def test_manifest_wrong_time_range_detected(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        bad_manifest = dataclasses.replace(
            art.manifest,
            earliest_epoch_seconds=999_999,
            latest_epoch_seconds=999_999_999,
        )
        bad = SubstrateAuditArtifact(
            manifest=bad_manifest, records=art.records,
        )
        result = bad.verify()
        assert result.ok is False
        assert result.reason is not None
        assert "time range" in result.reason

# -----------------------------
# HMAC verification
# -----------------------------

class TestHmacVerification:
    def test_hmac_secret_matches(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1", hmac_secret=b"shared",
        )
        result = art.verify(hmac_secret=b"shared")
        assert result.ok is True
        assert result.hmac_ok is True

    def test_hmac_secret_mismatch_fails(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1", hmac_secret=b"shared",
        )
        result = art.verify(hmac_secret=b"different")
        assert result.ok is False
        assert result.hmac_ok is False

    def test_hmac_not_verified_when_no_manifest_checkpoint(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",  # no secret → no checkpoint
        )
        result = art.verify(hmac_secret=b"any")
        assert result.ok is True
        assert result.hmac_ok is None

    def test_hmac_not_verified_when_no_caller_secret(self) -> None:
        ledger = _seeded_ledger(3)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1", hmac_secret=b"shared",
        )
        result = art.verify()
        assert result.ok is True
        assert result.hmac_ok is None

# -----------------------------
# Module surface
# -----------------------------

class TestModuleSurface:
    def test_format_version_constant(self) -> None:
        assert ARTIFACT_FORMAT_VERSION == "1"

    def test_artifact_is_frozen(self) -> None:
        ledger = _seeded_ledger(1)
        art = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="cell-1",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            art.manifest = None

    def test_manifest_is_frozen(self) -> None:
        m = SubstrateAuditManifest(
            format_version=ARTIFACT_FORMAT_VERSION,
            cell_id="cell-1",
            record_count=0,
            earliest_epoch_seconds=None,
            latest_epoch_seconds=None,
            chain_head_hash=GENESIS_PREV_HASH,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.cell_id = "other"

    def test_verification_dataclass(self) -> None:
        v = ArtifactVerification(
            ok=True, chain=None, manifest_ok=True,
            hmac_ok=None, reason=None,
        )
        assert v.ok is True
