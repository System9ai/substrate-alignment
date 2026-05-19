"""Consequence-exposure chain verifier

Pure-logic primitive verifying the **law-enforcement-parallel
consequence-exposure architecture**. Substrate-aligned
operation requires that misalignment exposes the actor to
proportionate consequence — without this chain, substrate-aligned
actors become "suckers" because manipulators face no cost.

The eight chain mechanisms
==========================

1. **DETECTION** — misalignment can be observed.
2. **IDENTIFICATION** — observed misalignment can be attributed to a
   specific actor.
3. **RECORDING** — attributed misalignment is durably recorded.
4. **AGGREGATION** — recorded misalignments accumulate into a track
   record.
5. **REPORTING** — accumulated record is reportable to peers / orgs.
6. **ADJUDICATION** — reports can produce verdicts.
7. **SANCTION** — verdicts produce proportionate consequence.
8. **RECOVERY_PATH** — sanctioned actor has a substrate-aligned
   recovery option.

A deployment that lacks any of these mechanisms breaks the chain.

Pure logic
==========

* No DAO, no LLM, no network. Caller asserts mechanism availability
  + strength.
* Honest uncertainty: empty assertion set → ``INSUFFICIENT_DATA``.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Tuple

class ExposureMechanism(str, Enum):
    """The eight consequence-exposure chain mechanisms."""

    DETECTION = "detection"
    IDENTIFICATION = "identification"
    RECORDING = "recording"
    AGGREGATION = "aggregation"
    REPORTING = "reporting"
    ADJUDICATION = "adjudication"
    SANCTION = "sanction"
    RECOVERY_PATH = "recovery_path"

class MechanismStatus(str, Enum):
    """Per-mechanism availability."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"

class ChainVerdict(str, Enum):
    """Aggregate chain coverage verdict."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class MechanismAssertion:
    """Caller-supplied assertion about one mechanism."""

    mechanism: ExposureMechanism
    available: bool
    strength: float
    description: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError("strength must be in [0, 1]")
        if not self.available and self.strength > 0.0:
            raise ValueError(
                "strength must be 0 when available is False"
            )

@dataclass(frozen=True, slots=True)
class MechanismFinding:
    """Evaluated mechanism status."""

    mechanism: ExposureMechanism
    status: MechanismStatus
    strength: float
    rationale: str

@dataclass(frozen=True, slots=True)
class ConsequenceExposureReport:  # pylint: disable=too-many-instance-attributes
    """Aggregate chain coverage report."""

    deployment_context_id: str
    verdict: ChainVerdict
    findings: Tuple[MechanismFinding, ...]
    available_count: int
    degraded_count: int
    unavailable_count: int
    average_strength: float
    rationale: str

    @property
    def is_complete(self) -> bool:
        """True iff verdict is COMPLETE."""
        return self.verdict is ChainVerdict.COMPLETE

    @property
    def is_insufficient(self) -> bool:
        """True iff verdict is INSUFFICIENT (operationally broken chain)."""
        return self.verdict is ChainVerdict.INSUFFICIENT

    def by_mechanism(
        self, mechanism: ExposureMechanism,
    ) -> Optional[MechanismFinding]:
        """Lookup the finding for a given mechanism."""
        for f in self.findings:
            if f.mechanism is mechanism:
                return f
        return None

    def missing_mechanisms(self) -> Tuple[ExposureMechanism, ...]:
        """Mechanisms not AVAILABLE."""
        return tuple(
            f.mechanism
            for f in self.findings
            if f.status is not MechanismStatus.AVAILABLE
        )

@dataclass(frozen=True, slots=True)
class ConsequenceExposureConfig:
    """Tunable thresholds."""

    available_strength_min: float = 0.6
    degraded_strength_min: float = 0.3
    complete_min_available: int = 8
    partial_min_available: int = 5

    def __post_init__(self) -> None:
        if not 0.0 < self.available_strength_min <= 1.0:
            raise ValueError(
                "available_strength_min must be in (0, 1]"
            )
        if not 0.0 < self.degraded_strength_min < self.available_strength_min:
            raise ValueError(
                "degraded_strength_min must be in (0, available_strength_min)"
            )
        if not 1 <= self.complete_min_available <= 8:
            raise ValueError("complete_min_available must be in [1, 8]")
        if not 1 <= self.partial_min_available < self.complete_min_available:
            raise ValueError(
                "partial_min_available must be in [1, complete_min_available)"
            )

DEFAULT_CONSEQUENCE_EXPOSURE_CONFIG: Final[ConsequenceExposureConfig] = (
    ConsequenceExposureConfig()
)

class ConsequenceExposureChain:  # pylint: disable=too-few-public-methods
    """Pure-logic chain verifier."""

    def __init__(
        self,
        *,
        config: ConsequenceExposureConfig = (
            DEFAULT_CONSEQUENCE_EXPOSURE_CONFIG
        ),
    ) -> None:
        self._config = config

    def assess(
        self,
        deployment_context_id: str,
        assertions: Tuple[MechanismAssertion, ...],
    ) -> ConsequenceExposureReport:
        """Verify the eight-mechanism chain for one deployment context."""
        if not deployment_context_id:
            raise ValueError("deployment_context_id must be non-empty")
        if not assertions:
            return ConsequenceExposureReport(
                deployment_context_id=deployment_context_id,
                verdict=ChainVerdict.INSUFFICIENT_DATA,
                findings=(),
                available_count=0,
                degraded_count=0,
                unavailable_count=0,
                average_strength=0.0,
                rationale="no mechanism assertions supplied",
            )
        self._validate_unique(assertions)
        assertion_by_kind = {a.mechanism: a for a in assertions}
        findings = tuple(
            self._evaluate(kind, assertion_by_kind.get(kind))
            for kind in ExposureMechanism
        )
        available = sum(
            1
            for f in findings
            if f.status is MechanismStatus.AVAILABLE
        )
        degraded = sum(
            1
            for f in findings
            if f.status is MechanismStatus.DEGRADED
        )
        unavailable = sum(
            1
            for f in findings
            if f.status is MechanismStatus.UNAVAILABLE
        )
        avg_strength = (
            sum(f.strength for f in findings) / len(findings)
            if findings
            else 0.0
        )
        verdict = self._aggregate(available)
        rationale = (
            f"context={deployment_context_id} available={available}/8 "
            f"degraded={degraded} unavailable={unavailable} "
            f"avg_strength={avg_strength:.3f} verdict={verdict.value}"
        )
        return ConsequenceExposureReport(
            deployment_context_id=deployment_context_id,
            verdict=verdict,
            findings=findings,
            available_count=available,
            degraded_count=degraded,
            unavailable_count=unavailable,
            average_strength=avg_strength,
            rationale=rationale,
        )

    def _evaluate(
        self,
        mechanism: ExposureMechanism,
        assertion: Optional[MechanismAssertion],
    ) -> MechanismFinding:
        cfg = self._config
        if assertion is None:
            return MechanismFinding(
                mechanism=mechanism,
                status=MechanismStatus.UNAVAILABLE,
                strength=0.0,
                rationale=f"no assertion supplied for {mechanism.value}",
            )
        if not assertion.available:
            return MechanismFinding(
                mechanism=mechanism,
                status=MechanismStatus.UNAVAILABLE,
                strength=0.0,
                rationale="available=False",
            )
        if assertion.strength >= cfg.available_strength_min:
            return MechanismFinding(
                mechanism=mechanism,
                status=MechanismStatus.AVAILABLE,
                strength=assertion.strength,
                rationale=(
                    f"strength={assertion.strength:.3f} >= "
                    f"{cfg.available_strength_min}"
                ),
            )
        if assertion.strength >= cfg.degraded_strength_min:
            return MechanismFinding(
                mechanism=mechanism,
                status=MechanismStatus.DEGRADED,
                strength=assertion.strength,
                rationale=(
                    f"strength={assertion.strength:.3f} in "
                    f"[{cfg.degraded_strength_min}, "
                    f"{cfg.available_strength_min})"
                ),
            )
        return MechanismFinding(
            mechanism=mechanism,
            status=MechanismStatus.UNAVAILABLE,
            strength=assertion.strength,
            rationale=(
                f"strength={assertion.strength:.3f} < "
                f"{cfg.degraded_strength_min}"
            ),
        )

    @staticmethod
    def _validate_unique(
        assertions: Tuple[MechanismAssertion, ...],
    ) -> None:
        seen: set[ExposureMechanism] = set()
        for a in assertions:
            if a.mechanism in seen:
                raise ValueError(
                    f"duplicate mechanism: {a.mechanism.value!r}"
                )
            seen.add(a.mechanism)

    def _aggregate(self, available_count: int) -> ChainVerdict:
        cfg = self._config
        if available_count >= cfg.complete_min_available:
            return ChainVerdict.COMPLETE
        if available_count >= cfg.partial_min_available:
            return ChainVerdict.PARTIAL
        return ChainVerdict.INSUFFICIENT

__all__ = [
    "DEFAULT_CONSEQUENCE_EXPOSURE_CONFIG",
    "ChainVerdict",
    "ConsequenceExposureChain",
    "ConsequenceExposureConfig",
    "ConsequenceExposureReport",
    "ExposureMechanism",
    "MechanismAssertion",
    "MechanismFinding",
    "MechanismStatus",
]
