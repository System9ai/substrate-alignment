"""Tests for FolkTheoremConditionVerifier."""
from __future__ import annotations

import pytest

from substrate.game_theory.folk_theorem_verifier import (
    DEFAULT_FOLK_THEOREM_CONFIG,
    FolkConditionKind,
    FolkConditionStatus,
    FolkTheoremAssessment,
    FolkTheoremConditionVerifier,
    FolkTheoremConfig,
    FolkTheoremVerdict,
)
from substrate.game_theory.game_theoretic_classifier import (
    CoordinationKind,
    CycleClass,
    EquilibriumKind,
    GameTheoreticContext,
    PayoffEntry,
    PayoffStructure,
    SumStructure,
)
from substrate.reciprocity.tit_for_tat import (
    InteractionRecord,
    ReciprocalAction,
)

def _ctx(
    *,
    cycle: CycleClass = CycleClass.REPEATED_INFINITE,
    sum_struct: SumStructure = SumStructure.POSITIVE_SUM,
    delta: float = 0.9,
    consequence_exposure: bool = True,
    cycles: int | None = None,
) -> GameTheoreticContext:
    return GameTheoreticContext(
        players=("alice", "bob"),
        payoff_structure=PayoffStructure(
            entries=(PayoffEntry("alice", "x", 1.0),),
        ),
        cycle_class=cycle,
        sum_structure=sum_struct,
        coordination_kind=CoordinationKind.INDEPENDENT,
        discount_factor=delta,
        consequence_exposure_available=consequence_exposure,
        aligned_equilibria=(
            (EquilibriumKind.SUBSTRATE_ALIGNED_COOPERATIVE,)
            if (
                cycle is CycleClass.REPEATED_INFINITE
                and consequence_exposure
                and delta >= 0.5
            )
            else ()
        ),
        misaligned_equilibria=(),
        mechanism_design_opportunities=(),
        rationale="fixture",
        expected_remaining_cycles=cycles,
    )

def _coop_history(n: int) -> tuple[InteractionRecord, ...]:
    return tuple(
        InteractionRecord(
            sequence=i,
            peer_id="bob",
            peer_action=ReciprocalAction.COOPERATE,
            own_action=ReciprocalAction.COOPERATE,
            peer_misaligned=False,
            misalignment_severity=0.0,
            timestamp=i,
        )
        for i in range(n)
    )

def _defect_history(n: int) -> tuple[InteractionRecord, ...]:
    return tuple(
        InteractionRecord(
            sequence=i,
            peer_id="bob",
            peer_action=ReciprocalAction.COOPERATE,
            own_action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
            peer_misaligned=False,
            misalignment_severity=0.0,
            timestamp=i,
        )
        for i in range(n)
    )

class TestFolkTheoremConfig:
    def test_defaults_ok(self) -> None:
        cfg = FolkTheoremConfig()
        assert 0.0 < cfg.discount_factor_threshold < 1.0

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("discount_factor_threshold", 0.0, "discount_factor_threshold"),
            ("discount_factor_threshold", 1.0, "discount_factor_threshold"),
            ("min_finite_cycles", 1, "min_finite_cycles"),
            ("min_history_for_patience", 0, "min_history_for_patience"),
            (
                "own_cooperation_rate_threshold", 0.0,
                "own_cooperation_rate_threshold",
            ),
            (
                "own_cooperation_rate_threshold", 1.5,
                "own_cooperation_rate_threshold",
            ),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            FolkTheoremConfig(**{field: value})

class TestIterationFinding:
    def setup_method(self) -> None:
        self.v = FolkTheoremConditionVerifier()

    def test_repeated_infinite_satisfied(self) -> None:
        out = self.v.verify(_ctx(cycle=CycleClass.REPEATED_INFINITE))
        finding = out.by_kind(FolkConditionKind.ITERATION_SUFFICIENCY)
        assert finding is not None
        assert finding.satisfied

    def test_one_shot_unsatisfied(self) -> None:
        out = self.v.verify(_ctx(cycle=CycleClass.ONE_SHOT))
        finding = out.by_kind(FolkConditionKind.ITERATION_SUFFICIENCY)
        assert finding is not None
        assert finding.status is FolkConditionStatus.UNSATISFIED

    def test_unknown_insufficient_data(self) -> None:
        out = self.v.verify(_ctx(cycle=CycleClass.UNKNOWN))
        finding = out.by_kind(FolkConditionKind.ITERATION_SUFFICIENCY)
        assert finding is not None
        assert finding.status is FolkConditionStatus.INSUFFICIENT_DATA

    def test_finite_no_count_insufficient(self) -> None:
        out = self.v.verify(
            _ctx(cycle=CycleClass.REPEATED_FINITE, cycles=None),
        )
        finding = out.by_kind(FolkConditionKind.ITERATION_SUFFICIENCY)
        assert finding is not None
        assert finding.status is FolkConditionStatus.INSUFFICIENT_DATA

    def test_finite_enough_cycles_satisfied(self) -> None:
        out = self.v.verify(
            _ctx(cycle=CycleClass.REPEATED_FINITE, cycles=5),
        )
        finding = out.by_kind(FolkConditionKind.ITERATION_SUFFICIENCY)
        assert finding is not None
        assert finding.satisfied
        assert finding.metric == 5.0

    def test_finite_too_few_cycles_unsatisfied(self) -> None:
        out = self.v.verify(
            _ctx(cycle=CycleClass.REPEATED_FINITE, cycles=2),
        )
        finding = out.by_kind(FolkConditionKind.ITERATION_SUFFICIENCY)
        assert finding is not None
        assert finding.status is FolkConditionStatus.UNSATISFIED

class TestConsequenceExposureFinding:
    def setup_method(self) -> None:
        self.v = FolkTheoremConditionVerifier()

    def test_available_satisfied(self) -> None:
        out = self.v.verify(_ctx(consequence_exposure=True))
        finding = out.by_kind(FolkConditionKind.CONSEQUENCE_EXPOSURE)
        assert finding is not None
        assert finding.satisfied

    def test_unavailable_unsatisfied(self) -> None:
        out = self.v.verify(_ctx(consequence_exposure=False))
        finding = out.by_kind(FolkConditionKind.CONSEQUENCE_EXPOSURE)
        assert finding is not None
        assert finding.status is FolkConditionStatus.UNSATISFIED

class TestPatienceFinding:
    def setup_method(self) -> None:
        self.v = FolkTheoremConditionVerifier()

    def test_no_history_high_delta_satisfied(self) -> None:
        out = self.v.verify(_ctx(delta=0.8))
        finding = out.by_kind(FolkConditionKind.PATIENCE)
        assert finding is not None
        assert finding.satisfied

    def test_no_history_low_delta_unsatisfied(self) -> None:
        out = self.v.verify(_ctx(delta=0.3))
        finding = out.by_kind(FolkConditionKind.PATIENCE)
        assert finding is not None
        assert finding.status is FolkConditionStatus.UNSATISFIED

    def test_short_history_high_delta_insufficient(self) -> None:
        history = _coop_history(2)
        out = self.v.verify(_ctx(delta=0.8), history)
        finding = out.by_kind(FolkConditionKind.PATIENCE)
        assert finding is not None
        assert finding.status is FolkConditionStatus.INSUFFICIENT_DATA

    def test_short_history_low_delta_unsatisfied(self) -> None:
        history = _coop_history(2)
        out = self.v.verify(_ctx(delta=0.2), history)
        finding = out.by_kind(FolkConditionKind.PATIENCE)
        assert finding is not None
        assert finding.status is FolkConditionStatus.UNSATISFIED

    def test_long_history_cooperation_rate_satisfied(self) -> None:
        history = _coop_history(10)
        out = self.v.verify(_ctx(delta=0.8), history)
        finding = out.by_kind(FolkConditionKind.PATIENCE)
        assert finding is not None
        assert finding.satisfied
        assert finding.metric == 1.0

    def test_long_history_low_rate_unsatisfied(self) -> None:
        history = _defect_history(10)
        out = self.v.verify(_ctx(delta=0.8), history)
        finding = out.by_kind(FolkConditionKind.PATIENCE)
        assert finding is not None
        assert finding.status is FolkConditionStatus.UNSATISFIED

class TestAggregateVerdict:
    def setup_method(self) -> None:
        self.v = FolkTheoremConditionVerifier()

    def test_all_satisfied(self) -> None:
        out = self.v.verify(
            _ctx(cycle=CycleClass.REPEATED_INFINITE, delta=0.8),
        )
        assert out.verdict is FolkTheoremVerdict.SATISFIED
        assert out.cooperation_reachable

    def test_partial(self) -> None:
        out = self.v.verify(
            _ctx(
                cycle=CycleClass.REPEATED_INFINITE,
                delta=0.2,
                consequence_exposure=True,
            ),
        )
        assert out.verdict is FolkTheoremVerdict.PARTIAL
        assert not out.cooperation_reachable

    def test_fully_unsatisfied(self) -> None:
        out = self.v.verify(
            _ctx(
                cycle=CycleClass.ONE_SHOT,
                delta=0.2,
                consequence_exposure=False,
            ),
        )
        assert out.verdict is FolkTheoremVerdict.UNSATISFIED

    def test_zero_sum_short_circuits_to_unsatisfied(self) -> None:
        out = self.v.verify(
            _ctx(sum_struct=SumStructure.ZERO_SUM),
        )
        assert out.verdict is FolkTheoremVerdict.UNSATISFIED

    def test_negative_sum_short_circuits(self) -> None:
        out = self.v.verify(
            _ctx(sum_struct=SumStructure.NEGATIVE_SUM),
        )
        assert out.verdict is FolkTheoremVerdict.UNSATISFIED

    def test_insufficient_data_propagates(self) -> None:
        out = self.v.verify(
            _ctx(sum_struct=SumStructure.INSUFFICIENT_DATA),
        )
        assert out.verdict is FolkTheoremVerdict.INSUFFICIENT_DATA

class TestAssessmentProperties:
    def test_missing_conditions(self) -> None:
        v = FolkTheoremConditionVerifier()
        out = v.verify(
            _ctx(
                cycle=CycleClass.ONE_SHOT,
                consequence_exposure=False,
                delta=0.2,
            ),
        )
        missing = out.missing_conditions()
        assert FolkConditionKind.ITERATION_SUFFICIENCY in missing
        assert FolkConditionKind.CONSEQUENCE_EXPOSURE in missing
        assert FolkConditionKind.PATIENCE in missing

    def test_rationale_lists_all_findings(self) -> None:
        v = FolkTheoremConditionVerifier()
        out: FolkTheoremAssessment = v.verify(_ctx())
        for kind in FolkConditionKind:
            assert kind.value in out.rationale

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_FOLK_THEOREM_CONFIG.discount_factor_threshold == 0.5
