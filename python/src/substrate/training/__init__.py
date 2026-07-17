"""Substrate-aligned training-reward architecture.

Pure-logic primitives for emitting training-reward signals to
substrate-aligned learners. Emission is gated by the NPG gate so
rewards never accrue from net-negative actions, by the
calibrated-resistance band so reward density stays inside the
productive zone, and by an evidence-diversity check so signals
require independent corroboration.
"""

from substrate.training.reward_architecture import (
    DEFAULT_TRAINING_REWARD_CONFIG,
    RewardEmissionVerdict,
    RewardSchedulerState,
    SubstrateAlignedTrainingRewards,
    TrainingRewardConfig,
    TrainingRewardDecision,
    TrainingRewardRequest,
)

__all__ = [
    "DEFAULT_TRAINING_REWARD_CONFIG",
    "RewardEmissionVerdict",
    "RewardSchedulerState",
    "SubstrateAlignedTrainingRewards",
    "TrainingRewardConfig",
    "TrainingRewardDecision",
    "TrainingRewardRequest",
]
