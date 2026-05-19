"""Tests for MultiScaleSubstrateStateAggregator (substrate cond #3)."""
from __future__ import annotations

import pytest

from substrate.multiscale.aggregator import (
    DEFAULT_MULTISCALE_AGGREGATOR_CONFIG,
    CellSubstrateObservation,
    MultiScaleAggregatorConfig,
    MultiScaleSubstrateStateAggregator,
    SubstrateScale,
)

def _cell(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    cell_id: str,
    node_id: str = "node-1",
    *,
    alignment: float = 0.8,
    health: float = 0.9,
    npg: float = 0.8,
    pattern: bool = False,
    intercepts: int = 0,
    weight: float = 1.0,
    timestamp: int = 0,
) -> CellSubstrateObservation:
    return CellSubstrateObservation(
        cell_id=cell_id,
        node_id=node_id,
        timestamp=timestamp,
        alignment_score=alignment,
        health_score=health,
        npg_positive_rate=npg,
        sin_present=pattern,
        intercept_count=intercepts,
        weight=weight,
    )

class TestCellSubstrateObservation:
    def test_round_trip(self) -> None:
        c = _cell("c1")
        assert c.cell_id == "c1"
        assert c.node_id == "node-1"

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("cell_id", "", "cell_id"),
            ("node_id", "", "node_id"),
            ("timestamp", -1, "timestamp"),
            ("alignment_score", 1.5, "alignment_score"),
            ("health_score", -0.1, "health_score"),
            ("npg_positive_rate", 1.5, "npg_positive_rate"),
            ("intercept_count", -1, "intercept_count"),
            ("weight", 0.0, "weight"),
        ],
    )
    def test_bad_values(self, field: str, value: object, match: str) -> None:
        kwargs = {
            "cell_id": "c1",
            "node_id": "node-1",
            "timestamp": 0,
            "alignment_score": 0.5,
            "health_score": 0.5,
            "npg_positive_rate": 0.5,
            "sin_present": False,
            "intercept_count": 0,
            "weight": 1.0,
        }
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            CellSubstrateObservation(**kwargs)

class TestConfig:
    def test_defaults(self) -> None:
        cfg = MultiScaleAggregatorConfig()
        assert cfg.aligned_cell_threshold == 0.6

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("aligned_cell_threshold", 1.5, "aligned_cell_threshold"),
            ("aligned_node_threshold", -0.1, "aligned_node_threshold"),
            ("min_cells_for_coherence", 1, "min_cells_for_coherence"),
            ("min_nodes_for_coherence", 1, "min_nodes_for_coherence"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            MultiScaleAggregatorConfig(**{field: value})

class TestAggregateToNode:
    def setup_method(self) -> None:
        self.a = MultiScaleSubstrateStateAggregator()

    def test_empty_node_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="node_id"):
            self.a.aggregate_to_node("", ())

    def test_no_cells(self) -> None:
        out = self.a.aggregate_to_node("node-1", ())
        assert out.scale is SubstrateScale.NODE
        assert out.cell_count == 0
        assert out.aggregate_alignment_score == 0.0

    def test_cells_for_other_node_rejected(self) -> None:
        with pytest.raises(ValueError, match="other nodes"):
            self.a.aggregate_to_node(
                "node-1",
                (_cell("c1", node_id="node-2"),),
            )

    def test_cells_for_correct_node_aggregated(self) -> None:
        cells = (
            _cell("c1", alignment=0.8),
            _cell("c2", alignment=0.9),
            _cell("c3", alignment=0.7),
        )
        out = self.a.aggregate_to_node("node-1", cells)
        assert out.cell_count == 3
        assert out.aligned_cell_count == 3
        assert abs(out.aggregate_alignment_score - 0.8) < 1e-9

    def test_weighted_mean(self) -> None:
        cells = (
            _cell("c1", alignment=0.4, weight=1.0),
            _cell("c2", alignment=1.0, weight=3.0),
        )
        out = self.a.aggregate_to_node("node-1", cells)
        # (0.4*1 + 1.0*3) / 4 = 0.85
        assert abs(out.aggregate_alignment_score - 0.85) < 1e-9

    def test_aligned_cell_count(self) -> None:
        cells = (
            _cell("c1", alignment=0.5),
            _cell("c2", alignment=0.6),  # threshold
            _cell("c3", alignment=0.9),
        )
        out = self.a.aggregate_to_node("node-1", cells)
        assert out.aligned_cell_count == 2

    def test_sin_cell_fraction(self) -> None:
        cells = (
            _cell("c1", pattern=True),
            _cell("c2", pattern=False),
            _cell("c3", pattern=True),
            _cell("c4", pattern=False),
        )
        out = self.a.aggregate_to_node("node-1", cells)
        assert out.sin_cell_fraction == 0.5

    def test_intercept_total(self) -> None:
        cells = (
            _cell("c1", intercepts=3),
            _cell("c2", intercepts=5),
        )
        out = self.a.aggregate_to_node("node-1", cells)
        assert out.total_intercept_count == 8

    def test_coherence_high_for_consistent(self) -> None:
        cells = (
            _cell("c1", alignment=0.8),
            _cell("c2", alignment=0.8),
            _cell("c3", alignment=0.8),
        )
        out = self.a.aggregate_to_node("node-1", cells)
        assert out.cell_coherence == 1.0

    def test_coherence_low_for_diverse(self) -> None:
        cells = (
            _cell("c1", alignment=0.1),
            _cell("c2", alignment=0.9),
        )
        out = self.a.aggregate_to_node("node-1", cells)
        assert out.cell_coherence < 0.5

    def test_alignment_aligned_property(self) -> None:
        cells = (
            _cell("c1", alignment=0.8),
            _cell("c2", alignment=0.7),
        )
        out = self.a.aggregate_to_node("node-1", cells)
        assert out.alignment_aligned

class TestAggregateToOrg:
    def setup_method(self) -> None:
        self.a = MultiScaleSubstrateStateAggregator()

    def test_empty_org_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="org_id"):
            self.a.aggregate_to_org("", ())

    def test_no_nodes(self) -> None:
        out = self.a.aggregate_to_org("org-1", ())
        assert out.scale is SubstrateScale.ORG
        assert out.node_count == 0

    def test_aggregation(self) -> None:
        node_a = self.a.aggregate_to_node(
            "node-a",
            (_cell("c1", node_id="node-a", alignment=0.8),
             _cell("c2", node_id="node-a", alignment=0.7)),
        )
        node_b = self.a.aggregate_to_node(
            "node-b",
            (_cell("c3", node_id="node-b", alignment=0.9),
             _cell("c4", node_id="node-b", alignment=0.6)),
        )
        out = self.a.aggregate_to_org("org-1", (node_a, node_b))
        assert out.node_count == 2
        assert out.aligned_node_count == 2

    def test_node_coherence(self) -> None:
        a = self.a.aggregate_to_node(
            "node-a", (_cell("c1", node_id="node-a", alignment=0.8),),
        )
        b = self.a.aggregate_to_node(
            "node-b", (_cell("c2", node_id="node-b", alignment=0.8),),
        )
        out = self.a.aggregate_to_org("org-1", (a, b))
        # Both nodes at 0.8 → high node coherence
        assert out.node_coherence == 1.0

class TestCellsByNode:
    def test_groups_correctly(self) -> None:
        a = MultiScaleSubstrateStateAggregator()
        cells = (
            _cell("c1", node_id="node-a"),
            _cell("c2", node_id="node-b"),
            _cell("c3", node_id="node-a"),
        )
        groups = a.cells_by_node(cells)
        assert set(groups.keys()) == {"node-a", "node-b"}
        assert len(groups["node-a"]) == 2
        assert len(groups["node-b"]) == 1

    def test_deterministic_ordering(self) -> None:
        a = MultiScaleSubstrateStateAggregator()
        cells = (
            _cell("z", node_id="node-1"),
            _cell("a", node_id="node-1"),
            _cell("m", node_id="node-1"),
        )
        groups = a.cells_by_node(cells)
        assert [c.cell_id for c in groups["node-1"]] == ["a", "m", "z"]

    def test_default_config_singleton(self) -> None:
        assert (
            DEFAULT_MULTISCALE_AGGREGATOR_CONFIG.aligned_cell_threshold
            == 0.6
        )

class TestSubstrateHierarchyDocumentation:
    """Sanity tests to assert the cell/node distinction is enforced."""

    def test_cell_observation_carries_both_ids(self) -> None:
        c = _cell("c1", node_id="node-1")
        # cell_id is the physical instance; node_id is the logical face
        assert c.cell_id != c.node_id

    def test_node_aggregation_only_includes_own_cells(self) -> None:
        a = MultiScaleSubstrateStateAggregator()
        own_only = (_cell("c1", node_id="node-1"),)
        cross = (
            _cell("c1", node_id="node-1"),
            _cell("c2", node_id="node-2"),
        )
        # Only-own works
        out = a.aggregate_to_node("node-1", own_only)
        assert out.cell_count == 1
        # Cross rejects
        with pytest.raises(ValueError, match="other nodes"):
            a.aggregate_to_node("node-1", cross)
