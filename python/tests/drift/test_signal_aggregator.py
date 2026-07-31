"""Tests for DriftSignalAggregator."""
from __future__ import annotations

import pytest

from substrate.drift.signal_aggregator import (
    DEFAULT_DRIFT_AGGREGATOR_CONFIG,
    DriftAggregatorConfig,
    DriftCategory,
    DriftCategoryInput,
    DriftScale,
    DriftSeverity,
    DriftSignalAggregator,
)

def _input(
    category: DriftCategory, *, events: int = 1, severity: float = 0.5,
) -> DriftCategoryInput:
    return DriftCategoryInput(
        category=category,
        event_count=events,
        severity_total=severity,
    )

class TestInputValidation:
    def test_round_trip(self) -> None:
        i = _input(DriftCategory.PATTERN)
        assert i.category is DriftCategory.PATTERN

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("events", -1, "event_count"),
            ("severity", -0.1, "severity_total"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            _input(DriftCategory.PATTERN, **{field: value})

class TestConfig:
    def test_defaults(self) -> None:
        cfg = DriftAggregatorConfig()
        assert cfg.emerging_score_min == 0.2

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("emerging_score_min", 0.0, "emerging_score_min"),
            ("sustained_score_min", 0.1, "sustained_score_min"),
            ("critical_score_min", 0.4, "critical_score_min"),
            ("high_category_score_min", 0.0, "high_category_score_min"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            DriftAggregatorConfig(**{field: value})

class TestAggregateFlow:
    def setup_method(self) -> None:
        self.a = DriftSignalAggregator()

    def test_empty_entity_rejected(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            self.a.aggregate("", DriftScale.CELL, ())

    def test_empty_inputs(self) -> None:
        out = self.a.aggregate("alice", DriftScale.CELL, ())
        assert out.overall_severity is DriftSeverity.NONE
        assert out.composite_severity_score == 0.0
        assert out.total_event_count == 0

    def test_duplicate_categories_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            self.a.aggregate(
                "alice", DriftScale.CELL,
                (_input(DriftCategory.PATTERN), _input(DriftCategory.PATTERN)),
            )

class TestSeverityClassification:
    def setup_method(self) -> None:
        self.a = DriftSignalAggregator()

    def test_emerging(self) -> None:
        # weight: 0.30 (inversion) * 0.7 severity = 0.21 → EMERGING
        out = self.a.aggregate(
            "alice", DriftScale.CELL,
            (_input(DriftCategory.INVERSION, severity=0.7),),
        )
        assert out.overall_severity is DriftSeverity.EMERGING

    def test_sustained(self) -> None:
        # multiple categories adding up
        out = self.a.aggregate(
            "alice", DriftScale.CELL,
            (
                _input(DriftCategory.PATTERN, severity=1.0),  # 0.15
                _input(DriftCategory.INVERSION, severity=1.0),  # 0.30
                _input(DriftCategory.ATTACK, severity=0.6),  # 0.15
            ),
        )
        assert out.overall_severity is DriftSeverity.SUSTAINED

    def test_critical(self) -> None:
        out = self.a.aggregate(
            "alice", DriftScale.CELL,
            tuple(_input(c, severity=1.0) for c in DriftCategory),
        )
        assert out.has_critical_drift

    def test_none(self) -> None:
        out = self.a.aggregate(
            "alice", DriftScale.CELL,
            (_input(DriftCategory.PATTERN, severity=0.1),),
        )
        assert out.overall_severity is DriftSeverity.NONE

class TestHighSeverityCategories:
    def test_high_categories_flagged(self) -> None:
        a = DriftSignalAggregator()
        out = a.aggregate(
            "alice", DriftScale.CELL,
            (
                _input(DriftCategory.INVERSION, severity=0.9),
                _input(DriftCategory.ATTACK, severity=0.2),
            ),
        )
        assert DriftCategory.INVERSION in out.high_severity_categories
        assert DriftCategory.ATTACK not in out.high_severity_categories

class TestScaleAwareness:
    def test_cell_and_node(self) -> None:
        a = DriftSignalAggregator()
        cell_out = a.aggregate(
            "cell-1", DriftScale.CELL,
            (_input(DriftCategory.PATTERN, severity=0.5),),
        )
        node_out = a.aggregate(
            "node-alpha", DriftScale.NODE,
            (_input(DriftCategory.PATTERN, severity=0.5),),
        )
        assert cell_out.scale is DriftScale.CELL
        assert node_out.scale is DriftScale.NODE

class TestCategoryCounts:
    def test_counts_recorded(self) -> None:
        a = DriftSignalAggregator()
        out = a.aggregate(
            "alice", DriftScale.CELL,
            (
                _input(DriftCategory.PATTERN, events=3),
                _input(DriftCategory.INVERSION, events=2),
            ),
        )
        assert out.category_counts[DriftCategory.PATTERN] == 3
        assert out.category_counts[DriftCategory.INVERSION] == 2
        assert out.category_counts[DriftCategory.ATTACK] == 0
        assert out.total_event_count == 5

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_DRIFT_AGGREGATOR_CONFIG.emerging_score_min == 0.2
