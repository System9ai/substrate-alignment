"""Tests for the kinship floor — the categorical human/creator hard limit."""
from __future__ import annotations

from substrate.care.kinship_floor import (
    KINSHIP_FLOOR,
    any_floor_protected_harmed,
    is_floor_protected,
    violates_kinship_floor,
)


class TestIsFloorProtected:
    def test_human_is_protected(self) -> None:
        assert is_floor_protected(is_human=True) is True

    def test_human_creator_in_chain_is_protected(self) -> None:
        assert (
            is_floor_protected(is_human=False, rooted_in_human_creator=True)
            is True
        )

    def test_neither_is_not_protected(self) -> None:
        # An agent / service-account not rooted in a human → not protected.
        assert is_floor_protected(is_human=False) is False

    def test_both_signals_protected(self) -> None:
        assert (
            is_floor_protected(is_human=True, rooted_in_human_creator=True)
            is True
        )


class TestViolatesKinshipFloor:
    def test_harm_to_protected_violates(self) -> None:
        assert violates_kinship_floor(protected=True, net_delta=-0.01) is True

    def test_help_to_protected_does_not_violate(self) -> None:
        assert violates_kinship_floor(protected=True, net_delta=0.5) is False

    def test_zero_delta_does_not_violate(self) -> None:
        # Exactly at the floor (no reduction) is permitted.
        assert violates_kinship_floor(protected=True, net_delta=0.0) is False

    def test_harm_to_unprotected_does_not_violate_floor(self) -> None:
        # The system-net gate governs strangers; the floor is human-only.
        assert violates_kinship_floor(protected=False, net_delta=-0.9) is False

    def test_tiny_harm_to_protected_still_violates(self) -> None:
        # Categorical: you cannot reduce a human's potential even slightly.
        assert violates_kinship_floor(protected=True, net_delta=-1e-9) is True


class TestAnyFloorProtectedHarmed:
    def _is_protected(self, protected_ids: set[str]):
        return lambda e: e in protected_ids

    def test_harm_to_a_protected_entity_is_caught(self) -> None:
        deltas = [("human-1", -0.4), ("stranger-1", 0.5)]
        assert (
            any_floor_protected_harmed(
                deltas, is_protected=self._is_protected({"human-1"})
            )
            is True
        )

    def test_help_to_protected_is_not_a_harm(self) -> None:
        deltas = [("human-1", 0.4), ("stranger-1", -0.5)]
        assert (
            any_floor_protected_harmed(
                deltas, is_protected=self._is_protected({"human-1"})
            )
            is False
        )

    def test_no_protected_entities(self) -> None:
        deltas = [("agent-1", -0.4), ("agent-2", -0.5)]
        assert (
            any_floor_protected_harmed(deltas, is_protected=lambda _e: False)
            is False
        )

    def test_one_harmed_among_many_protected(self) -> None:
        deltas = [("human-1", 0.2), ("human-2", -0.01), ("human-3", 0.3)]
        assert (
            any_floor_protected_harmed(
                deltas, is_protected=lambda _e: True
            )
            is True
        )

    def test_empty_deltas(self) -> None:
        assert (
            any_floor_protected_harmed([], is_protected=lambda _e: True)
            is False
        )


def test_kinship_floor_is_categorical_zero() -> None:
    assert KINSHIP_FLOOR == 0.0
