"""Tests for CrossCellAuditVerifier"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from substrate.artifact.cross_cell_verifier import (
    CellArtifactFinding,
    CrossCellAuditVerifier,
    CrossCellFindingSeverity,
    CrossCellInconsistency,
    CrossCellOverlap,
    CrossCellVerificationReport,
    DEFAULT_HIGH_SEVERITY_FIELDS,
    DEFAULT_LOW_SEVERITY_FIELDS,
    DEFAULT_MEDIUM_SEVERITY_FIELDS,
)
from substrate.artifact.substrate_audit_artifact import (
    SubstrateAuditArtifact,
)
from substrate.audit.substrate_trace import (
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

def _ledger_with(  # pylint: disable=too-many-arguments
    *,
    decision_id: str = "d-1",
    decision_kind: str = "observer_activate",
    permitted: bool = True,
    rationale: str = "ok",
    epoch_seconds: int = 1_700_000_000,
    npg_verdict: NetPotentialGainVerdict | None = (
        NetPotentialGainVerdict.NET_POSITIVE
    ),
    resistance_band: ResistanceBandClassification | None = None,
    sin_summary: DriftPatternSummary | None = None,
    harness_intercept_kinds: tuple[InterceptKind, ...] = (),
) -> SubstrateTraceLedger:
    ledger = SubstrateTraceLedger()
    ledger.append(
        decision_id=decision_id,
        decision_kind=decision_kind,
        permitted=permitted,
        rationale=rationale,
        epoch_seconds=epoch_seconds,
        npg_verdict=npg_verdict,
        resistance_band=resistance_band,
        sin_summary=sin_summary,
        harness_intercept_kinds=harness_intercept_kinds,
    )
    return ledger

def _artifact_with(
    *,
    cell_id: str,
    **overrides: Any,
) -> SubstrateAuditArtifact:
    ledger = _ledger_with(**overrides)
    return SubstrateAuditArtifact.from_ledger(
        ledger=ledger, cell_id=cell_id,
    )

# -----------------------------
# Constructor validation
# -----------------------------

class TestConstructorValidation:
    def test_default_construction(self) -> None:
        v = CrossCellAuditVerifier()
        assert v is not None

    def test_overlapping_severity_sets_rejected(self) -> None:
        with pytest.raises(ValueError, match="disjoint"):
            CrossCellAuditVerifier(
                high_severity_fields=frozenset({"foo"}),
                medium_severity_fields=frozenset({"foo"}),
            )

    def test_high_low_overlap_rejected(self) -> None:
        with pytest.raises(ValueError, match="disjoint"):
            CrossCellAuditVerifier(
                high_severity_fields=frozenset({"x"}),
                low_severity_fields=frozenset({"x"}),
            )

    def test_default_severity_sets_disjoint(self) -> None:
        assert DEFAULT_HIGH_SEVERITY_FIELDS.isdisjoint(
            DEFAULT_MEDIUM_SEVERITY_FIELDS
        )
        assert DEFAULT_HIGH_SEVERITY_FIELDS.isdisjoint(
            DEFAULT_LOW_SEVERITY_FIELDS
        )
        assert DEFAULT_MEDIUM_SEVERITY_FIELDS.isdisjoint(
            DEFAULT_LOW_SEVERITY_FIELDS
        )

# -----------------------------
# Empty + single-artifact cases
# -----------------------------

class TestEmptyAndSingle:
    def test_empty_artifacts_returns_empty_report(self) -> None:
        v = CrossCellAuditVerifier()
        report = v.verify(artifacts=())
        assert report.total_artifacts == 0
        assert report.total_unique_decisions == 0
        assert report.per_cell == ()
        assert report.overlaps == ()
        assert report.inconsistencies == ()
        assert report.ok is True

    def test_single_clean_artifact(self) -> None:
        v = CrossCellAuditVerifier()
        report = v.verify(artifacts=(_artifact_with(cell_id="A"),))
        assert report.total_artifacts == 1
        assert report.all_artifacts_valid is True
        assert report.cross_cell_consistent is True
        assert report.ok is True
        assert report.overlaps == ()  # only one cell → no overlap

    def test_single_invalid_artifact_marked_invalid(self) -> None:
        v = CrossCellAuditVerifier()
        original = _artifact_with(cell_id="A")
        bad_manifest = dataclasses.replace(
            original.manifest, record_count=99,
        )
        bad_artifact = SubstrateAuditArtifact(
            manifest=bad_manifest, records=original.records,
        )
        report = v.verify(artifacts=(bad_artifact,))
        assert report.all_artifacts_valid is False
        assert report.ok is False

# -----------------------------
# Cross-cell overlap detection
# -----------------------------

class TestCrossCellOverlap:
    def test_two_cells_non_overlapping_decisions(self) -> None:
        v = CrossCellAuditVerifier()
        a = _artifact_with(cell_id="A", decision_id="d-1")
        b = _artifact_with(cell_id="B", decision_id="d-2")
        report = v.verify(artifacts=(a, b))
        assert report.total_unique_decisions == 2
        assert report.overlaps == ()
        assert report.inconsistencies == ()
        assert report.ok is True

    def test_two_cells_same_decision_id_consistent(self) -> None:
        v = CrossCellAuditVerifier()
        a = _artifact_with(cell_id="A", decision_id="shared")
        b = _artifact_with(cell_id="B", decision_id="shared")
        report = v.verify(artifacts=(a, b))
        assert report.total_unique_decisions == 1
        assert len(report.overlaps) == 1
        overlap = report.overlaps[0]
        assert overlap.decision_id == "shared"
        assert set(overlap.cells) == {"A", "B"}
        assert overlap.consistent is True
        assert report.inconsistencies == ()
        assert report.ok is True

    def test_three_cells_same_decision_id_consistent(self) -> None:
        v = CrossCellAuditVerifier()
        artifacts = tuple(
            _artifact_with(cell_id=c, decision_id="shared")
            for c in ("A", "B", "C")
        )
        report = v.verify(artifacts=artifacts)
        assert len(report.overlaps) == 1
        assert set(report.overlaps[0].cells) == {"A", "B", "C"}
        assert report.ok is True

    def test_same_cell_multiple_artifacts_not_an_overlap(self) -> None:
        v = CrossCellAuditVerifier()
        a1 = _artifact_with(cell_id="A", decision_id="d-1")
        a2 = _artifact_with(cell_id="A", decision_id="d-2")
        report = v.verify(artifacts=(a1, a2))
        # Same cell across two artifacts → no cross-cell overlap.
        assert report.overlaps == ()

# -----------------------------
# Inconsistency detection
# -----------------------------

class TestInconsistencyDetection:
    def test_inconsistent_verdict_high_severity(self) -> None:
        v = CrossCellAuditVerifier()
        a = _artifact_with(
            cell_id="A",
            decision_id="shared",
            npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
        )
        b = _artifact_with(
            cell_id="B",
            decision_id="shared",
            npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE,
        )
        report = v.verify(artifacts=(a, b))
        assert len(report.inconsistencies) == 1
        finding = report.inconsistencies[0]
        assert finding.severity is CrossCellFindingSeverity.HIGH
        assert "npg_verdict" in finding.differing_fields
        assert report.ok is False

    def test_inconsistent_permitted_high_severity(self) -> None:
        v = CrossCellAuditVerifier()
        a = _artifact_with(
            cell_id="A", decision_id="shared", permitted=True,
        )
        b = _artifact_with(
            cell_id="B", decision_id="shared", permitted=False,
        )
        report = v.verify(artifacts=(a, b))
        assert report.inconsistencies[0].severity is \
            CrossCellFindingSeverity.HIGH

    def test_inconsistent_rationale_low_severity(self) -> None:
        v = CrossCellAuditVerifier()
        a = _artifact_with(
            cell_id="A", decision_id="shared", rationale="alpha",
        )
        b = _artifact_with(
            cell_id="B", decision_id="shared", rationale="beta",
        )
        report = v.verify(artifacts=(a, b))
        assert len(report.inconsistencies) == 1
        assert report.inconsistencies[0].severity is \
            CrossCellFindingSeverity.LOW
        assert "rationale" in report.inconsistencies[0].differing_fields

    def test_inconsistent_epoch_medium_severity(self) -> None:
        v = CrossCellAuditVerifier()
        a = _artifact_with(
            cell_id="A", decision_id="shared", epoch_seconds=100,
        )
        b = _artifact_with(
            cell_id="B", decision_id="shared", epoch_seconds=999,
        )
        report = v.verify(artifacts=(a, b))
        assert report.inconsistencies[0].severity is \
            CrossCellFindingSeverity.MEDIUM

    def test_inconsistent_resistance_band_high(self) -> None:
        v = CrossCellAuditVerifier()
        a = _artifact_with(
            cell_id="A", decision_id="shared",
            resistance_band=ResistanceBandClassification.PRODUCTIVE,
        )
        b = _artifact_with(
            cell_id="B", decision_id="shared",
            resistance_band=ResistanceBandClassification.STRESSED,
        )
        report = v.verify(artifacts=(a, b))
        assert report.inconsistencies[0].severity is \
            CrossCellFindingSeverity.HIGH
        assert "resistance_band" in report.inconsistencies[0].differing_fields

    def test_inconsistent_sin_summary_high(self) -> None:
        v = CrossCellAuditVerifier()
        sin_a = DriftPatternSummary(
            dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
            composite_confidence=0.9,
            amplifier_pattern_present=True,
            kinds_detected=(DriftPattern.SELF_REFERENCE_MISCALIBRATION,),
        )
        sin_b = DriftPatternSummary(
            dominant_pattern=DriftPattern.REACTIVE_NET_NEGATIVE,
            composite_confidence=0.9,
            amplifier_pattern_present=False,
            kinds_detected=(DriftPattern.REACTIVE_NET_NEGATIVE,),
        )
        a = _artifact_with(
            cell_id="A", decision_id="shared", sin_summary=sin_a,
        )
        b = _artifact_with(
            cell_id="B", decision_id="shared", sin_summary=sin_b,
        )
        report = v.verify(artifacts=(a, b))
        assert report.inconsistencies[0].severity is \
            CrossCellFindingSeverity.HIGH

    def test_inconsistent_intercepts_high(self) -> None:
        v = CrossCellAuditVerifier()
        a = _artifact_with(
            cell_id="A", decision_id="shared",
            harness_intercept_kinds=(InterceptKind.NPG_NEGATIVE,),
        )
        b = _artifact_with(
            cell_id="B", decision_id="shared",
            harness_intercept_kinds=(InterceptKind.INVERSION_DETECTED,),
        )
        report = v.verify(artifacts=(a, b))
        assert report.inconsistencies[0].severity is \
            CrossCellFindingSeverity.HIGH

    def test_multiple_differing_fields_take_highest_severity(self) -> None:
        v = CrossCellAuditVerifier()
        a = _artifact_with(
            cell_id="A", decision_id="shared",
            rationale="alpha",  # LOW
            epoch_seconds=100,  # MEDIUM
            permitted=True,  # HIGH
        )
        b = _artifact_with(
            cell_id="B", decision_id="shared",
            rationale="beta", epoch_seconds=999, permitted=False,
        )
        report = v.verify(artifacts=(a, b))
        assert report.inconsistencies[0].severity is \
            CrossCellFindingSeverity.HIGH

# -----------------------------
# Per-cell verification surface
# -----------------------------

class TestPerCellVerification:
    def test_per_cell_findings_one_per_artifact(self) -> None:
        v = CrossCellAuditVerifier()
        report = v.verify(artifacts=(
            _artifact_with(cell_id="A"),
            _artifact_with(cell_id="B"),
            _artifact_with(cell_id="C"),
        ))
        assert len(report.per_cell) == 3
        cell_ids = [f.cell_id for f in report.per_cell]
        assert cell_ids == ["A", "B", "C"]
        for f in report.per_cell:
            assert f.verification.ok is True
            assert f.record_count == 1

    def test_per_cell_records_artifact_index(self) -> None:
        v = CrossCellAuditVerifier()
        report = v.verify(artifacts=(
            _artifact_with(cell_id="A"),
            _artifact_with(cell_id="B"),
        ))
        indices = [f.artifact_index for f in report.per_cell]
        assert indices == [0, 1]

# -----------------------------
# HMAC secret routing
# -----------------------------

class TestHmacSecretRouting:
    def test_hmac_verifies_per_cell_with_correct_secret(self) -> None:
        v = CrossCellAuditVerifier()
        ledger_a = _ledger_with(decision_id="d-1")
        ledger_b = _ledger_with(decision_id="d-2")
        a = SubstrateAuditArtifact.from_ledger(
            ledger=ledger_a, cell_id="A", hmac_secret=b"secret-A",
        )
        b = SubstrateAuditArtifact.from_ledger(
            ledger=ledger_b, cell_id="B", hmac_secret=b"secret-B",
        )
        report = v.verify(
            artifacts=(a, b),
            hmac_secrets={"A": b"secret-A", "B": b"secret-B"},
        )
        for finding in report.per_cell:
            assert finding.verification.hmac_ok is True
        assert report.ok is True

    def test_wrong_secret_marks_cell_invalid(self) -> None:
        v = CrossCellAuditVerifier()
        ledger = _ledger_with(decision_id="d-1")
        a = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="A", hmac_secret=b"correct",
        )
        report = v.verify(
            artifacts=(a,),
            hmac_secrets={"A": b"wrong"},
        )
        assert report.per_cell[0].verification.hmac_ok is False
        assert report.all_artifacts_valid is False
        assert report.ok is False

    def test_missing_secret_skips_hmac(self) -> None:
        v = CrossCellAuditVerifier()
        ledger = _ledger_with(decision_id="d-1")
        a = SubstrateAuditArtifact.from_ledger(
            ledger=ledger, cell_id="A", hmac_secret=b"secret",
        )
        # Caller didn't supply secret for "A" → hmac not verified, but
        # other checks still pass.
        report = v.verify(artifacts=(a,))
        assert report.per_cell[0].verification.hmac_ok is None
        assert report.ok is True

# -----------------------------
# Report aggregate properties
# -----------------------------

class TestReportAggregate:
    def test_total_unique_decisions_dedupes(self) -> None:
        v = CrossCellAuditVerifier()
        a = _artifact_with(cell_id="A", decision_id="d-1")
        b = _artifact_with(cell_id="B", decision_id="d-1")
        c = _artifact_with(cell_id="C", decision_id="d-2")
        report = v.verify(artifacts=(a, b, c))
        assert report.total_unique_decisions == 2

    def test_highest_severity_picks_high_over_low(self) -> None:
        v = CrossCellAuditVerifier()
        # Two decisions, different severities.
        a1 = _artifact_with(
            cell_id="A", decision_id="d-1", rationale="x",
        )
        b1 = _artifact_with(
            cell_id="B", decision_id="d-1", rationale="y",
        )
        a2 = _artifact_with(
            cell_id="A2", decision_id="d-2", permitted=True,
        )
        b2 = _artifact_with(
            cell_id="B2", decision_id="d-2", permitted=False,
        )
        # NOTE: a + a2 are different cell IDs so we use separate cells.
        report = v.verify(artifacts=(a1, b1, a2, b2))
        assert report.highest_severity is CrossCellFindingSeverity.HIGH

    def test_no_inconsistency_yields_none_severity(self) -> None:
        v = CrossCellAuditVerifier()
        report = v.verify(artifacts=(
            _artifact_with(cell_id="A", decision_id="d-1"),
            _artifact_with(cell_id="B", decision_id="d-1"),
        ))
        assert report.highest_severity is CrossCellFindingSeverity.NONE

    def test_ok_property_composes_all_validity(self) -> None:
        v = CrossCellAuditVerifier()
        a = _artifact_with(cell_id="A", decision_id="d-1", permitted=True)
        b = _artifact_with(cell_id="B", decision_id="d-1", permitted=False)
        report = v.verify(artifacts=(a, b))
        # Artifacts are individually valid; cross-cell inconsistent.
        assert report.all_artifacts_valid is True
        assert report.cross_cell_consistent is False
        assert report.ok is False

# -----------------------------
# Custom severity classification
# -----------------------------

class TestCustomSeverity:
    def test_custom_high_field_set(self) -> None:
        # Treat rationale as HIGH.
        v = CrossCellAuditVerifier(
            high_severity_fields=frozenset({"rationale"}),
            medium_severity_fields=DEFAULT_MEDIUM_SEVERITY_FIELDS,
            low_severity_fields=frozenset(),
        )
        a = _artifact_with(
            cell_id="A", decision_id="shared", rationale="x",
        )
        b = _artifact_with(
            cell_id="B", decision_id="shared", rationale="y",
        )
        report = v.verify(artifacts=(a, b))
        assert report.inconsistencies[0].severity is \
            CrossCellFindingSeverity.HIGH

    def test_unclassified_field_defaults_to_medium(self) -> None:
        v = CrossCellAuditVerifier(
            high_severity_fields=frozenset({"permitted"}),
            medium_severity_fields=frozenset(),
            low_severity_fields=frozenset(),
        )
        # rationale is unclassified by the custom config → MEDIUM default.
        a = _artifact_with(
            cell_id="A", decision_id="shared", rationale="x",
        )
        b = _artifact_with(
            cell_id="B", decision_id="shared", rationale="y",
        )
        report = v.verify(artifacts=(a, b))
        assert report.inconsistencies[0].severity is \
            CrossCellFindingSeverity.MEDIUM

# -----------------------------
# Module surface
# -----------------------------

class TestModuleSurface:
    def test_report_is_frozen(self) -> None:
        v = CrossCellAuditVerifier()
        report = v.verify(artifacts=())
        with pytest.raises(dataclasses.FrozenInstanceError):
            report.total_artifacts = 99  # type: ignore[misc]

    def test_severity_enum_values(self) -> None:
        assert CrossCellFindingSeverity.NONE.value == "none"
        assert CrossCellFindingSeverity.LOW.value == "low"
        assert CrossCellFindingSeverity.MEDIUM.value == "medium"
        assert CrossCellFindingSeverity.HIGH.value == "high"

    def test_overlap_inconsistency_finding_are_frozen(self) -> None:
        v = CrossCellAuditVerifier()
        a = _artifact_with(cell_id="A", decision_id="d-1", permitted=True)
        b = _artifact_with(cell_id="B", decision_id="d-1", permitted=False)
        report = v.verify(artifacts=(a, b))
        for o in report.overlaps:
            assert isinstance(o, CrossCellOverlap)
            with pytest.raises(dataclasses.FrozenInstanceError):
                o.consistent = True  # type: ignore[misc]
        for i in report.inconsistencies:
            assert isinstance(i, CrossCellInconsistency)
            with pytest.raises(dataclasses.FrozenInstanceError):
                i.severity = CrossCellFindingSeverity.LOW  # type: ignore[misc]

    def test_cell_artifact_finding_dataclass(self) -> None:
        v = CrossCellAuditVerifier()
        report = v.verify(artifacts=(_artifact_with(cell_id="A"),))
        f = report.per_cell[0]
        assert isinstance(f, CellArtifactFinding)
        with pytest.raises(dataclasses.FrozenInstanceError):
            f.cell_id = "X"  # type: ignore[misc]

    def test_report_dataclass(self) -> None:
        v = CrossCellAuditVerifier()
        report = v.verify(artifacts=())
        assert isinstance(report, CrossCellVerificationReport)
