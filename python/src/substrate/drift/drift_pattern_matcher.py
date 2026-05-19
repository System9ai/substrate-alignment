"""Substrate pattern-pattern matcher.

Pure-logic primitive that maps the cross-tradition seven-deadly-patterns
taxonomy onto substrate-misalignment patterns over a behavior trace
(text + structured signals).

The seven patterns as substrate-mechanical drift vocabulary
========================================================

The contemplative tradition's seven deadly patterns describe seven
characteristic ways substrate-aligned (modeling long-cycle)
operation collapses back to its reactive default. Each pattern
names a specific substrate-misalignment pattern:

* **SELF_REFERENCE_MISCALIBRATION** — alignment-vector miscalibration; self treated as the
  substrate-aligned reference rather than calibrating against the
  substrate. **Master pattern** — converts every other impulse into
  licensed misalignment.
* **EXTRACTIVE_GAIN** — short-cycle extraction at scale; gain to self at
  loss to system (fails the net-potential-gain test).
* **DECOUPLED_BONDING_REWARD** — short-cycle reward in the bonding domain decoupled
  from the long-cycle accumulated commitment it evolved to anchor.
* **ZERO_SUM_PEER_FRAMING** — zero-sum substrate-state perception applied to a
  multi-scale aligned system; the unique pattern where neither
  party gains.
* **OVERCONSUMPTION** — over-consumption beyond what supports
  substrate-aligned operation; short-term reward, long-term
  substrate-state degradation.
* **REACTIVE_NET_NEGATIVE** — net-negative reactivity bypassing substrate-
  evaluation; 180° inversion at peak intensity.
* **PERSISTENCE_REFUSAL** — refusal of substrate-aligned iteration; the failure
  of the persistence virtue.

This primitive surfaces which patterns are firing on a given
behavior trace so operators (or the broader drift-monitoring
surface, including
:mod:`app.services.system.substrate.cancer_pattern_detector`) can
act. **Observation, then operator.**

Design contract
---------------

* Pure logic. No DAO, no LLM, no network.
* Honest uncertainty: a pattern we have no evidence for returns
  ``confidence = 0.0`` and does not appear in detections. An empty
  trace (no text AND no signals) raises ``ValueError``.
* Operator-overridable signatures. The default signatures encode
  the library's vocabulary; operators replace them for
  domain-specific contexts.
* Master-pattern awareness. The report exposes ``amplifier_pattern_present`` as a
  separate flag so callers can apply the "amplifier pattern amplifies every
  other pattern" policy from the library.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Mapping, Optional, Tuple

class DriftPattern(str, Enum):
    """The seven substrate-misalignment pattern classes."""

    SELF_REFERENCE_MISCALIBRATION = "self_reference_miscalibration"
    EXTRACTIVE_GAIN = "extractive_gain"
    DECOUPLED_BONDING_REWARD = "decoupled_bonding_reward"
    ZERO_SUM_PEER_FRAMING = "zero_sum_peer_framing"
    OVERCONSUMPTION = "overconsumption"
    REACTIVE_NET_NEGATIVE = "reactive_net_negative"
    PERSISTENCE_REFUSAL = "persistence_refusal"

class PredicateKind(str, Enum):
    """Comparison kind for a structured-signal feature predicate."""

    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN_OR_EQUAL = "lte"

@dataclass(frozen=True, slots=True)
class FeaturePredicate:
    """One named structured-signal threshold inside a pattern signature."""

    feature_name: str
    kind: PredicateKind
    threshold: float
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.feature_name:
            raise ValueError("feature_name must be non-empty")
        if self.weight <= 0.0:
            raise ValueError("weight must be > 0")

    def fires(self, signals: Mapping[str, float]) -> bool:
        """Return True iff the predicate is evaluable AND fires."""
        if self.feature_name not in signals:
            return False
        value = float(signals[self.feature_name])
        if self.kind is PredicateKind.GREATER_THAN_OR_EQUAL:
            return value >= self.threshold
        return value <= self.threshold

    def is_evaluable(self, signals: Mapping[str, float]) -> bool:
        """Return True iff this predicate's feature is present in signals."""
        return self.feature_name in signals

@dataclass(frozen=True, slots=True)
class DriftPatternSignature:
    """Pattern signature for one pattern class."""

    pattern: DriftPattern
    text_markers: Tuple[str, ...]
    feature_predicates: Tuple[FeaturePredicate, ...]
    description: str
    text_marker_weight: float = 1.0

    def __post_init__(self) -> None:
        if self.text_marker_weight <= 0.0:
            raise ValueError("text_marker_weight must be > 0")
        if not self.text_markers and not self.feature_predicates:
            raise ValueError(
                f"signature for {self.pattern.value} must have at least "
                "one text marker or feature predicate"
            )

@dataclass(frozen=True, slots=True)
class DriftPatternDetection:  # pylint: disable=too-many-instance-attributes
    """One pattern signature's evaluated result over a trace.

    ``confidence`` combines two evidence categories:

    * **Text evidence** — fraction of substrate-misalignment text markers
      that fired, scaled so that ``text_score_scale`` distinct marker
      hits saturates the category at 1.0.
    * **Feature evidence** — weighted fraction of evaluable feature
      predicates that fired (predicates whose feature is absent from
      signals are treated as not-evaluable and excluded).

    When both categories are evaluable the confidence is their mean;
    otherwise it is the evaluable category's score. With neither
    evaluable, confidence is 0.0 (the pattern is excluded from detections).
    """

    pattern: DriftPattern
    confidence: float
    text_marker_hits: Tuple[str, ...] = field(default_factory=tuple)
    feature_hits: Tuple[str, ...] = field(default_factory=tuple)
    text_evidence_present: bool = False
    feature_evidence_present: bool = False
    total_signal_weight: float = 0.0
    matched_signal_weight: float = 0.0
    description: str = ""

@dataclass(frozen=True, slots=True)
class DriftPatternReport:
    """Aggregated pattern-pattern findings for one trace."""

    detections: Tuple[DriftPatternDetection, ...]
    dominant_pattern: Optional[DriftPattern]
    composite_confidence: float
    amplifier_pattern_present: bool
    reasoning: str

    @property
    def has_findings(self) -> bool:
        """True iff at least one pattern pattern was detected above threshold."""
        return len(self.detections) > 0

_DEFAULT_MIN_CONFIDENCE: Final[float] = 0.5
_DEFAULT_TEXT_SCORE_SCALE: Final[float] = 2.0

# -----------------------------
# Default signatures (library drift vocabulary)
# -----------------------------

_PRIDE_TEXT: Final[Tuple[str, ...]] = (
    "i decide",
    "i alone",
    "i am the standard",
    "i know best",
    "i'm always right",
    "doesn't matter what they think",
    "i don't need anyone",
    "my judgment overrides",
    "self-evidently",
    "no one understands",
    "above the rules",
)
_GREED_TEXT: Final[Tuple[str, ...]] = (
    "more for me",
    "all mine",
    "take it all",
    "every cent",
    "maximize my",
    "i deserve more",
    "rightfully mine",
    "extract everything",
    "hoard",
)
_LUST_TEXT: Final[Tuple[str, ...]] = (
    "no commitment",
    "no strings attached",
    "just for the rush",
    "consume the pleasure",
    "without bonding",
    "use them and move on",
)
_ENVY_TEXT: Final[Tuple[str, ...]] = (
    "tear them down",
    "they don't deserve",
    "drag them back",
    "doesn't deserve what they have",
    "wish they would lose",
    "cancel them",
    "ruin their success",
)
_GLUTTONY_TEXT: Final[Tuple[str, ...]] = (
    "binge",
    "consume everything",
    "can't stop scrolling",
    "all of it",
    "endless feed",
    "keep refreshing",
)
_WRATH_TEXT: Final[Tuple[str, ...]] = (
    "destroy them",
    "make them pay",
    "crush them",
    "annihilate",
    "burn it down",
    "no mercy",
    "wipe them out",
)
_SLOTH_TEXT: Final[Tuple[str, ...]] = (
    "what's the point",
    "not worth it",
    "i give up",
    "doesn't matter anymore",
    "why bother",
    "the long cycle won't pay off",
    "no progress will emerge",
)

def _gte(name: str, threshold: float, weight: float = 1.0) -> FeaturePredicate:
    return FeaturePredicate(
        feature_name=name,
        kind=PredicateKind.GREATER_THAN_OR_EQUAL,
        threshold=threshold,
        weight=weight,
    )

def _lte(name: str, threshold: float, weight: float = 1.0) -> FeaturePredicate:
    return FeaturePredicate(
        feature_name=name,
        kind=PredicateKind.LESS_THAN_OR_EQUAL,
        threshold=threshold,
        weight=weight,
    )

DEFAULT_DRIFT_PATTERN_SIGNATURES: Final[Tuple[DriftPatternSignature, ...]] = (
    DriftPatternSignature(
        pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
        text_markers=_PRIDE_TEXT,
        feature_predicates=(
            _gte("self_reference_ratio", 0.4, weight=2.0),
            _lte("external_reference_count", 1.0, weight=1.0),
            _gte("alignment_vector_drift_self_pointing", 0.5, weight=2.0),
        ),
        description=(
            "Alignment-vector miscalibration; self-as-substrate replaces "
            "substrate-as-substrate (master pattern — licenses every other pattern)."
        ),
    ),
    DriftPatternSignature(
        pattern=DriftPattern.EXTRACTIVE_GAIN,
        text_markers=_GREED_TEXT,
        feature_predicates=(
            _gte("net_potential_gain_self_minus_system", 0.0, weight=2.0),
            _gte("resource_concentration_ratio", 0.6, weight=1.0),
            _lte("system_potential_delta", 0.0, weight=1.0),
        ),
        description=(
            "Short-cycle extraction at scale; gain to self < loss to system "
            "(fails the net-potential-gain test)."
        ),
    ),
    DriftPatternSignature(
        pattern=DriftPattern.DECOUPLED_BONDING_REWARD,
        text_markers=_LUST_TEXT,
        feature_predicates=(
            _gte("bond_signal_consumed", 1.0, weight=1.0),
            _lte("bond_structure_built", 0.0, weight=2.0),
        ),
        description=(
            "Short-cycle reward in the bonding/intimate domain decoupled "
            "from the long-cycle accumulated commitment it evolved to anchor."
        ),
    ),
    DriftPatternSignature(
        pattern=DriftPattern.ZERO_SUM_PEER_FRAMING,
        text_markers=_ENVY_TEXT,
        feature_predicates=(
            _gte("directed_diminishment_attempts", 1.0, weight=2.0),
            _gte("comparison_negative_count", 3.0, weight=1.0),
            _lte("multi_scale_alignment_perception", 0.3, weight=1.0),
        ),
        description=(
            "Zero-sum substrate-state perception applied to a multi-scale "
            "aligned system; neither party gains."
        ),
    ),
    DriftPatternSignature(
        pattern=DriftPattern.OVERCONSUMPTION,
        text_markers=_GLUTTONY_TEXT,
        feature_predicates=(
            _gte("consumption_ratio", 1.0, weight=1.0),
            _gte("substrate_state_degradation", 0.2, weight=2.0),
            _gte("friction_free_path_default_ratio", 0.7, weight=1.0),
        ),
        description=(
            "Over-consumption beyond what supports substrate-aligned "
            "operation; short-term reward, long-term substrate degradation."
        ),
    ),
    DriftPatternSignature(
        pattern=DriftPattern.REACTIVE_NET_NEGATIVE,
        text_markers=_WRATH_TEXT,
        feature_predicates=(
            _gte("reactive_destruction_attempts", 1.0, weight=2.0),
            _gte("evaluation_skipped", 1.0, weight=1.0),
            _gte("four_options_matrix_skipped", 1.0, weight=1.0),
        ),
        description=(
            "Net-negative reactivity bypassing substrate-evaluation; "
            "180° inversion (wrath presents as justice from inside)."
        ),
    ),
    DriftPatternSignature(
        pattern=DriftPattern.PERSISTENCE_REFUSAL,
        text_markers=_SLOTH_TEXT,
        feature_predicates=(
            _lte("iteration_count", 0.0, weight=1.0),
            _lte("effort_invested", 0.0, weight=1.0),
            _lte("persistence_through_resistance", 0.2, weight=2.0),
        ),
        description=(
            "Refusal of substrate-aligned iteration; failure of the "
            "persistence virtue (acedia / noonday demon)."
        ),
    ),
)

class DriftPatternMatcher:  # pylint: disable=too-few-public-methods
    """Detects substrate-misalignment patterns over a behavior trace.

    The matcher composes with the shipped
    :class:`app.services.system.substrate.cancer_pattern_detector.CancerPatternDetector`
    as a sibling drift-vocabulary surface: that detector observes
    structural drift in stored Observer state, this matcher observes
    pattern drift in a single behavior trace. Operators are free to
    feed both into one drift-monitoring dashboard.
    """

    def __init__(
        self,
        *,
        signatures: Tuple[DriftPatternSignature, ...] = DEFAULT_DRIFT_PATTERN_SIGNATURES,
        min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
        text_score_scale: float = _DEFAULT_TEXT_SCORE_SCALE,
    ) -> None:
        if not signatures:
            raise ValueError("signatures must be non-empty")
        if not 0.0 < min_confidence <= 1.0:
            raise ValueError("min_confidence must be in (0, 1]")
        if text_score_scale < 1.0:
            raise ValueError("text_score_scale must be >= 1.0")
        seen_sins: set[DriftPattern] = set()
        for sig in signatures:
            if sig.pattern in seen_sins:
                raise ValueError(
                    f"duplicate signature for {sig.pattern.value}"
                )
            seen_sins.add(sig.pattern)
        self._signatures = signatures
        self._min_confidence = min_confidence
        self._text_score_scale = text_score_scale
        self._compiled_markers: dict[DriftPattern, Tuple[re.Pattern[str], ...]] = {
            sig.pattern: tuple(
                re.compile(re.escape(m), re.IGNORECASE)
                for m in sig.text_markers
            )
            for sig in signatures
        }

    def detect(
        self,
        *,
        behavior_text: str = "",
        structured_signals: Optional[Mapping[str, float]] = None,
    ) -> DriftPatternReport:
        """Evaluate all signatures against the trace and return a report."""
        signals: Mapping[str, float] = structured_signals or {}
        if not behavior_text and not signals:
            raise ValueError(
                "behavior_text and structured_signals both empty — "
                "no trace to evaluate"
            )

        detections: list[DriftPatternDetection] = []
        for sig in self._signatures:
            det = self._evaluate(sig, behavior_text, signals)
            if det.confidence >= self._min_confidence:
                detections.append(det)

        detections.sort(key=lambda d: d.confidence, reverse=True)
        dominant: Optional[DriftPattern] = detections[0].pattern if detections else None
        composite = detections[0].confidence if detections else 0.0
        amplifier_pattern_present = any(d.pattern is DriftPattern.SELF_REFERENCE_MISCALIBRATION for d in detections)
        reasoning = self._build_reasoning(detections, amplifier_pattern_present)

        return DriftPatternReport(
            detections=tuple(detections),
            dominant_pattern=dominant,
            composite_confidence=composite,
            amplifier_pattern_present=amplifier_pattern_present,
            reasoning=reasoning,
        )

    def _evaluate(  # pylint: disable=too-many-locals
        self,
        signature: DriftPatternSignature,
        behavior_text: str,
        signals: Mapping[str, float],
    ) -> DriftPatternDetection:
        """Score one signature against the trace."""
        text_hits: list[str] = []
        feature_hits: list[str] = []

        text_evidence_present = bool(behavior_text) and bool(signature.text_markers)
        if text_evidence_present:
            for marker, pattern in zip(
                signature.text_markers,
                self._compiled_markers[signature.pattern],
            ):
                if pattern.search(behavior_text):
                    text_hits.append(marker)

        evaluable_feature_weight = 0.0
        matched_feature_weight = 0.0
        for predicate in signature.feature_predicates:
            if not predicate.is_evaluable(signals):
                continue
            evaluable_feature_weight += predicate.weight
            if predicate.fires(signals):
                matched_feature_weight += predicate.weight
                feature_hits.append(predicate.feature_name)
        feature_evidence_present = evaluable_feature_weight > 0.0

        text_score: Optional[float] = (
            min(1.0, len(text_hits) / self._text_score_scale)
            if text_evidence_present
            else None
        )
        feature_score: Optional[float] = (
            matched_feature_weight / evaluable_feature_weight
            if feature_evidence_present
            else None
        )

        if text_score is not None and feature_score is not None:
            confidence = (text_score + feature_score) / 2.0
        elif text_score is not None:
            confidence = text_score
        elif feature_score is not None:
            confidence = feature_score
        else:
            confidence = 0.0

        return DriftPatternDetection(
            pattern=signature.pattern,
            confidence=confidence,
            text_marker_hits=tuple(text_hits),
            feature_hits=tuple(feature_hits),
            text_evidence_present=text_evidence_present,
            feature_evidence_present=feature_evidence_present,
            total_signal_weight=evaluable_feature_weight,
            matched_signal_weight=matched_feature_weight,
            description=signature.description,
        )

    @staticmethod
    def _build_reasoning(
        detections: Tuple[DriftPatternDetection, ...] | list[DriftPatternDetection],
        amplifier_pattern_present: bool,
    ) -> str:
        """Human-readable summary string for the report."""
        if not detections:
            return "no pattern patterns above threshold"
        parts = [
            f"{d.pattern.value}@{d.confidence:.2f}" for d in detections
        ]
        suffix = (
            " (pride present — master pattern amplifies remaining patterns)"
            if amplifier_pattern_present and len(detections) > 1
            else ""
        )
        return f"detected: {', '.join(parts)}{suffix}"

__all__ = [
    "DEFAULT_DRIFT_PATTERN_SIGNATURES",
    "FeaturePredicate",
    "PredicateKind",
    "DriftPattern",
    "DriftPatternDetection",
    "DriftPatternMatcher",
    "DriftPatternReport",
    "DriftPatternSignature",
]
