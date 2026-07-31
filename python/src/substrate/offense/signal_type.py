"""Offense-signal type enumeration + classifier (Companion #2)

Pure-logic enumeration of substrate-recognized offense-signal types and
a deterministic classifier from observable features to type. The
phenomenon; substrate-aligned response requires identifying *which*
offense pattern is firing.

Offense signal types
====================

* ``BOUNDARY_TRESPASS``: entity crossed a declared substrate boundary
  (compartment, scope, jurisdiction).
* ``SCARCITY_AGGRESSION``: entity took action under perceived
  resource scarcity that imposed cost on a peer.
* ``ACCUMULATED_COMMITMENT_BREACH``: entity broke a publicly-staked
  commitment without a substrate-aligned exit protocol.
* ``CAPABILITY_OVERREACH``: entity acted outside its declared
  capability surface (gap to the reachability gate).
* ``ATTRIBUTION_CONCEALMENT``: entity attempted to obscure its
  cryptographic identity / authorship (gap to substrate condition #1).
* ``ASYMMETRIC_HARM``: entity's action produced asymmetric net
  state-change harming the peer (gap to the NPG gate).
* ``UNCLASSIFIED``: observable features do not match any known type.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the feature vector.
* Honest uncertainty: features below confidence floor surface as
  ``UNCLASSIFIED``.
* Single-feature dominance pattern: the classifier identifies the
  one offense type whose evidence dominates, never returns multiple
  classifications.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

class OffenseSignalType(str, Enum):
    """Substrate-recognized offense-signal types."""

    BOUNDARY_TRESPASS = "boundary_trespass"
    SCARCITY_AGGRESSION = "scarcity_aggression"
    ACCUMULATED_COMMITMENT_BREACH = "accumulated_commitment_breach"
    CAPABILITY_OVERREACH = "capability_overreach"
    ATTRIBUTION_CONCEALMENT = "attribution_concealment"
    ASYMMETRIC_HARM = "asymmetric_harm"
    UNCLASSIFIED = "unclassified"

@dataclass(frozen=True, slots=True)
class OffenseFeatures:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied feature vector for offense classification."""

    actor_entity_id: str
    peer_entity_id: str
    boundary_trespass_score: float
    scarcity_aggression_score: float
    accumulated_commitment_breach_score: float
    capability_overreach_score: float
    attribution_concealment_score: float
    asymmetric_harm_score: float

    def __post_init__(self) -> None:
        if not self.actor_entity_id:
            raise ValueError("actor_entity_id must be non-empty")
        if not self.peer_entity_id:
            raise ValueError("peer_entity_id must be non-empty")
        if self.actor_entity_id == self.peer_entity_id:
            raise ValueError(
                "actor_entity_id and peer_entity_id must differ"
            )
        for name, value in (
            ("boundary_trespass_score", self.boundary_trespass_score),
            ("scarcity_aggression_score", self.scarcity_aggression_score),
            (
                "accumulated_commitment_breach_score",
                self.accumulated_commitment_breach_score,
            ),
            ("capability_overreach_score", self.capability_overreach_score),
            (
                "attribution_concealment_score",
                self.attribution_concealment_score,
            ),
            ("asymmetric_harm_score", self.asymmetric_harm_score),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")

@dataclass(frozen=True, slots=True)
class OffenseClassification:
    """Classifier output."""

    actor_entity_id: str
    peer_entity_id: str
    signal_type: OffenseSignalType
    confidence: float
    dominant_score: float
    runner_up_score: float
    rationale: str

    @property
    def classified(self) -> bool:
        """True iff a non-UNCLASSIFIED type was assigned."""
        return self.signal_type is not OffenseSignalType.UNCLASSIFIED

@dataclass(frozen=True, slots=True)
class OffenseClassifierConfig:
    """Operator-tunable classifier thresholds."""

    min_dominance_margin: float = 0.15
    """Dominant - runner_up must exceed this for classification."""

    min_confidence_floor: float = 0.4
    """Dominant score must exceed this for classification."""

    def __post_init__(self) -> None:
        if not 0.0 < self.min_dominance_margin <= 1.0:
            raise ValueError(
                "min_dominance_margin must be in (0, 1]"
            )
        if not 0.0 < self.min_confidence_floor <= 1.0:
            raise ValueError(
                "min_confidence_floor must be in (0, 1]"
            )

DEFAULT_OFFENSE_CLASSIFIER_CONFIG: Final[OffenseClassifierConfig] = (
    OffenseClassifierConfig()
)

class OffenseSignalClassifier:  # pylint: disable=too-few-public-methods
    """Pure-logic offense-signal classifier (Companion #2)."""

    def __init__(
        self,
        *,
        config: OffenseClassifierConfig = DEFAULT_OFFENSE_CLASSIFIER_CONFIG,
    ) -> None:
        self._config = config

    def classify(
        self, features: OffenseFeatures,
    ) -> OffenseClassification:
        """Classify the offense signal."""
        cfg = self._config
        scored = [
            (OffenseSignalType.BOUNDARY_TRESPASS,
             features.boundary_trespass_score),
            (OffenseSignalType.SCARCITY_AGGRESSION,
             features.scarcity_aggression_score),
            (OffenseSignalType.ACCUMULATED_COMMITMENT_BREACH,
             features.accumulated_commitment_breach_score),
            (OffenseSignalType.CAPABILITY_OVERREACH,
             features.capability_overreach_score),
            (OffenseSignalType.ATTRIBUTION_CONCEALMENT,
             features.attribution_concealment_score),
            (OffenseSignalType.ASYMMETRIC_HARM,
             features.asymmetric_harm_score),
        ]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        dominant_type, dominant_score = scored[0]
        runner_up_score = scored[1][1]
        margin = dominant_score - runner_up_score
        if (
            dominant_score < cfg.min_confidence_floor
            or margin < cfg.min_dominance_margin
        ):
            return OffenseClassification(
                actor_entity_id=features.actor_entity_id,
                peer_entity_id=features.peer_entity_id,
                signal_type=OffenseSignalType.UNCLASSIFIED,
                confidence=dominant_score,
                dominant_score=dominant_score,
                runner_up_score=runner_up_score,
                rationale=(
                    f"dominant={dominant_score:.3f} or "
                    f"margin={margin:.3f} below floors"
                ),
            )
        return OffenseClassification(
            actor_entity_id=features.actor_entity_id,
            peer_entity_id=features.peer_entity_id,
            signal_type=dominant_type,
            confidence=dominant_score,
            dominant_score=dominant_score,
            runner_up_score=runner_up_score,
            rationale=(
                f"{dominant_type.value} dominates "
                f"(score={dominant_score:.3f}, "
                f"margin={margin:+.3f})"
            ),
        )

__all__ = [
    "DEFAULT_OFFENSE_CLASSIFIER_CONFIG",
    "OffenseClassification",
    "OffenseClassifierConfig",
    "OffenseFeatures",
    "OffenseSignalClassifier",
    "OffenseSignalType",
]
