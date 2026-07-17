"""Tests for CrossEntityStateInterpreter."""
from __future__ import annotations

import pytest

from substrate.cross_entity.interpreter import (
    DEFAULT_CROSS_ENTITY_INTERPRETER_CONFIG,
    ClusterMode,
    CrossEntityInterpreterConfig,
    CrossEntityStateInterpreter,
    PeerSubstrateClassification,
)
from substrate.cross_entity.observer import (
    CrossEntityObservationReport,
    ObservationScope,
    PeerStateDigest,
)

def _digest(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    peer: str,
    scope: ObservationScope = ObservationScope.CELL,
    *,
    alignment: float = 0.8,
    health: float = 0.9,
    coupling: float = 0.7,
    obs_count: int = 5,
    signal_freq: dict | None = None,
) -> PeerStateDigest:
    return PeerStateDigest(
        peer_id=peer,
        peer_scope=scope,
        observation_count=obs_count,
        latest_timestamp=100,
        avg_alignment=alignment,
        avg_health=health,
        avg_coupling=coupling,
        signal_kind_frequencies=signal_freq or {},
        average_quality=0.9,
        rationale="test",
    )

def _report(
    *,
    observer: str = "alice",
    cells: tuple = (),
    nodes: tuple = (),
) -> CrossEntityObservationReport:
    return CrossEntityObservationReport(
        observer_id=observer,
        cell_peers=cells,
        node_peers=nodes,
        total_observation_count=sum(d.observation_count for d in cells + nodes),
        rationale="test",
    )

class TestConfig:
    def test_defaults(self) -> None:
        cfg = CrossEntityInterpreterConfig()
        assert cfg.aligned_alignment_min == 0.7

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("aligned_alignment_min", 0.0, "aligned_alignment_min"),
            ("misaligned_alignment_max", 0.8, "misaligned_alignment_max"),
            ("coupling_degraded_max", 0.6, "coupling_degraded_max"),
            (
                "min_observations_for_classification", 0,
                "min_observations_for_classification",
            ),
            ("cohesion_min_peers", 0, "cohesion_min_peers"),
            (
                "misaligned_signal_count_min", 0,
                "misaligned_signal_count_min",
            ),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            CrossEntityInterpreterConfig(**{field: value})

class TestPerPeerClassification:
    def setup_method(self) -> None:
        self.i = CrossEntityStateInterpreter()

    def test_aligned(self) -> None:
        out = self.i.interpret(_report(
            cells=(_digest("c1", alignment=0.85, coupling=0.7),),
        ))
        assert out.cell_peers[0].is_aligned

    def test_misaligned_by_alignment(self) -> None:
        out = self.i.interpret(_report(
            cells=(_digest("c1", alignment=0.2, coupling=0.5),),
        ))
        assert out.cell_peers[0].is_misaligned

    def test_misaligned_by_signal_count(self) -> None:
        out = self.i.interpret(_report(
            cells=(_digest(
                "c1", alignment=0.7, coupling=0.6,
                signal_freq={"threat": 3, "loss": 1},
            ),),
        ))
        assert out.cell_peers[0].is_misaligned

    def test_coupling_degraded(self) -> None:
        out = self.i.interpret(_report(
            cells=(_digest("c1", alignment=0.8, coupling=0.1),),
        ))
        assert (
            out.cell_peers[0].classification
            is PeerSubstrateClassification.COUPLING_DEGRADED
        )

    def test_mixed(self) -> None:
        out = self.i.interpret(_report(
            cells=(_digest("c1", alignment=0.5, coupling=0.5),),
        ))
        assert (
            out.cell_peers[0].classification
            is PeerSubstrateClassification.MIXED
        )

    def test_insufficient_data(self) -> None:
        out = self.i.interpret(_report(
            cells=(_digest("c1", obs_count=1),),
        ))
        assert (
            out.cell_peers[0].classification
            is PeerSubstrateClassification.INSUFFICIENT_DATA
        )

class TestClusterMode:
    def setup_method(self) -> None:
        self.i = CrossEntityStateInterpreter()

    def test_empty_cluster_unclassifiable(self) -> None:
        out = self.i.interpret(_report())
        assert out.cell_cluster_mode is ClusterMode.UNCLASSIFIABLE
        assert out.node_cluster_mode is ClusterMode.UNCLASSIFIABLE

    def test_sparse_cluster(self) -> None:
        out = self.i.interpret(_report(
            cells=(_digest("c1", alignment=0.85, coupling=0.7),),
        ))
        # Only 1 cell peer, cohesion_min_peers default = 2 → SPARSE
        assert out.cell_cluster_mode is ClusterMode.SPARSE

    def test_coherent_aligned(self) -> None:
        out = self.i.interpret(_report(
            cells=(
                _digest("c1", alignment=0.85, coupling=0.7),
                _digest("c2", alignment=0.9, coupling=0.8),
            ),
        ))
        assert out.cell_cluster_mode is ClusterMode.COHERENT_ALIGNED
        assert out.has_cell_alignment

    def test_coherent_misaligned(self) -> None:
        out = self.i.interpret(_report(
            cells=(
                _digest("c1", alignment=0.2, coupling=0.5),
                _digest("c2", alignment=0.1, coupling=0.5),
            ),
        ))
        assert out.cell_cluster_mode is ClusterMode.COHERENT_MISALIGNED

    def test_fragmented(self) -> None:
        out = self.i.interpret(_report(
            cells=(
                _digest("c1", alignment=0.85, coupling=0.7),
                _digest("c2", alignment=0.2, coupling=0.5),
            ),
        ))
        assert out.cell_cluster_mode is ClusterMode.FRAGMENTED

class TestScaleSeparation:
    def test_cell_and_node_clusters_separate(self) -> None:
        i = CrossEntityStateInterpreter()
        out = i.interpret(_report(
            cells=(
                _digest("c1", alignment=0.85, coupling=0.7),
                _digest("c2", alignment=0.9, coupling=0.8),
            ),
            nodes=(
                _digest(
                    "n1",
                    scope=ObservationScope.NODE,
                    alignment=0.2,
                    coupling=0.5,
                ),
                _digest(
                    "n2",
                    scope=ObservationScope.NODE,
                    alignment=0.1,
                    coupling=0.5,
                ),
            ),
        ))
        assert out.cell_cluster_mode is ClusterMode.COHERENT_ALIGNED
        assert out.node_cluster_mode is ClusterMode.COHERENT_MISALIGNED

class TestEdgeCases:
    def test_empty_observer_rejected(self) -> None:
        i = CrossEntityStateInterpreter()
        with pytest.raises(ValueError, match="observer_id"):
            i.interpret(_report(observer=""))

    def test_default_config_singleton(self) -> None:
        assert (
            DEFAULT_CROSS_ENTITY_INTERPRETER_CONFIG.aligned_alignment_min
            == 0.7
        )
