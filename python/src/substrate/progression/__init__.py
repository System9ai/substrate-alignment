"""Per-entity substrate-state-trajectory progression model.. Pure-logic primitives — entity progression
state plus the tier-consolidation engine. The DAO that persists this state
lives at `app/core/db/directory/substrate/dao_substrate_trajectory_progression.py`;
this module owns the *value semantics*.
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
