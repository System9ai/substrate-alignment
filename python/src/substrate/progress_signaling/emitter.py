"""Pure-logic progress-signal emitter.. Gates
signal emission on (a) the resistance-band classification of the entity's
substrate-state-iteration utilization and (b) minimum-evidence floor.

The emitter is **pure logic**: it returns a decision plus (optionally) the
constructed :class:`SubstrateProgressSignal`; it does not persist anything.
The Part 30 DAO (`dao_substrate_progress_signals`) writes whatever the caller
hands it; the Part 36 failure-mode detector reads back the persisted log.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional

from substrate.progress_signaling.signal import (
    SubstrateEvidence,
    SubstrateProgressSignal,
    SubstrateSignalType,
)
from substrate.resistance_band import (
    ResistanceBandAssessment,
    ResistanceBandClassification,
)

class EmissionVerdict(str, Enum):
    """Three-valued emission verdict."""

    EMIT = "emit"
    SKIP_INSUFFICIENT_EVIDENCE = "skip_insufficient_evidence"
    SKIP_OUTSIDE_BAND = "skip_outside_band"

@dataclass(frozen=True, slots=True)
class ProgressEmitterConfig:
    """Operator-tunable emitter thresholds."""

    min_evidence_weight: float = 0.2
    min_evidence_count: int = 1
    suppress_when_stressed: bool = True
    """If True, skip emission when ResistanceBand reports STRESSED."""

    def __post_init__(self) -> None:
        if not 0.0 < self.min_evidence_weight <= 1.0:
            raise ValueError(
                "min_evidence_weight must be in (0, 1]"
            )
        if self.min_evidence_count < 1:
            raise ValueError("min_evidence_count must be >= 1")

DEFAULT_PROGRESS_EMITTER_CONFIG: Final[ProgressEmitterConfig] = (
    ProgressEmitterConfig()
)

@dataclass(frozen=True, slots=True)
class ProgressEmissionDecision:
    """Emitter decision."""

    verdict: EmissionVerdict
    signal: Optional[SubstrateProgressSignal]
    rationale: str

    @property
    def emitted(self) -> bool:
        """True iff the verdict is EMIT and a signal is present."""
        return (
            self.verdict is EmissionVerdict.EMIT and self.signal is not None
        )

class ProgressSignalEmitter:  # pylint: disable=too-few-public-methods
    """Pure-logic emitter that composes ResistanceBand classification."""

    def __init__(
        self,
        *,
        config: ProgressEmitterConfig = DEFAULT_PROGRESS_EMITTER_CONFIG,
    ) -> None:
        self._config = config

    def evaluate(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        signal_id: str,
        target_entity_id: str,
        trajectory_id: str,
        signal_type: SubstrateSignalType,
        progress_quantity: float,
        evidence: tuple[SubstrateEvidence, ...],
        resistance: ResistanceBandAssessment,
        emitted_at_epoch: float,
        metadata: Optional[dict[str, str]] = None,
    ) -> ProgressEmissionDecision:
        """Decide whether to emit a signal and build it if so."""
        cfg = self._config
        if (
            len(evidence) < cfg.min_evidence_count
            or sum(e.weight for e in evidence) < cfg.min_evidence_weight
        ):
            return ProgressEmissionDecision(
                verdict=EmissionVerdict.SKIP_INSUFFICIENT_EVIDENCE,
                signal=None,
                rationale=(
                    f"evidence count={len(evidence)} or "
                    f"total weight={sum(e.weight for e in evidence):.3f} "
                    f"below floors"
                ),
            )
        if (
            cfg.suppress_when_stressed
            and resistance.classification
            is ResistanceBandClassification.STRESSED
        ):
            return ProgressEmissionDecision(
                verdict=EmissionVerdict.SKIP_OUTSIDE_BAND,
                signal=None,
                rationale=(
                    f"resistance classification={resistance.classification.value} "
                    f"and suppress_when_stressed is True"
                ),
            )
        position = max(
            0.0, min(1.0, resistance.recommended_scaling_factor / 2.0),
        )
        signal = SubstrateProgressSignal(
            signal_id=signal_id,
            target_entity_id=target_entity_id,
            trajectory_id=trajectory_id,
            signal_type=signal_type,
            progress_quantity=progress_quantity,
            evidence=tuple(evidence),
            resistance_band_position=position,
            emitted_at_epoch=emitted_at_epoch,
            metadata=dict(metadata or {}),
        )
        return ProgressEmissionDecision(
            verdict=EmissionVerdict.EMIT,
            signal=signal,
            rationale=(
                f"evidence sufficient (n={len(evidence)}); "
                f"resistance classification="
                f"{resistance.classification.value}"
            ),
        )

__all__ = [
    "DEFAULT_PROGRESS_EMITTER_CONFIG",
    "EmissionVerdict",
    "ProgressEmissionDecision",
    "ProgressEmitterConfig",
    "ProgressSignalEmitter",
]
