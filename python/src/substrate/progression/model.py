"""Per-entity progression value model.

Pure-logic value types. Cells, nodes, and orgs each carry their own
:class:`SubstrateStateTrajectoryProgression` instance; a host persistence
layer stores the snapshots.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

class EntityLayer(str, Enum):
    """The substrate hierarchy scale of the progressing entity."""

    CELL = "cell"
    NODE = "node"
    ORG = "org"

ENTITY_LAYERS: Final[frozenset[str]] = frozenset(
    layer.value for layer in EntityLayer
)

@dataclass(frozen=True, slots=True)
class ConsolidationTier:
    """One discrete tier-consolidation level."""

    tier_id: str
    tier_name: str
    tier_index: int
    threshold_quantity: float
    capabilities_unlocked: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.tier_id:
            raise ValueError("tier_id must be non-empty")
        if not self.tier_name:
            raise ValueError("tier_name must be non-empty")
        if self.tier_index < 0:
            raise ValueError("tier_index must be >= 0")
        if self.threshold_quantity < 0:
            raise ValueError("threshold_quantity must be >= 0")

@dataclass(frozen=True, slots=True)
class ConsolidationEvent:
    """One historical tier-consolidation event."""

    event_id: str
    from_tier_index: int
    to_tier_index: int
    transitioned_at_epoch: float
    progress_at_transition: float

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must be non-empty")
        if self.from_tier_index < 0:
            raise ValueError("from_tier_index must be >= 0")
        if self.to_tier_index <= self.from_tier_index:
            raise ValueError(
                "to_tier_index must exceed from_tier_index"
            )
        if self.transitioned_at_epoch < 0:
            raise ValueError(
                "transitioned_at_epoch must be >= 0"
            )
        if self.progress_at_transition < 0:
            raise ValueError(
                "progress_at_transition must be >= 0"
            )

@dataclass(frozen=True, slots=True)
class StreakState:
    """Current sustained-iteration marker."""

    streak_kind: str
    consecutive_count: int
    last_increment_at_epoch: float

    def __post_init__(self) -> None:
        if not self.streak_kind:
            raise ValueError("streak_kind must be non-empty")
        if self.consecutive_count < 0:
            raise ValueError("consecutive_count must be >= 0")
        if self.last_increment_at_epoch < 0:
            raise ValueError(
                "last_increment_at_epoch must be >= 0"
            )

    @property
    def active(self) -> bool:
        """True iff the streak has at least one increment."""
        return self.consecutive_count > 0

@dataclass(frozen=True, slots=True)
class AchievementRef:
    """Pointer to one specific accumulated-progress acquisition."""

    achievement_id: str
    achievement_name: str
    earned_at_epoch: float

    def __post_init__(self) -> None:
        if not self.achievement_id:
            raise ValueError("achievement_id must be non-empty")
        if not self.achievement_name:
            raise ValueError("achievement_name must be non-empty")
        if self.earned_at_epoch < 0:
            raise ValueError("earned_at_epoch must be >= 0")

@dataclass(frozen=True, slots=True)
class SubstrateStateTrajectoryProgression:  # pylint: disable=too-many-instance-attributes
    """Per-entity progression snapshot."""

    entity_id: str
    entity_layer: EntityLayer
    current_tier_index: int
    accumulated_progress_quantity: float
    progress_to_next_tier: float
    consolidation_history: tuple[ConsolidationEvent, ...]
    streak_state: StreakState
    achievements_earned: tuple[AchievementRef, ...]
    progression_momentum: float

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if self.current_tier_index < 0:
            raise ValueError("current_tier_index must be >= 0")
        if self.accumulated_progress_quantity < 0:
            raise ValueError(
                "accumulated_progress_quantity must be >= 0"
            )
        if self.progress_to_next_tier < 0:
            raise ValueError(
                "progress_to_next_tier must be >= 0"
            )
        if not -1.0 <= self.progression_momentum <= 1.0:
            raise ValueError(
                "progression_momentum must be in [-1, 1]"
            )
        # consolidation_history must be strictly ascending by
        # transitioned_at_epoch and by tier_index.
        prev_epoch = -1.0
        prev_tier = -1
        for event in self.consolidation_history:
            if event.transitioned_at_epoch <= prev_epoch:
                raise ValueError(
                    "consolidation_history must be ascending by epoch"
                )
            if event.from_tier_index < prev_tier:
                raise ValueError(
                    "consolidation_history must be ascending by tier"
                )
            prev_epoch = event.transitioned_at_epoch
            prev_tier = event.to_tier_index

    @property
    def has_history(self) -> bool:
        """True iff at least one consolidation transition has happened."""
        return bool(self.consolidation_history)

    @property
    def streak_active(self) -> bool:
        """True iff the current streak has at least one increment."""
        return self.streak_state.active

__all__ = [
    "AchievementRef",
    "ConsolidationEvent",
    "ConsolidationTier",
    "ENTITY_LAYERS",
    "EntityLayer",
    "StreakState",
    "SubstrateStateTrajectoryProgression",
]
