"""Substrate-state-trajectory progress-feedback signal dataclass.. Pure-logic primitive: the
:class:`SubstrateProgressSignal` is emitted to report evidence of
progress along a substrate-state-trajectory. Used for agent training,
user substrate-aligned workflows, and multi-cycle iteration.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping

class SubstrateSignalType(str, Enum):
    """Five signal kinds aligned with tier-consolidation levels."""

    PROGRESS_MARKER = "progress_marker"
    MILESTONE = "milestone"
    CONSOLIDATION = "consolidation"
    ACHIEVEMENT = "achievement"
    STREAK = "streak"

SUBSTRATE_SIGNAL_TYPES: Final[frozenset[str]] = frozenset(
    t.value for t in SubstrateSignalType
)

@dataclass(frozen=True, slots=True)
class SubstrateEvidence:
    """One evidence record supporting a progress signal.

    Evidence is *typed*: a signal grounded in (e.g.) ``"audit_pass"`` is
    qualitatively different from one grounded in ``"action_count"``.
    Downstream consumers (the alignment audit) weight signals by
    the evidence-source mix.
    """

    evidence_id: str
    evidence_kind: str
    weight: float
    rationale: str

    def __post_init__(self) -> None:
        if not self.evidence_id:
            raise ValueError("evidence_id must be non-empty")
        if not self.evidence_kind:
            raise ValueError("evidence_kind must be non-empty")
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError("weight must be in [0, 1]")

@dataclass(frozen=True, slots=True)
class SubstrateProgressSignal:  # pylint: disable=too-many-instance-attributes
    """One trajectory-feedback signal."""

    signal_id: str
    target_entity_id: str
    trajectory_id: str
    signal_type: SubstrateSignalType
    progress_quantity: float
    evidence: tuple[SubstrateEvidence, ...]
    resistance_band_position: float
    emitted_at_epoch: float
    metadata: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.signal_id:
            raise ValueError("signal_id must be non-empty")
        if not self.target_entity_id:
            raise ValueError("target_entity_id must be non-empty")
        if not self.trajectory_id:
            raise ValueError("trajectory_id must be non-empty")
        if self.progress_quantity < 0:
            raise ValueError("progress_quantity must be >= 0")
        if not 0.0 <= self.resistance_band_position <= 1.0:
            raise ValueError(
                "resistance_band_position must be in [0, 1]"
            )
        if self.emitted_at_epoch < 0:
            raise ValueError("emitted_at_epoch must be >= 0")

    @property
    def total_evidence_weight(self) -> float:
        """Sum of evidence weights, bounded by the evidence tuple."""
        return sum(e.weight for e in self.evidence)

    @property
    def has_evidence(self) -> bool:
        """True iff the signal is grounded in at least one evidence record."""
        return bool(self.evidence)

__all__ = [
    "SUBSTRATE_SIGNAL_TYPES",
    "SubstrateEvidence",
    "SubstrateProgressSignal",
    "SubstrateSignalType",
]
