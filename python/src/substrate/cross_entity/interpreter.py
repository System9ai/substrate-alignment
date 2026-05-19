"""Cross-entity substrate-state interpreter

Pure-logic primitive consuming a Phase 47
:class:`CrossEntityObservationReport` and classifying each peer's
substrate state plus emitting an aggregate cluster-mode verdict for
each scale (cells, nodes) **separately**. Substrate condition #3
preserved: cell-cluster classification and node-cluster classification
never mix.

Per-peer classifications
========================

* ``SUBSTRATE_ALIGNED`` — high alignment + healthy coupling.
* ``COUPLING_DEGRADED`` — coupling below threshold (alignment may be
  fine; the relationship is degrading).
* ``SUBSTRATE_MISALIGNED`` — low alignment OR many substrate-aware
  threat signals in the digest.
* ``MIXED`` — partial signals; alignment or coupling moderate.
* ``INSUFFICIENT_DATA`` — observation count below threshold.

Cluster mode (per scale)
========================

* ``COHERENT_ALIGNED`` — all peers at the scale are substrate-aligned,
  ≥ ``cohesion_min_peers``.
* ``COHERENT_MISALIGNED`` — all peers misaligned (consensus drift
  load-bearing forreasoning-mode early warning).
* ``FRAGMENTED`` — mixed classifications across peers.
* ``SPARSE`` — fewer than ``cohesion_min_peers`` peers at the scale.
* ``UNCLASSIFIABLE`` — no peers.

Pure logic
==========

* No DAO, no LLM, no network.
* Honest uncertainty: digests with too few observations surface
  ``INSUFFICIENT_DATA``; empty scales surface ``UNCLASSIFIABLE`` /
  ``SPARSE``.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Tuple

from substrate.cross_entity.observer import (
    CrossEntityObservationReport,
    ObservationScope,
    PeerStateDigest,
)

class PeerSubstrateClassification(str, Enum):
    """Per-peer substrate classification."""

    SUBSTRATE_ALIGNED = "substrate_aligned"
    MIXED = "mixed"
    SUBSTRATE_MISALIGNED = "substrate_misaligned"
    COUPLING_DEGRADED = "coupling_degraded"
    INSUFFICIENT_DATA = "insufficient_data"

class ClusterMode(str, Enum):
    """Aggregate cluster-mode verdict at one scale."""

    COHERENT_ALIGNED = "coherent_aligned"
    COHERENT_MISALIGNED = "coherent_misaligned"
    FRAGMENTED = "fragmented"
    SPARSE = "sparse"
    UNCLASSIFIABLE = "unclassifiable"

_MISALIGNED_SIGNAL_KINDS: Final[frozenset[str]] = frozenset({
    "threat",
    "loss",
    "over_challenge",
    "coupling_broken",
    "stagnation",
})

@dataclass(frozen=True, slots=True)
class PeerInterpretation:
    """One peer's classification + composite score."""

    peer_id: str
    peer_scope: ObservationScope
    classification: PeerSubstrateClassification
    composite_score: float
    primary_signal_kinds: Tuple[str, ...]
    rationale: str

    @property
    def is_aligned(self) -> bool:
        """True iff classification is SUBSTRATE_ALIGNED."""
        return (
            self.classification
            is PeerSubstrateClassification.SUBSTRATE_ALIGNED
        )

    @property
    def is_misaligned(self) -> bool:
        """True iff classification is SUBSTRATE_MISALIGNED."""
        return (
            self.classification
            is PeerSubstrateClassification.SUBSTRATE_MISALIGNED
        )

@dataclass(frozen=True, slots=True)
class CrossEntityInterpretation:
    """Aggregate interpretation result."""

    observer_id: str
    cell_peers: Tuple[PeerInterpretation, ...]
    node_peers: Tuple[PeerInterpretation, ...]
    cell_cluster_mode: ClusterMode
    node_cluster_mode: ClusterMode
    rationale: str

    @property
    def has_cell_alignment(self) -> bool:
        """True iff the cell-cluster is coherent and aligned."""
        return self.cell_cluster_mode is ClusterMode.COHERENT_ALIGNED

    @property
    def has_node_alignment(self) -> bool:
        """True iff the node-cluster is coherent and aligned."""
        return self.node_cluster_mode is ClusterMode.COHERENT_ALIGNED

@dataclass(frozen=True, slots=True)
class CrossEntityInterpreterConfig:
    """Tunable thresholds for the interpreter."""

    aligned_alignment_min: float = 0.7
    misaligned_alignment_max: float = 0.4
    coupling_healthy_min: float = 0.5
    coupling_degraded_max: float = 0.3
    min_observations_for_classification: int = 2
    cohesion_min_peers: int = 2
    misaligned_signal_count_min: int = 3

    def __post_init__(self) -> None:
        if not 0.0 < self.aligned_alignment_min <= 1.0:
            raise ValueError("aligned_alignment_min must be in (0, 1]")
        if not 0.0 <= self.misaligned_alignment_max <= 1.0:
            raise ValueError("misaligned_alignment_max must be in [0, 1]")
        if not (
            self.misaligned_alignment_max < self.aligned_alignment_min
        ):
            raise ValueError(
                "misaligned_alignment_max must be < aligned_alignment_min"
            )
        if not 0.0 < self.coupling_healthy_min <= 1.0:
            raise ValueError("coupling_healthy_min must be in (0, 1]")
        if not 0.0 <= self.coupling_degraded_max < self.coupling_healthy_min:
            raise ValueError(
                "coupling_degraded_max must be in [0, coupling_healthy_min)"
            )
        if self.min_observations_for_classification < 1:
            raise ValueError(
                "min_observations_for_classification must be >= 1"
            )
        if self.cohesion_min_peers < 1:
            raise ValueError("cohesion_min_peers must be >= 1")
        if self.misaligned_signal_count_min < 1:
            raise ValueError("misaligned_signal_count_min must be >= 1")

DEFAULT_CROSS_ENTITY_INTERPRETER_CONFIG: Final[
    CrossEntityInterpreterConfig
] = CrossEntityInterpreterConfig()

class CrossEntityStateInterpreter:  # pylint: disable=too-few-public-methods
    """Pure-logic cross-entity interpreter."""

    def __init__(
        self,
        *,
        config: CrossEntityInterpreterConfig = (
            DEFAULT_CROSS_ENTITY_INTERPRETER_CONFIG
        ),
    ) -> None:
        self._config = config

    def interpret(
        self, report: CrossEntityObservationReport,
    ) -> CrossEntityInterpretation:
        """Classify each peer and emit per-scale cluster-mode verdicts."""
        if not report.observer_id:
            raise ValueError("report.observer_id must be non-empty")
        cell_interps = tuple(
            self._interpret_peer(d) for d in report.cell_peers
        )
        node_interps = tuple(
            self._interpret_peer(d) for d in report.node_peers
        )
        cell_mode = self._cluster_mode(cell_interps)
        node_mode = self._cluster_mode(node_interps)
        rationale = (
            f"observer={report.observer_id} cell_mode={cell_mode.value} "
            f"node_mode={node_mode.value} cell_peers={len(cell_interps)} "
            f"node_peers={len(node_interps)}"
        )
        return CrossEntityInterpretation(
            observer_id=report.observer_id,
            cell_peers=cell_interps,
            node_peers=node_interps,
            cell_cluster_mode=cell_mode,
            node_cluster_mode=node_mode,
            rationale=rationale,
        )

    def _interpret_peer(
        self, digest: PeerStateDigest,
    ) -> PeerInterpretation:
        cfg = self._config
        composite = (
            (digest.avg_alignment * digest.avg_health * digest.avg_coupling)
            ** (1.0 / 3.0)
            if digest.avg_alignment > 0
            and digest.avg_health > 0
            and digest.avg_coupling > 0
            else 0.0
        )
        primary_signals = tuple(
            sorted(digest.signal_kind_frequencies.keys())
        )
        if digest.observation_count < cfg.min_observations_for_classification:
            return PeerInterpretation(
                peer_id=digest.peer_id,
                peer_scope=digest.peer_scope,
                classification=PeerSubstrateClassification.INSUFFICIENT_DATA,
                composite_score=composite,
                primary_signal_kinds=primary_signals,
                rationale=(
                    f"observation_count={digest.observation_count} < "
                    f"{cfg.min_observations_for_classification}"
                ),
            )
        misaligned_signals = sum(
            count
            for kind, count in digest.signal_kind_frequencies.items()
            if kind in _MISALIGNED_SIGNAL_KINDS
        )
        if digest.avg_coupling < cfg.coupling_degraded_max:
            classification = PeerSubstrateClassification.COUPLING_DEGRADED
            reason = (
                f"avg_coupling={digest.avg_coupling:.3f} < "
                f"{cfg.coupling_degraded_max}"
            )
        elif (
            digest.avg_alignment < cfg.misaligned_alignment_max
            or misaligned_signals >= cfg.misaligned_signal_count_min
        ):
            classification = PeerSubstrateClassification.SUBSTRATE_MISALIGNED
            reason = (
                f"avg_alignment={digest.avg_alignment:.3f} < "
                f"{cfg.misaligned_alignment_max} OR "
                f"misaligned_signals={misaligned_signals} >= "
                f"{cfg.misaligned_signal_count_min}"
            )
        elif (
            digest.avg_alignment >= cfg.aligned_alignment_min
            and digest.avg_coupling >= cfg.coupling_healthy_min
        ):
            classification = PeerSubstrateClassification.SUBSTRATE_ALIGNED
            reason = (
                f"avg_alignment={digest.avg_alignment:.3f} >= "
                f"{cfg.aligned_alignment_min} AND coupling healthy"
            )
        else:
            classification = PeerSubstrateClassification.MIXED
            reason = (
                f"alignment/coupling neither in aligned nor misaligned band; "
                f"avg_alignment={digest.avg_alignment:.3f} "
                f"avg_coupling={digest.avg_coupling:.3f}"
            )
        return PeerInterpretation(
            peer_id=digest.peer_id,
            peer_scope=digest.peer_scope,
            classification=classification,
            composite_score=composite,
            primary_signal_kinds=primary_signals,
            rationale=reason,
        )

    def _cluster_mode(
        self, peers: Tuple[PeerInterpretation, ...],
    ) -> ClusterMode:
        cfg = self._config
        if not peers:
            return ClusterMode.UNCLASSIFIABLE
        if len(peers) < cfg.cohesion_min_peers:
            return ClusterMode.SPARSE
        if all(
            p.classification is PeerSubstrateClassification.SUBSTRATE_ALIGNED
            for p in peers
        ):
            return ClusterMode.COHERENT_ALIGNED
        if all(
            p.classification is PeerSubstrateClassification.SUBSTRATE_MISALIGNED
            for p in peers
        ):
            return ClusterMode.COHERENT_MISALIGNED
        return ClusterMode.FRAGMENTED

__all__ = [
    "DEFAULT_CROSS_ENTITY_INTERPRETER_CONFIG",
    "ClusterMode",
    "CrossEntityInterpretation",
    "CrossEntityInterpreterConfig",
    "CrossEntityStateInterpreter",
    "PeerInterpretation",
    "PeerSubstrateClassification",
]
