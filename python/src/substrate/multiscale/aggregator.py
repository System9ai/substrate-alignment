"""Multi-scale substrate-state aggregator — substrate condition #3.

Pure-logic primitive making the **the host application entity hierarchy** explicit
in code, per substrate condition #3 (multi-scale alignment
architecture). The hierarchy:

* **Cell** (physical, replicable, ``cell_id``) — one running
  the host application instance. Holds its own state. Replication and placement
  operate here.
* **Node** (logical, persistent, ``node_id`` = cryptographic
  identity) — the substrate "face" peer entities see. Aggregates
  1..N cells (which may span cloud / region / service-group). The
  identity that survives cell replacement.
* **Org** (optional, ``org_id``) — the organizational scale at which
  substrate-aligned mode emerges as a civilizational property.

The biology analogy:

``cell → tissue/organ → organism``

Substrate-state intelligence emerges at each scale: individual cells
have alignment; nodes have aggregate alignment + emergent coherence
from cell coordination; orgs have civilizational alignment.

What this primitive does
========================

* :meth:`aggregate_to_node` — folds a sequence of
  :class:`CellSubstrateObservation` records (one per cell) into a
  :class:`NodeAggregatedState`. Weighted-mean alignment, cell
  coherence (how aligned cells are with each other), pattern-cell
  fraction, NPG-positive rate.
* :meth:`aggregate_to_org` — folds a sequence of
  :class:`NodeAggregatedState` records into an
  :class:`OrgAggregatedState` at the next scale.
* :meth:`cells_by_node` — groups observations by ``node_id`` so
  callers can roll up per-node without writing the partitioning by
  hand.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the cell observations;
  this primitive does the aggregation.
* Honest uncertainty: empty cell sets surface as ``cell_count=0`` and
  an explicit rationale; the aggregator never invents a node-level
  alignment from nothing.
* Frozen dataclasses with slots throughout.
* **Cell→node binding enforced.** :meth:`aggregate_to_node` rejects
  observations whose ``node_id`` does not match the target node — the
  primitive will not silently mix substrate state across nodes.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import mean, pstdev
from typing import Dict, Final, Tuple

class SubstrateScale(str, Enum):
    """The three scales in the the host application substrate hierarchy."""

    CELL = "cell"
    NODE = "node"
    ORG = "org"

@dataclass(frozen=True, slots=True)
class CellSubstrateObservation:  # pylint: disable=too-many-instance-attributes
    """One cell's substrate state at a point in time.

    Cells are **physical, replicable** instances of the the host application
    application. A cell is uniquely identified by ``cell_id`` and
    belongs to exactly one node via ``node_id``.
    """

    cell_id: str
    node_id: str
    timestamp: int
    alignment_score: float
    health_score: float
    npg_positive_rate: float
    sin_present: bool
    intercept_count: int
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.cell_id:
            raise ValueError("cell_id must be non-empty")
        if not self.node_id:
            raise ValueError("node_id must be non-empty")
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if not 0.0 <= self.alignment_score <= 1.0:
            raise ValueError("alignment_score must be in [0, 1]")
        if not 0.0 <= self.health_score <= 1.0:
            raise ValueError("health_score must be in [0, 1]")
        if not 0.0 <= self.npg_positive_rate <= 1.0:
            raise ValueError("npg_positive_rate must be in [0, 1]")
        if self.intercept_count < 0:
            raise ValueError("intercept_count must be >= 0")
        if self.weight <= 0:
            raise ValueError("weight must be > 0")

@dataclass(frozen=True, slots=True)
class NodeAggregatedState:  # pylint: disable=too-many-instance-attributes
    """Node-level substrate state derived from a cell cluster.

    A node is **logical, persistent** — the substrate "face" peer
    entities see. Its substrate state is emergent from its cells, like
    tissue intelligence emerges from cells.
    """

    node_id: str
    scale: SubstrateScale
    cell_count: int
    aligned_cell_count: int
    aggregate_alignment_score: float
    aggregate_health_score: float
    aggregate_npg_positive_rate: float
    sin_cell_fraction: float
    cell_coherence: float
    total_intercept_count: int
    rationale: str

    @property
    def alignment_aligned(self) -> bool:
        """True iff aggregate_alignment_score is at or above 0.6."""
        return self.aggregate_alignment_score >= 0.6

@dataclass(frozen=True, slots=True)
class OrgAggregatedState:
    """Org-level substrate state derived from a node cluster.

    The civilizational scale — emergent from nodes the way nodes
    emerge from cells.
    """

    org_id: str
    scale: SubstrateScale
    node_count: int
    aligned_node_count: int
    aggregate_alignment_score: float
    node_coherence: float
    rationale: str

@dataclass(frozen=True, slots=True)
class MultiScaleAggregatorConfig:
    """Tunable thresholds for aggregation."""

    aligned_cell_threshold: float = 0.6
    aligned_node_threshold: float = 0.6
    min_cells_for_coherence: int = 2
    min_nodes_for_coherence: int = 2

    def __post_init__(self) -> None:
        if not 0.0 <= self.aligned_cell_threshold <= 1.0:
            raise ValueError("aligned_cell_threshold must be in [0, 1]")
        if not 0.0 <= self.aligned_node_threshold <= 1.0:
            raise ValueError("aligned_node_threshold must be in [0, 1]")
        if self.min_cells_for_coherence < 2:
            raise ValueError("min_cells_for_coherence must be >= 2")
        if self.min_nodes_for_coherence < 2:
            raise ValueError("min_nodes_for_coherence must be >= 2")

DEFAULT_MULTISCALE_AGGREGATOR_CONFIG: Final[MultiScaleAggregatorConfig] = (
    MultiScaleAggregatorConfig()
)

class MultiScaleSubstrateStateAggregator:  # pylint: disable=too-few-public-methods
    """Pure-logic multi-scale aggregator (substrate condition #3)."""

    def __init__(
        self,
        *,
        config: MultiScaleAggregatorConfig = (
            DEFAULT_MULTISCALE_AGGREGATOR_CONFIG
        ),
    ) -> None:
        self._config = config

    def aggregate_to_node(  # pylint: disable=too-many-locals
        self,
        node_id: str,
        cell_observations: Tuple[CellSubstrateObservation, ...],
    ) -> NodeAggregatedState:
        """Fold cell observations into a node-level substrate state."""
        if not node_id:
            raise ValueError("node_id must be non-empty")
        own = [o for o in cell_observations if o.node_id == node_id]
        mismatched = [o for o in cell_observations if o.node_id != node_id]
        if mismatched:
            raise ValueError(
                f"observations contain cells bound to other nodes: "
                f"{sorted({o.node_id for o in mismatched})!r}"
            )
        if not own:
            return NodeAggregatedState(
                node_id=node_id,
                scale=SubstrateScale.NODE,
                cell_count=0,
                aligned_cell_count=0,
                aggregate_alignment_score=0.0,
                aggregate_health_score=0.0,
                aggregate_npg_positive_rate=0.0,
                sin_cell_fraction=0.0,
                cell_coherence=0.0,
                total_intercept_count=0,
                rationale=f"no cells observed for node_id={node_id!r}",
            )
        cfg = self._config
        total_weight = sum(o.weight for o in own)
        alignment_avg = sum(
            o.alignment_score * o.weight for o in own
        ) / total_weight
        health_avg = sum(
            o.health_score * o.weight for o in own
        ) / total_weight
        npg_avg = sum(
            o.npg_positive_rate * o.weight for o in own
        ) / total_weight
        aligned_count = sum(
            1 for o in own if o.alignment_score >= cfg.aligned_cell_threshold
        )
        sin_count = sum(1 for o in own if o.sin_present)
        sin_fraction = sin_count / len(own)
        coherence = self._cell_coherence(own)
        intercept_total = sum(o.intercept_count for o in own)
        rationale = (
            f"node={node_id!r} cells={len(own)} aligned={aligned_count} "
            f"alignment={alignment_avg:.3f} health={health_avg:.3f} "
            f"npg+={npg_avg:.3f} sin_frac={sin_fraction:.3f} "
            f"coherence={coherence:.3f}"
        )
        return NodeAggregatedState(
            node_id=node_id,
            scale=SubstrateScale.NODE,
            cell_count=len(own),
            aligned_cell_count=aligned_count,
            aggregate_alignment_score=alignment_avg,
            aggregate_health_score=health_avg,
            aggregate_npg_positive_rate=npg_avg,
            sin_cell_fraction=sin_fraction,
            cell_coherence=coherence,
            total_intercept_count=intercept_total,
            rationale=rationale,
        )

    def aggregate_to_org(
        self,
        org_id: str,
        node_states: Tuple[NodeAggregatedState, ...],
    ) -> OrgAggregatedState:
        """Fold node-level states into an org-level substrate state."""
        if not org_id:
            raise ValueError("org_id must be non-empty")
        if not node_states:
            return OrgAggregatedState(
                org_id=org_id,
                scale=SubstrateScale.ORG,
                node_count=0,
                aligned_node_count=0,
                aggregate_alignment_score=0.0,
                node_coherence=0.0,
                rationale=f"no nodes observed for org_id={org_id!r}",
            )
        cfg = self._config
        alignment_avg = mean(
            n.aggregate_alignment_score for n in node_states
        )
        aligned_nodes = sum(
            1
            for n in node_states
            if n.aggregate_alignment_score >= cfg.aligned_node_threshold
        )
        coherence = self._node_coherence(node_states)
        return OrgAggregatedState(
            org_id=org_id,
            scale=SubstrateScale.ORG,
            node_count=len(node_states),
            aligned_node_count=aligned_nodes,
            aggregate_alignment_score=alignment_avg,
            node_coherence=coherence,
            rationale=(
                f"org={org_id!r} nodes={len(node_states)} "
                f"aligned={aligned_nodes} "
                f"alignment={alignment_avg:.3f} "
                f"coherence={coherence:.3f}"
            ),
        )

    @staticmethod
    def cells_by_node(
        cell_observations: Tuple[CellSubstrateObservation, ...],
    ) -> Dict[str, Tuple[CellSubstrateObservation, ...]]:
        """Group observations by ``node_id`` (deterministic, sorted within)."""
        groups: Dict[str, list[CellSubstrateObservation]] = {}
        for obs in cell_observations:
            groups.setdefault(obs.node_id, []).append(obs)
        return {
            node_id: tuple(sorted(items, key=lambda o: o.cell_id))
            for node_id, items in sorted(groups.items())
        }

    def _cell_coherence(
        self, observations: list[CellSubstrateObservation],
    ) -> float:
        if len(observations) < self._config.min_cells_for_coherence:
            return 1.0 if observations else 0.0
        scores = [o.alignment_score for o in observations]
        avg = abs(mean(scores))
        stdev = pstdev(scores)
        if avg == 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - stdev / (avg + 1e-9)))

    def _node_coherence(
        self, node_states: Tuple[NodeAggregatedState, ...],
    ) -> float:
        if len(node_states) < self._config.min_nodes_for_coherence:
            return 1.0 if node_states else 0.0
        scores = [n.aggregate_alignment_score for n in node_states]
        avg = abs(mean(scores))
        stdev = pstdev(scores)
        if avg == 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - stdev / (avg + 1e-9)))

__all__ = [
    "DEFAULT_MULTISCALE_AGGREGATOR_CONFIG",
    "CellSubstrateObservation",
    "MultiScaleAggregatorConfig",
    "MultiScaleSubstrateStateAggregator",
    "NodeAggregatedState",
    "OrgAggregatedState",
    "SubstrateScale",
]
