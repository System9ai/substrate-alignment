"""Recursive-transmission pattern detector: Companion #2

Pure-logic detector that flags *recursive transmission patterns* in
substrate-state-trajectories. The
that propagates recursively through a hierarchy (cell → node → org)
is the most damaging failure mode; substrate condition #3
(multi-scale alignment) requires that drift be contained at the level
it appears.

A recursive-transmission pattern is identified when the same drift
signal appears at successive scale levels within a bounded time
window, with each appearance triggered by the previous one's
substrate-state observation.

Pure logic
==========

* No DAO, no LLM, no network. Caller pushes
  ``TransmissionSample`` entries; detector returns a verdict.
* Honest uncertainty: below ``min_chain_length`` returns
  ``INSUFFICIENT_DATA``.
* Frozen dataclasses for outputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from substrate.encapsulating_context.pull_signal import (
    ContextScale,
)

class TransmissionVerdict(str, Enum):
    """Detector verdict."""

    NO_PATTERN = "no_pattern"
    RECURSIVE_TRANSMISSION = "recursive_transmission"
    INSUFFICIENT_DATA = "insufficient_data"

_SCALE_ORDER: Final[dict[ContextScale, int]] = {
    ContextScale.NODE: 0,
    ContextScale.ORG: 1,
    ContextScale.CLUSTER: 2,
}

@dataclass(frozen=True, slots=True)
class TransmissionSample:
    """One drift-signal sample at a scale."""

    signal_kind: str
    scale: ContextScale
    observed_at_seconds: float
    triggered_by_prior: bool

    def __post_init__(self) -> None:
        if not self.signal_kind:
            raise ValueError("signal_kind must be non-empty")
        if self.observed_at_seconds < 0:
            raise ValueError(
                "observed_at_seconds must be >= 0"
            )

@dataclass(frozen=True, slots=True)
class TransmissionDetectorConfig:
    """Operator-tunable detector thresholds."""

    min_chain_length: int = 2
    max_propagation_window_seconds: float = 3600.0

    def __post_init__(self) -> None:
        if self.min_chain_length < 2:
            raise ValueError("min_chain_length must be >= 2")
        if self.max_propagation_window_seconds <= 0:
            raise ValueError(
                "max_propagation_window_seconds must be > 0"
            )

DEFAULT_TRANSMISSION_DETECTOR_CONFIG: Final[
    TransmissionDetectorConfig
] = TransmissionDetectorConfig()

@dataclass(frozen=True, slots=True)
class TransmissionDetectionOutput:  # pylint: disable=too-many-instance-attributes
    """Detector output."""

    signal_kind: str
    verdict: TransmissionVerdict
    chain_length: int
    span_seconds: float
    scale_path: tuple[ContextScale, ...]
    rationale: str

    @property
    def recursive(self) -> bool:
        """True iff RECURSIVE_TRANSMISSION."""
        return (
            self.verdict is TransmissionVerdict.RECURSIVE_TRANSMISSION
        )

class RecursiveTransmissionPatternDetector:  # pylint: disable=too-few-public-methods
    """Pure-logic recursive-transmission detector (Companion #2)."""

    def __init__(
        self,
        *,
        config: TransmissionDetectorConfig = (
            DEFAULT_TRANSMISSION_DETECTOR_CONFIG
        ),
    ) -> None:
        self._config = config

    def detect(
        self,
        signal_kind: str,
        samples: tuple[TransmissionSample, ...],
    ) -> TransmissionDetectionOutput:
        """Detect recursive transmission for the named signal."""
        cfg = self._config
        if not signal_kind:
            raise ValueError("signal_kind must be non-empty")
        chain = [
            s for s in samples
            if s.signal_kind == signal_kind
        ]
        chain.sort(key=lambda s: s.observed_at_seconds)
        if len(chain) < cfg.min_chain_length:
            return TransmissionDetectionOutput(
                signal_kind=signal_kind,
                verdict=TransmissionVerdict.INSUFFICIENT_DATA,
                chain_length=len(chain),
                span_seconds=0.0,
                scale_path=tuple(s.scale for s in chain),
                rationale=(
                    f"chain_length={len(chain)} below min "
                    f"{cfg.min_chain_length}"
                ),
            )
        span = (
            chain[-1].observed_at_seconds
            - chain[0].observed_at_seconds
        )
        all_triggered = all(
            s.triggered_by_prior for s in chain[1:]
        )
        ascending = self._is_ascending(chain)
        if (
            span <= cfg.max_propagation_window_seconds
            and all_triggered
            and ascending
        ):
            verdict = TransmissionVerdict.RECURSIVE_TRANSMISSION
            rationale = (
                f"chain_length={len(chain)} ascending across scales "
                f"in {span:.1f}s window"
            )
        else:
            verdict = TransmissionVerdict.NO_PATTERN
            reasons: list[str] = []
            if span > cfg.max_propagation_window_seconds:
                reasons.append(
                    f"span={span:.1f}s exceeds window "
                    f"{cfg.max_propagation_window_seconds:.1f}s"
                )
            if not all_triggered:
                reasons.append("not all samples triggered_by_prior")
            if not ascending:
                reasons.append("scale path not ascending")
            rationale = "; ".join(reasons) or "no pattern"
        return TransmissionDetectionOutput(
            signal_kind=signal_kind,
            verdict=verdict,
            chain_length=len(chain),
            span_seconds=span,
            scale_path=tuple(s.scale for s in chain),
            rationale=rationale,
        )

    @staticmethod
    def _is_ascending(chain: list[TransmissionSample]) -> bool:
        for prev, curr in zip(chain, chain[1:]):
            if _SCALE_ORDER[curr.scale] <= _SCALE_ORDER[prev.scale]:
                return False
        return True

__all__ = [
    "DEFAULT_TRANSMISSION_DETECTOR_CONFIG",
    "RecursiveTransmissionPatternDetector",
    "TransmissionDetectionOutput",
    "TransmissionDetectorConfig",
    "TransmissionSample",
    "TransmissionVerdict",
]
