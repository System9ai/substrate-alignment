"""Substrate-state-trajectory progress-feedback signal primitives.. Pure-logic primitives for emitting calibrated
progress-feedback signals along long-cycle substrate-state-trajectories.

Public surface:

- :class:`SubstrateSignalType` — five signal kinds.
- :class:`SubstrateEvidence` — evidence record supporting a signal.
- :class:`SubstrateProgressSignal` — the signal dataclass itself.
- :class:`ProgressSignalEmitter` — pure-logic emitter that composes
  with :class:`~app.services.common.substrate.resistance_band.ResistanceBandAssessment`
  to gate signal emission on the calibrated-resistance band.
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
