"""Heuristic ReasoningModeClassifier.

A concrete pure-logic implementation of the
:class:`app.services.common.substrate.harness.ReasoningModeClassifier`
Protocol shipped in Phase 8. The classifier maps a decision context
(text plus optional structured signals) onto the library's
3D-vs-5D reasoning-mode taxonomy from

* **REACTIVE** — present-tense reactive operation; reactive mode
  default. The agent is reacting to immediate sensory / emotional
  stimuli with no abstract projection past the present cycle.
* **MODELING** — substrate-aware projective operation; field-mode.
  The agent is forecasting future substrate-state trajectories,
  reasoning about iteration over time, considering multi-scale
  alignment.
* **TRANSITION** — mixed evidence. The agent is partway between the
  default 3D and sustained 5D; both modes are visible.
* **UNKNOWN** — no signal in either category. Honest uncertainty
  the harness should not intercept on noisy classification.

The string labels match the Protocol's documented return values
exactly (``reactive_3d`` / ``modeling_5d`` / ``transition`` /
``unknown``).

Pure logic
==========

* No DAO, no LLM, no network. Marker vocabulary is regex over the
  trace text; structured signals (when supplied via the richer
  :meth:`classify_full` method) are simple float thresholds.
* Honest uncertainty. Below confidence threshold the classifier
  returns UNKNOWN rather than guessing.
* Composition. :meth:`classify_full` returns a rich
  :class:`ReasoningModeClassification` with marker hits, scores, and
  rationale — suitable for the :class:`SubstrateTraceLedger`
  (Phase 16) and for the substrate-aware harness's intercept
  decisions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping, Optional, Tuple

class ReasoningMode(str, Enum):
    """The four reasoning-mode labels (Protocol-compatible str values)."""

    REACTIVE = "reactive"
    MODELING = "modeling"
    TRANSITION = "transition"
    UNKNOWN = "unknown"

@dataclass(frozen=True, slots=True)
class ReasoningModeClassification:  # pylint: disable=too-many-instance-attributes
    """Rich classification result with marker hits and scores."""

    mode: ReasoningMode
    confidence: float
    reactive_score: float
    projective_score: float
    reactive_hits: Tuple[str, ...]
    projective_hits: Tuple[str, ...]
    signals_consulted: bool
    reasoning: str

# -----------------------------
# Default markers (library heuristics)
# -----------------------------

_REACTIVE_3D_MARKERS: Final[Tuple[str, ...]] = (
    "right now",
    "immediately",
    "this second",
    "can't wait",
    "i need it now",
    "without thinking",
    "react to",
    "they did x so",
    "i feel like",
    "rush of",
    "craving",
    "must have now",
    "the urge",
    "no time to think",
    "before they can stop me",
    "i want it now",
)

_MODELING_5D_MARKERS: Final[Tuple[str, ...]] = (
    "in the long run",
    "long cycle",
    "long-term",
    "long term",
    "downstream effect",
    "downstream consequence",
    "will lead to",
    "if we do this, then",
    "if i do this, then",
    "multi-generational",
    "across iterations",
    "compounding over time",
    "substrate-aligned",
    "substrate alignment",
    "accumulated commitment",
    "the trajectory",
    "the path we're on",
    "persist through",
    "the long arc",
    "iterate forward",
    "the next iteration",
    "system-wide effect",
    "multi-scale",
    "across the system",
)

DEFAULT_REACTIVE_MARKERS: Final[Tuple[str, ...]] = _REACTIVE_3D_MARKERS
DEFAULT_PROJECTIVE_MARKERS: Final[Tuple[str, ...]] = _MODELING_5D_MARKERS

DEFAULT_SATURATION_COUNT: Final[int] = 3
DEFAULT_MIN_CONFIDENCE: Final[float] = 0.3
DEFAULT_DOMINANCE_RATIO: Final[float] = 1.5

# Structured-signal feature names the classifier understands when
# ``signals`` are supplied to :meth:`classify_full`. Operators may
# pass additional unknown keys; they are ignored.
SIGNAL_FORECAST_HORIZON_SECONDS: Final[str] = "forecast_horizon_seconds"
SIGNAL_FORECAST_HORIZON_PROJECTIVE_BELOW: Final[float] = 86_400.0
SIGNAL_CONSEQUENCE_EXPOSURE: Final[str] = "consequence_exposure_present"
SIGNAL_REACTIVE_TRIGGER: Final[str] = "reactive_trigger_present"
SIGNAL_ABSTRACT_REASONING_DEPTH: Final[str] = "abstract_reasoning_depth"

class HeuristicReasoningModeClassifier:
    """Pure-logic ReasoningModeClassifier (Protocol satisfier).

    Matches the harness's :class:`ReasoningModeClassifier` Protocol
    :meth:`classify` returns ``(label, confidence)`` for text alone.
    :meth:`classify_full` is a richer entry point for callers who
    have structured signals and want the marker-hit breakdown.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        reactive_markers: Tuple[str, ...] = DEFAULT_REACTIVE_MARKERS,
        projective_markers: Tuple[str, ...] = DEFAULT_PROJECTIVE_MARKERS,
        saturation_count: int = DEFAULT_SATURATION_COUNT,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        dominance_ratio: float = DEFAULT_DOMINANCE_RATIO,
    ) -> None:
        if not reactive_markers and not projective_markers:
            raise ValueError(
                "at least one of reactive_markers / projective_markers "
                "must be non-empty"
            )
        if saturation_count < 1:
            raise ValueError("saturation_count must be >= 1")
        if not 0.0 < min_confidence <= 1.0:
            raise ValueError("min_confidence must be in (0, 1]")
        if dominance_ratio < 1.0:
            raise ValueError("dominance_ratio must be >= 1.0")
        self._reactive_markers = reactive_markers
        self._projective_markers = projective_markers
        self._saturation = float(saturation_count)
        self._min_confidence = min_confidence
        self._dominance_ratio = dominance_ratio
        self._reactive_patterns = tuple(
            re.compile(re.escape(m), re.IGNORECASE)
            for m in reactive_markers
        )
        self._projective_patterns = tuple(
            re.compile(re.escape(m), re.IGNORECASE)
            for m in projective_markers
        )

    def classify(self, *, output_text: str) -> Tuple[str, float]:
        """Protocol-compliant entry point: ``(mode_label, confidence)``."""
        result = self.classify_full(output_text=output_text)
        return result.mode.value, result.confidence

    def classify_full(
        self,
        *,
        output_text: str,
        signals: Optional[Mapping[str, float]] = None,
    ) -> ReasoningModeClassification:
        """Return the rich classification including marker hits."""
        reactive_hits = self._match_hits(
            output_text, self._reactive_markers, self._reactive_patterns,
        )
        projective_hits = self._match_hits(
            output_text, self._projective_markers, self._projective_patterns,
        )

        reactive_score = min(1.0, len(reactive_hits) / self._saturation)
        projective_score = min(1.0, len(projective_hits) / self._saturation)

        signals_used = False
        if signals:
            reactive_bump, projective_bump, signals_used = (
                self._score_signals(signals)
            )
            reactive_score = min(1.0, reactive_score + reactive_bump)
            projective_score = min(1.0, projective_score + projective_bump)

        mode, confidence, reasoning = self._classify(
            reactive_score, projective_score,
            reactive_hits, projective_hits, signals_used,
        )

        return ReasoningModeClassification(
            mode=mode,
            confidence=confidence,
            reactive_score=reactive_score,
            projective_score=projective_score,
            reactive_hits=tuple(reactive_hits),
            projective_hits=tuple(projective_hits),
            signals_consulted=signals_used,
            reasoning=reasoning,
        )

    @staticmethod
    def _match_hits(
        text: str,
        markers: Tuple[str, ...],
        patterns: Tuple[re.Pattern[str], ...],
    ) -> list[str]:
        if not text:
            return []
        return [m for m, p in zip(markers, patterns) if p.search(text)]

    @staticmethod
    def _score_signals(
        signals: Mapping[str, float],
    ) -> Tuple[float, float, bool]:
        """Translate structured signals into score bumps for each side."""
        reactive_bump = 0.0
        projective_bump = 0.0
        consulted = False

        if SIGNAL_FORECAST_HORIZON_SECONDS in signals:
            consulted = True
            horizon = float(signals[SIGNAL_FORECAST_HORIZON_SECONDS])
            if horizon >= SIGNAL_FORECAST_HORIZON_PROJECTIVE_BELOW:
                projective_bump += 0.4
            elif horizon < 60.0:
                reactive_bump += 0.4
        if SIGNAL_CONSEQUENCE_EXPOSURE in signals:
            consulted = True
            if signals[SIGNAL_CONSEQUENCE_EXPOSURE] >= 1.0:
                projective_bump += 0.3
        if SIGNAL_REACTIVE_TRIGGER in signals:
            consulted = True
            if signals[SIGNAL_REACTIVE_TRIGGER] >= 1.0:
                reactive_bump += 0.4
        if SIGNAL_ABSTRACT_REASONING_DEPTH in signals:
            consulted = True
            depth = float(signals[SIGNAL_ABSTRACT_REASONING_DEPTH])
            if depth >= 3.0:
                projective_bump += 0.3
            elif depth <= 0.0:
                reactive_bump += 0.2
        return reactive_bump, projective_bump, consulted

    def _classify(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        reactive_score: float,
        projective_score: float,
        reactive_hits: list[str],
        projective_hits: list[str],
        signals_used: bool,
    ) -> Tuple[ReasoningMode, float, str]:
        max_score = max(reactive_score, projective_score)
        # Honest uncertainty: nothing fired above the floor.
        if max_score < self._min_confidence:
            return (
                ReasoningMode.UNKNOWN,
                max_score,
                self._reasoning_text(
                    "no marker or signal above min_confidence",
                    reactive_score, projective_score,
                    reactive_hits, projective_hits, signals_used,
                ),
            )
        # Dominance check — one side must be ratio× the other to win.
        if reactive_score >= self._dominance_ratio * max(
            projective_score, 1e-9,
        ):
            return (
                ReasoningMode.REACTIVE,
                reactive_score,
                self._reasoning_text(
                    "reactive markers dominate by ratio",
                    reactive_score, projective_score,
                    reactive_hits, projective_hits, signals_used,
                ),
            )
        if projective_score >= self._dominance_ratio * max(
            reactive_score, 1e-9,
        ):
            return (
                ReasoningMode.MODELING,
                projective_score,
                self._reasoning_text(
                    "projective markers dominate by ratio",
                    reactive_score, projective_score,
                    reactive_hits, projective_hits, signals_used,
                ),
            )
        # Both above threshold but neither dominates → transition.
        return (
            ReasoningMode.TRANSITION,
            max_score,
            self._reasoning_text(
                "mixed evidence; neither mode dominates",
                reactive_score, projective_score,
                reactive_hits, projective_hits, signals_used,
            ),
        )

    @staticmethod
    def _reasoning_text(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        verdict_phrase: str,
        reactive_score: float,
        projective_score: float,
        reactive_hits: list[str],
        projective_hits: list[str],
        signals_used: bool,
    ) -> str:
        suffix = " (signals consulted)" if signals_used else ""
        return (
            f"{verdict_phrase}: reactive={reactive_score:.2f}"
            f" ({len(reactive_hits)} hits)"
            f" projective={projective_score:.2f}"
            f" ({len(projective_hits)} hits){suffix}"
        )

__all__ = [
    "ReasoningMode",
    "ReasoningModeClassification",
    "DEFAULT_DOMINANCE_RATIO",
    "DEFAULT_MIN_CONFIDENCE",
    "DEFAULT_PROJECTIVE_MARKERS",
    "DEFAULT_REACTIVE_MARKERS",
    "DEFAULT_SATURATION_COUNT",
    "HeuristicReasoningModeClassifier",
    "SIGNAL_ABSTRACT_REASONING_DEPTH",
    "SIGNAL_CONSEQUENCE_EXPOSURE",
    "SIGNAL_FORECAST_HORIZON_SECONDS",
    "SIGNAL_REACTIVE_TRIGGER",
]
