"""Substrate-aligned training-reward architecture.

Pure-logic composition. The orchestrator emits a
``SubstrateProgressSignal`` **only if** all four gates pass:

1. :class:`~substrate.net_potential_gain_gate.NetPotentialGainGate`
   returns a non-negative verdict for the proposed action.
2. The provided evidence tuple clears the
   :class:`~substrate.progress_signaling.emitter.ProgressSignalEmitter`
   evidence floors AND has multi-modal diversity (at least N distinct
   evidence kinds: anti-reward-hacking criterion).
3. The calibrated interval (from the `SubstrateAlignedIntervalCalibrator`)
   has elapsed since the last signal for this `(agent, signal_type)` pair.
4. The resistance band is not `STRESSED` (subject to the emitter config).

The orchestrator is **stateful in the bounded sense**: it carries a
per-`(agent, signal_type)` last-emit timestamp map so it can enforce the
calibrated interval. Persistence is out of scope here; callers wire the
state map to a durable store as they see fit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Mapping

from substrate.net_potential_gain_gate import (
    NetPotentialGainEvaluation,
    NetPotentialGainGate,
    NetPotentialGainVerdict,
)  # pylint: disable=duplicate-code
from substrate.progress_signaling.emitter import (
    EmissionVerdict,
    ProgressSignalEmitter,
)
from substrate.progress_signaling.interval_calibrator import (
    SubstrateAlignedIntervalCalibrator,
)
from substrate.progress_signaling.signal import (
    SubstrateEvidence,
    SubstrateProgressSignal,
    SubstrateSignalType,
)
from substrate.resistance_band import (
    ResistanceBandAssessment,
)

class RewardEmissionVerdict(str, Enum):
    """Four-valued reward-emission verdict."""

    EMIT = "emit"
    SKIP_NET_NEGATIVE = "skip_net_negative"
    SKIP_INSUFFICIENT_EVIDENCE_DIVERSITY = "skip_insufficient_diversity"
    SKIP_INTERVAL_NOT_ELAPSED = "skip_interval_not_elapsed"

@dataclass(frozen=True, slots=True)
class TrainingRewardConfig:
    """Operator-tunable gates."""

    min_distinct_evidence_kinds: int = 2
    """Anti-reward-hacking: require evidence from N distinct kinds."""

    skip_on_npg_insufficient_data: bool = True
    """If True, treat INSUFFICIENT_DATA from NPG as a skip rather than
    an emit. Substrate-aligned default: never reward without evidence
    of net-positive impact."""

    def __post_init__(self) -> None:
        if self.min_distinct_evidence_kinds < 1:
            raise ValueError(
                "min_distinct_evidence_kinds must be >= 1"
            )

DEFAULT_TRAINING_REWARD_CONFIG: Final[TrainingRewardConfig] = (
    TrainingRewardConfig()
)

@dataclass(frozen=True, slots=True)
class TrainingRewardRequest:  # pylint: disable=too-many-instance-attributes
    """Per-step reward-emission request."""

    agent_id: str
    trajectory_id: str
    action_kind: str
    affected_entity_ids: tuple[str, ...]
    proposed_outcome: Mapping[str, object]
    evidence: tuple[SubstrateEvidence, ...]
    signal_type: SubstrateSignalType
    progress_quantity: float
    tier_index: int
    resistance: ResistanceBandAssessment
    epoch: float
    signal_id: str

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("agent_id must be non-empty")
        if not self.trajectory_id:
            raise ValueError("trajectory_id must be non-empty")
        if not self.action_kind:
            raise ValueError("action_kind must be non-empty")
        if not self.signal_id:
            raise ValueError("signal_id must be non-empty")
        if self.tier_index < 0:
            raise ValueError("tier_index must be >= 0")
        if self.epoch < 0:
            raise ValueError("epoch must be >= 0")
        if self.progress_quantity < 0:
            raise ValueError("progress_quantity must be >= 0")

@dataclass(frozen=True, slots=True)
class TrainingRewardDecision:
    """Per-step decision + (optionally) the emitted signal."""

    verdict: RewardEmissionVerdict
    signal: SubstrateProgressSignal | None
    npg_evaluation: NetPotentialGainEvaluation | None
    rationale: str

    @property
    def emitted(self) -> bool:
        """True iff a signal was constructed and approved for emission."""
        return (
            self.verdict is RewardEmissionVerdict.EMIT
            and self.signal is not None
        )

@dataclass(slots=True)
class RewardSchedulerState:
    """Per-(agent, signal_type) last-emit timestamp map."""

    last_emit_epoch_by_key: dict[str, float] = field(
        default_factory=lambda: {},
    )

    @staticmethod
    def _key(agent_id: str, signal_type: SubstrateSignalType) -> str:
        return f"{agent_id}::{signal_type.value}"

    def last_emit(
        self, agent_id: str, signal_type: SubstrateSignalType,
    ) -> float | None:
        """Return last-emit epoch for the pair, or ``None`` if never emitted."""
        return self.last_emit_epoch_by_key.get(
            self._key(agent_id, signal_type),
        )

    def record_emit(
        self,
        *,
        agent_id: str,
        signal_type: SubstrateSignalType,
        epoch: float,
    ) -> None:
        """Record an emit at ``epoch``."""
        if epoch < 0:
            raise ValueError("epoch must be >= 0")
        self.last_emit_epoch_by_key[self._key(agent_id, signal_type)] = epoch

class SubstrateAlignedTrainingRewards:  # pylint: disable=too-few-public-methods
    """Substrate-aligned training-reward orchestrator."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        npg_gate: NetPotentialGainGate,
        emitter: ProgressSignalEmitter,
        interval_calibrator: SubstrateAlignedIntervalCalibrator,
        scheduler_state: RewardSchedulerState,
        config: TrainingRewardConfig = DEFAULT_TRAINING_REWARD_CONFIG,
    ) -> None:
        self._npg_gate = npg_gate
        self._emitter = emitter
        self._interval_calibrator = interval_calibrator
        self._state = scheduler_state
        self._config = config

    def evaluate(  # pylint: disable=too-many-locals
        self, request: TrainingRewardRequest,
    ) -> TrainingRewardDecision:
        """Evaluate the reward emission for one step."""
        cfg = self._config
        # ── Gate 1: NPG ────────────────────────────────────────────
        npg_eval = self._npg_gate.evaluate(
            actor_entity_id=request.agent_id,
            action_kind=request.action_kind,
            affected_entity_ids=request.affected_entity_ids,
            proposed_outcome=request.proposed_outcome,
        )
        if npg_eval.verdict is NetPotentialGainVerdict.NET_NEGATIVE:
            return TrainingRewardDecision(
                verdict=RewardEmissionVerdict.SKIP_NET_NEGATIVE,
                signal=None,
                npg_evaluation=npg_eval,
                rationale="NPG verdict is NET_NEGATIVE",
            )
        if (
            cfg.skip_on_npg_insufficient_data
            and npg_eval.verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA
        ):
            return TrainingRewardDecision(
                verdict=RewardEmissionVerdict.SKIP_NET_NEGATIVE,
                signal=None,
                npg_evaluation=npg_eval,
                rationale=(
                    "NPG verdict INSUFFICIENT_DATA + "
                    "skip_on_npg_insufficient_data is True"
                ),
            )
        # ── Gate 2: evidence diversity ─────────────────────────────
        distinct_kinds = len({e.evidence_kind for e in request.evidence})
        if distinct_kinds < cfg.min_distinct_evidence_kinds:
            return TrainingRewardDecision(
                verdict=(
                    RewardEmissionVerdict.SKIP_INSUFFICIENT_EVIDENCE_DIVERSITY
                ),
                signal=None,
                npg_evaluation=npg_eval,
                rationale=(
                    f"distinct evidence kinds={distinct_kinds} "
                    f"below min {cfg.min_distinct_evidence_kinds}"
                ),
            )
        # ── Gate 3: calibrated interval ────────────────────────────
        interval = self._interval_calibrator.calibrate(
            signal_type=request.signal_type,
            tier_index=request.tier_index,
            resistance=request.resistance,
        )
        last_epoch = self._state.last_emit(
            request.agent_id, request.signal_type,
        )
        if last_epoch is not None:
            elapsed = request.epoch - last_epoch
            if elapsed < interval.target_seconds and not math.isclose(
                elapsed, float(interval.target_seconds),
            ):
                return TrainingRewardDecision(
                    verdict=(
                        RewardEmissionVerdict.SKIP_INTERVAL_NOT_ELAPSED
                    ),
                    signal=None,
                    npg_evaluation=npg_eval,
                    rationale=(
                        f"elapsed={elapsed:.1f}s < target="
                        f"{interval.target_seconds}s"
                    ),
                )
        # ── Gate 4: emitter (resistance + evidence floor) ──────────
        emit_decision = self._emitter.evaluate(
            signal_id=request.signal_id,
            target_entity_id=request.agent_id,
            trajectory_id=request.trajectory_id,
            signal_type=request.signal_type,
            progress_quantity=request.progress_quantity,
            evidence=request.evidence,
            resistance=request.resistance,
            emitted_at_epoch=request.epoch,
            metadata={"action_kind": request.action_kind},
        )
        if emit_decision.verdict is not EmissionVerdict.EMIT:
            return TrainingRewardDecision(
                verdict=RewardEmissionVerdict.SKIP_INTERVAL_NOT_ELAPSED,
                signal=None,
                npg_evaluation=npg_eval,
                rationale=(
                    f"emitter declined: {emit_decision.verdict.value}"
                ),
            )
        # ── Record + return ────────────────────────────────────────
        self._state.record_emit(
            agent_id=request.agent_id,
            signal_type=request.signal_type,
            epoch=request.epoch,
        )
        return TrainingRewardDecision(
            verdict=RewardEmissionVerdict.EMIT,
            signal=emit_decision.signal,
            npg_evaluation=npg_eval,
            rationale=(
                f"all four gates passed; "
                f"calibrated interval={interval.target_seconds}s"
            ),
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
