"""Tests for SubstrateTraceRecord + SubstrateTraceLedger"""
from __future__ import annotations

import dataclasses

import pytest

from substrate.audit.substrate_trace import (
    GENESIS_PREV_HASH,
    LedgerVerification,
    DriftPatternSummary,
    SubstrateTraceLedger,
    SubstrateTraceRecord,
)
from substrate.drift.drift_pattern_matcher import (
    DriftPattern,
    DriftPatternDetection,
    DriftPatternMatcher,
    DriftPatternReport,
)
from substrate.harness import InterceptKind
from substrate.net_potential_gain_gate import (
    NetPotentialGainVerdict,
)
from substrate.resistance_band import (
    ResistanceBandClassification,
)

# -----------------------------
# DriftPattern summary projection
# -----------------------------

class TestSinReportSummary:
    def test_from_report_empty(self) -> None:
        report = DriftPatternReport(
            detections=(),
            dominant_pattern=None,
            composite_confidence=0.0,
            amplifier_pattern_present=False,
            reasoning="no pattern patterns above threshold",
        )
        s = DriftPatternSummary.from_report(report)
        assert s.dominant_pattern is None
        assert s.composite_confidence == 0.0
        assert s.amplifier_pattern_present is False
        assert s.kinds_detected == ()

    def test_from_report_with_detections(self) -> None:
        report = DriftPatternReport(
            detections=(
                DriftPatternDetection(pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION, confidence=0.9),
                DriftPatternDetection(pattern=DriftPattern.REACTIVE_NET_NEGATIVE, confidence=0.6),
            ),
            dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
            composite_confidence=0.9,
            amplifier_pattern_present=True,
            reasoning="detected: pride@0.90, wrath@0.60 (pride present...)",
        )
        s = DriftPatternSummary.from_report(report)
        assert s.dominant_pattern is DriftPattern.SELF_REFERENCE_MISCALIBRATION
        assert s.composite_confidence == 0.9
        assert s.amplifier_pattern_present is True
        assert s.kinds_detected == (DriftPattern.SELF_REFERENCE_MISCALIBRATION, DriftPattern.REACTIVE_NET_NEGATIVE)

    def test_summary_round_trips_through_real_matcher(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text="I alone decide — destroy them, no mercy."
        )
        s = DriftPatternSummary.from_report(report)
        assert s.dominant_pattern is not None
        assert s.kinds_detected == tuple(d.pattern for d in report.detections)

# -----------------------------
# Append validation
# -----------------------------

class TestLedgerAppendValidation:
    def _ok_args(self) -> dict[str, object]:
        return {
            "decision_id": "decision-1",
            "decision_kind": "observer_activate",
            "permitted": True,
            "rationale": "ok",
            "epoch_seconds": 1_700_000_000,
        }

    def test_empty_decision_id_rejected(self) -> None:
        ledger = SubstrateTraceLedger()
        args = self._ok_args()
        args["decision_id"] = ""
        with pytest.raises(ValueError, match="decision_id"):
            ledger.append(**args)

    def test_empty_decision_kind_rejected(self) -> None:
        ledger = SubstrateTraceLedger()
        args = self._ok_args()
        args["decision_kind"] = ""
        with pytest.raises(ValueError, match="decision_kind"):
            ledger.append(**args)

    def test_negative_epoch_rejected(self) -> None:
        ledger = SubstrateTraceLedger()
        args = self._ok_args()
        args["epoch_seconds"] = -1
        with pytest.raises(ValueError, match="epoch_seconds"):
            ledger.append(**args)

    def test_duplicate_intercept_kinds_rejected(self) -> None:
        ledger = SubstrateTraceLedger()
        with pytest.raises(ValueError, match="harness_intercept_kinds"):
            ledger.append(
                **self._ok_args(),
                harness_intercept_kinds=(
                    InterceptKind.NPG_NEGATIVE,
                    InterceptKind.NPG_NEGATIVE,
                ),
            )

    def test_sin_summary_confidence_out_of_range_rejected(self) -> None:
        ledger = SubstrateTraceLedger()
        bad = DriftPatternSummary(
            dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
            composite_confidence=1.5,
            amplifier_pattern_present=True,
            kinds_detected=(DriftPattern.SELF_REFERENCE_MISCALIBRATION,),
        )
        with pytest.raises(ValueError, match="sin_composite_confidence"):
            ledger.append(**self._ok_args(), sin_summary=bad)

    def test_duplicate_sin_kinds_rejected(self) -> None:
        ledger = SubstrateTraceLedger()
        bad = DriftPatternSummary(
            dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
            composite_confidence=0.9,
            amplifier_pattern_present=True,
            kinds_detected=(DriftPattern.SELF_REFERENCE_MISCALIBRATION, DriftPattern.SELF_REFERENCE_MISCALIBRATION),
        )
        with pytest.raises(ValueError, match="sin_kinds_detected"):
            ledger.append(**self._ok_args(), sin_summary=bad)

# -----------------------------
# Append: basic behaviour
# -----------------------------

class TestLedgerAppend:
    def test_empty_ledger_starts_at_zero(self) -> None:
        ledger = SubstrateTraceLedger()
        assert ledger.length == 0
        assert ledger.records() == ()
        assert ledger.last() is None

    def test_first_record_uses_genesis_prev_hash(self) -> None:
        ledger = SubstrateTraceLedger()
        rec = ledger.append(
            decision_id="d-1",
            decision_kind="x",
            permitted=True,
            rationale="ok",
            epoch_seconds=10,
        )
        assert rec.sequence == 0
        assert rec.prev_hash == GENESIS_PREV_HASH
        assert len(rec.record_hash) == 64

    def test_sequence_increments(self) -> None:
        ledger = SubstrateTraceLedger()
        for i in range(5):
            rec = ledger.append(
                decision_id=f"d-{i}",
                decision_kind="x",
                permitted=True,
                rationale=f"r{i}",
                epoch_seconds=10 + i,
            )
            assert rec.sequence == i

    def test_prev_hash_chains(self) -> None:
        ledger = SubstrateTraceLedger()
        a = ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        b = ledger.append(
            decision_id="d-2", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=2,
        )
        assert b.prev_hash == a.record_hash

    def test_last_returns_most_recent(self) -> None:
        ledger = SubstrateTraceLedger()
        a = ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        assert ledger.last() == a
        b = ledger.append(
            decision_id="d-2", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=2,
        )
        assert ledger.last() == b

    def test_optional_fields_default_to_absent(self) -> None:
        ledger = SubstrateTraceLedger()
        rec = ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        assert rec.npg_verdict is None
        assert rec.resistance_band is None
        assert rec.sin_dominant is None
        assert rec.sin_pride_present is False
        assert rec.sin_kinds_detected == ()
        assert rec.harness_intercept_kinds == ()

    def test_full_context_stored(self) -> None:
        ledger = SubstrateTraceLedger()
        summary = DriftPatternSummary(
            dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
            composite_confidence=0.85,
            amplifier_pattern_present=True,
            kinds_detected=(DriftPattern.SELF_REFERENCE_MISCALIBRATION, DriftPattern.REACTIVE_NET_NEGATIVE),
        )
        rec = ledger.append(
            decision_id="d-1",
            decision_kind="mcp_tool_dispatch",
            permitted=False,
            rationale="NPG negative",
            epoch_seconds=1_700_000_000,
            npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE,
            resistance_band=ResistanceBandClassification.STRESSED,
            sin_summary=summary,
            harness_intercept_kinds=(
                InterceptKind.NPG_NEGATIVE,
                InterceptKind.INVERSION_DETECTED,
            ),
        )
        assert rec.npg_verdict is NetPotentialGainVerdict.NET_NEGATIVE
        assert rec.resistance_band is ResistanceBandClassification.STRESSED
        assert rec.sin_dominant is DriftPattern.SELF_REFERENCE_MISCALIBRATION
        assert rec.sin_composite_confidence == 0.85
        assert rec.sin_pride_present is True
        assert rec.sin_kinds_detected == (
            DriftPattern.SELF_REFERENCE_MISCALIBRATION,
            DriftPattern.REACTIVE_NET_NEGATIVE,
        )
        assert rec.harness_intercept_kinds == (
            InterceptKind.NPG_NEGATIVE,
            InterceptKind.INVERSION_DETECTED,
        )

# -----------------------------
# Verification — clean and tampered
# -----------------------------

class TestLedgerVerify:
    def test_empty_ledger_verifies(self) -> None:
        ledger = SubstrateTraceLedger()
        result = ledger.verify()
        assert result.ok is True
        assert result.bad_sequence is None
        assert result.reason is None

    def test_clean_chain_verifies(self) -> None:
        ledger = SubstrateTraceLedger()
        for i in range(5):
            ledger.append(
                decision_id=f"d-{i}", decision_kind="x", permitted=True,
                rationale="r", epoch_seconds=i,
            )
        assert ledger.verify().ok is True

    def test_tampered_rationale_detected(self) -> None:
        ledger = SubstrateTraceLedger()
        ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="original", epoch_seconds=1,
        )
        ledger.append(
            decision_id="d-2", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=2,
        )
        # Mutate record 0 by rebuilding it with a different rationale
        # — record_hash will no longer match canonical body.
        original = ledger.records()[0]
        tampered = dataclasses.replace(original, rationale="tampered")
        rebuilt = SubstrateTraceLedger.from_records(
            (tampered, ledger.records()[1])
        )
        result = rebuilt.verify()
        assert result.ok is False
        assert result.bad_sequence == 0
        assert result.reason is not None
        assert "record_hash" in result.reason

    def test_sequence_gap_detected(self) -> None:
        ledger = SubstrateTraceLedger()
        ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        bad = dataclasses.replace(ledger.records()[0], sequence=99)
        rebuilt = SubstrateTraceLedger.from_records((bad,))
        result = rebuilt.verify()
        assert result.ok is False
        assert result.bad_sequence == 0
        assert result.reason is not None
        assert "sequence" in result.reason.lower()

    def test_prev_hash_mismatch_detected(self) -> None:
        ledger = SubstrateTraceLedger()
        ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        ledger.append(
            decision_id="d-2", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=2,
        )
        bad_second = dataclasses.replace(
            ledger.records()[1], prev_hash="a" * 64,
        )
        rebuilt = SubstrateTraceLedger.from_records(
            (ledger.records()[0], bad_second)
        )
        result = rebuilt.verify()
        assert result.ok is False
        assert result.bad_sequence == 1
        assert result.reason is not None
        assert "prev_hash" in result.reason.lower()

    def test_short_record_hash_detected(self) -> None:
        ledger = SubstrateTraceLedger()
        ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        bad = dataclasses.replace(ledger.records()[0], record_hash="deadbeef")
        rebuilt = SubstrateTraceLedger.from_records((bad,))
        result = rebuilt.verify()
        # Body-mismatch is detected before hex-length validation, but
        # either way the chain is rejected at sequence 0.
        assert result.ok is False
        assert result.bad_sequence == 0

# -----------------------------
# Determinism / reproducibility
# -----------------------------

class TestDeterminism:
    def test_same_inputs_produce_same_record_hash(self) -> None:
        ledger_a = SubstrateTraceLedger()
        ledger_b = SubstrateTraceLedger()
        for ledger in (ledger_a, ledger_b):
            ledger.append(
                decision_id="d-1", decision_kind="x", permitted=True,
                rationale="r", epoch_seconds=42,
                npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
                resistance_band=ResistanceBandClassification.PRODUCTIVE,
                sin_summary=DriftPatternSummary(
                    dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
                    composite_confidence=0.5,
                    amplifier_pattern_present=True,
                    kinds_detected=(DriftPattern.SELF_REFERENCE_MISCALIBRATION,),
                ),
                harness_intercept_kinds=(InterceptKind.NPG_NEGATIVE,),
            )
        assert ledger_a.records()[0].record_hash == \
            ledger_b.records()[0].record_hash

    def test_different_inputs_produce_different_hashes(self) -> None:
        ledger = SubstrateTraceLedger()
        a = ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        b = ledger.append(
            decision_id="d-2", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        # Different decision_id AND different prev_hash position → different hash.
        assert a.record_hash != b.record_hash

    def test_canonical_dict_excludes_record_hash(self) -> None:
        ledger = SubstrateTraceLedger()
        rec = ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        assert "record_hash" not in rec.to_canonical_dict()
        assert "prev_hash" in rec.to_canonical_dict()

# -----------------------------
# Queries
# -----------------------------

class TestQueries:
    def _seeded_ledger(self) -> SubstrateTraceLedger:
        ledger = SubstrateTraceLedger()
        ledger.append(
            decision_id="d-1", decision_kind="observer_activate",
            permitted=True, rationale="ok", epoch_seconds=1,
            npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
        )
        ledger.append(
            decision_id="d-2", decision_kind="mcp_tool_dispatch",
            permitted=False, rationale="NPG negative", epoch_seconds=2,
            npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE,
            harness_intercept_kinds=(InterceptKind.NPG_NEGATIVE,),
        )
        ledger.append(
            decision_id="d-3", decision_kind="observer_activate",
            permitted=True, rationale="ok", epoch_seconds=3,
            npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
        )
        return ledger

    def test_by_decision_kind_filters_correctly(self) -> None:
        ledger = self._seeded_ledger()
        rs = ledger.by_decision_kind("observer_activate")
        assert tuple(r.decision_id for r in rs) == ("d-1", "d-3")

    def test_by_npg_verdict_filters_correctly(self) -> None:
        ledger = self._seeded_ledger()
        rs = ledger.by_npg_verdict(NetPotentialGainVerdict.NET_NEGATIVE)
        assert tuple(r.decision_id for r in rs) == ("d-2",)

    def test_by_intercept_kind_filters_correctly(self) -> None:
        ledger = self._seeded_ledger()
        rs = ledger.by_intercept_kind(InterceptKind.NPG_NEGATIVE)
        assert tuple(r.decision_id for r in rs) == ("d-2",)

    def test_denied_filters_correctly(self) -> None:
        ledger = self._seeded_ledger()
        rs = ledger.denied()
        assert tuple(r.decision_id for r in rs) == ("d-2",)

    def test_empty_filters_return_empty_tuple(self) -> None:
        ledger = SubstrateTraceLedger()
        assert ledger.by_decision_kind("nope") == ()
        assert ledger.by_npg_verdict(NetPotentialGainVerdict.NET_NEGATIVE) == ()
        assert ledger.by_intercept_kind(InterceptKind.NPG_NEGATIVE) == ()
        assert ledger.denied() == ()

# -----------------------------
# from_records + serialization round-trip
# -----------------------------

class TestRoundTrip:
    def test_from_records_preserves_chain(self) -> None:
        original = SubstrateTraceLedger()
        for i in range(3):
            original.append(
                decision_id=f"d-{i}", decision_kind="x", permitted=True,
                rationale="r", epoch_seconds=i,
            )
        rebuilt = SubstrateTraceLedger.from_records(original.records())
        assert rebuilt.records() == original.records()
        assert rebuilt.verify().ok is True

    def test_initial_records_constructor(self) -> None:
        original = SubstrateTraceLedger()
        for i in range(3):
            original.append(
                decision_id=f"d-{i}", decision_kind="x", permitted=True,
                rationale="r", epoch_seconds=i,
            )
        copy = SubstrateTraceLedger(initial_records=original.records())
        assert copy.verify().ok is True
        # Continuing the chain on the copy maintains integrity.
        copy.append(
            decision_id="d-3", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=99,
        )
        assert copy.verify().ok is True
        assert copy.records()[-1].prev_hash == original.records()[-1].record_hash

# -----------------------------
# HMAC checkpoint
# -----------------------------

class TestHmacCheckpoint:
    def test_checkpoint_deterministic_for_same_key_and_range(self) -> None:
        ledger = SubstrateTraceLedger()
        for i in range(3):
            ledger.append(
                decision_id=f"d-{i}", decision_kind="x", permitted=True,
                rationale="r", epoch_seconds=i,
            )
        cp_a = ledger.compute_checkpoint(secret=b"shared-secret")
        cp_b = ledger.compute_checkpoint(secret=b"shared-secret")
        assert cp_a == cp_b
        assert len(cp_a) == 64

    def test_checkpoint_differs_for_different_secret(self) -> None:
        ledger = SubstrateTraceLedger()
        ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        a = ledger.compute_checkpoint(secret=b"key-a")
        b = ledger.compute_checkpoint(secret=b"key-b")
        assert a != b

    def test_checkpoint_range(self) -> None:
        ledger = SubstrateTraceLedger()
        for i in range(5):
            ledger.append(
                decision_id=f"d-{i}", decision_kind="x", permitted=True,
                rationale="r", epoch_seconds=i,
            )
        full = ledger.compute_checkpoint(secret=b"k")
        partial = ledger.compute_checkpoint(
            secret=b"k", start_sequence=0, end_sequence_exclusive=3,
        )
        assert full != partial

    def test_empty_secret_rejected(self) -> None:
        ledger = SubstrateTraceLedger()
        ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        with pytest.raises(ValueError, match="secret"):
            ledger.compute_checkpoint(secret=b"")

    def test_negative_start_rejected(self) -> None:
        ledger = SubstrateTraceLedger()
        ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        with pytest.raises(ValueError, match="start_sequence"):
            ledger.compute_checkpoint(secret=b"k", start_sequence=-1)

    def test_end_past_length_rejected(self) -> None:
        ledger = SubstrateTraceLedger()
        ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        with pytest.raises(ValueError, match="end_sequence_exclusive"):
            ledger.compute_checkpoint(
                secret=b"k", end_sequence_exclusive=99,
            )

    def test_empty_range_rejected(self) -> None:
        ledger = SubstrateTraceLedger()
        ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        with pytest.raises(ValueError, match="end_sequence_exclusive"):
            ledger.compute_checkpoint(
                secret=b"k", start_sequence=1, end_sequence_exclusive=1,
            )

# -----------------------------
# Record canonical dict shape
# -----------------------------

class TestRecordCanonicalDict:
    def test_canonical_dict_has_all_expected_keys(self) -> None:
        ledger = SubstrateTraceLedger()
        rec = ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        d = rec.to_canonical_dict()
        expected_keys = {
            "sequence", "epoch_seconds", "decision_id", "decision_kind",
            "permitted", "rationale", "npg_verdict", "resistance_band",
            "sin_dominant", "sin_composite_confidence", "sin_pride_present",
            "sin_kinds_detected", "harness_intercept_kinds", "prev_hash",
        }
        assert set(d.keys()) == expected_keys

    def test_enum_values_serialize_as_strings(self) -> None:
        ledger = SubstrateTraceLedger()
        rec = ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
            npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
            resistance_band=ResistanceBandClassification.PRODUCTIVE,
            sin_summary=DriftPatternSummary(
                dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
                composite_confidence=0.5,
                amplifier_pattern_present=True,
                kinds_detected=(DriftPattern.SELF_REFERENCE_MISCALIBRATION,),
            ),
            harness_intercept_kinds=(InterceptKind.INVERSION_DETECTED,),
        )
        d = rec.to_canonical_dict()
        assert d["npg_verdict"] == NetPotentialGainVerdict.NET_POSITIVE.value
        assert d["resistance_band"] == \
            ResistanceBandClassification.PRODUCTIVE.value
        assert d["sin_dominant"] == DriftPattern.SELF_REFERENCE_MISCALIBRATION.value
        assert d["sin_kinds_detected"] == [DriftPattern.SELF_REFERENCE_MISCALIBRATION.value]
        assert d["harness_intercept_kinds"] == \
            [InterceptKind.INVERSION_DETECTED.value]

# -----------------------------
# LedgerVerification dataclass
# -----------------------------

class TestLedgerVerification:
    def test_success_dataclass(self) -> None:
        v = LedgerVerification(ok=True, bad_sequence=None, reason=None)
        assert v.ok is True
        assert v.bad_sequence is None

    def test_failure_dataclass(self) -> None:
        v = LedgerVerification(
            ok=False, bad_sequence=3, reason="prev_hash mismatch",
        )
        assert v.ok is False
        assert v.bad_sequence == 3
        assert v.reason == "prev_hash mismatch"

# -----------------------------
# SubstrateTraceRecord frozen
# -----------------------------

class TestRecordFrozen:
    def test_record_is_frozen(self) -> None:
        ledger = SubstrateTraceLedger()
        rec = ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            rec.rationale = "mutated"

    def test_record_equality_by_value(self) -> None:
        ledger_a = SubstrateTraceLedger()
        ledger_b = SubstrateTraceLedger()
        rec_a = ledger_a.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        rec_b = ledger_b.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        assert rec_a == rec_b
        # Different ledgers, same inputs → identical record (same hash chain).

# -----------------------------
# Module surface
# -----------------------------

class TestModuleSurface:
    def test_genesis_prev_hash_is_64_zeros(self) -> None:
        assert GENESIS_PREV_HASH == "0" * 64

    def test_record_type_is_substrate_trace_record(self) -> None:
        ledger = SubstrateTraceLedger()
        rec = ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        assert isinstance(rec, SubstrateTraceRecord)

# -----------------------------
# Cell/node actor identity (substrate condition #3)
# -----------------------------

class TestCellNodeActorIdentity:
    def test_legacy_records_unaffected(self) -> None:
        # Legacy records (no actor ids) should have identical hashes
        # to the schema before the cell/node fields were added
        # the canonical dict only includes the new keys when non-None.
        ledger = SubstrateTraceLedger()
        rec = ledger.append(
            decision_id="d-1", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        # Recompute hash and compare
        from substrate.audit.substrate_trace import (  # noqa: E501  pylint: disable=import-outside-toplevel
            _hash_canonical,
        )
        assert rec.record_hash == _hash_canonical(rec.to_canonical_dict())
        # The canonical dict must not contain the actor fields
        assert "actor_cell_id" not in rec.to_canonical_dict()
        assert "actor_node_id" not in rec.to_canonical_dict()

    def test_with_actor_cell_and_node(self) -> None:
        ledger = SubstrateTraceLedger()
        rec = ledger.append(
            decision_id="d-2", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
            actor_cell_id="cell-az1-a",
            actor_node_id="node-alpha",
        )
        assert rec.actor_cell_id == "cell-az1-a"
        assert rec.actor_node_id == "node-alpha"
        # The canonical dict includes both keys
        d = rec.to_canonical_dict()
        assert d["actor_cell_id"] == "cell-az1-a"
        assert d["actor_node_id"] == "node-alpha"

    def test_actor_fields_change_hash(self) -> None:
        # Two ledgers — one with actor ids, one without — produce
        # different hashes for otherwise-identical records.
        ledger_a = SubstrateTraceLedger()
        ledger_b = SubstrateTraceLedger()
        rec_a = ledger_a.append(
            decision_id="d", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
        )
        rec_b = ledger_b.append(
            decision_id="d", decision_kind="x", permitted=True,
            rationale="r", epoch_seconds=1,
            actor_cell_id="cell-1", actor_node_id="node-1",
        )
        assert rec_a.record_hash != rec_b.record_hash

    def test_empty_actor_cell_id_rejected(self) -> None:
        ledger = SubstrateTraceLedger()
        with pytest.raises(ValueError, match="actor_cell_id"):
            ledger.append(
                decision_id="d", decision_kind="x", permitted=True,
                rationale="r", epoch_seconds=1,
                actor_cell_id="",
            )

    def test_empty_actor_node_id_rejected(self) -> None:
        ledger = SubstrateTraceLedger()
        with pytest.raises(ValueError, match="actor_node_id"):
            ledger.append(
                decision_id="d", decision_kind="x", permitted=True,
                rationale="r", epoch_seconds=1,
                actor_node_id="",
            )

    def test_chain_verifies_with_actor_fields(self) -> None:
        ledger = SubstrateTraceLedger()
        for i in range(3):
            ledger.append(
                decision_id=f"d-{i}", decision_kind="x", permitted=True,
                rationale="r", epoch_seconds=i,
                actor_cell_id=f"cell-{i}", actor_node_id="node-alpha",
            )
        verification = ledger.verify()
        assert verification.ok
