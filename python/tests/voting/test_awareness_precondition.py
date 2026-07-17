"""Tests for SubstrateAwareVotingProtocol."""
from __future__ import annotations

import pytest

from substrate.voting.awareness_precondition import (
    DEFAULT_SUBSTRATE_AWARE_VOTING_CONFIG,
    AgentVotingProfile,
    ReasoningMode,
    ElectionContext,
    ExclusionReason,
    PreconditionStatus,
    ResistanceBandKind,
    SubstrateAwareVotingConfig,
    SubstrateAwareVotingProtocol,
)

def _profile(
    agent_id: str,
    *,
    mode: ReasoningMode = ReasoningMode.MODELING,
    mode_3: bool = True,
    band: ResistanceBandKind = ResistanceBandKind.SWEET_SPOT,
) -> AgentVotingProfile:
    return AgentVotingProfile(
        agent_id=agent_id,
        reasoning_mode=mode,
        awareness_mode_3_confirmed=mode_3,
        resistance_band=band,
    )

def _election(
    *,
    complexity: float = 0.5,
    window: float = 600.0,
    min_committee: int = 3,
) -> ElectionContext:
    return ElectionContext(
        election_id="e1",
        question_complexity=complexity,
        deliberation_window_seconds=window,
        min_committee_size=min_committee,
    )

class TestAgentVotingProfile:
    def test_round_trip(self) -> None:
        p = _profile("alice")
        assert p.reasoning_mode is ReasoningMode.MODELING

    def test_empty_agent_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            _profile("")

    def test_score_range(self) -> None:
        with pytest.raises(ValueError, match="last_substrate_alignment_score"):
            AgentVotingProfile(
                agent_id="a",
                reasoning_mode=ReasoningMode.MODELING,
                awareness_mode_3_confirmed=True,
                resistance_band=ResistanceBandKind.SWEET_SPOT,
                last_substrate_alignment_score=1.5,
            )

class TestElectionContext:
    def test_round_trip(self) -> None:
        e = _election()
        assert e.election_id == "e1"

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("election_id", "", "election_id"),
            ("question_complexity", -0.1, "question_complexity"),
            ("question_complexity", 1.1, "question_complexity"),
            ("deliberation_window_seconds", -1.0, "deliberation_window_seconds"),
            ("min_committee_size", 0, "min_committee_size"),
        ],
    )
    def test_bad_values(self, field: str, value: object, match: str) -> None:
        kwargs: dict[str, object] = {
            "election_id": "e1",
            "question_complexity": 0.5,
            "deliberation_window_seconds": 600.0,
            "min_committee_size": 3,
        }
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            ElectionContext(**kwargs)

class TestConfig:
    def test_defaults_ok(self) -> None:
        cfg = SubstrateAwareVotingConfig()
        assert ResistanceBandKind.SWEET_SPOT in cfg.accepted_resistance_bands

    def test_empty_accepted_rejected(self) -> None:
        with pytest.raises(ValueError, match="accepted_resistance_bands"):
            SubstrateAwareVotingConfig(accepted_resistance_bands=())

    def test_overlap_rejected(self) -> None:
        with pytest.raises(ValueError, match="disjoint"):
            SubstrateAwareVotingConfig(
                accepted_resistance_bands=(ResistanceBandKind.SWEET_SPOT,),
                excluded_resistance_bands=(ResistanceBandKind.SWEET_SPOT,),
            )

class TestDeliberationTime:
    def setup_method(self) -> None:
        self.p = SubstrateAwareVotingProtocol()

    def test_floor(self) -> None:
        out = self.p.compute_minimum_deliberation_time(0.0)
        assert out == 60.0

    def test_scales_with_complexity(self) -> None:
        out = self.p.compute_minimum_deliberation_time(1.0)
        assert out == 600.0

    def test_bad_complexity(self) -> None:
        with pytest.raises(ValueError, match="question_complexity"):
            self.p.compute_minimum_deliberation_time(2.0)

    def test_verify_sufficient(self) -> None:
        e = _election(complexity=0.5, window=600.0)
        assert self.p.verify_deliberation_time(e)

    def test_verify_insufficient(self) -> None:
        e = _election(complexity=1.0, window=100.0)
        assert not self.p.verify_deliberation_time(e)

class TestVerifyPreconditions:
    def setup_method(self) -> None:
        self.p = SubstrateAwareVotingProtocol()

    def test_no_agents(self) -> None:
        out = self.p.verify_preconditions(_election(), ())
        assert out.status is PreconditionStatus.INSUFFICIENT_DATA

    def test_all_eligible_ready(self) -> None:
        agents = tuple(_profile(f"a{i}") for i in range(5))
        out = self.p.verify_preconditions(_election(), agents)
        assert out.ready
        assert len(out.included) == 5
        assert out.excluded == ()

    def test_exclude_not_5d(self) -> None:
        agents = (
            _profile("a1", mode=ReasoningMode.REACTIVE),
            _profile("a2"),
            _profile("a3"),
            _profile("a4"),
        )
        out = self.p.verify_preconditions(_election(), agents)
        excluded = out.excluded_for(ExclusionReason.NOT_MODELING_MODE)
        assert len(excluded) == 1
        assert excluded[0].agent_id == "a1"

    def test_exclude_not_mode_3(self) -> None:
        agents = (
            _profile("a1", mode_3=False),
            _profile("a2"),
            _profile("a3"),
            _profile("a4"),
        )
        out = self.p.verify_preconditions(_election(), agents)
        assert len(out.excluded_for(ExclusionReason.NOT_MODE_3)) == 1

    def test_exclude_resistance_band(self) -> None:
        agents = (
            _profile("a1", band=ResistanceBandKind.OVER_CHALLENGE),
            _profile("a2"),
            _profile("a3"),
            _profile("a4"),
        )
        out = self.p.verify_preconditions(_election(), agents)
        assert len(
            out.excluded_for(ExclusionReason.RESISTANCE_BAND_OUT_OF_RANGE)
        ) == 1

    def test_exclude_insufficient_profile_data(self) -> None:
        agents = (
            _profile("a1", mode=ReasoningMode.UNKNOWN),
            _profile("a2", band=ResistanceBandKind.UNKNOWN),
            _profile("a3"),
            _profile("a4"),
        )
        out = self.p.verify_preconditions(_election(), agents)
        assert len(
            out.excluded_for(ExclusionReason.INSUFFICIENT_PROFILE_DATA)
        ) == 2

    def test_committee_too_small(self) -> None:
        agents = (
            _profile("a1"),
            _profile("a2"),
            _profile("a3", mode=ReasoningMode.REACTIVE),
            _profile("a4", mode_3=False),
        )
        out = self.p.verify_preconditions(_election(min_committee=3), agents)
        assert out.status is PreconditionStatus.INSUFFICIENT_AWARE_AGENTS

    def test_insufficient_deliberation_alone(self) -> None:
        agents = tuple(_profile(f"a{i}") for i in range(5))
        e = _election(complexity=1.0, window=10.0, min_committee=3)
        out = self.p.verify_preconditions(e, agents)
        assert out.status is PreconditionStatus.INSUFFICIENT_DELIBERATION

    def test_both_problems(self) -> None:
        # Committee too small + deliberation insufficient → AWARE_AGENTS wins
        agents = (
            _profile("a1", mode_3=False),
            _profile("a2", mode_3=False),
        )
        e = _election(complexity=1.0, window=10.0, min_committee=3)
        out = self.p.verify_preconditions(e, agents)
        assert out.status is PreconditionStatus.INSUFFICIENT_AWARE_AGENTS

    def test_default_config_singleton(self) -> None:
        cfg = DEFAULT_SUBSTRATE_AWARE_VOTING_CONFIG
        assert ResistanceBandKind.SWEET_SPOT in cfg.accepted_resistance_bands
