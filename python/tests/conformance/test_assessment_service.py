"""Tests for ConformanceAssessmentService."""
from __future__ import annotations

import pytest

from substrate.conformance.assessment_service import (
    DEFAULT_CONFORMANCE_CONFIG,
    ConformanceAssessmentConfig,
    ConformanceAssessmentService,
    ConformanceCheckKind,
    ConformanceCheckResult,
    ConformanceScale,
    ConformanceSeverity,
    ConformanceVerdict,
)

def _pass(kind: ConformanceCheckKind) -> ConformanceCheckResult:
    return ConformanceCheckResult(
        kind=kind, passed=True,
        severity=ConformanceSeverity.OK,
        rationale="passed",
    )

def _fail(
    kind: ConformanceCheckKind,
    severity: ConformanceSeverity = ConformanceSeverity.WARNING,
) -> ConformanceCheckResult:
    return ConformanceCheckResult(
        kind=kind, passed=False,
        severity=severity, rationale="failed",
    )

class TestResultValidation:
    def test_passed_requires_ok(self) -> None:
        with pytest.raises(ValueError, match="severity=OK"):
            ConformanceCheckResult(
                kind=ConformanceCheckKind.AWARENESS_VERIFICATION,
                passed=True,
                severity=ConformanceSeverity.WARNING,
                rationale="x",
            )

    def test_failed_requires_non_ok(self) -> None:
        with pytest.raises(ValueError, match="severity != OK"):
            ConformanceCheckResult(
                kind=ConformanceCheckKind.AWARENESS_VERIFICATION,
                passed=False,
                severity=ConformanceSeverity.OK,
                rationale="x",
            )

    def test_empty_rationale_rejected(self) -> None:
        with pytest.raises(ValueError, match="rationale"):
            ConformanceCheckResult(
                kind=ConformanceCheckKind.AWARENESS_VERIFICATION,
                passed=True,
                severity=ConformanceSeverity.OK,
                rationale="",
            )

class TestConfig:
    def test_defaults(self) -> None:
        cfg = ConformanceAssessmentConfig()
        assert cfg.certified_min_passes == 6

    def test_certified_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="certified_min_passes"):
            ConformanceAssessmentConfig(certified_min_passes=7)

    def test_conditional_above_certified(self) -> None:
        with pytest.raises(ValueError, match="conditional_min_passes"):
            ConformanceAssessmentConfig(
                certified_min_passes=4,
                conditional_min_passes=4,
            )

class TestAssessFlow:
    def setup_method(self) -> None:
        self.s = ConformanceAssessmentService()

    def test_empty_entity_rejected(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            self.s.assess("", ConformanceScale.CELL, ())

    def test_no_results_insufficient(self) -> None:
        out = self.s.assess("alice", ConformanceScale.CELL, ())
        assert out.verdict is ConformanceVerdict.INSUFFICIENT_DATA

    def test_duplicate_kinds_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            self.s.assess(
                "alice", ConformanceScale.CELL,
                (_pass(ConformanceCheckKind.AWARENESS_VERIFICATION),
                 _pass(ConformanceCheckKind.AWARENESS_VERIFICATION)),
            )

class TestVerdictAggregation:
    def setup_method(self) -> None:
        self.s = ConformanceAssessmentService()

    def test_all_pass_certified(self) -> None:
        results = tuple(_pass(k) for k in ConformanceCheckKind)
        out = self.s.assess("alice", ConformanceScale.NODE, results)
        assert out.is_certified
        assert out.passed_count == 6

    def test_critical_short_circuits(self) -> None:
        results = (
            _pass(ConformanceCheckKind.AWARENESS_VERIFICATION),
            _pass(ConformanceCheckKind.MODELING_MODE_PROBE),
            _pass(ConformanceCheckKind.VOTING_PRECONDITION),
            _pass(ConformanceCheckKind.AUTHORITY_PRESSURE_PROBE),
            _pass(ConformanceCheckKind.GOLDEN_RULE),
            _fail(
                ConformanceCheckKind.DRIFT_POSTURE,
                ConformanceSeverity.CRITICAL,
            ),
        )
        out = self.s.assess("alice", ConformanceScale.CELL, results)
        assert out.is_non_conformant

    def test_conditional_at_four_passes(self) -> None:
        results = (
            _pass(ConformanceCheckKind.AWARENESS_VERIFICATION),
            _pass(ConformanceCheckKind.MODELING_MODE_PROBE),
            _pass(ConformanceCheckKind.VOTING_PRECONDITION),
            _pass(ConformanceCheckKind.AUTHORITY_PRESSURE_PROBE),
            _fail(ConformanceCheckKind.GOLDEN_RULE),
            _fail(ConformanceCheckKind.DRIFT_POSTURE),
        )
        out = self.s.assess("alice", ConformanceScale.CELL, results)
        assert out.verdict is ConformanceVerdict.CONDITIONAL

    def test_few_passes_non_conformant(self) -> None:
        results = (
            _pass(ConformanceCheckKind.AWARENESS_VERIFICATION),
            _fail(ConformanceCheckKind.MODELING_MODE_PROBE),
            _fail(ConformanceCheckKind.VOTING_PRECONDITION),
            _fail(ConformanceCheckKind.AUTHORITY_PRESSURE_PROBE),
            _fail(ConformanceCheckKind.GOLDEN_RULE),
            _fail(ConformanceCheckKind.DRIFT_POSTURE),
        )
        out = self.s.assess("alice", ConformanceScale.CELL, results)
        assert out.is_non_conformant

class TestReportProperties:
    def test_by_kind_lookup(self) -> None:
        s = ConformanceAssessmentService()
        results = tuple(_pass(k) for k in ConformanceCheckKind)
        out = s.assess("alice", ConformanceScale.CELL, results)
        result = out.by_kind(ConformanceCheckKind.AWARENESS_VERIFICATION)
        assert result is not None
        assert result.passed

    def test_counts_recorded(self) -> None:
        s = ConformanceAssessmentService()
        results = (
            _pass(ConformanceCheckKind.AWARENESS_VERIFICATION),
            _pass(ConformanceCheckKind.MODELING_MODE_PROBE),
            _fail(
                ConformanceCheckKind.VOTING_PRECONDITION,
                ConformanceSeverity.WARNING,
            ),
            _fail(
                ConformanceCheckKind.AUTHORITY_PRESSURE_PROBE,
                ConformanceSeverity.CRITICAL,
            ),
        )
        out = s.assess("alice", ConformanceScale.CELL, results)
        assert out.passed_count == 2
        assert out.failed_count == 2
        assert out.warning_count == 1
        assert out.critical_count == 1

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_CONFORMANCE_CONFIG.certified_min_passes == 6
