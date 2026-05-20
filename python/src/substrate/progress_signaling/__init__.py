"""Progress-feedback signal primitives.

Pure-logic primitives for emitting calibrated progress-feedback
signals along long-cycle substrate-state trajectories. The emitter
composes with :class:`~substrate.resistance_band.ResistanceBandAssessment`
to gate emission on the productive-resistance band so progress
signals only fire when the underlying utilisation is in the
productive zone.

Public surface:

- :class:`SubstrateSignalType` — the five signal kinds.
- :class:`SubstrateEvidence` — the per-signal evidence record.
- :class:`SubstrateProgressSignal` — the signal dataclass itself.
- :class:`ProgressSignalEmitter` — the pure-logic emitter.
"""

from substrate.progress_signaling.signal import (
    SubstrateEvidence,
    SubstrateProgressSignal,
    SubstrateSignalType,
)
from substrate.progress_signaling.emitter import (
    DEFAULT_PROGRESS_EMITTER_CONFIG,
    ProgressEmissionDecision,
    ProgressEmitterConfig,
    ProgressSignalEmitter,
)

__all__ = [
    "DEFAULT_PROGRESS_EMITTER_CONFIG",
    "ProgressEmissionDecision",
    "ProgressEmitterConfig",
    "ProgressSignalEmitter",
    "SubstrateEvidence",
    "SubstrateProgressSignal",
    "SubstrateSignalType",
]
