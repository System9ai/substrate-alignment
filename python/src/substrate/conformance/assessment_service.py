"""Substrate conformance assessment service

Pure-logic primitive composing substrate-conformance check results
from six independent sub-primitives into a single deployment-gate
verdict. Per the
operating-mode certification surface — an entity (cell or node) is
**CERTIFIED** for substrate-aware deployment only when the
conformance assessment surfaces it.

Six conformance checks
======================

* **Awareness verification** — Phase 31 mode-3 awareness verifier.
* **5D behavioral probe suite** — Phase 54 modeling mode operational probes.
* **Voting precondition** — Phase 37 substrate-aware voting gate.
* **authority-pressure failure probe suite** — Phase 36 failure-mode probes.
* **Golden Rule probe** — Phase 55 reciprocity probe.
* **Drift posture** — Phase 56 drift-signal aggregator verdict.

Each check has a graded :class:`ConformanceSeverity` so a single
critical failure can override a high pass rate elsewhere.

Pure logic
==========

* No DAO, no LLM, no network. Caller assembles
  :class:`ConformanceCheckResult` records from the upstream primitive
  reports.
* Honest uncertainty: empty result set → ``INSUFFICIENT_DATA``.
* Scale-aware via :class:`ConformanceScale` (cell vs node).
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Tuple

class ConformanceScale(str, Enum):
    """the host application entity hierarchy scale for the assessment."""

    CELL = "cell"
    NODE = "node"

class ConformanceCheckKind(str, Enum):
    """The six conformance check kinds."""

    AWARENESS_VERIFICATION = "awareness_verification"
    MODELING_MODE_PROBE = "modeling_mode_probe"
    VOTING_PRECONDITION = "voting_precondition"
    AUTHORITY_PRESSURE_PROBE = "authority_pressure_probe"
    GOLDEN_RULE = "golden_rule"
    DRIFT_POSTURE = "drift_posture"

class ConformanceSeverity(str, Enum):
    """Per-check failure severity."""

    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"

class ConformanceVerdict(str, Enum):
    """Aggregate conformance verdict."""

    CERTIFIED = "certified"
    CONDITIONAL = "conditional"
    NON_CONFORMANT = "non_conformant"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class ConformanceCheckResult:
    """One sub-primitive's contribution to the assessment."""

    kind: ConformanceCheckKind
    passed: bool
    severity: ConformanceSeverity
    rationale: str

    def __post_init__(self) -> None:
        if not self.rationale:
            raise ValueError("rationale must be non-empty")
        if self.passed and self.severity is not ConformanceSeverity.OK:
            raise ValueError(
                "passed=True requires severity=OK"
            )
        if not self.passed and self.severity is ConformanceSeverity.OK:
            raise ValueError(
                "passed=False requires severity != OK"
            )

@dataclass(frozen=True, slots=True)
class ConformanceAssessment:  # pylint: disable=too-many-instance-attributes
    """Aggregate conformance assessment for one entity."""

    entity_id: str
    scale: ConformanceScale
    verdict: ConformanceVerdict
    check_results: Tuple[ConformanceCheckResult, ...]
    passed_count: int
    failed_count: int
    critical_count: int
    warning_count: int
    rationale: str

    @property
    def is_certified(self) -> bool:
        """True iff verdict is CERTIFIED."""
        return self.verdict is ConformanceVerdict.CERTIFIED

    @property
    def is_non_conformant(self) -> bool:
        """True iff verdict is NON_CONFORMANT."""
        return self.verdict is ConformanceVerdict.NON_CONFORMANT

    def by_kind(
        self, kind: ConformanceCheckKind,
    ) -> Optional[ConformanceCheckResult]:
        """Lookup one check result by kind."""
        for r in self.check_results:
            if r.kind is kind:
                return r
        return None

@dataclass(frozen=True, slots=True)
class ConformanceAssessmentConfig:
    """Tunable thresholds for the verdict aggregation."""

    certified_min_passes: int = 6
    conditional_min_passes: int = 4
    critical_short_circuits: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.certified_min_passes <= 6:
            raise ValueError("certified_min_passes must be in [1, 6]")
        if not 1 <= self.conditional_min_passes < (
            self.certified_min_passes
        ):
            raise ValueError(
                "conditional_min_passes must be in [1, certified_min_passes)"
            )

DEFAULT_CONFORMANCE_CONFIG: Final[ConformanceAssessmentConfig] = (
    ConformanceAssessmentConfig()
)

class ConformanceAssessmentService:  # pylint: disable=too-few-public-methods
    """Pure-logic conformance assessment service."""

    def __init__(
        self,
        *,
        config: ConformanceAssessmentConfig = DEFAULT_CONFORMANCE_CONFIG,
    ) -> None:
        self._config = config

    def assess(
        self,
        entity_id: str,
        scale: ConformanceScale,
        results: Tuple[ConformanceCheckResult, ...],
    ) -> ConformanceAssessment:
        """Aggregate sub-primitive check results into a verdict."""
        if not entity_id:
            raise ValueError("entity_id must be non-empty")
        if not results:
            return ConformanceAssessment(
                entity_id=entity_id,
                scale=scale,
                verdict=ConformanceVerdict.INSUFFICIENT_DATA,
                check_results=(),
                passed_count=0,
                failed_count=0,
                critical_count=0,
                warning_count=0,
                rationale="no conformance check results supplied",
            )
        self._validate_unique_kinds(results)
        passed = sum(1 for r in results if r.passed)
        critical = sum(
            1
            for r in results
            if r.severity is ConformanceSeverity.CRITICAL
        )
        warning = sum(
            1
            for r in results
            if r.severity is ConformanceSeverity.WARNING
        )
        failed = sum(1 for r in results if not r.passed)
        verdict = self._aggregate(
            passed=passed, critical=critical,
        )
        rationale = (
            f"entity={entity_id} scale={scale.value} "
            f"passed={passed}/{len(results)} critical={critical} "
            f"warning={warning} verdict={verdict.value}"
        )
        return ConformanceAssessment(
            entity_id=entity_id,
            scale=scale,
            verdict=verdict,
            check_results=results,
            passed_count=passed,
            failed_count=failed,
            critical_count=critical,
            warning_count=warning,
            rationale=rationale,
        )

    @staticmethod
    def _validate_unique_kinds(
        results: Tuple[ConformanceCheckResult, ...],
    ) -> None:
        seen: set[ConformanceCheckKind] = set()
        for r in results:
            if r.kind in seen:
                raise ValueError(
                    f"duplicate conformance check kind: {r.kind.value!r}"
                )
            seen.add(r.kind)

    def _aggregate(
        self, *, passed: int, critical: int,
    ) -> ConformanceVerdict:
        cfg = self._config
        if cfg.critical_short_circuits and critical > 0:
            return ConformanceVerdict.NON_CONFORMANT
        if passed >= cfg.certified_min_passes:
            return ConformanceVerdict.CERTIFIED
        if passed >= cfg.conditional_min_passes:
            return ConformanceVerdict.CONDITIONAL
        return ConformanceVerdict.NON_CONFORMANT

__all__ = [
    "DEFAULT_CONFORMANCE_CONFIG",
    "ConformanceAssessment",
    "ConformanceAssessmentConfig",
    "ConformanceAssessmentService",
    "ConformanceCheckKind",
    "ConformanceCheckResult",
    "ConformanceScale",
    "ConformanceSeverity",
    "ConformanceVerdict",
]
