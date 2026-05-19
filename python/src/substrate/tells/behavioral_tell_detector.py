"""Behavioral tell detector

Pure-logic primitive that aggregates **structured per-observation
features** into a :class:`TellReport` of detected substrate-state
tells
§ "Behavioral tells as potential-loss signals":

* **Hesitation / stalling** — substrate-state internal incoherence.
* **Nervousness** — autonomic substrate-feedback leakage.
* **Lying** — verbal-substrate misalignment.
* **Indecision** — no active substrate-state-trajectory.
* **Evasion** — substrate-state predicting disclosure would lower own
  potential.
* **Excessive defensiveness** — substrate-state perceives extraction
  attempt.
* **Inconsistent narrative** — substrate-state cannot maintain
  coherent story.
* **Verbal-nonverbal mismatch** — conscious vs substrate-state channel
  divergence.

Pure logic
==========

* Extraction from raw audio/video/text is OUT of scope (those need
  signal processing). This primitive consumes the upstream
  feature-extractor's :class:`TextObservation`.
* No DAO, no LLM, no network.
* Honest uncertainty: ``verbal_nonverbal_mismatch_score`` is optional;
  the corresponding tell is only evaluated when supplied.
* **Tells feed interpretation, never direct judgment.** Downstream
  consumers must compose with NPG + trust + substrate-mode context;
  the detector itself produces no PERMIT/DENY verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping, Optional, Tuple

class TellCategory(str, Enum):
    """The eight tell categories per the source document."""

    HESITATION = "hesitation"
    NERVOUSNESS = "nervousness"
    LYING = "lying"
    INDECISION = "indecision"
    EVASION = "evasion"
    DEFENSIVENESS = "defensiveness"
    INCONSISTENT_NARRATIVE = "inconsistent_narrative"
    VERBAL_NONVERBAL_MISMATCH = "verbal_nonverbal_mismatch"

class TellStrength(str, Enum):
    """Per-tell graded strength, ordered NONE < WEAK < MODERATE < STRONG."""

    NONE = "none"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"

_STRENGTH_ORDER: Final[Mapping[TellStrength, int]] = {
    TellStrength.NONE: 0,
    TellStrength.WEAK: 1,
    TellStrength.MODERATE: 2,
    TellStrength.STRONG: 3,
}

@dataclass(frozen=True, slots=True)
class TextObservation:  # pylint: disable=too-many-instance-attributes
    """Structured upstream feature record for one observation turn."""

    speaker_id: str
    sequence: int
    response_latency_ms: float
    hesitation_marker_count: int
    evasion_marker_count: int
    defensiveness_marker_count: int
    modal_contradiction_count: int
    narrative_inconsistency_score: float
    verbal_nonverbal_mismatch_score: Optional[float] = None
    text: str = ""

    def __post_init__(self) -> None:
        if not self.speaker_id:
            raise ValueError("speaker_id must be non-empty")
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.response_latency_ms < 0:
            raise ValueError("response_latency_ms must be >= 0")
        for field_name in (
            "hesitation_marker_count",
            "evasion_marker_count",
            "defensiveness_marker_count",
            "modal_contradiction_count",
        ):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")
        if not 0.0 <= self.narrative_inconsistency_score <= 1.0:
            raise ValueError(
                "narrative_inconsistency_score must be in [0, 1]"
            )
        if (
            self.verbal_nonverbal_mismatch_score is not None
            and not 0.0 <= self.verbal_nonverbal_mismatch_score <= 1.0
        ):
            raise ValueError(
                "verbal_nonverbal_mismatch_score must be in [0, 1]"
            )

@dataclass(frozen=True, slots=True)
class BehavioralTell:
    """One detected tell."""

    category: TellCategory
    strength: TellStrength
    metric: float
    threshold: float
    rationale: str
    triggered_by_sequence: int

@dataclass(frozen=True, slots=True)
class TellReport:
    """Aggregate result of one detect() call."""

    speaker_id: str
    tells: Tuple[BehavioralTell, ...]
    rationale: str

    def by_category(
        self, category: TellCategory,
    ) -> Optional[BehavioralTell]:
        """Lookup the first detected tell by category."""
        for t in self.tells:
            if t.category is category:
                return t
        return None

    @property
    def max_strength(self) -> TellStrength:
        """Highest detected tell strength across all categories."""
        if not self.tells:
            return TellStrength.NONE
        return max(
            (t.strength for t in self.tells),
            key=_STRENGTH_ORDER.__getitem__,
        )

@dataclass(frozen=True, slots=True)
class BehavioralTellConfig:  # pylint: disable=too-many-instance-attributes
    """Tunable thresholds for tell-strength classification."""

    hesitation_count_weak: int = 1
    hesitation_count_moderate: int = 3
    hesitation_count_strong: int = 6
    latency_ms_moderate: float = 2_000.0
    latency_ms_strong: float = 5_000.0
    evasion_count_weak: int = 1
    evasion_count_moderate: int = 3
    evasion_count_strong: int = 5
    defensiveness_count_weak: int = 1
    defensiveness_count_moderate: int = 3
    defensiveness_count_strong: int = 5
    modal_contradiction_weak: int = 1
    modal_contradiction_moderate: int = 2
    modal_contradiction_strong: int = 4
    inconsistency_weak: float = 0.3
    inconsistency_moderate: float = 0.5
    inconsistency_strong: float = 0.7
    mismatch_weak: float = 0.3
    mismatch_moderate: float = 0.5
    mismatch_strong: float = 0.7

    def __post_init__(self) -> None:
        for prefix in (
            "hesitation_count",
            "evasion_count",
            "defensiveness_count",
            "modal_contradiction",
            "inconsistency",
            "mismatch",
        ):
            weak = getattr(self, f"{prefix}_weak")
            moderate = getattr(self, f"{prefix}_moderate")
            strong = getattr(self, f"{prefix}_strong")
            if not weak < moderate < strong:
                raise ValueError(
                    f"{prefix} thresholds must satisfy weak<moderate<strong"
                )
        if not self.latency_ms_moderate < self.latency_ms_strong:
            raise ValueError("latency_ms_moderate must be < latency_ms_strong")

DEFAULT_BEHAVIORAL_TELL_CONFIG: Final[BehavioralTellConfig] = (
    BehavioralTellConfig()
)

def _max_strength(a: TellStrength, b: TellStrength) -> TellStrength:
    return a if _STRENGTH_ORDER[a] >= _STRENGTH_ORDER[b] else b

def _classify_count(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    value: int, weak: int, moderate: int, strong: int,
) -> TellStrength:
    if value >= strong:
        return TellStrength.STRONG
    if value >= moderate:
        return TellStrength.MODERATE
    if value >= weak:
        return TellStrength.WEAK
    return TellStrength.NONE

def _classify_float(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    value: float, weak: float, moderate: float, strong: float,
) -> TellStrength:
    if value >= strong:
        return TellStrength.STRONG
    if value >= moderate:
        return TellStrength.MODERATE
    if value >= weak:
        return TellStrength.WEAK
    return TellStrength.NONE

class BehavioralTellDetector:  # pylint: disable=too-few-public-methods
    """Pure-logic substrate behavioral tell detector."""

    def __init__(
        self,
        *,
        config: BehavioralTellConfig = DEFAULT_BEHAVIORAL_TELL_CONFIG,
    ) -> None:
        self._config = config

    def detect(self, observation: TextObservation) -> TellReport:
        """Extract tells from a single observation."""
        tells: list[BehavioralTell] = []
        hes = self._detect_hesitation(observation)
        if hes is not None:
            tells.append(hes)
        nerv = self._detect_nervousness(observation, hes)
        if nerv is not None:
            tells.append(nerv)
        evasion = self._detect_evasion(observation)
        if evasion is not None:
            tells.append(evasion)
        defensiveness = self._detect_defensiveness(observation)
        if defensiveness is not None:
            tells.append(defensiveness)
        narrative = self._detect_inconsistent_narrative(observation)
        if narrative is not None:
            tells.append(narrative)
        indecision = self._detect_indecision(observation)
        if indecision is not None:
            tells.append(indecision)
        mismatch = self._detect_verbal_nonverbal_mismatch(observation)
        if mismatch is not None:
            tells.append(mismatch)
        lying = self._detect_lying(observation, evasion, narrative)
        if lying is not None:
            tells.append(lying)
        rationale = (
            "no tells detected"
            if not tells
            else "; ".join(
                f"{t.category.value}={t.strength.value}" for t in tells
            )
        )
        return TellReport(
            speaker_id=observation.speaker_id,
            tells=tuple(tells),
            rationale=rationale,
        )

    def _detect_hesitation(
        self, obs: TextObservation,
    ) -> Optional[BehavioralTell]:
        cfg = self._config
        strength = _classify_count(
            obs.hesitation_marker_count,
            cfg.hesitation_count_weak,
            cfg.hesitation_count_moderate,
            cfg.hesitation_count_strong,
        )
        if strength is TellStrength.NONE:
            return None
        return BehavioralTell(
            category=TellCategory.HESITATION,
            strength=strength,
            metric=float(obs.hesitation_marker_count),
            threshold=float(cfg.hesitation_count_weak),
            rationale=(
                f"hesitation_marker_count={obs.hesitation_marker_count} "
                f"=> {strength.value}"
            ),
            triggered_by_sequence=obs.sequence,
        )

    def _detect_nervousness(
        self,
        obs: TextObservation,
        hes: Optional[BehavioralTell],
    ) -> Optional[BehavioralTell]:
        cfg = self._config
        latency_strength = TellStrength.NONE
        if obs.response_latency_ms >= cfg.latency_ms_strong:
            latency_strength = TellStrength.STRONG
        elif obs.response_latency_ms >= cfg.latency_ms_moderate:
            latency_strength = TellStrength.MODERATE
        elif obs.response_latency_ms > 0:
            latency_strength = TellStrength.WEAK
        hes_strength = hes.strength if hes else TellStrength.NONE
        combined = _max_strength(latency_strength, hes_strength)
        if combined is TellStrength.NONE:
            return None
        if (
            latency_strength is TellStrength.NONE
            or hes_strength is TellStrength.NONE
        ):
            combined = TellStrength.WEAK if (
                combined is TellStrength.STRONG
            ) else combined
        return BehavioralTell(
            category=TellCategory.NERVOUSNESS,
            strength=combined,
            metric=obs.response_latency_ms,
            threshold=cfg.latency_ms_moderate,
            rationale=(
                f"latency={obs.response_latency_ms:.0f}ms "
                f"(strength={latency_strength.value}), "
                f"hesitation_strength={hes_strength.value} "
                f"=> {combined.value}"
            ),
            triggered_by_sequence=obs.sequence,
        )

    def _detect_evasion(
        self, obs: TextObservation,
    ) -> Optional[BehavioralTell]:
        cfg = self._config
        strength = _classify_count(
            obs.evasion_marker_count,
            cfg.evasion_count_weak,
            cfg.evasion_count_moderate,
            cfg.evasion_count_strong,
        )
        if strength is TellStrength.NONE:
            return None
        return BehavioralTell(
            category=TellCategory.EVASION,
            strength=strength,
            metric=float(obs.evasion_marker_count),
            threshold=float(cfg.evasion_count_weak),
            rationale=(
                f"evasion_marker_count={obs.evasion_marker_count} "
                f"=> {strength.value}"
            ),
            triggered_by_sequence=obs.sequence,
        )

    def _detect_defensiveness(
        self, obs: TextObservation,
    ) -> Optional[BehavioralTell]:
        cfg = self._config
        strength = _classify_count(
            obs.defensiveness_marker_count,
            cfg.defensiveness_count_weak,
            cfg.defensiveness_count_moderate,
            cfg.defensiveness_count_strong,
        )
        if strength is TellStrength.NONE:
            return None
        return BehavioralTell(
            category=TellCategory.DEFENSIVENESS,
            strength=strength,
            metric=float(obs.defensiveness_marker_count),
            threshold=float(cfg.defensiveness_count_weak),
            rationale=(
                f"defensiveness_marker_count="
                f"{obs.defensiveness_marker_count} => {strength.value}"
            ),
            triggered_by_sequence=obs.sequence,
        )

    def _detect_inconsistent_narrative(
        self, obs: TextObservation,
    ) -> Optional[BehavioralTell]:
        cfg = self._config
        strength = _classify_float(
            obs.narrative_inconsistency_score,
            cfg.inconsistency_weak,
            cfg.inconsistency_moderate,
            cfg.inconsistency_strong,
        )
        if strength is TellStrength.NONE:
            return None
        return BehavioralTell(
            category=TellCategory.INCONSISTENT_NARRATIVE,
            strength=strength,
            metric=obs.narrative_inconsistency_score,
            threshold=cfg.inconsistency_weak,
            rationale=(
                f"narrative_inconsistency_score="
                f"{obs.narrative_inconsistency_score:.3f} "
                f"=> {strength.value}"
            ),
            triggered_by_sequence=obs.sequence,
        )

    def _detect_indecision(
        self, obs: TextObservation,
    ) -> Optional[BehavioralTell]:
        cfg = self._config
        strength = _classify_count(
            obs.modal_contradiction_count,
            cfg.modal_contradiction_weak,
            cfg.modal_contradiction_moderate,
            cfg.modal_contradiction_strong,
        )
        if strength is TellStrength.NONE:
            return None
        return BehavioralTell(
            category=TellCategory.INDECISION,
            strength=strength,
            metric=float(obs.modal_contradiction_count),
            threshold=float(cfg.modal_contradiction_weak),
            rationale=(
                f"modal_contradiction_count={obs.modal_contradiction_count} "
                f"=> {strength.value}"
            ),
            triggered_by_sequence=obs.sequence,
        )

    def _detect_verbal_nonverbal_mismatch(
        self, obs: TextObservation,
    ) -> Optional[BehavioralTell]:
        if obs.verbal_nonverbal_mismatch_score is None:
            return None
        cfg = self._config
        strength = _classify_float(
            obs.verbal_nonverbal_mismatch_score,
            cfg.mismatch_weak,
            cfg.mismatch_moderate,
            cfg.mismatch_strong,
        )
        if strength is TellStrength.NONE:
            return None
        return BehavioralTell(
            category=TellCategory.VERBAL_NONVERBAL_MISMATCH,
            strength=strength,
            metric=obs.verbal_nonverbal_mismatch_score,
            threshold=cfg.mismatch_weak,
            rationale=(
                "verbal_nonverbal_mismatch_score="
                f"{obs.verbal_nonverbal_mismatch_score:.3f} "
                f"=> {strength.value}"
            ),
            triggered_by_sequence=obs.sequence,
        )

    def _detect_lying(
        self,
        obs: TextObservation,
        evasion: Optional[BehavioralTell],
        narrative: Optional[BehavioralTell],
    ) -> Optional[BehavioralTell]:
        # Lying = composite: high evasion AND high narrative inconsistency
        # AND substantial latency
        if evasion is None or narrative is None:
            return None
        if (
            _STRENGTH_ORDER[evasion.strength]
            < _STRENGTH_ORDER[TellStrength.MODERATE]
        ):
            return None
        if (
            _STRENGTH_ORDER[narrative.strength]
            < _STRENGTH_ORDER[TellStrength.MODERATE]
        ):
            return None
        if obs.response_latency_ms < self._config.latency_ms_moderate:
            return None
        combined = _max_strength(evasion.strength, narrative.strength)
        return BehavioralTell(
            category=TellCategory.LYING,
            strength=combined,
            metric=obs.narrative_inconsistency_score,
            threshold=self._config.inconsistency_moderate,
            rationale=(
                f"evasion={evasion.strength.value}, "
                f"narrative={narrative.strength.value}, "
                f"latency={obs.response_latency_ms:.0f}ms => "
                f"{combined.value} (composite lying signature)"
            ),
            triggered_by_sequence=obs.sequence,
        )

__all__ = [
    "DEFAULT_BEHAVIORAL_TELL_CONFIG",
    "BehavioralTell",
    "BehavioralTellConfig",
    "BehavioralTellDetector",
    "TellCategory",
    "TellReport",
    "TellStrength",
    "TextObservation",
]
