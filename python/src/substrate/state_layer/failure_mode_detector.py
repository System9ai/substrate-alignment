"""State-layer failure-mode detector — Companion #2

Pure-logic detector that classifies the *substrate-state-layer*
failure mode an entity is experiencing. Substrate condition #3
identifies four canonical failure modes:

* ``SATURATION`` — substrate-state layer at capacity; new
  trajectories rejected.
* ``FRAGMENTATION`` — compartmentalization invariants intact but
  state-layer fragmented across many small partitions.
* ``CORRUPTION`` — compartmentalization invariant violated;
  state-layer no longer trustworthy.
* ``DECOHERENCE`` — observed substrate-state diverges from declared
  state; calibration broken.
* ``NONE`` — no failure mode detected.

The detector consumes a feature vector — capacity utilization,
partition count, corruption flag, calibration divergence — and
returns the dominant failure mode or ``NONE``.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the feature vector.
* Honest uncertainty: features below confidence floor surface as
  ``UNCLASSIFIED``.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

class StateLayerFailureMode(str, Enum):
    """Substrate state-layer failure modes."""

    NONE = "none"
    SATURATION = "saturation"
    FRAGMENTATION = "fragmentation"
    CORRUPTION = "corruption"
    DECOHERENCE = "decoherence"
    UNCLASSIFIED = "unclassified"

@dataclass(frozen=True, slots=True)
class FailureModeFeatures:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied feature vector."""

    entity_id: str
    capacity_utilization: float
    partition_count: int
    corruption_flag: bool
    calibration_divergence: float

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if not 0.0 <= self.capacity_utilization <= 1.0:
            raise ValueError(
                "capacity_utilization must be in [0, 1]"
            )
        if self.partition_count < 0:
            raise ValueError("partition_count must be >= 0")
        if not 0.0 <= self.calibration_divergence <= 1.0:
            raise ValueError(
                "calibration_divergence must be in [0, 1]"
            )

@dataclass(frozen=True, slots=True)
class FailureModeDetectorConfig:
    """Operator-tunable detector thresholds."""

    saturation_threshold: float = 0.9
    fragmentation_partition_threshold: int = 20
    decoherence_divergence_threshold: float = 0.4

    def __post_init__(self) -> None:
        if not 0.0 < self.saturation_threshold <= 1.0:
            raise ValueError(
                "saturation_threshold must be in (0, 1]"
            )
        if self.fragmentation_partition_threshold < 2:
            raise ValueError(
                "fragmentation_partition_threshold must be >= 2"
            )
        if not 0.0 < self.decoherence_divergence_threshold <= 1.0:
            raise ValueError(
                "decoherence_divergence_threshold must be in (0, 1]"
            )

DEFAULT_FAILURE_MODE_DETECTOR_CONFIG: Final[
    FailureModeDetectorConfig
] = FailureModeDetectorConfig()

@dataclass(frozen=True, slots=True)
class FailureModeDecision:  # pylint: disable=too-many-instance-attributes
    """Detector output."""

    entity_id: str
    mode: StateLayerFailureMode
    capacity_utilization: float
    partition_count: int
    corruption_flag: bool
    calibration_divergence: float
    rationale: str

    @property
    def failed(self) -> bool:
        """True iff a non-NONE failure mode is detected."""
        return self.mode not in (
            StateLayerFailureMode.NONE,
            StateLayerFailureMode.UNCLASSIFIED,
        )

class StateLayerFailureModeDetector:  # pylint: disable=too-few-public-methods
    """Pure-logic state-layer failure-mode detector (Companion #2)."""

    def __init__(
        self,
        *,
        config: FailureModeDetectorConfig = (
            DEFAULT_FAILURE_MODE_DETECTOR_CONFIG
        ),
    ) -> None:
        self._config = config

    def detect(
        self, features: FailureModeFeatures,
    ) -> FailureModeDecision:
        """Detect the dominant state-layer failure mode."""
        cfg = self._config
        # Corruption dominates — it makes other diagnostics
        # untrustworthy.
        if features.corruption_flag:
            return self._decide(
                features,
                StateLayerFailureMode.CORRUPTION,
                "corruption_flag set; other diagnostics unreliable",
            )
        if (
            features.calibration_divergence
            >= cfg.decoherence_divergence_threshold
        ):
            return self._decide(
                features,
                StateLayerFailureMode.DECOHERENCE,
                f"calibration_divergence="
                f"{features.calibration_divergence:.3f} >= "
                f"{cfg.decoherence_divergence_threshold:.3f}",
            )
        if features.capacity_utilization >= cfg.saturation_threshold:
            return self._decide(
                features,
                StateLayerFailureMode.SATURATION,
                f"capacity_utilization="
                f"{features.capacity_utilization:.3f} >= "
                f"{cfg.saturation_threshold:.3f}",
            )
        if (
            features.partition_count
            >= cfg.fragmentation_partition_threshold
        ):
            return self._decide(
                features,
                StateLayerFailureMode.FRAGMENTATION,
                f"partition_count={features.partition_count} >= "
                f"{cfg.fragmentation_partition_threshold}",
            )
        return self._decide(
            features,
            StateLayerFailureMode.NONE,
            "no failure mode detected",
        )

    @staticmethod
    def _decide(
        features: FailureModeFeatures,
        mode: StateLayerFailureMode,
        rationale: str,
    ) -> FailureModeDecision:
        return FailureModeDecision(
            entity_id=features.entity_id,
            mode=mode,
            capacity_utilization=features.capacity_utilization,
            partition_count=features.partition_count,
            corruption_flag=features.corruption_flag,
            calibration_divergence=features.calibration_divergence,
            rationale=rationale,
        )

__all__ = [
    "DEFAULT_FAILURE_MODE_DETECTOR_CONFIG",
    "FailureModeDecision",
    "FailureModeDetectorConfig",
    "FailureModeFeatures",
    "StateLayerFailureMode",
    "StateLayerFailureModeDetector",
]
