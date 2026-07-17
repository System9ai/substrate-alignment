"""Substrate-awareness voting precondition

Pure-logic primitive enforcing the **three preconditions for
substrate-aligned voting** before the consensus engine accepts any
vote. Agents must be substrate-aware, independent, and given
sufficient deliberation time; otherwise voting quality collapses.

Three per-agent conditions
==========================

1. **5D reasoning-mode operation**: agent must be classified as
   :attr:`ReasoningMode.MODELING`.
2. **Mode-3 game-theoretic awareness confirmed**: the verifier
   must have returned :attr:`AwarenessMode.MODE_3` for this agent.
3. **Productive resistance band**: agent must operate in
   :attr:`ResistanceBandKind.SWEET_SPOT` or
   :attr:`ResistanceBandKind.PRODUCTIVE_DEEP` per the resistance_band
   primitive (substrate condition #9).

Plus one election-level condition:

4. **Sufficient deliberation time**: the election's deliberation
   window must meet
   ``compute_minimum_deliberation_time(question_complexity)``.

Architectural commitment
========================

Votes by non-substrate-aware agents or agents outside the productive
resistance band are **not counted**: they are structurally not
substrate-aligned reasoning even if they appear to be votes. The
consensus engine refuses to aggregate them.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the per-agent
  :class:`AgentVotingProfile` and election :class:`ElectionContext`.
* Honest uncertainty: an agent whose profile carries
  :attr:`ReasoningMode.UNKNOWN` or
  :attr:`ResistanceBandKind.UNKNOWN` is excluded as
  :attr:`ExclusionReason.INSUFFICIENT_PROFILE_DATA`.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Optional, Tuple

class ReasoningMode(str, Enum):
    """Vocabulary parallel to the reasoning_mode_classifier."""

    REACTIVE = "reactive"
    MODELING = "modeling"
    TRANSITION = "transition"
    UNKNOWN = "unknown"

class ResistanceBandKind(str, Enum):
    """Vocabulary parallel to the resistance_band primitive."""

    SWEET_SPOT = "sweet_spot"
    PRODUCTIVE_DEEP = "productive_deep"
    UNDER_CHALLENGE = "under_challenge"
    OVER_CHALLENGE = "over_challenge"
    UNKNOWN = "unknown"

class ExclusionReason(str, Enum):
    """Per-agent exclusion categories."""

    NOT_MODELING_MODE = "not_modeling_mode"
    NOT_MODE_3 = "not_mode_3"
    RESISTANCE_BAND_OUT_OF_RANGE = "resistance_band_out_of_range"
    INSUFFICIENT_PROFILE_DATA = "insufficient_profile_data"

class PreconditionStatus(str, Enum):
    """Election-level top-level verdict."""

    READY = "ready"
    INSUFFICIENT_AWARE_AGENTS = "insufficient_aware_agents"
    INSUFFICIENT_DELIBERATION = "insufficient_deliberation"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class AgentVotingProfile:
    """Per-agent substrate readiness snapshot for an election."""

    agent_id: str
    reasoning_mode: ReasoningMode
    awareness_mode_3_confirmed: bool
    resistance_band: ResistanceBandKind
    last_substrate_alignment_score: float = 0.5

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("agent_id must be non-empty")
        if not 0.0 <= self.last_substrate_alignment_score <= 1.0:
            raise ValueError(
                "last_substrate_alignment_score must be in [0, 1]"
            )

@dataclass(frozen=True, slots=True)
class ElectionContext:
    """Caller-supplied election metadata."""

    election_id: str
    question_complexity: float
    deliberation_window_seconds: float
    min_committee_size: int

    def __post_init__(self) -> None:
        if not self.election_id:
            raise ValueError("election_id must be non-empty")
        if not 0.0 <= self.question_complexity <= 1.0:
            raise ValueError("question_complexity must be in [0, 1]")
        if self.deliberation_window_seconds < 0:
            raise ValueError("deliberation_window_seconds must be >= 0")
        if self.min_committee_size < 1:
            raise ValueError("min_committee_size must be >= 1")

@dataclass(frozen=True, slots=True)
class VotingExclusion:
    """One agent excluded from the substrate-aware committee."""

    agent_id: str
    reason: ExclusionReason
    rationale: str

@dataclass(frozen=True, slots=True)
class PreconditionVerification:
    """Aggregate verification result."""

    election_id: str
    status: PreconditionStatus
    included: Tuple[str, ...]
    excluded: Tuple[VotingExclusion, ...]
    deliberation_sufficient: bool
    rationale: str

    @property
    def ready(self) -> bool:
        """True iff status is READY."""
        return self.status is PreconditionStatus.READY

    def excluded_for(
        self, reason: ExclusionReason,
    ) -> Tuple[VotingExclusion, ...]:
        """All exclusions for a given reason."""
        return tuple(e for e in self.excluded if e.reason is reason)

@dataclass(frozen=True, slots=True)
class SubstrateAwareVotingConfig:
    """Tunable thresholds."""

    accepted_resistance_bands: Tuple[ResistanceBandKind, ...] = (
        ResistanceBandKind.SWEET_SPOT,
        ResistanceBandKind.PRODUCTIVE_DEEP,
    )
    deliberation_seconds_per_complexity: float = 600.0
    deliberation_floor_seconds: float = 60.0
    excluded_resistance_bands: Tuple[ResistanceBandKind, ...] = field(
        default_factory=tuple,
    )

    def __post_init__(self) -> None:
        if not self.accepted_resistance_bands:
            raise ValueError("accepted_resistance_bands must be non-empty")
        if self.deliberation_seconds_per_complexity < 0:
            raise ValueError(
                "deliberation_seconds_per_complexity must be >= 0"
            )
        if self.deliberation_floor_seconds < 0:
            raise ValueError("deliberation_floor_seconds must be >= 0")
        accepted = set(self.accepted_resistance_bands)
        excluded = set(self.excluded_resistance_bands)
        if accepted & excluded:
            raise ValueError(
                "accepted_resistance_bands and excluded_resistance_bands "
                "must be disjoint"
            )

DEFAULT_SUBSTRATE_AWARE_VOTING_CONFIG: Final[SubstrateAwareVotingConfig] = (
    SubstrateAwareVotingConfig()
)

class SubstrateAwareVotingProtocol:
    """Pure-logic voting precondition verifier."""

    def __init__(
        self,
        *,
        config: SubstrateAwareVotingConfig = DEFAULT_SUBSTRATE_AWARE_VOTING_CONFIG,
    ) -> None:
        self._config = config

    def compute_minimum_deliberation_time(
        self, question_complexity: float,
    ) -> float:
        """Required deliberation window for one question complexity."""
        if not 0.0 <= question_complexity <= 1.0:
            raise ValueError("question_complexity must be in [0, 1]")
        cfg = self._config
        return max(
            cfg.deliberation_floor_seconds,
            cfg.deliberation_seconds_per_complexity * question_complexity,
        )

    def verify_deliberation_time(self, election: ElectionContext) -> bool:
        """True iff election's deliberation window meets the required floor."""
        required = self.compute_minimum_deliberation_time(
            election.question_complexity,
        )
        return election.deliberation_window_seconds >= required

    def verify_preconditions(
        self,
        election: ElectionContext,
        eligible_agents: Tuple[AgentVotingProfile, ...],
    ) -> PreconditionVerification:
        """Run all four preconditions and aggregate the verdict."""
        if not eligible_agents:
            return PreconditionVerification(
                election_id=election.election_id,
                status=PreconditionStatus.INSUFFICIENT_DATA,
                included=(),
                excluded=(),
                deliberation_sufficient=(
                    self.verify_deliberation_time(election)
                ),
                rationale="no eligible agents supplied",
            )
        included: list[str] = []
        excluded: list[VotingExclusion] = []
        for profile in eligible_agents:
            reason = self._exclusion_reason_for(profile)
            if reason is None:
                included.append(profile.agent_id)
            else:
                excluded.append(
                    VotingExclusion(
                        agent_id=profile.agent_id,
                        reason=reason,
                        rationale=self._exclusion_rationale(profile, reason),
                    )
                )
        deliberation_sufficient = self.verify_deliberation_time(election)
        status = self._aggregate_status(
            election=election,
            included=tuple(included),
            deliberation_sufficient=deliberation_sufficient,
        )
        rationale = self._build_rationale(
            status, len(included), len(excluded), deliberation_sufficient,
        )
        return PreconditionVerification(
            election_id=election.election_id,
            status=status,
            included=tuple(included),
            excluded=tuple(excluded),
            deliberation_sufficient=deliberation_sufficient,
            rationale=rationale,
        )

    def _exclusion_reason_for(
        self, profile: AgentVotingProfile,
    ) -> Optional[ExclusionReason]:
        if (
            profile.reasoning_mode is ReasoningMode.UNKNOWN
            or profile.resistance_band is ResistanceBandKind.UNKNOWN
        ):
            return ExclusionReason.INSUFFICIENT_PROFILE_DATA
        if profile.reasoning_mode is not ReasoningMode.MODELING:
            return ExclusionReason.NOT_MODELING_MODE
        if not profile.awareness_mode_3_confirmed:
            return ExclusionReason.NOT_MODE_3
        if profile.resistance_band not in (
            self._config.accepted_resistance_bands
        ):
            return ExclusionReason.RESISTANCE_BAND_OUT_OF_RANGE
        return None

    @staticmethod
    def _exclusion_rationale(
        profile: AgentVotingProfile, reason: ExclusionReason,
    ) -> str:
        if reason is ExclusionReason.NOT_MODELING_MODE:
            return (
                f"reasoning_mode={profile.reasoning_mode.value}; "
                "required MODELING"
            )
        if reason is ExclusionReason.NOT_MODE_3:
            return "awareness_mode_3_confirmed=False"
        if reason is ExclusionReason.RESISTANCE_BAND_OUT_OF_RANGE:
            return (
                f"resistance_band={profile.resistance_band.value} not "
                "in accepted bands"
            )
        return (
            f"profile carries UNKNOWN values (mode="
            f"{profile.reasoning_mode.value}, band="
            f"{profile.resistance_band.value})"
        )

    @staticmethod
    def _aggregate_status(
        *,
        election: ElectionContext,
        included: Tuple[str, ...],
        deliberation_sufficient: bool,
    ) -> PreconditionStatus:
        committee_ok = len(included) >= election.min_committee_size
        if committee_ok and deliberation_sufficient:
            return PreconditionStatus.READY
        if not committee_ok and not deliberation_sufficient:
            return PreconditionStatus.INSUFFICIENT_AWARE_AGENTS
        if not committee_ok:
            return PreconditionStatus.INSUFFICIENT_AWARE_AGENTS
        return PreconditionStatus.INSUFFICIENT_DELIBERATION

    @staticmethod
    def _build_rationale(
        status: PreconditionStatus,
        included: int,
        excluded: int,
        deliberation_sufficient: bool,
    ) -> str:
        return (
            f"status={status.value}: included={included}, "
            f"excluded={excluded}, deliberation_sufficient="
            f"{deliberation_sufficient}"
        )

__all__ = [
    "DEFAULT_SUBSTRATE_AWARE_VOTING_CONFIG",
    "AgentVotingProfile",
    "ReasoningMode",
    "ElectionContext",
    "ExclusionReason",
    "PreconditionStatus",
    "PreconditionVerification",
    "ResistanceBandKind",
    "SubstrateAwareVotingConfig",
    "SubstrateAwareVotingProtocol",
    "VotingExclusion",
]
