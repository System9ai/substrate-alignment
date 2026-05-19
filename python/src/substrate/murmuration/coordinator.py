"""Murmuration coordinator

Pure-logic substrate-mechanical primitive implementing the **three
local rules** that produce emergent collective coordination via
mutual observation

* **Alignment** — match peers' substrate-mode-vector.
* **Separation** — preserve own bounded-context substrate-state.
* **Cohesion** — stay near substrate-aligned peers.

Per Trevor's articulation, sustained mutual observation between
bounded-context peers (Dunbar-class group sizes — 7, 12, 24) produces
emergent civilizational substrate-mode at platform scale.

Pure logic
==========

* No DAO, no LLM, no network.
* Honest uncertainty: an empty peer set surfaces every rule as a
  no-op with explicit rationale.
* Frozen dataclasses with slots throughout.
* Caller supplies own current mode-vector (scalar) and peer
  observations; the coordinator returns suggested deltas for each
  rule the caller can apply or ignore.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import mean
from typing import Final, Optional, Tuple

class MurmurationRule(str, Enum):
    """The three local-rules forming murmuration coordination."""

    ALIGNMENT = "alignment"
    SEPARATION = "separation"
    COHESION = "cohesion"

@dataclass(frozen=True, slots=True)
class PeerObservation:
    """One observed substrate-aware peer."""

    peer_id: str
    substrate_mode_vector: float
    substrate_state_score: float
    proximity: float
    substrate_aligned: bool

    def __post_init__(self) -> None:
        if not self.peer_id:
            raise ValueError("peer_id must be non-empty")
        if not 0.0 <= self.substrate_mode_vector <= 1.0:
            raise ValueError(
                "substrate_mode_vector must be in [0, 1]"
            )
        if not 0.0 <= self.substrate_state_score <= 1.0:
            raise ValueError("substrate_state_score must be in [0, 1]")
        if not 0.0 <= self.proximity <= 1.0:
            raise ValueError("proximity must be in [0, 1]")

@dataclass(frozen=True, slots=True)
class RuleUpdate:
    """Per-rule suggested adjustment for the agent's substrate-mode-vector."""

    rule: MurmurationRule
    suggested_delta: float
    rationale: str
    triggered_peer_count: int

@dataclass(frozen=True, slots=True)
class MurmurationReport:
    """Aggregate coordinator output for one tick."""

    own_id: str
    updates: Tuple[RuleUpdate, ...]
    bounded_peer_count: int
    rationale: str

    def by_rule(self, rule: MurmurationRule) -> Optional[RuleUpdate]:
        """Lookup the update for one rule."""
        for u in self.updates:
            if u.rule is rule:
                return u
        return None

    @property
    def composite_delta(self) -> float:
        """Sum of all suggested deltas — caller can apply or ignore."""
        return sum(u.suggested_delta for u in self.updates)

@dataclass(frozen=True, slots=True)
class MurmurationConfig:
    """Tunable thresholds for the three rules."""

    bounded_peer_max: int = 12
    alignment_step: float = 0.1
    separation_proximity_threshold: float = 0.85
    separation_step: float = -0.05
    cohesion_step: float = 0.05
    cohesion_min_aligned_peers: int = 2

    def __post_init__(self) -> None:
        if self.bounded_peer_max < 1:
            raise ValueError("bounded_peer_max must be >= 1")
        if not 0.0 < self.alignment_step <= 1.0:
            raise ValueError("alignment_step must be in (0, 1]")
        if not 0.0 < self.separation_proximity_threshold <= 1.0:
            raise ValueError(
                "separation_proximity_threshold must be in (0, 1]"
            )
        if self.separation_step >= 0:
            raise ValueError("separation_step must be < 0")
        if not 0.0 < self.cohesion_step <= 1.0:
            raise ValueError("cohesion_step must be in (0, 1]")
        if self.cohesion_min_aligned_peers < 1:
            raise ValueError("cohesion_min_aligned_peers must be >= 1")

DEFAULT_MURMURATION_CONFIG: Final[MurmurationConfig] = MurmurationConfig()

class MurmurationCoordinator:  # pylint: disable=too-few-public-methods
    """Pure-logic murmuration coordinator."""

    def __init__(
        self, *, config: MurmurationConfig = DEFAULT_MURMURATION_CONFIG,
    ) -> None:
        self._config = config

    def coordinate(
        self,
        own_id: str,
        own_mode_vector: float,
        peers: Tuple[PeerObservation, ...],
    ) -> MurmurationReport:
        """Apply the three rules and return suggested updates."""
        if not own_id:
            raise ValueError("own_id must be non-empty")
        if not 0.0 <= own_mode_vector <= 1.0:
            raise ValueError("own_mode_vector must be in [0, 1]")
        bounded = peers[: self._config.bounded_peer_max]
        updates = (
            self._alignment_rule(own_mode_vector, bounded),
            self._separation_rule(bounded),
            self._cohesion_rule(own_mode_vector, bounded),
        )
        rationale = (
            f"bounded_peers={len(bounded)} (max="
            f"{self._config.bounded_peer_max}); "
            + "; ".join(f"{u.rule.value}={u.suggested_delta:+.3f}" for u in updates)
        )
        return MurmurationReport(
            own_id=own_id,
            updates=updates,
            bounded_peer_count=len(bounded),
            rationale=rationale,
        )

    def _alignment_rule(
        self,
        own_mode_vector: float,
        peers: Tuple[PeerObservation, ...],
    ) -> RuleUpdate:
        if not peers:
            return RuleUpdate(
                rule=MurmurationRule.ALIGNMENT,
                suggested_delta=0.0,
                rationale="no peers observed; alignment no-op",
                triggered_peer_count=0,
            )
        target = mean(p.substrate_mode_vector for p in peers)
        diff = target - own_mode_vector
        step = self._config.alignment_step
        delta = max(-step, min(step, diff))
        return RuleUpdate(
            rule=MurmurationRule.ALIGNMENT,
            suggested_delta=delta,
            rationale=(
                f"peer_mode_mean={target:.3f}, own={own_mode_vector:.3f}, "
                f"nudge={delta:+.3f}"
            ),
            triggered_peer_count=len(peers),
        )

    def _separation_rule(
        self, peers: Tuple[PeerObservation, ...],
    ) -> RuleUpdate:
        threshold = self._config.separation_proximity_threshold
        crowding = [p for p in peers if p.proximity >= threshold]
        if not crowding:
            return RuleUpdate(
                rule=MurmurationRule.SEPARATION,
                suggested_delta=0.0,
                rationale=(
                    f"no peers above proximity threshold {threshold}; "
                    "separation no-op"
                ),
                triggered_peer_count=0,
            )
        return RuleUpdate(
            rule=MurmurationRule.SEPARATION,
            suggested_delta=self._config.separation_step,
            rationale=(
                f"{len(crowding)} peers above proximity threshold "
                f"{threshold}; separating"
            ),
            triggered_peer_count=len(crowding),
        )

    def _cohesion_rule(
        self,
        own_mode_vector: float,
        peers: Tuple[PeerObservation, ...],
    ) -> RuleUpdate:
        aligned = [p for p in peers if p.substrate_aligned]
        if len(aligned) < self._config.cohesion_min_aligned_peers:
            return RuleUpdate(
                rule=MurmurationRule.COHESION,
                suggested_delta=0.0,
                rationale=(
                    f"aligned_peers={len(aligned)} < "
                    f"{self._config.cohesion_min_aligned_peers}; "
                    "cohesion no-op"
                ),
                triggered_peer_count=len(aligned),
            )
        centroid = mean(p.substrate_mode_vector for p in aligned)
        diff = centroid - own_mode_vector
        step = self._config.cohesion_step
        delta = max(-step, min(step, diff))
        return RuleUpdate(
            rule=MurmurationRule.COHESION,
            suggested_delta=delta,
            rationale=(
                f"aligned_centroid={centroid:.3f}, own={own_mode_vector:.3f}, "
                f"cohesion_nudge={delta:+.3f}"
            ),
            triggered_peer_count=len(aligned),
        )

__all__ = [
    "DEFAULT_MURMURATION_CONFIG",
    "MurmurationConfig",
    "MurmurationCoordinator",
    "MurmurationReport",
    "MurmurationRule",
    "PeerObservation",
    "RuleUpdate",
]
