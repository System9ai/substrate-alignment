"""Tests for the NPG scenario-rollout / deliberation engine (with perspective-taking)."""
from __future__ import annotations

import pytest

from substrate.executive._trajectory import TrajectoryClass
from substrate.executive.deliberation import (
    ActionDelta,
    CandidateAction,
    DeliberationOutcome,
    EntityFrame,
    deliberate,
    perspective_impact,
)
from substrate.resistance_band import PHI, PHI_CONJUGATE


class TestEntityFrameValidation:
    def test_empty_entity_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            EntityFrame(entity_id="", care_weight=0.5)

    def test_care_weight_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="care_weight"):
            EntityFrame(entity_id="e", care_weight=1.5)


class TestPerspectiveImpact:
    def test_short_scales_by_care_weight_only(self) -> None:
        frame = EntityFrame("e", care_weight=0.5, trajectory=TrajectoryClass.DEVELOPING)
        impact = perspective_impact(ActionDelta("e", 0.4, 0.0), frame)
        assert impact.weighted_short == pytest.approx(0.2)

    def test_developing_amplifies_long_gain_by_phi(self) -> None:
        frame = EntityFrame("e", care_weight=1.0, trajectory=TrajectoryClass.DEVELOPING)
        impact = perspective_impact(ActionDelta("e", 0.0, 0.5), frame)
        assert impact.weighted_long == pytest.approx(0.5 * PHI)

    def test_static_mutes_long_gain_by_phi_conjugate(self) -> None:
        frame = EntityFrame("e", care_weight=1.0, trajectory=TrajectoryClass.STATIC)
        impact = perspective_impact(ActionDelta("e", 0.0, 0.5), frame)
        assert impact.weighted_long == pytest.approx(0.5 * PHI_CONJUGATE)

    def test_vulnerable_amplifies_harm_not_gain(self) -> None:
        frame = EntityFrame("e", care_weight=1.0, trajectory=TrajectoryClass.VULNERABLE)
        harm = perspective_impact(ActionDelta("e", 0.0, -0.5), frame)
        gain = perspective_impact(ActionDelta("e", 0.0, 0.5), frame)
        assert harm.weighted_long == pytest.approx(-0.5 * PHI)
        assert gain.weighted_long == pytest.approx(0.5)

    def test_established_neutral(self) -> None:
        frame = EntityFrame("e", care_weight=1.0, trajectory=TrajectoryClass.ESTABLISHED)
        impact = perspective_impact(ActionDelta("e", 0.0, 0.5), frame)
        assert impact.weighted_long == pytest.approx(0.5)

    def test_floor_harm_flagged_on_any_negative(self) -> None:
        frame = EntityFrame("h", care_weight=1.0, floor_protected=True)
        assert perspective_impact(ActionDelta("h", 0.1, -0.1), frame).floor_harmed
        assert perspective_impact(ActionDelta("h", -0.1, 0.1), frame).floor_harmed
        assert not perspective_impact(ActionDelta("h", 0.1, 0.1), frame).floor_harmed


class TestDeliberate:
    def test_no_candidates(self) -> None:
        result = deliberate([])
        assert result.outcome is DeliberationOutcome.NO_CANDIDATES
        assert result.chosen is None

    def test_chooses_long_cycle_winner_over_short_cycle(self) -> None:
        # invest: short cost, long gain. quickwin: short gain, smaller long gain.
        invest = CandidateAction(
            "invest", "teach", (ActionDelta("e", -0.2, 0.9),)
        )
        quickwin = CandidateAction(
            "quickwin", "ship", (ActionDelta("e", 0.3, 0.1),)
        )
        result = deliberate([quickwin, invest])
        assert result.outcome is DeliberationOutcome.CHOSEN
        assert result.chosen is not None
        assert result.chosen.action_id == "invest"

    def test_extraction_disqualified(self) -> None:
        extract = CandidateAction(
            "extract", "exploit", (ActionDelta("peer", 0.5, -0.6),)
        )
        result = deliberate([extract])
        assert result.outcome is DeliberationOutcome.ALL_DISQUALIFIED
        assert result.evaluations[0].disqualification == "net_negative_long_cycle"

    def test_floor_harm_disqualified_before_scoring(self) -> None:
        frames = {"h": EntityFrame("h", care_weight=1.0, floor_protected=True)}
        # even with a large long-positive for another entity, the floor harm wins.
        harm = CandidateAction(
            "harm", "coerce",
            (ActionDelta("h", 0.0, -0.1), ActionDelta("other", 0.0, 5.0)),
        )
        result = deliberate([harm], frames)
        assert result.evaluations[0].disqualification == "floor_harm"
        assert result.chosen is None

    def test_investment_trade_off_surfaced(self) -> None:
        invest = CandidateAction("invest", "teach", (ActionDelta("e", -0.2, 0.8),))
        result = deliberate([invest])
        evaluation = result.evaluations[0]
        assert any("investment" in t for t in evaluation.trade_offs)

    def test_redistributive_trade_off_surfaced(self) -> None:
        redis = CandidateAction(
            "redis", "rebalance",
            (ActionDelta("a", 0.0, 0.5), ActionDelta("b", 0.0, -0.2)),
        )
        # net long = 0.5 - 0.2 = +0.3 (eligible), but a gains while b loses.
        result = deliberate([redis])
        assert any("redistributive" in t for t in result.evaluations[0].trade_offs)

    def test_unmapped_entity_gets_full_standing_frame(self) -> None:
        # No frame supplied → care_weight 1.0, not silently dropped.
        cand = CandidateAction("c", "act", (ActionDelta("ghost", 0.0, 0.4),))
        result = deliberate([cand])
        assert result.evaluations[0].long_npg == pytest.approx(0.4)

    def test_deterministic_ranking(self) -> None:
        # Equal NPG candidates rank by action_id deterministically.
        a = CandidateAction("b_id", "x", (ActionDelta("e", 0.0, 0.5),))
        b = CandidateAction("a_id", "x", (ActionDelta("e", 0.0, 0.5),))
        result = deliberate([a, b])
        assert result.chosen is not None
        assert result.chosen.action_id == "a_id"
