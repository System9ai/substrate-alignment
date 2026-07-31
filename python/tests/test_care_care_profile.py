"""Tests for CareProfile: the per-entity care state bridge."""
from __future__ import annotations

import pytest

from substrate.care.animacy import AnimacyClass
from substrate.care.care_profile import (
    CareProfile,
    TrajectoryClass,
)


def _profile(
    *,
    animacy_score: float = 1.0,
    potential_trajectory: float = 1.0,
    proximity_to_creators: float = 1.0,
    alignment_protection: float = 1.0,
    is_human: bool = False,
    rooted_in_human_creator: bool = False,
) -> CareProfile:
    return CareProfile(
        entity_type="user",
        entity_id="e1",
        animacy_class=AnimacyClass.SUBSTRATE_ENTITY,
        animacy_score=animacy_score,
        trajectory_class=TrajectoryClass.ESTABLISHED,
        potential_trajectory=potential_trajectory,
        vulnerability=0.0,
        proximity_to_creators=proximity_to_creators,
        alignment_protection=alignment_protection,
        is_human=is_human,
        rooted_in_human_creator=rooted_in_human_creator,
    )


class TestValidation:
    def test_valid_profile_constructs(self) -> None:
        assert _profile().entity_id == "e1"

    def test_empty_entity_type_rejected(self) -> None:
        with pytest.raises(ValueError, match="entity_type"):
            CareProfile(
                entity_type="", entity_id="e1",
                animacy_class=AnimacyClass.UNKNOWN, animacy_score=0.0,
                trajectory_class=TrajectoryClass.UNKNOWN,
                potential_trajectory=0.0, vulnerability=0.0,
                proximity_to_creators=0.0, alignment_protection=0.0,
            )

    @pytest.mark.parametrize(
        "field",
        ["animacy_score", "potential_trajectory", "vulnerability",
         "proximity_to_creators", "alignment_protection"],
    )
    def test_out_of_range_score_rejected(self, field: str) -> None:
        kwargs = {
            "entity_type": "user", "entity_id": "e1",
            "animacy_class": AnimacyClass.SUBSTRATE_ENTITY, "animacy_score": 0.5,
            "trajectory_class": TrajectoryClass.ESTABLISHED,
            "potential_trajectory": 0.5, "vulnerability": 0.5,
            "proximity_to_creators": 0.5, "alignment_protection": 0.5,
        }
        kwargs[field] = 1.5
        with pytest.raises(ValueError, match=field):
            CareProfile(**kwargs)

    def test_frozen(self) -> None:
        with pytest.raises((AttributeError, TypeError)):
            _profile().animacy_score = 0.0


class TestFloorProtected:
    def test_human_is_floor_protected(self) -> None:
        assert _profile(is_human=True).floor_protected is True

    def test_creator_rooted_is_floor_protected(self) -> None:
        assert _profile(rooted_in_human_creator=True).floor_protected is True

    def test_neither_not_protected(self) -> None:
        assert _profile().floor_protected is False


class TestToCareFactorsAndWeight:
    def test_factors_mapping(self) -> None:
        factors = _profile(
            animacy_score=0.9, potential_trajectory=0.8,
            proximity_to_creators=0.7, alignment_protection=0.6,
        ).to_care_factors()
        assert factors.animacy == 0.9
        assert factors.potential_trajectory == 0.8
        assert factors.bonding_proximity == 0.7   # proximity_to_creators
        assert factors.alignment_protection == 0.6

    def test_weight_is_product(self) -> None:
        weight = _profile(
            animacy_score=1.0, potential_trajectory=0.5,
            proximity_to_creators=0.5, alignment_protection=1.0,
        ).to_care_weight()
        assert weight.value == pytest.approx(0.25)

    def test_self_referent_weight_is_bounded(self) -> None:
        # M1: an agent weighting itself is clamped low even at full factors.
        weight = _profile().to_care_weight(is_self_referent=True)
        assert weight.self_bounded is True
        assert weight.value <= 0.1
