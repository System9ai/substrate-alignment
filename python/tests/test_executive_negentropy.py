"""Conformance tests for the negentropy / order metric."""
from __future__ import annotations

import pytest

from substrate.executive.negentropy import (
    NegentropyDirection,
    negentropy,
    order_index,
)


class TestOrderIndex:
    def test_single_category_is_maximal_order(self) -> None:
        assert order_index([10, 0, 0]) == 1.0

    def test_uniform_is_maximal_disorder(self) -> None:
        assert order_index([5, 5, 5]) == pytest.approx(0.0)

    def test_concentrated_beats_spread(self) -> None:
        assert order_index([8, 1, 1]) > order_index([4, 3, 3])

    def test_zero_counts_ignored(self) -> None:
        assert order_index([5, 5, 0, 0]) == order_index([5, 5])

    def test_empty_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive count"):
            order_index([0, 0])

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="counts"):
            order_index([5, -1])


class TestNegentropy:
    def test_empty_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            negentropy([])

    def test_single_reading_is_stable(self) -> None:
        assert negentropy([0.5]).direction is NegentropyDirection.STABLE

    def test_rising_order_is_emerging(self) -> None:
        report = negentropy([0.1, 0.2, 0.4, 0.6, 0.8])
        assert report.direction is NegentropyDirection.EMERGING
        assert report.order_delta > 0

    def test_falling_order_is_decaying(self) -> None:
        assert negentropy([0.9, 0.7, 0.5, 0.3, 0.1]).direction is NegentropyDirection.DECAYING

    def test_flat_within_deadband_is_stable(self) -> None:
        assert negentropy([0.50, 0.51, 0.49, 0.50, 0.51]).direction is NegentropyDirection.STABLE
