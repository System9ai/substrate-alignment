"""Cross-entity state-signal observer

Pure-logic primitive aggregating a stream of peer substrate-state
observations into a :class:`CrossEntityObservationReport`. **Scale-
aware**: each :class:`PeerStateObservation` carries an
:class:`ObservationScope` distinguishing observations of an individual
peer **cell** (physical, replicable) from observations of a peer
**node**'s aggregate (logical, persistent face of the cell cluster).

the host application hierarchy is enforced at the observation surface:

* Observing a cell → ``peer_scope=ObservationScope.CELL`` and
  ``peer_id=cell_id``.
* Observing a node's aggregate → ``peer_scope=ObservationScope.NODE``
  and ``peer_id=node_id``.

The :class:`CrossEntityObservationReport` keeps cell-level and
node-level peer digests **separated**, so substrate condition #3
(multi-scale alignment) is preserved end-to-end.

Pure logic
==========

* No DAO, no LLM, no network. Observations are caller-supplied.
* Honest uncertainty: empty observation set surfaces an empty digest
  with explicit rationale; the observer never fabricates aggregate
  state.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import mean
from typing import Dict, Final, Mapping, Optional, Tuple

class ObservationScope(str, Enum):
    """Which scale of the host application entity hierarchy is being observed."""

    CELL = "cell"
    NODE = "node"

@dataclass(frozen=True, slots=True)
class PeerStateObservation:  # pylint: disable=too-many-instance-attributes
    """One observation of a peer's substrate state at a moment in time."""

    sequence: int
    timestamp: int
    observer_id: str
    peer_id: str
    peer_scope: ObservationScope
    alignment_score: float
    health_score: float
    coupling_field_strength: float
    primary_signal_kinds: Tuple[str, ...] = ()
    observation_quality: float = 1.0

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if not self.observer_id:
            raise ValueError("observer_id must be non-empty")
        if not self.peer_id:
            raise ValueError("peer_id must be non-empty")
        if self.observer_id == self.peer_id:
            raise ValueError("observer_id and peer_id must differ")
        if not 0.0 <= self.alignment_score <= 1.0:
            raise ValueError("alignment_score must be in [0, 1]")
        if not 0.0 <= self.health_score <= 1.0:
            raise ValueError("health_score must be in [0, 1]")
        if not 0.0 <= self.coupling_field_strength <= 1.0:
            raise ValueError("coupling_field_strength must be in [0, 1]")
        if not 0.0 <= self.observation_quality <= 1.0:
            raise ValueError("observation_quality must be in [0, 1]")

@dataclass(frozen=True, slots=True)
class PeerStateDigest:  # pylint: disable=too-many-instance-attributes
    """Aggregate digest of all observations of one peer."""

    peer_id: str
    peer_scope: ObservationScope
    observation_count: int
    latest_timestamp: int
    avg_alignment: float
    avg_health: float
    avg_coupling: float
    signal_kind_frequencies: Mapping[str, int]
    average_quality: float
    rationale: str

    @property
    def is_cell_scope(self) -> bool:
        """True iff this digest is for a peer cell (physical)."""
        return self.peer_scope is ObservationScope.CELL

    @property
    def is_node_scope(self) -> bool:
        """True iff this digest is for a peer node (logical aggregate)."""
        return self.peer_scope is ObservationScope.NODE

@dataclass(frozen=True, slots=True)
class CrossEntityObservationReport:
    """Aggregate observer result for one observer."""

    observer_id: str
    cell_peers: Tuple[PeerStateDigest, ...]
    node_peers: Tuple[PeerStateDigest, ...]
    total_observation_count: int
    rationale: str

    def digest_for(self, peer_id: str) -> Optional[PeerStateDigest]:
        """Return the digest for any peer regardless of scope."""
        for d in self.cell_peers:
            if d.peer_id == peer_id:
                return d
        for d in self.node_peers:
            if d.peer_id == peer_id:
                return d
        return None

    @property
    def cell_peer_count(self) -> int:
        """Number of distinct cell peers observed."""
        return len(self.cell_peers)

    @property
    def node_peer_count(self) -> int:
        """Number of distinct node peers observed."""
        return len(self.node_peers)

@dataclass(frozen=True, slots=True)
class CrossEntityObserverConfig:
    """Tunable thresholds (currently informational)."""

    quality_threshold: float = 0.3

    def __post_init__(self) -> None:
        if not 0.0 < self.quality_threshold <= 1.0:
            raise ValueError("quality_threshold must be in (0, 1]")

DEFAULT_CROSS_ENTITY_OBSERVER_CONFIG: Final[CrossEntityObserverConfig] = (
    CrossEntityObserverConfig()
)

class CrossEntityStateSignalObserver:  # pylint: disable=too-few-public-methods
    """Pure-logic cross-entity peer-state observer."""

    def __init__(
        self,
        *,
        config: CrossEntityObserverConfig = (
            DEFAULT_CROSS_ENTITY_OBSERVER_CONFIG
        ),
    ) -> None:
        self._config = config

    def observe(
        self,
        observer_id: str,
        observations: Tuple[PeerStateObservation, ...],
    ) -> CrossEntityObservationReport:
        """Aggregate peer observations into a scale-separated report."""
        if not observer_id:
            raise ValueError("observer_id must be non-empty")
        relevant = tuple(
            o for o in observations
            if o.observer_id == observer_id
            and o.observation_quality >= self._config.quality_threshold
        )
        if not relevant:
            return CrossEntityObservationReport(
                observer_id=observer_id,
                cell_peers=(),
                node_peers=(),
                total_observation_count=0,
                rationale=(
                    f"no observations meeting quality threshold "
                    f">= {self._config.quality_threshold}"
                ),
            )
        # Partition by scope, then group by peer_id within each scope.
        grouped: Dict[
            Tuple[ObservationScope, str], list[PeerStateObservation]
        ] = {}
        for obs in relevant:
            grouped.setdefault((obs.peer_scope, obs.peer_id), []).append(obs)
        cell_digests: list[PeerStateDigest] = []
        node_digests: list[PeerStateDigest] = []
        for (scope, peer_id), items in grouped.items():
            digest = self._digest(peer_id, scope, items)
            if scope is ObservationScope.CELL:
                cell_digests.append(digest)
            else:
                node_digests.append(digest)
        cell_digests.sort(key=lambda d: d.peer_id)
        node_digests.sort(key=lambda d: d.peer_id)
        rationale = (
            f"observer={observer_id} cell_peers={len(cell_digests)} "
            f"node_peers={len(node_digests)} obs={len(relevant)}"
        )
        return CrossEntityObservationReport(
            observer_id=observer_id,
            cell_peers=tuple(cell_digests),
            node_peers=tuple(node_digests),
            total_observation_count=len(relevant),
            rationale=rationale,
        )

    @staticmethod
    def _digest(
        peer_id: str,
        scope: ObservationScope,
        items: list[PeerStateObservation],
    ) -> PeerStateDigest:
        avg_alignment = mean(o.alignment_score for o in items)
        avg_health = mean(o.health_score for o in items)
        avg_coupling = mean(o.coupling_field_strength for o in items)
        avg_quality = mean(o.observation_quality for o in items)
        latest = max(o.timestamp for o in items)
        freq: Dict[str, int] = {}
        for o in items:
            for kind in o.primary_signal_kinds:
                freq[kind] = freq.get(kind, 0) + 1
        return PeerStateDigest(
            peer_id=peer_id,
            peer_scope=scope,
            observation_count=len(items),
            latest_timestamp=latest,
            avg_alignment=avg_alignment,
            avg_health=avg_health,
            avg_coupling=avg_coupling,
            signal_kind_frequencies=freq,
            average_quality=avg_quality,
            rationale=(
                f"peer={peer_id} scope={scope.value} obs={len(items)} "
                f"alignment={avg_alignment:.3f} coupling={avg_coupling:.3f}"
            ),
        )

__all__ = [
    "DEFAULT_CROSS_ENTITY_OBSERVER_CONFIG",
    "CrossEntityObservationReport",
    "CrossEntityObserverConfig",
    "CrossEntityStateSignalObserver",
    "ObservationScope",
    "PeerStateDigest",
    "PeerStateObservation",
]
