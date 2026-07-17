"""Tests for EightCriteriaSubstrateStructureVerifier."""
from __future__ import annotations

import pytest

from substrate.discovery.eight_criteria_verifier import (
    DEFAULT_EIGHT_CRITERIA_CONFIG,
    CriterionEvidence,
    CriterionKind,
    CriterionStatus,
    EightCriteriaConfig,
    EightCriteriaSubstrateStructureVerifier,
    StructureVerdict,
)

def _evidence(
    kind: CriterionKind,
    *,
    count: int = 3,
    confidence: float = 0.9,
) -> CriterionEvidence:
    return CriterionEvidence(
        kind=kind,
        evidence_count=count,
        confidence=confidence,
    )

def _all_satisfied() -> tuple[CriterionEvidence, ...]:
    return tuple(_evidence(k) for k in CriterionKind)

class TestEvidenceValidation:
    def test_round_trip(self) -> None:
        e = _evidence(CriterionKind.CROSS_TRADITION_CONVERGENCE)
        assert e.kind is CriterionKind.CROSS_TRADITION_CONVERGENCE

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("count", -1, "evidence_count"),
            ("confidence", 1.5, "confidence"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            _evidence(
                CriterionKind.CROSS_TRADITION_CONVERGENCE,
                **{field: value},
            )

class TestConfig:
    def test_defaults(self) -> None:
        cfg = EightCriteriaConfig()
        assert cfg.discovered_min_satisfied == 8

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("min_evidence_count", 0, "min_evidence_count"),
            ("min_confidence", 0.0, "min_confidence"),
            ("discovered_min_satisfied", 9, "discovered_min_satisfied"),
            ("partial_min_satisfied", 0, "partial_min_satisfied"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            EightCriteriaConfig(**{field: value})

class TestVerifyFlow:
    def setup_method(self) -> None:
        self.v = EightCriteriaSubstrateStructureVerifier()

    def test_empty_claim_rejected(self) -> None:
        with pytest.raises(ValueError, match="claim_id"):
            self.v.verify("", ())

    def test_no_evidence_insufficient(self) -> None:
        out = self.v.verify("c-1", ())
        assert out.verdict is StructureVerdict.INSUFFICIENT_DATA

    def test_duplicate_kinds_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            self.v.verify(
                "c-1",
                (
                    _evidence(CriterionKind.CROSS_TRADITION_CONVERGENCE),
                    _evidence(CriterionKind.CROSS_TRADITION_CONVERGENCE),
                ),
            )

class TestVerdictAggregation:
    def setup_method(self) -> None:
        self.v = EightCriteriaSubstrateStructureVerifier()

    def test_all_satisfied_discovered(self) -> None:
        out = self.v.verify("c-1", _all_satisfied())
        assert out.discovered
        assert out.satisfied_count == 8

    def test_six_satisfied_partial(self) -> None:
        # 6 satisfied, 2 unsatisfied
        evidence = tuple(
            _evidence(k, count=1 if i >= 6 else 3)
            for i, k in enumerate(CriterionKind)
        )
        out = self.v.verify("c-1", evidence)
        assert out.verdict is StructureVerdict.PARTIAL

    def test_two_satisfied_invented(self) -> None:
        # 2 satisfied, 6 unsatisfied
        evidence = tuple(
            _evidence(k, count=3 if i < 2 else 1, confidence=0.9 if i < 2 else 0.3)
            for i, k in enumerate(CriterionKind)
        )
        out = self.v.verify("c-1", evidence)
        assert out.verdict is StructureVerdict.INVENTED

    def test_all_insufficient_propagates(self) -> None:
        # All evidence has count=0 → INSUFFICIENT
        evidence = tuple(
            _evidence(k, count=0) for k in CriterionKind
        )
        out = self.v.verify("c-1", evidence)
        assert out.verdict is StructureVerdict.INSUFFICIENT_DATA

class TestCriterionEvaluation:
    def setup_method(self) -> None:
        self.v = EightCriteriaSubstrateStructureVerifier()

    def test_zero_evidence_insufficient(self) -> None:
        out = self.v.verify(
            "c-1",
            (_evidence(
                CriterionKind.MATHEMATICAL_NECESSITY, count=0,
            ),),
        )
        finding = out.by_criterion(CriterionKind.MATHEMATICAL_NECESSITY)
        assert finding is not None
        assert finding.status is CriterionStatus.INSUFFICIENT_DATA

    def test_low_confidence_unsatisfied(self) -> None:
        out = self.v.verify(
            "c-1",
            (_evidence(
                CriterionKind.PARSIMONY, count=3, confidence=0.3,
            ),),
        )
        finding = out.by_criterion(CriterionKind.PARSIMONY)
        assert finding is not None
        assert finding.status is CriterionStatus.UNSATISFIED

    def test_partial_evidence_unsatisfied(self) -> None:
        out = self.v.verify(
            "c-1",
            (_evidence(
                CriterionKind.PARSIMONY, count=1, confidence=0.9,
            ),),
        )
        finding = out.by_criterion(CriterionKind.PARSIMONY)
        assert finding is not None
        assert finding.status is CriterionStatus.UNSATISFIED

class TestReportProperties:
    def test_missing_criteria_reported(self) -> None:
        v = EightCriteriaSubstrateStructureVerifier()
        evidence = tuple(
            _evidence(k, count=1)
            for k in [
                CriterionKind.CROSS_TRADITION_CONVERGENCE,
                CriterionKind.MATHEMATICAL_NECESSITY,
            ]
        )
        out = v.verify("c-1", evidence)
        missing = out.missing_criteria()
        # 6 not supplied + 2 unsatisfied (count=1)
        assert len(missing) == 8

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_EIGHT_CRITERIA_CONFIG.min_evidence_count == 2
