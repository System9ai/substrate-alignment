"""Tests for the NPG calculus on the observed entity graph (WS-8)."""
from __future__ import annotations

import pytest

from substrate.executive.observed_graph import (
    NpgEdge,
    detect_extraction,
)
from substrate.executive.quantities import Cycle


class TestNpgEdgeValidation:
    def test_empty_source_rejected(self) -> None:
        with pytest.raises(ValueError, match="source_entity_id"):
            NpgEdge("", "t", -0.5, Cycle.SHORT)

    def test_empty_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="target_entity_id"):
            NpgEdge("s", "", -0.5, Cycle.SHORT)


class TestDetectExtraction:
    def test_empty_graph(self) -> None:
        report = detect_extraction([])
        assert not report.rollups
        assert not report.extractive
        assert not report.supportive

    def test_predator_flagged_extractive(self) -> None:
        edges = [
            NpgEdge("pred", "v1", -0.6, Cycle.SHORT),
            NpgEdge("pred", "v2", -0.4, Cycle.SHORT),
        ]
        report = detect_extraction(edges)
        assert len(report.extractive) == 1
        pred = report.extractive[0]
        assert pred.entity_id == "pred"
        assert pred.short_cycle_taken == pytest.approx(1.0)
        assert pred.long_cycle_given == 0.0
        assert pred.is_extractive is True
        assert pred.is_supportive is False

    def test_mentor_flagged_supportive(self) -> None:
        edges = [
            NpgEdge("mentor", "student", 0.8, Cycle.LONG),
            NpgEdge("mentor", "x", -0.1, Cycle.SHORT),
        ]
        report = detect_extraction(edges)
        assert len(report.supportive) == 1
        mentor = report.supportive[0]
        assert mentor.long_cycle_given == pytest.approx(0.8)
        assert mentor.is_supportive is True
        assert mentor.is_extractive is False

    def test_short_cycle_giving_is_not_long_support(self) -> None:
        # A short-cycle gift does not count as sustained long-cycle support.
        edges = [NpgEdge("a", "b", 0.5, Cycle.SHORT)]
        rollup = detect_extraction(edges).rollups[0]
        assert rollup.long_cycle_given == 0.0
        assert rollup.short_cycle_taken == 0.0  # it's a gift, not a taking

    def test_long_cycle_taking_not_counted_as_short_extraction(self) -> None:
        # Sustained correction (long-cycle negative) is not one-off extraction.
        edges = [NpgEdge("a", "b", -0.5, Cycle.LONG)]
        rollup = detect_extraction(edges).rollups[0]
        assert rollup.short_cycle_taken == 0.0

    def test_ranking_worst_extractor_first(self) -> None:
        edges = [
            NpgEdge("mild", "v", -0.2, Cycle.SHORT),
            NpgEdge("severe", "v", -0.9, Cycle.SHORT),
        ]
        report = detect_extraction(edges)
        assert report.rollups[0].entity_id == "severe"
        assert report.rollups[1].entity_id == "mild"

    def test_threshold_gates_extractive(self) -> None:
        edges = [NpgEdge("a", "b", -0.3, Cycle.SHORT)]
        assert not detect_extraction(edges, extraction_threshold=0.5).extractive
        assert len(detect_extraction(edges, extraction_threshold=0.0).extractive) == 1

    def test_net_potential_caused_is_signed_sum(self) -> None:
        edges = [
            NpgEdge("a", "b", 0.5, Cycle.LONG),
            NpgEdge("a", "c", -0.2, Cycle.SHORT),
        ]
        rollup = detect_extraction(edges).rollups[0]
        assert rollup.net_potential_caused == pytest.approx(0.3)
        assert rollup.edge_count == 2
