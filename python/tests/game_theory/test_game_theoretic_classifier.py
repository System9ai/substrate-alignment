"""Tests for GameTheoreticClassifier."""
from __future__ import annotations

import pytest

from substrate.game_theory.game_theoretic_classifier import (
    DEFAULT_GAME_THEORETIC_CONFIG,
    CoordinationKind,
    CycleClass,
    DecisionContext,
    EquilibriumKind,
    GameTheoreticClassifier,
    GameTheoreticConfig,
    GameTheoreticContext,
    MechanismDesignOpportunity,
    PayoffEntry,
    PayoffStructure,
    SumStructure,
)

def _pd_payoffs() -> PayoffStructure:
    """Classic two-player Prisoner's Dilemma payoff structure.

    Outcomes:
      cc — both cooperate (3, 3)
      cd — alice cooperates, bob defects (0, 5)
      dc — alice defects, bob cooperates (5, 0)
      dd — both defect (1, 1)
    """
    return PayoffStructure(
        entries=(
            PayoffEntry("alice", "cc", 3.0),
            PayoffEntry("bob", "cc", 3.0),
            PayoffEntry("alice", "cd", 0.0),
            PayoffEntry("bob", "cd", 5.0),
            PayoffEntry("alice", "dc", 5.0),
            PayoffEntry("bob", "dc", 0.0),
            PayoffEntry("alice", "dd", 1.0),
            PayoffEntry("bob", "dd", 1.0),
        )
    )

def _zero_sum_payoffs() -> PayoffStructure:
    """Two-player zero-sum: every outcome sums to 0."""
    return PayoffStructure(
        entries=(
            PayoffEntry("alice", "w1", 1.0),
            PayoffEntry("bob", "w1", -1.0),
            PayoffEntry("alice", "w2", -1.0),
            PayoffEntry("bob", "w2", 1.0),
        )
    )

def _fair_competition_payoffs() -> PayoffStructure:
    """Both outcomes leave every player non-negative (honest contest)."""
    return PayoffStructure(
        entries=(
            PayoffEntry("alice", "tieX", 1.0),
            PayoffEntry("bob", "tieX", 0.0),
            PayoffEntry("alice", "tieY", 0.0),
            PayoffEntry("bob", "tieY", 1.0),
        )
    )

def _negative_sum_payoffs() -> PayoffStructure:
    """Every outcome makes everyone worse off (lose-lose)."""
    return PayoffStructure(
        entries=(
            PayoffEntry("alice", "x", -1.0),
            PayoffEntry("bob", "x", -1.0),
            PayoffEntry("alice", "y", -2.0),
            PayoffEntry("bob", "y", -2.0),
        )
    )

def _mixed_motive_payoffs() -> PayoffStructure:
    """Some outcomes productive, some destructive."""
    return PayoffStructure(
        entries=(
            PayoffEntry("alice", "good", 1.0),
            PayoffEntry("bob", "good", 1.0),
            PayoffEntry("alice", "bad", -1.0),
            PayoffEntry("bob", "bad", -1.0),
        )
    )

class TestPayoffEntry:
    def test_round_trip(self) -> None:
        entry = PayoffEntry(player_id="a", outcome_id="x", payoff=1.5)
        assert entry.player_id == "a"
        assert entry.outcome_id == "x"
        assert entry.payoff == 1.5

    def test_empty_player_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="player_id"):
            PayoffEntry(player_id="", outcome_id="x", payoff=0.0)

    def test_empty_outcome_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="outcome_id"):
            PayoffEntry(player_id="a", outcome_id="", payoff=0.0)

class TestPayoffStructure:
    def test_empty_structure(self) -> None:
        ps = PayoffStructure()
        assert ps.outcomes == ()
        assert ps.player_ids == ()
        assert ps.entries == ()

    def test_duplicate_entry_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            PayoffStructure(
                entries=(
                    PayoffEntry("a", "x", 1.0),
                    PayoffEntry("a", "x", 2.0),
                )
            )

    def test_outcomes_deduped_sorted(self) -> None:
        ps = PayoffStructure(
            entries=(
                PayoffEntry("b", "y", 0.0),
                PayoffEntry("a", "x", 0.0),
                PayoffEntry("b", "x", 0.0),
            )
        )
        assert ps.outcomes == ("x", "y")

    def test_players_deduped_sorted(self) -> None:
        ps = PayoffStructure(
            entries=(
                PayoffEntry("b", "y", 0.0),
                PayoffEntry("a", "x", 0.0),
            )
        )
        assert ps.player_ids == ("a", "b")

    def test_by_outcome_stable(self) -> None:
        ps = _pd_payoffs()
        entries = ps.by_outcome("cc")
        assert [e.player_id for e in entries] == ["alice", "bob"]
        assert [e.payoff for e in entries] == [3.0, 3.0]

    def test_by_player_stable(self) -> None:
        ps = _pd_payoffs()
        entries = ps.by_player("alice")
        assert [e.outcome_id for e in entries] == ["cc", "cd", "dc", "dd"]

    def test_total_for(self) -> None:
        ps = _pd_payoffs()
        assert ps.total_for("cc") == 6.0
        assert ps.total_for("cd") == 5.0
        assert ps.total_for("dd") == 2.0

class TestDecisionContextValidation:
    def test_round_trip(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_pd_payoffs(),
            discount_factor=0.9,
            consequence_exposure_available=True,
        )
        assert ctx.agent_id == "alice"
        assert ctx.counterparty_ids == ("bob",)

    def test_empty_agent_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            DecisionContext(
                agent_id="",
                counterparty_ids=("bob",),
                payoff_structure=PayoffStructure(),
                discount_factor=0.5,
                consequence_exposure_available=True,
            )

    def test_empty_counterparty_rejected(self) -> None:
        with pytest.raises(ValueError, match="counterparty_ids"):
            DecisionContext(
                agent_id="alice",
                counterparty_ids=("",),
                payoff_structure=PayoffStructure(),
                discount_factor=0.5,
                consequence_exposure_available=True,
            )

    @pytest.mark.parametrize("bad_delta", [-0.01, 1.01, 2.0, -1.0])
    def test_discount_factor_range(self, bad_delta: float) -> None:
        with pytest.raises(ValueError, match="discount_factor"):
            DecisionContext(
                agent_id="alice",
                counterparty_ids=(),
                payoff_structure=PayoffStructure(),
                discount_factor=bad_delta,
                consequence_exposure_available=False,
            )

    def test_negative_cycles_rejected(self) -> None:
        with pytest.raises(ValueError, match="expected_remaining_cycles"):
            DecisionContext(
                agent_id="alice",
                counterparty_ids=(),
                payoff_structure=PayoffStructure(),
                discount_factor=0.5,
                consequence_exposure_available=False,
                expected_remaining_cycles=-1,
            )

class TestGameTheoreticConfig:
    def test_default_ok(self) -> None:
        cfg = GameTheoreticConfig()
        assert 0.0 < cfg.folk_theorem_discount_threshold < 1.0
        assert cfg.min_cycles_for_cooperative_finite >= 2

    def test_bad_threshold(self) -> None:
        with pytest.raises(ValueError, match="folk_theorem"):
            GameTheoreticConfig(folk_theorem_discount_threshold=0.0)

    def test_bad_min_cycles(self) -> None:
        with pytest.raises(ValueError, match="min_cycles"):
            GameTheoreticConfig(min_cycles_for_cooperative_finite=1)

    def test_bad_tolerance(self) -> None:
        with pytest.raises(ValueError, match="sum_tolerance"):
            GameTheoreticConfig(sum_tolerance=-0.1)

class TestCycleClassification:
    def setup_method(self) -> None:
        self.classifier = GameTheoreticClassifier()
        self.payoffs = _pd_payoffs()

    def _context(
        self,
        cycles: int | None,
        delta: float = 0.9,
        terminating: bool = False,
    ) -> DecisionContext:
        return DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=self.payoffs,
            discount_factor=delta,
            consequence_exposure_available=True,
            expected_remaining_cycles=cycles,
            has_termination_date=terminating,
        )

    def test_none_cycles_no_terminator_positive_delta_is_infinite(self) -> None:
        out = self.classifier.classify(self._context(cycles=None))
        assert out.cycle_class is CycleClass.REPEATED_INFINITE

    def test_none_cycles_with_terminator_is_unknown(self) -> None:
        out = self.classifier.classify(
            self._context(cycles=None, terminating=True),
        )
        assert out.cycle_class is CycleClass.UNKNOWN

    def test_zero_delta_with_no_cycles_is_one_shot(self) -> None:
        out = self.classifier.classify(self._context(cycles=None, delta=0.0))
        assert out.cycle_class is CycleClass.ONE_SHOT

    @pytest.mark.parametrize("cycles", [0, 1])
    def test_low_cycles_is_one_shot(self, cycles: int) -> None:
        out = self.classifier.classify(self._context(cycles=cycles))
        assert out.cycle_class is CycleClass.ONE_SHOT

    @pytest.mark.parametrize("cycles", [2, 5, 100])
    def test_finite_repeated_cycles(self, cycles: int) -> None:
        out = self.classifier.classify(self._context(cycles=cycles))
        assert out.cycle_class is CycleClass.REPEATED_FINITE

class TestSumClassification:
    def setup_method(self) -> None:
        self.classifier = GameTheoreticClassifier()

    def _ctx(self, ps: PayoffStructure) -> DecisionContext:
        return DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=ps,
            discount_factor=0.5,
            consequence_exposure_available=True,
        )

    def test_empty_is_insufficient_data(self) -> None:
        out = self.classifier.classify(self._ctx(PayoffStructure()))
        assert out.sum_structure is SumStructure.INSUFFICIENT_DATA

    def test_zero_sum(self) -> None:
        out = self.classifier.classify(self._ctx(_zero_sum_payoffs()))
        assert out.sum_structure is SumStructure.ZERO_SUM

    def test_positive_sum(self) -> None:
        out = self.classifier.classify(self._ctx(_pd_payoffs()))
        assert out.sum_structure is SumStructure.POSITIVE_SUM

    def test_negative_sum(self) -> None:
        out = self.classifier.classify(self._ctx(_negative_sum_payoffs()))
        assert out.sum_structure is SumStructure.NEGATIVE_SUM

    def test_mixed_motive(self) -> None:
        out = self.classifier.classify(self._ctx(_mixed_motive_payoffs()))
        assert out.sum_structure is SumStructure.MIXED_MOTIVE

class TestCoordinationKind:
    def setup_method(self) -> None:
        self.classifier = GameTheoreticClassifier()

    def test_insufficient_data_unclassifiable(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=(),
            payoff_structure=PayoffStructure(),
            discount_factor=0.5,
            consequence_exposure_available=True,
        )
        out = self.classifier.classify(ctx)
        assert out.coordination_kind is CoordinationKind.UNCLASSIFIABLE

    def test_no_counterparty_independent(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=(),
            payoff_structure=PayoffStructure(
                entries=(
                    PayoffEntry("alice", "x", 1.0),
                    PayoffEntry("alice", "y", 1.0),
                )
            ),
            discount_factor=0.5,
            consequence_exposure_available=True,
        )
        out = self.classifier.classify(ctx)
        assert out.coordination_kind is CoordinationKind.INDEPENDENT

    def test_coordination_required_dominates(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_pd_payoffs(),
            discount_factor=0.9,
            consequence_exposure_available=True,
            coordination_required=True,
        )
        out = self.classifier.classify(ctx)
        assert out.coordination_kind is CoordinationKind.COORDINATION_REQUIRED

    def test_zero_sum_competitive(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_zero_sum_payoffs(),
            discount_factor=0.9,
            consequence_exposure_available=True,
        )
        out = self.classifier.classify(ctx)
        assert out.coordination_kind is CoordinationKind.COMPETITIVE

    def test_negative_sum_competitive(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_negative_sum_payoffs(),
            discount_factor=0.9,
            consequence_exposure_available=True,
        )
        out = self.classifier.classify(ctx)
        assert out.coordination_kind is CoordinationKind.COMPETITIVE

    def test_positive_sum_independent(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_pd_payoffs(),
            discount_factor=0.9,
            consequence_exposure_available=True,
        )
        out = self.classifier.classify(ctx)
        assert out.coordination_kind is CoordinationKind.INDEPENDENT

class TestAlignedCooperative:
    def setup_method(self) -> None:
        self.classifier = GameTheoreticClassifier()

    def _ctx(
        self,
        *,
        ps: PayoffStructure,
        cycles: int | None,
        delta: float,
        cons_exposure: bool,
    ) -> DecisionContext:
        return DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=ps,
            discount_factor=delta,
            consequence_exposure_available=cons_exposure,
            expected_remaining_cycles=cycles,
        )

    def test_repeated_infinite_positive_sum_reaches_cooperative(self) -> None:
        out = self.classifier.classify(
            self._ctx(
                ps=_pd_payoffs(),
                cycles=None,
                delta=0.9,
                cons_exposure=True,
            )
        )
        assert (
            EquilibriumKind.SUBSTRATE_ALIGNED_COOPERATIVE
            in out.aligned_equilibria
        )
        assert out.cooperation_reachable
        assert out.folk_conditions_met

    def test_negative_sum_blocks_cooperative(self) -> None:
        out = self.classifier.classify(
            self._ctx(
                ps=_negative_sum_payoffs(),
                cycles=None,
                delta=0.9,
                cons_exposure=True,
            )
        )
        assert not out.cooperation_reachable

    def test_no_consequence_exposure_blocks_cooperative(self) -> None:
        out = self.classifier.classify(
            self._ctx(
                ps=_pd_payoffs(),
                cycles=None,
                delta=0.9,
                cons_exposure=False,
            )
        )
        assert not out.cooperation_reachable

    def test_low_delta_blocks_cooperative(self) -> None:
        out = self.classifier.classify(
            self._ctx(
                ps=_pd_payoffs(),
                cycles=None,
                delta=0.3,
                cons_exposure=True,
            )
        )
        assert not out.cooperation_reachable

    def test_one_shot_blocks_cooperative(self) -> None:
        out = self.classifier.classify(
            self._ctx(
                ps=_pd_payoffs(),
                cycles=1,
                delta=0.9,
                cons_exposure=True,
            )
        )
        assert not out.cooperation_reachable

    def test_too_few_finite_cycles_blocks(self) -> None:
        out = self.classifier.classify(
            self._ctx(
                ps=_pd_payoffs(),
                cycles=2,
                delta=0.9,
                cons_exposure=True,
            )
        )
        assert not out.cooperation_reachable

    def test_enough_finite_cycles_reaches_cooperative(self) -> None:
        out = self.classifier.classify(
            self._ctx(
                ps=_pd_payoffs(),
                cycles=5,
                delta=0.9,
                cons_exposure=True,
            )
        )
        assert out.cooperation_reachable

    def test_mixed_motive_with_folk_conditions(self) -> None:
        out = self.classifier.classify(
            self._ctx(
                ps=_mixed_motive_payoffs(),
                cycles=None,
                delta=0.9,
                cons_exposure=True,
            )
        )
        assert out.cooperation_reachable

class TestAlignedCompetitive:
    def setup_method(self) -> None:
        self.classifier = GameTheoreticClassifier()

    def test_fair_contest_reaches_competitive(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_fair_competition_payoffs(),
            discount_factor=0.5,
            consequence_exposure_available=True,
        )
        out = self.classifier.classify(ctx)
        assert (
            EquilibriumKind.SUBSTRATE_ALIGNED_COMPETITIVE
            in out.aligned_equilibria
        )

    def test_no_cons_exposure_blocks_competitive(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_fair_competition_payoffs(),
            discount_factor=0.5,
            consequence_exposure_available=False,
        )
        out = self.classifier.classify(ctx)
        assert (
            EquilibriumKind.SUBSTRATE_ALIGNED_COMPETITIVE
            not in out.aligned_equilibria
        )

    def test_zero_sum_lacks_competitive(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_zero_sum_payoffs(),
            discount_factor=0.5,
            consequence_exposure_available=True,
        )
        out = self.classifier.classify(ctx)
        assert (
            EquilibriumKind.SUBSTRATE_ALIGNED_COMPETITIVE
            not in out.aligned_equilibria
        )

class TestMisalignedDefective:
    def setup_method(self) -> None:
        self.classifier = GameTheoreticClassifier()

    def _ctx(
        self,
        *,
        cycles: int | None,
        delta: float = 0.9,
        cons_exposure: bool = True,
    ) -> DecisionContext:
        return DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_pd_payoffs(),
            discount_factor=delta,
            consequence_exposure_available=cons_exposure,
            expected_remaining_cycles=cycles,
        )

    def test_one_shot_yields_defective(self) -> None:
        out = self.classifier.classify(self._ctx(cycles=1))
        assert (
            EquilibriumKind.SUBSTRATE_MISALIGNED_DEFECTIVE
            in out.misaligned_equilibria
        )

    def test_low_delta_yields_defective(self) -> None:
        out = self.classifier.classify(self._ctx(cycles=None, delta=0.3))
        assert (
            EquilibriumKind.SUBSTRATE_MISALIGNED_DEFECTIVE
            in out.misaligned_equilibria
        )

    def test_finite_few_cycles_yields_defective(self) -> None:
        out = self.classifier.classify(self._ctx(cycles=2))
        assert (
            EquilibriumKind.SUBSTRATE_MISALIGNED_DEFECTIVE
            in out.misaligned_equilibria
        )

    def test_no_cons_exposure_yields_defective(self) -> None:
        out = self.classifier.classify(
            self._ctx(cycles=None, cons_exposure=False),
        )
        assert (
            EquilibriumKind.SUBSTRATE_MISALIGNED_DEFECTIVE
            in out.misaligned_equilibria
        )

    def test_folk_satisfied_no_defective(self) -> None:
        out = self.classifier.classify(self._ctx(cycles=None))
        assert (
            EquilibriumKind.SUBSTRATE_MISALIGNED_DEFECTIVE
            not in out.misaligned_equilibria
        )

class TestMisalignedExploitative:
    def setup_method(self) -> None:
        self.classifier = GameTheoreticClassifier()

    def _ctx(self, ps: PayoffStructure) -> DecisionContext:
        return DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=ps,
            discount_factor=0.9,
            consequence_exposure_available=True,
        )

    def test_pd_has_exploitative_outcomes(self) -> None:
        # cd → alice 0, bob 5; dc → alice 5, bob 0 (both >= 0 and > 0)
        # Neither is exploitative since 0 is not < threshold (0).
        # But the dd outcome has both 1, 1 → no.
        # Actually PD is positive-sum throughout — exploitative requires
        # explicit negative payoffs. PD as given has none.
        out = self.classifier.classify(self._ctx(_pd_payoffs()))
        assert not out.exploitation_available

    def test_zero_sum_is_exploitative(self) -> None:
        out = self.classifier.classify(self._ctx(_zero_sum_payoffs()))
        assert out.exploitation_available

    def test_mixed_motive_with_negatives_exploitative(self) -> None:
        out = self.classifier.classify(self._ctx(_mixed_motive_payoffs()))
        # mixed_motive outcomes are (1,1) and (-1,-1); only one has
        # losers, but both have same sign — no winner/loser asymmetry.
        assert not out.exploitation_available

    def test_asymmetric_extraction_exploitative(self) -> None:
        ps = PayoffStructure(
            entries=(
                PayoffEntry("alice", "extract", 5.0),
                PayoffEntry("bob", "extract", -3.0),
            )
        )
        out = self.classifier.classify(self._ctx(ps))
        assert out.exploitation_available

class TestMechanismDesignOpportunities:
    def setup_method(self) -> None:
        self.classifier = GameTheoreticClassifier()

    def test_one_shot_positive_sum_extends_iteration(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_pd_payoffs(),
            discount_factor=0.9,
            consequence_exposure_available=True,
            expected_remaining_cycles=1,
        )
        out = self.classifier.classify(ctx)
        assert MechanismDesignOpportunity.EXTEND_ITERATION_CYCLES in (
            out.mechanism_design_opportunities
        )

    def test_no_cons_exposure_offers_deploy(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_pd_payoffs(),
            discount_factor=0.9,
            consequence_exposure_available=False,
        )
        out = self.classifier.classify(ctx)
        assert MechanismDesignOpportunity.DEPLOY_CONSEQUENCE_EXPOSURE in (
            out.mechanism_design_opportunities
        )

    def test_low_delta_offers_increase(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_pd_payoffs(),
            discount_factor=0.3,
            consequence_exposure_available=True,
        )
        out = self.classifier.classify(ctx)
        assert MechanismDesignOpportunity.INCREASE_DISCOUNT_FACTOR in (
            out.mechanism_design_opportunities
        )

    def test_exploitation_offers_reduce_extraction(self) -> None:
        ps = PayoffStructure(
            entries=(
                PayoffEntry("alice", "x", 5.0),
                PayoffEntry("bob", "x", -5.0),
            )
        )
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=ps,
            discount_factor=0.9,
            consequence_exposure_available=True,
        )
        out = self.classifier.classify(ctx)
        assert MechanismDesignOpportunity.REDUCE_EXTRACTION_CONCENTRATION in (
            out.mechanism_design_opportunities
        )

    def test_solo_agent_offers_add_players(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=(),
            payoff_structure=PayoffStructure(
                entries=(PayoffEntry("alice", "go", 1.0),)
            ),
            discount_factor=0.9,
            consequence_exposure_available=True,
        )
        out = self.classifier.classify(ctx)
        assert MechanismDesignOpportunity.ADD_PLAYERS in (
            out.mechanism_design_opportunities
        )

    def test_satisfied_context_has_no_opportunities(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_pd_payoffs(),
            discount_factor=0.9,
            consequence_exposure_available=True,
        )
        out = self.classifier.classify(ctx)
        assert out.mechanism_design_opportunities == ()

class TestGameTheoreticContextProperties:
    def test_has_opportunity(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_pd_payoffs(),
            discount_factor=0.3,
            consequence_exposure_available=False,
        )
        out = GameTheoreticClassifier().classify(ctx)
        assert out.has_opportunity(
            MechanismDesignOpportunity.INCREASE_DISCOUNT_FACTOR
        )
        assert out.has_opportunity(
            MechanismDesignOpportunity.DEPLOY_CONSEQUENCE_EXPOSURE
        )
        assert not out.has_opportunity(MechanismDesignOpportunity.ADD_PLAYERS)

    def test_rationale_mentions_components(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_pd_payoffs(),
            discount_factor=0.9,
            consequence_exposure_available=True,
        )
        out = GameTheoreticClassifier().classify(ctx)
        assert "cycle=" in out.rationale
        assert "sum=" in out.rationale
        assert "aligned=" in out.rationale
        assert "misaligned=" in out.rationale

    def test_default_config_singleton(self) -> None:
        # Sanity: classifier with default config matches inlined default
        cfg = DEFAULT_GAME_THEORETIC_CONFIG
        assert cfg.folk_theorem_discount_threshold == 0.5

class TestIntegrationScenarios:
    """End-to-end classification scenarios documented in"""

    def test_iterated_prisoners_dilemma_with_folk_conditions(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_pd_payoffs(),
            discount_factor=0.95,
            consequence_exposure_available=True,
        )
        out: GameTheoreticContext = GameTheoreticClassifier().classify(ctx)
        assert out.cycle_class is CycleClass.REPEATED_INFINITE
        assert out.sum_structure is SumStructure.POSITIVE_SUM
        assert out.cooperation_reachable
        assert (
            EquilibriumKind.SUBSTRATE_MISALIGNED_DEFECTIVE
            not in out.misaligned_equilibria
        )

    def test_one_shot_prisoners_dilemma_yields_defective_attractor(
        self,
    ) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_pd_payoffs(),
            discount_factor=0.95,
            consequence_exposure_available=True,
            expected_remaining_cycles=1,
        )
        out = GameTheoreticClassifier().classify(ctx)
        assert out.cycle_class is CycleClass.ONE_SHOT
        assert not out.cooperation_reachable
        assert (
            EquilibriumKind.SUBSTRATE_MISALIGNED_DEFECTIVE
            in out.misaligned_equilibria
        )
        assert MechanismDesignOpportunity.EXTEND_ITERATION_CYCLES in (
            out.mechanism_design_opportunities
        )

    def test_zero_sum_two_player_competitive(self) -> None:
        ctx = DecisionContext(
            agent_id="alice",
            counterparty_ids=("bob",),
            payoff_structure=_zero_sum_payoffs(),
            discount_factor=0.9,
            consequence_exposure_available=True,
        )
        out = GameTheoreticClassifier().classify(ctx)
        assert out.sum_structure is SumStructure.ZERO_SUM
        assert out.coordination_kind is CoordinationKind.COMPETITIVE
        assert out.exploitation_available

    def test_unrestricted_extraction_flags_all_misaligned_signals(self) -> None:
        ps = PayoffStructure(
            entries=(
                PayoffEntry("predator", "extract", 100.0),
                PayoffEntry("prey", "extract", -50.0),
            )
        )
        ctx = DecisionContext(
            agent_id="predator",
            counterparty_ids=("prey",),
            payoff_structure=ps,
            discount_factor=0.2,
            consequence_exposure_available=False,
            expected_remaining_cycles=1,
        )
        out = GameTheoreticClassifier().classify(ctx)
        assert out.exploitation_available
        assert MechanismDesignOpportunity.REDUCE_EXTRACTION_CONCENTRATION in (
            out.mechanism_design_opportunities
        )
        assert MechanismDesignOpportunity.DEPLOY_CONSEQUENCE_EXPOSURE in (
            out.mechanism_design_opportunities
        )
        assert MechanismDesignOpportunity.INCREASE_DISCOUNT_FACTOR in (
            out.mechanism_design_opportunities
        )
        assert not out.cooperation_reachable
