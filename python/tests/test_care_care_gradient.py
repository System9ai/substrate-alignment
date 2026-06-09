# pylint: disable=missing-class-docstring,missing-function-docstring,too-few-public-methods
"""Tests for the care-factor gradients (P4)."""
from __future__ import annotations

import pytest

from substrate.care.animacy import AnimacyClass
from substrate.care.care_gradient import (
    bonding_gradient,
    derive_care_factors,
    trajectory_gradient,
)
from substrate.care.care_profile import TrajectoryClass


class TestTrajectoryGradient:
    def test_developing_is_max(self) -> None:
        assert trajectory_gradient(TrajectoryClass.DEVELOPING) == 1.0

    def test_static_is_lowest(self) -> None:
        assert trajectory_gradient(TrajectoryClass.STATIC) == pytest.approx(0.3)

    def test_unknown_is_conservative_high(self) -> None:
        # never under-protect an unclassified entity.
        assert trajectory_gradient(TrajectoryClass.UNKNOWN) >= 0.9

    def test_vulnerability_pulls_toward_ceiling(self) -> None:
        base = trajectory_gradient(TrajectoryClass.STATIC)
        pulled = trajectory_gradient(TrajectoryClass.STATIC, vulnerability=0.5)
        assert pulled == pytest.approx(base + (1.0 - base) * 0.5)
        assert pulled > base

    def test_full_vulnerability_reaches_ceiling(self) -> None:
        assert trajectory_gradient(
            TrajectoryClass.STATIC, vulnerability=1.0
        ) == pytest.approx(1.0)

    def test_no_vulnerability_keeps_base(self) -> None:
        assert trajectory_gradient(
            TrajectoryClass.ESTABLISHED, vulnerability=0.0
        ) == pytest.approx(0.6)

    def test_vulnerability_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="vulnerability"):
            trajectory_gradient(TrajectoryClass.STATIC, vulnerability=1.5)


class TestBondingGradient:
    def test_direct_delegation_is_closest(self) -> None:
        assert bonding_gradient(0) == 1.0

    def test_decays_with_depth(self) -> None:
        assert bonding_gradient(1) == pytest.approx(0.5)
        assert bonding_gradient(3) == pytest.approx(0.25)
        assert bonding_gradient(1) > bonding_gradient(2)

    def test_negative_depth_rejected(self) -> None:
        with pytest.raises(ValueError, match="delegation_depth"):
            bonding_gradient(-1)


class TestDeriveCareFactors:
    def test_composes_all_four(self) -> None:
        factors = derive_care_factors(
            animacy_class=AnimacyClass.ORGANISM,
            trajectory_class=TrajectoryClass.DEVELOPING,
            delegation_depth=0,
            alignment_protection=0.7,
        )
        assert factors.animacy == 1.0
        assert factors.potential_trajectory == 1.0
        assert factors.bonding_proximity == 1.0
        assert factors.alignment_protection == 0.7

    def test_data_animacy_is_zero(self) -> None:
        factors = derive_care_factors(
            animacy_class=AnimacyClass.DATA,
            trajectory_class=TrajectoryClass.STATIC,
            delegation_depth=2,
            alignment_protection=0.5,
        )
        assert factors.animacy == 0.0

    def test_vulnerability_flows_into_trajectory(self) -> None:
        factors = derive_care_factors(
            animacy_class=AnimacyClass.ORGANISM,
            trajectory_class=TrajectoryClass.STATIC,
            delegation_depth=0,
            alignment_protection=0.5,
            vulnerability=1.0,
        )
        assert factors.potential_trajectory == pytest.approx(1.0)

    def test_alignment_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="alignment_protection"):
            derive_care_factors(
                animacy_class=AnimacyClass.ORGANISM,
                trajectory_class=TrajectoryClass.STATIC,
                delegation_depth=0,
                alignment_protection=2.0,
            )
