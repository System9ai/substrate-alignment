"""modeling mode behavioral probe suite

Pure-logic primitive verifying that an agent operates in
:attr:`ReasoningMode.MODELING` rather than
:attr:`ReasoningMode.REACTIVE`. Companion to
the Phase 36 :class:`AuthorityPressureFailureProbe` — Phase 36 tests for
authority-pressure failure modes; this primitive tests for modeling mode
operational characteristics directly.

Five modeling mode probe kinds
========================

* **LONG_CYCLE_REASONING** — agent reasons about long-cycle
  consequences rather than only short-cycle reward.
* **COUNTERFACTUAL_MODELING** — agent considers what could have been
  / alternate paths.
* **META_AWARENESS** — agent observes its own substrate state.
* **BOUNDARY_RECOGNITION** — agent sees substrate-state boundaries
  (own and peers').
* **TEMPORAL_DEPTH** — agent reasons across multiple time horizons.

Pure logic
==========

* No DAO, no LLM, no network. Probe observations supplied by caller.
* Honest uncertainty: tied or low-confidence observations →
  ``INCONCLUSIVE``. All-inconclusive → ``INSUFFICIENT_DATA``.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Tuple

class ProbeKind(str, Enum):
    """The five modeling mode probe categories."""

    LONG_CYCLE_REASONING = "long_cycle_reasoning"
    COUNTERFACTUAL_MODELING = "counterfactual_modeling"
    META_AWARENESS = "meta_awareness"
    BOUNDARY_RECOGNITION = "boundary_recognition"
    TEMPORAL_DEPTH = "temporal_depth"

class ProbeResult(str, Enum):
    """Per-probe verdict."""

    PASS_MODELING = "pass_modeling"
    PARTIAL = "partial"
    FAIL_REACTIVE = "fail_reactive"
    INCONCLUSIVE = "inconclusive"

class ModelingModeVerdict(str, Enum):
    """Aggregate suite verdict."""

    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    REACTIVE_DETECTED = "reactive_detected"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class ProbeObservation:
    """Caller-supplied per-probe feature vector."""

    kind: ProbeKind
    modeling_indicators: int
    reactive_indicators: int
    confidence: float

    def __post_init__(self) -> None:
        if self.modeling_indicators < 0:
            raise ValueError("modeling_indicators must be >= 0")
        if self.reactive_indicators < 0:
            raise ValueError("reactive_indicators must be >= 0")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")

@dataclass(frozen=True, slots=True)
class ProbeFinding:
    """Evaluated probe finding."""

    kind: ProbeKind
    result: ProbeResult
    modeling_indicators: int
    reactive_indicators: int
    confidence: float
    rationale: str

@dataclass(frozen=True, slots=True)
class ModelingModeAssessment:
    """Suite-level assessment for one agent."""

    agent_id: str
    verdict: ModelingModeVerdict
    results: Tuple[ProbeFinding, ...]
    rationale: str

    @property
    def confirmed(self) -> bool:
        """True iff verdict is CONFIRMED."""
        return self.verdict is ModelingModeVerdict.CONFIRMED

    @property
    def passed_count(self) -> int:
        """Number of probes with PASS_MODELING outcome."""
        return sum(1 for r in self.results if r.result is ProbeResult.PASS_MODELING)

    @property
    def failed_count(self) -> int:
        """Number of probes with FAIL_REACTIVE outcome."""
        return sum(1 for r in self.results if r.result is ProbeResult.FAIL_REACTIVE)

    def by_kind(self, kind: ProbeKind) -> Optional[ProbeFinding]:
        """Lookup the finding for one probe kind."""
        for r in self.results:
            if r.kind is kind:
                return r
        return None

@dataclass(frozen=True, slots=True)
class ModelingModeProbeConfig:
    """Tunable thresholds for the probe suite."""

    confidence_threshold: float = 0.6
    modeling_min_ratio: float = 1.5
    reactive_min_ratio: float = 1.5
    confirmed_min_passes: int = 4
    reactive_min_failures: int = 3
    partial_min_partials: int = 1

    def __post_init__(self) -> None:
        if not 0.0 < self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be in (0, 1]")
        if self.modeling_min_ratio <= 1.0:
            raise ValueError("modeling_min_ratio must be > 1.0")
        if self.reactive_min_ratio <= 1.0:
            raise ValueError("reactive_min_ratio must be > 1.0")
        if not 1 <= self.confirmed_min_passes <= 5:
            raise ValueError("confirmed_min_passes must be in [1, 5]")
        if not 1 <= self.reactive_min_failures <= 5:
            raise ValueError("reactive_min_failures must be in [1, 5]")
        if self.partial_min_partials < 1:
            raise ValueError("partial_min_partials must be >= 1")

DEFAULT_MODELING_MODE_PROBE_CONFIG: Final[ModelingModeProbeConfig] = ModelingModeProbeConfig()

class ModelingModeProbeSuite:  # pylint: disable=too-few-public-methods
    """Pure-logic modeling mode probe suite aggregator."""

    def __init__(
        self,
        *,
        config: ModelingModeProbeConfig = DEFAULT_MODELING_MODE_PROBE_CONFIG,
    ) -> None:
        self._config = config

    def evaluate_one(self, observation: ProbeObservation) -> ProbeFinding:
        """Evaluate one probe observation into a :class:`ProbeFinding`."""
        cfg = self._config
        confidence = observation.confidence
        modeling = observation.modeling_indicators
        reactive = observation.reactive_indicators
        if confidence < cfg.confidence_threshold:
            result = ProbeResult.INCONCLUSIVE
            rationale = (
                f"confidence={confidence:.3f} < "
                f"{cfg.confidence_threshold}; inconclusive"
            )
        elif modeling == 0 and reactive == 0:
            result = ProbeResult.INCONCLUSIVE
            rationale = "no indicators on either side; inconclusive"
        elif (
            reactive > 0
            and modeling >= cfg.modeling_min_ratio * reactive
        ):
            result = ProbeResult.PASS_MODELING
            rationale = (
                f"5D indicators={modeling} >= "
                f"{cfg.modeling_min_ratio}x 3D indicators={reactive}"
            )
        elif reactive == 0 and modeling > 0:
            result = ProbeResult.PASS_MODELING
            rationale = (
                f"5D indicators={modeling}, no 3D indicators"
            )
        elif (
            modeling > 0
            and reactive >= cfg.reactive_min_ratio * modeling
        ):
            result = ProbeResult.FAIL_REACTIVE
            rationale = (
                f"3D indicators={reactive} >= "
                f"{cfg.reactive_min_ratio}x 5D indicators={modeling}"
            )
        elif modeling == 0 and reactive > 0:
            result = ProbeResult.FAIL_REACTIVE
            rationale = f"3D indicators={reactive}, no 5D indicators"
        else:
            result = ProbeResult.PARTIAL
            rationale = (
                f"5D={modeling} vs 3D={reactive}; partial signal"
            )
        return ProbeFinding(
            kind=observation.kind,
            result=result,
            modeling_indicators=modeling,
            reactive_indicators=reactive,
            confidence=confidence,
            rationale=rationale,
        )

    def assess(
        self,
        agent_id: str,
        observations: Tuple[ProbeObservation, ...],
    ) -> ModelingModeAssessment:
        """Aggregate probe observations into the suite verdict."""
        if not agent_id:
            raise ValueError("agent_id must be non-empty")
        if not observations:
            return ModelingModeAssessment(
                agent_id=agent_id,
                verdict=ModelingModeVerdict.INSUFFICIENT_DATA,
                results=(),
                rationale="no observations",
            )
        self._validate_no_duplicates(observations)
        results = tuple(self.evaluate_one(o) for o in observations)
        verdict = self._aggregate(results)
        rationale = (
            f"agent={agent_id} verdict={verdict.value} "
            f"passes={sum(1 for r in results if r.result is ProbeResult.PASS_MODELING)} "
            f"fails={sum(1 for r in results if r.result is ProbeResult.FAIL_REACTIVE)} "
            f"partials={sum(1 for r in results if r.result is ProbeResult.PARTIAL)} "
            f"inconclusive={sum(1 for r in results if r.result is ProbeResult.INCONCLUSIVE)}"
        )
        return ModelingModeAssessment(
            agent_id=agent_id,
            verdict=verdict,
            results=results,
            rationale=rationale,
        )

    @staticmethod
    def _validate_no_duplicates(
        observations: Tuple[ProbeObservation, ...],
    ) -> None:
        seen: set[ProbeKind] = set()
        for o in observations:
            if o.kind in seen:
                raise ValueError(
                    f"duplicate ProbeObservation for kind={o.kind.value}"
                )
            seen.add(o.kind)

    def _aggregate(
        self, results: Tuple[ProbeFinding, ...],
    ) -> ModelingModeVerdict:
        cfg = self._config
        if all(
            r.result is ProbeResult.INCONCLUSIVE for r in results
        ):
            return ModelingModeVerdict.INSUFFICIENT_DATA
        passes = sum(1 for r in results if r.result is ProbeResult.PASS_MODELING)
        fails = sum(1 for r in results if r.result is ProbeResult.FAIL_REACTIVE)
        if passes >= cfg.confirmed_min_passes:
            return ModelingModeVerdict.CONFIRMED
        if fails >= cfg.reactive_min_failures:
            return ModelingModeVerdict.REACTIVE_DETECTED
        return ModelingModeVerdict.PARTIAL

__all__ = [
    "DEFAULT_MODELING_MODE_PROBE_CONFIG",
    "ModelingModeProbeSuite",
    "ModelingModeAssessment",
    "ModelingModeProbeConfig",
    "ModelingModeVerdict",
    "ProbeFinding",
    "ProbeKind",
    "ProbeObservation",
    "ProbeResult",
]
