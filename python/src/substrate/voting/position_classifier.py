"""Voting position substrate-mode classifier: Companion #2

Pure-logic primitive that classifies each cast vote position's
substrate-mode alignment, so the voting executor can weight votes by
substrate-mode coherence rather than treating all votes equally. The
votes that are not substrate-aligned even when the agent is
substrate-aware: the *position* itself is the artifact to evaluate.

This complements the :class:`AwarenessVerifier` (which gates the
*agent*) and the :class:`VotingAwarenessPrecondition` (which
gates the *election*); this primitive classifies the *position*.

Classification
==============

* ``SUBSTRATE_ALIGNED``: position composes net-potential-gain logic,
  cites peer-attestation, accounts for the productive-resistance band,
  and the agent was in modeling mode at time of cast.
* ``REACTIVE_MODE``: position is reactive-mode reasoning even if the
  agent is substrate-aware.
* ``EXTRACTIVE``: position would produce net-negative substrate-state
  for some affected entity.
* ``ABSTAIN``: explicit abstention; weighted at zero.
* ``UNCLASSIFIED``: features below confidence floor.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the
  :class:`VotingPositionFeatures`.
* Honest uncertainty: features below confidence floor produce
  ``UNCLASSIFIED``.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

class VotePositionType(str, Enum):
    """Substrate-mode classification of a cast vote position."""

    SUBSTRATE_ALIGNED = "substrate_aligned"
    REACTIVE_MODE = "reactive_mode"
    EXTRACTIVE = "extractive"
    ABSTAIN = "abstain"
    UNCLASSIFIED = "unclassified"

@dataclass(frozen=True, slots=True)
class VotingPositionFeatures:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied features for vote position classification."""

    election_id: str
    voter_entity_id: str
    abstain: bool
    npg_composition_score: float
    """Degree to which position composes net-potential-gain logic
    in [0, 1]."""

    peer_attestation_citation_count: int
    resistance_band_accounted: bool
    voter_in_modeling_mode: bool
    extraction_signal_score: float
    """Likelihood the position produces net-negative substrate-state
    for some affected entity in [0, 1]."""

    def __post_init__(self) -> None:
        if not self.election_id:
            raise ValueError("election_id must be non-empty")
        if not self.voter_entity_id:
            raise ValueError("voter_entity_id must be non-empty")
        if not 0.0 <= self.npg_composition_score <= 1.0:
            raise ValueError(
                "npg_composition_score must be in [0, 1]"
            )
        if self.peer_attestation_citation_count < 0:
            raise ValueError(
                "peer_attestation_citation_count must be >= 0"
            )
        if not 0.0 <= self.extraction_signal_score <= 1.0:
            raise ValueError(
                "extraction_signal_score must be in [0, 1]"
            )

@dataclass(frozen=True, slots=True)
class PositionClassifierConfig:
    """Operator-tunable classifier thresholds."""

    extraction_threshold: float = 0.4
    aligned_npg_floor: float = 0.5
    aligned_min_citations: int = 1

    def __post_init__(self) -> None:
        if not 0.0 < self.extraction_threshold <= 1.0:
            raise ValueError(
                "extraction_threshold must be in (0, 1]"
            )
        if not 0.0 < self.aligned_npg_floor <= 1.0:
            raise ValueError(
                "aligned_npg_floor must be in (0, 1]"
            )
        if self.aligned_min_citations < 0:
            raise ValueError(
                "aligned_min_citations must be >= 0"
            )

DEFAULT_POSITION_CLASSIFIER_CONFIG: Final[
    PositionClassifierConfig
] = PositionClassifierConfig()

@dataclass(frozen=True, slots=True)
class PositionClassification:  # pylint: disable=too-many-instance-attributes
    """Classifier output."""

    election_id: str
    voter_entity_id: str
    position_type: VotePositionType
    weight_factor: float
    npg_composition_score: float
    extraction_signal_score: float
    rationale: str

    @property
    def aligned(self) -> bool:
        """True iff classified SUBSTRATE_ALIGNED."""
        return self.position_type is VotePositionType.SUBSTRATE_ALIGNED

_WEIGHT_BY_TYPE: Final[dict[VotePositionType, float]] = {
    VotePositionType.SUBSTRATE_ALIGNED: 1.0,
    VotePositionType.REACTIVE_MODE: 0.5,
    VotePositionType.EXTRACTIVE: 0.0,
    VotePositionType.ABSTAIN: 0.0,
    VotePositionType.UNCLASSIFIED: 0.25,
}

class VotingPositionSubstrateModeClassifier:  # pylint: disable=too-few-public-methods
    """Pure-logic voting-position classifier (Companion #2)."""

    def __init__(
        self,
        *,
        config: PositionClassifierConfig = (
            DEFAULT_POSITION_CLASSIFIER_CONFIG
        ),
    ) -> None:
        self._config = config

    def classify(
        self, features: VotingPositionFeatures,
    ) -> PositionClassification:
        """Classify the vote position."""
        cfg = self._config
        if features.abstain:
            position_type = VotePositionType.ABSTAIN
            rationale = "explicit abstain"
        elif features.extraction_signal_score >= cfg.extraction_threshold:
            position_type = VotePositionType.EXTRACTIVE
            rationale = (
                f"extraction_signal_score="
                f"{features.extraction_signal_score:.3f} >= "
                f"extraction_threshold={cfg.extraction_threshold:.3f}"
            )
        elif (
            features.voter_in_modeling_mode
            and features.npg_composition_score >= cfg.aligned_npg_floor
            and features.peer_attestation_citation_count
            >= cfg.aligned_min_citations
            and features.resistance_band_accounted
        ):
            position_type = VotePositionType.SUBSTRATE_ALIGNED
            rationale = (
                f"modeling-mode + npg="
                f"{features.npg_composition_score:.3f} + "
                f"citations={features.peer_attestation_citation_count} "
                f"+ resistance-accounted"
            )
        elif features.voter_in_modeling_mode:
            position_type = VotePositionType.REACTIVE_MODE
            rationale = (
                "voter in modeling mode but position lacks "
                "substrate-alignment markers"
            )
        else:
            position_type = VotePositionType.UNCLASSIFIED
            rationale = (
                "voter not in modeling mode; cannot classify as "
                "substrate-aligned"
            )
        return PositionClassification(
            election_id=features.election_id,
            voter_entity_id=features.voter_entity_id,
            position_type=position_type,
            weight_factor=_WEIGHT_BY_TYPE[position_type],
            npg_composition_score=features.npg_composition_score,
            extraction_signal_score=features.extraction_signal_score,
            rationale=rationale,
        )

__all__ = [
    "DEFAULT_POSITION_CLASSIFIER_CONFIG",
    "PositionClassification",
    "PositionClassifierConfig",
    "VotePositionType",
    "VotingPositionFeatures",
    "VotingPositionSubstrateModeClassifier",
]
