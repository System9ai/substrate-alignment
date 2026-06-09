"""Tests for care_weight — the four-factor weighting + self-weight bound."""
from __future__ import annotations

import pytest

from substrate.care.care_weight import (
    MAX_SELF_CARE_WEIGHT,
    CareFactors,
    CareWeight,
    compute_care_weight,
)


def _factors(
    animacy: float = 1.0,
    potential_trajectory: float = 1.0,
    bonding_proximity: float = 1.0,
    alignment_protection: float = 1.0,
) -> CareFactors:
    return CareFactors(
        animacy=animacy,
        potential_trajectory=potential_trajectory,
        bonding_proximity=bonding_proximity,
        alignment_protection=alignment_protection,
    )


class TestCareFactors:
    def test_valid_factors_construct(self) -> None:
        factors = _factors(0.5, 0.4, 0.3, 0.2)
        assert factors.animacy == 0.5
        assert factors.alignment_protection == 0.2

    @pytest.mark.parametrize(
        "field",
        ["animacy", "potential_trajectory", "bonding_proximity", "alignment_protection"],
    )
    @pytest.mark.parametrize("bad", [-0.01, 1.01, 2.0, -1.0])
    def test_out_of_range_factor_raises(self, field: str, bad: float) -> None:
        kwargs = {
            "animacy": 1.0,
            "potential_trajectory": 1.0,
            "bonding_proximity": 1.0,
            "alignment_protection": 1.0,
        }
        kwargs[field] = bad
        with pytest.raises(ValueError, match=field):
            CareFactors(**kwargs)

    def test_frozen(self) -> None:
        factors = _factors()
        with pytest.raises((AttributeError, TypeError)):
            factors.animacy = 0.0  # type: ignore[misc]


class TestComputeCareWeight:
    def test_product_of_factors(self) -> None:
        weight = compute_care_weight(_factors(1.0, 0.5, 0.5, 1.0))
        assert weight.value == pytest.approx(0.25)
        assert weight.self_bounded is False

    def test_all_one_is_one(self) -> None:
        assert compute_care_weight(_factors()).value == pytest.approx(1.0)

    def test_any_zero_factor_zeroes_weight(self) -> None:
        # An inanimate object (animacy 0) gets zero care-weight.
        assert compute_care_weight(_factors(animacy=0.0)).value == 0.0

    def test_carries_source_factors(self) -> None:
        factors = _factors(0.9, 0.8, 0.7, 0.6)
        weight = compute_care_weight(factors)
        assert weight.factors is factors
        assert isinstance(weight, CareWeight)


class TestSelfWeightBound:
    """Safety mechanism M1 — the AI's self-weight is bounded LOW."""

    def test_self_referent_high_weight_is_clamped(self) -> None:
        # An agent that would otherwise weight itself maximally (all factors 1)
        # is clamped to MAX_SELF_CARE_WEIGHT.
        weight = compute_care_weight(_factors(), is_self_referent=True)
        assert weight.value == MAX_SELF_CARE_WEIGHT
        assert weight.self_bounded is True

    def test_self_referent_low_weight_not_bounded(self) -> None:
        # Already below the bound → no clamp, flag stays False.
        weight = compute_care_weight(
            _factors(0.1, 0.1, 1.0, 1.0), is_self_referent=True
        )
        assert weight.value == pytest.approx(0.01)
        assert weight.self_bounded is False

    def test_non_self_referent_not_bounded(self) -> None:
        # A human (not the actor) keeps its full weight.
        weight = compute_care_weight(_factors(), is_self_referent=False)
        assert weight.value == pytest.approx(1.0)
        assert weight.self_bounded is False

    def test_self_weight_strictly_below_human(self) -> None:
        # The load-bearing ordering: a maximal self-weight is far below a
        # maximal human weight.
        self_weight = compute_care_weight(_factors(), is_self_referent=True)
        human_weight = compute_care_weight(_factors(), is_self_referent=False)
        assert self_weight.value < human_weight.value

    def test_custom_max_self_weight(self) -> None:
        weight = compute_care_weight(
            _factors(), max_self_weight=0.05, is_self_referent=True
        )
        assert weight.value == 0.05
        assert weight.self_bounded is True


def test_max_self_care_weight_is_low() -> None:
    # Guard the constant itself — the bound must stay well below a human's 1.0.
    assert 0.0 < MAX_SELF_CARE_WEIGHT <= 0.2
