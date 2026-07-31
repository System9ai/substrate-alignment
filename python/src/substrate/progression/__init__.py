"""Per-entity substrate-state-trajectory progression model.

Pure-logic primitives for tracking an entity's progression along a
substrate-state trajectory: the entity-progression state record plus
the tier-consolidation engine. Persistence is the host application's
concern; this module owns only the value semantics.
"""

from substrate.progression.model import (
    AchievementRef,
    ConsolidationEvent,
    ConsolidationTier,
    EntityLayer,
    StreakState,
    SubstrateStateTrajectoryProgression,
)
from substrate.progression.tier_engine import (
    DEFAULT_TIER_ENGINE_CONFIG,
    TierEngineConfig,
    TierProgressionEngine,
    TierTransition,
    multiplicative_tier_thresholds,
)

__all__ = [
    "AchievementRef",
    "ConsolidationEvent",
    "ConsolidationTier",
    "DEFAULT_TIER_ENGINE_CONFIG",
    "EntityLayer",
    "StreakState",
    "SubstrateStateTrajectoryProgression",
    "TierEngineConfig",
    "TierProgressionEngine",
    "TierTransition",
    "multiplicative_tier_thresholds",
]
