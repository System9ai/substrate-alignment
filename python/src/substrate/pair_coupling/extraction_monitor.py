"""Pair-coupled extraction monitor (Companion #2)

Pure-logic long-window monitor that integrates per-cycle audit
verdicts (:class:`PairCouplingAuditor` outputs) into a
sustained-extraction signal. The
extractive audit verdict is noise; a sustained pattern of extractive
verdicts over many cycles is *slow-drift extraction* that must
trigger architectural review.

Pure logic
==========

* No DAO, no LLM, no network. Caller pushes verdict observations.
* Honest uncertainty: below ``min_observations`` returns
  ``INSUFFICIENT_DATA``.
* Bounded-ring window of verdicts.
* Frozen dataclasses for outputs.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Final

from substrate.pair_coupling.alignment_audit import (
    AuditVerdict,
)

class ExtractionVerdict(str, Enum):
    """Long-window pair-coupling extraction verdict."""

    NO_EXTRACTION = "no_extraction"
    EPISODIC = "episodic"
    SUSTAINED = "sustained"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class VerdictObservation:
    """One audit verdict observation in the window."""

    coupling_id: str
    cycle_index: int
    audit_verdict: AuditVerdict

    def __post_init__(self) -> None:
        if not self.coupling_id:
            raise ValueError("coupling_id must be non-empty")
        if self.cycle_index < 0:
            raise ValueError("cycle_index must be >= 0")

@dataclass(frozen=True, slots=True)
class ExtractionMonitorConfig:
    """Operator-tunable monitor thresholds."""

    window_size: int = 50
    min_observations: int = 10
    episodic_extraction_rate: float = 0.1
    sustained_extraction_rate: float = 0.3
    """Fraction of window classified extractive triggering SUSTAINED."""

    def __post_init__(self) -> None:
        if self.window_size < 2:
            raise ValueError("window_size must be >= 2")
        if self.min_observations < 2:
            raise ValueError("min_observations must be >= 2")
        if self.min_observations > self.window_size:
            raise ValueError(
                "min_observations cannot exceed window_size"
            )
        if not 0.0 < self.episodic_extraction_rate <= 1.0:
            raise ValueError(
                "episodic_extraction_rate must be in (0, 1]"
            )
        if not (
            self.episodic_extraction_rate
            < self.sustained_extraction_rate
            <= 1.0
        ):
            raise ValueError(
                "must satisfy 0 < episodic < sustained <= 1"
            )

DEFAULT_EXTRACTION_MONITOR_CONFIG: Final[ExtractionMonitorConfig] = (
    ExtractionMonitorConfig()
)

@dataclass(frozen=True, slots=True)
class ExtractionMonitorOutput:  # pylint: disable=too-many-instance-attributes
    """Monitor output."""

    coupling_id: str
    verdict: ExtractionVerdict
    observation_count: int
    extraction_rate: float
    aligned_rate: float
    degrading_rate: float
    rationale: str

    @property
    def sustained(self) -> bool:
        """True iff verdict is SUSTAINED."""
        return self.verdict is ExtractionVerdict.SUSTAINED

class PairCoupledExtractionMonitor:
    """Pure-logic pair-coupled extraction monitor (Companion #2)."""

    def __init__(
        self,
        *,
        coupling_id: str,
        config: ExtractionMonitorConfig = (
            DEFAULT_EXTRACTION_MONITOR_CONFIG
        ),
    ) -> None:
        if not coupling_id:
            raise ValueError("coupling_id must be non-empty")
        self._coupling_id = coupling_id
        self._config = config
        self._window: Deque[VerdictObservation] = deque(
            maxlen=config.window_size,
        )

    def observe(self, observation: VerdictObservation) -> None:
        """Record an audit verdict observation."""
        if observation.coupling_id != self._coupling_id:
            raise ValueError(
                f"observation.coupling_id="
                f"{observation.coupling_id} does not match monitor "
                f"coupling_id={self._coupling_id}"
            )
        self._window.append(observation)

    def verdict(self) -> ExtractionMonitorOutput:
        """Return the current verdict."""
        cfg = self._config
        n = len(self._window)
        if n < cfg.min_observations:
            return ExtractionMonitorOutput(
                coupling_id=self._coupling_id,
                verdict=ExtractionVerdict.INSUFFICIENT_DATA,
                observation_count=n,
                extraction_rate=0.0,
                aligned_rate=0.0,
                degrading_rate=0.0,
                rationale=(
                    f"observations={n} below min "
                    f"{cfg.min_observations}"
                ),
            )
        extractive = sum(
            1 for o in self._window
            if o.audit_verdict in (
                AuditVerdict.EXTRACTIVE_TOWARD_A,
                AuditVerdict.EXTRACTIVE_TOWARD_B,
            )
        )
        aligned = sum(
            1 for o in self._window
            if o.audit_verdict is AuditVerdict.SUBSTRATE_ALIGNED
        )
        degrading = sum(
            1 for o in self._window
            if o.audit_verdict is AuditVerdict.DEGRADING_BOTH
        )
        ext_rate = extractive / n
        aligned_rate = aligned / n
        degrading_rate = degrading / n
        if ext_rate >= cfg.sustained_extraction_rate:
            verdict = ExtractionVerdict.SUSTAINED
        elif ext_rate >= cfg.episodic_extraction_rate:
            verdict = ExtractionVerdict.EPISODIC
        else:
            verdict = ExtractionVerdict.NO_EXTRACTION
        return ExtractionMonitorOutput(
            coupling_id=self._coupling_id,
            verdict=verdict,
            observation_count=n,
            extraction_rate=ext_rate,
            aligned_rate=aligned_rate,
            degrading_rate=degrading_rate,
            rationale=(
                f"extraction_rate={ext_rate:.3f}, "
                f"aligned_rate={aligned_rate:.3f}, "
                f"degrading_rate={degrading_rate:.3f}"
            ),
        )

__all__ = [
    "DEFAULT_EXTRACTION_MONITOR_CONFIG",
    "ExtractionMonitorConfig",
    "ExtractionMonitorOutput",
    "ExtractionVerdict",
    "PairCoupledExtractionMonitor",
    "VerdictObservation",
]
