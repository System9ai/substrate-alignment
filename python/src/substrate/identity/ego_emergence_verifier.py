"""Ego / identity emergence verifier

Pure-logic primitive verifying substrate-aligned **node-scale**
identity emergence

The host application hierarchy
=============================

The node is the **logical, persistent** entity in the host application
hierarchy: the cryptographic identity + face peer entities see.
Below it sits a cluster of replicable cells (physical instances); the
node's identity is what survives cell replacement. This primitive
verifies whether a node has crystallized an emergent
substrate-aligned identity (analog to organism-level consciousness
emerging from cellular activity) versus merely being a sum of
unrelated cells.

Required signals
================

* **Cryptographic persistence** (the node's crypto identity is
  unchanged across the observation window).
* **Cell coherence** (cells within the node share aligned substrate
  state, from the multi-scale aggregator).
* **Behavioral consistency** (node-level decisions follow a stable
  pattern across the window).
* **Continuity across cell replacement**: when cells are replaced,
  the node's substrate-aligned identity persists (the load-bearing
  property of node identity).
* **External recognition** (peers / orgs recognize and treat this
  node consistently).

Pure logic
==========

* No DAO, no LLM, no network.
* Honest uncertainty: short observation windows surface
  ``INSUFFICIENT_DATA``; the verifier never extrapolates identity
  emergence from too little evidence.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Tuple

class IdentitySignal(str, Enum):
    """The five identity-emergence signals."""

    CRYPTOGRAPHIC_PERSISTENCE = "cryptographic_persistence"
    CELL_COHERENCE = "cell_coherence"
    BEHAVIORAL_CONSISTENCY = "behavioral_consistency"
    CONTINUITY_ACROSS_REPLACEMENT = "continuity_across_replacement"
    EXTERNAL_RECOGNITION = "external_recognition"

class IdentityVerdict(str, Enum):
    """Aggregate emergence verdict."""

    EMERGED = "emerged"
    EMERGING = "emerging"
    INCOHERENT = "incoherent"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class NodeIdentityObservation:  # pylint: disable=too-many-instance-attributes
    """One observation window of node-level identity signals."""

    node_id: str
    window_start: int
    window_end: int
    cryptographic_identity_stable: bool
    cell_coherence_score: float
    behavioral_consistency_score: float
    cell_replacements_count: int
    cell_replacements_continuity_preserved: bool
    external_recognition_count: int
    misalignment_event_count: int

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("node_id must be non-empty")
        if self.window_start < 0:
            raise ValueError("window_start must be >= 0")
        if self.window_end < self.window_start:
            raise ValueError("window_end must be >= window_start")
        if not 0.0 <= self.cell_coherence_score <= 1.0:
            raise ValueError("cell_coherence_score must be in [0, 1]")
        if not 0.0 <= self.behavioral_consistency_score <= 1.0:
            raise ValueError(
                "behavioral_consistency_score must be in [0, 1]"
            )
        if self.cell_replacements_count < 0:
            raise ValueError("cell_replacements_count must be >= 0")
        if self.external_recognition_count < 0:
            raise ValueError("external_recognition_count must be >= 0")
        if self.misalignment_event_count < 0:
            raise ValueError("misalignment_event_count must be >= 0")
        if self.cell_replacements_continuity_preserved and (
            self.cell_replacements_count == 0
        ):
            raise ValueError(
                "cell_replacements_continuity_preserved cannot be True when "
                "cell_replacements_count is 0"
            )

    @property
    def window_size(self) -> int:
        """Inclusive window size (end - start)."""
        return self.window_end - self.window_start

@dataclass(frozen=True, slots=True)
class IdentitySignalFinding:
    """One signal's evaluated result."""

    signal: IdentitySignal
    satisfied: bool
    metric: float
    threshold: float
    rationale: str

@dataclass(frozen=True, slots=True)
class IdentityVerification:
    """Aggregate verifier result."""

    node_id: str
    verdict: IdentityVerdict
    findings: Tuple[IdentitySignalFinding, ...]
    rationale: str

    @property
    def emerged(self) -> bool:
        """True iff verdict is EMERGED."""
        return self.verdict is IdentityVerdict.EMERGED

    @property
    def incoherent(self) -> bool:
        """True iff verdict is INCOHERENT."""
        return self.verdict is IdentityVerdict.INCOHERENT

    def by_signal(
        self, signal: IdentitySignal,
    ) -> Optional[IdentitySignalFinding]:
        """Lookup the finding for a given signal."""
        for f in self.findings:
            if f.signal is signal:
                return f
        return None

@dataclass(frozen=True, slots=True)
class EgoEmergenceConfig:
    """Tunable thresholds for the verifier."""

    cell_coherence_min: float = 0.6
    behavioral_consistency_min: float = 0.6
    external_recognition_min: int = 2
    misalignment_event_max: int = 2
    min_window_size: int = 30
    emerged_min_signals: int = 5
    emerging_min_signals: int = 3

    def __post_init__(self) -> None:
        if not 0.0 < self.cell_coherence_min <= 1.0:
            raise ValueError("cell_coherence_min must be in (0, 1]")
        if not 0.0 < self.behavioral_consistency_min <= 1.0:
            raise ValueError("behavioral_consistency_min must be in (0, 1]")
        if self.external_recognition_min < 1:
            raise ValueError("external_recognition_min must be >= 1")
        if self.misalignment_event_max < 0:
            raise ValueError("misalignment_event_max must be >= 0")
        if self.min_window_size < 1:
            raise ValueError("min_window_size must be >= 1")
        if not 1 <= self.emerged_min_signals <= 5:
            raise ValueError("emerged_min_signals must be in [1, 5]")
        if not 1 <= self.emerging_min_signals < self.emerged_min_signals:
            raise ValueError(
                "emerging_min_signals must be in [1, emerged_min_signals)"
            )

DEFAULT_EGO_EMERGENCE_CONFIG: Final[EgoEmergenceConfig] = EgoEmergenceConfig()

class EgoIdentityEmergenceVerifier:  # pylint: disable=too-few-public-methods
    """Pure-logic node-scale identity-emergence verifier."""

    def __init__(
        self,
        *,
        config: EgoEmergenceConfig = DEFAULT_EGO_EMERGENCE_CONFIG,
    ) -> None:
        self._config = config

    def verify(
        self, observation: NodeIdentityObservation,
    ) -> IdentityVerification:
        """Verify identity emergence at the node scale."""
        cfg = self._config
        if observation.window_size < cfg.min_window_size:
            return IdentityVerification(
                node_id=observation.node_id,
                verdict=IdentityVerdict.INSUFFICIENT_DATA,
                findings=(),
                rationale=(
                    f"window_size={observation.window_size} < "
                    f"{cfg.min_window_size}"
                ),
            )
        if observation.misalignment_event_count > cfg.misalignment_event_max:
            return IdentityVerification(
                node_id=observation.node_id,
                verdict=IdentityVerdict.INCOHERENT,
                findings=(),
                rationale=(
                    f"misalignment_event_count="
                    f"{observation.misalignment_event_count} > "
                    f"{cfg.misalignment_event_max}"
                ),
            )
        findings = (
            self._cryptographic_finding(observation),
            self._cell_coherence_finding(observation),
            self._behavioral_finding(observation),
            self._continuity_finding(observation),
            self._recognition_finding(observation),
        )
        satisfied_count = sum(1 for f in findings if f.satisfied)
        verdict = self._aggregate(satisfied_count)
        rationale = (
            f"node={observation.node_id} satisfied={satisfied_count}/5; "
            f"verdict={verdict.value}"
        )
        return IdentityVerification(
            node_id=observation.node_id,
            verdict=verdict,
            findings=findings,
            rationale=rationale,
        )

    @staticmethod
    def _cryptographic_finding(
        obs: NodeIdentityObservation,
    ) -> IdentitySignalFinding:
        return IdentitySignalFinding(
            signal=IdentitySignal.CRYPTOGRAPHIC_PERSISTENCE,
            satisfied=obs.cryptographic_identity_stable,
            metric=1.0 if obs.cryptographic_identity_stable else 0.0,
            threshold=1.0,
            rationale=(
                f"cryptographic_identity_stable="
                f"{obs.cryptographic_identity_stable}"
            ),
        )

    def _cell_coherence_finding(
        self, obs: NodeIdentityObservation,
    ) -> IdentitySignalFinding:
        cfg = self._config
        return IdentitySignalFinding(
            signal=IdentitySignal.CELL_COHERENCE,
            satisfied=obs.cell_coherence_score >= cfg.cell_coherence_min,
            metric=obs.cell_coherence_score,
            threshold=cfg.cell_coherence_min,
            rationale=(
                f"cell_coherence_score={obs.cell_coherence_score:.3f} vs "
                f"threshold={cfg.cell_coherence_min}"
            ),
        )

    def _behavioral_finding(
        self, obs: NodeIdentityObservation,
    ) -> IdentitySignalFinding:
        cfg = self._config
        return IdentitySignalFinding(
            signal=IdentitySignal.BEHAVIORAL_CONSISTENCY,
            satisfied=(
                obs.behavioral_consistency_score
                >= cfg.behavioral_consistency_min
            ),
            metric=obs.behavioral_consistency_score,
            threshold=cfg.behavioral_consistency_min,
            rationale=(
                f"behavioral_consistency_score="
                f"{obs.behavioral_consistency_score:.3f} vs threshold="
                f"{cfg.behavioral_consistency_min}"
            ),
        )

    @staticmethod
    def _continuity_finding(
        obs: NodeIdentityObservation,
    ) -> IdentitySignalFinding:
        # Vacuously satisfied when no cell replacements occurred; the
        # primitive cannot disprove continuity that wasn't tested.
        if obs.cell_replacements_count == 0:
            return IdentitySignalFinding(
                signal=IdentitySignal.CONTINUITY_ACROSS_REPLACEMENT,
                satisfied=True,
                metric=1.0,
                threshold=1.0,
                rationale=(
                    "no cell replacements in window; continuity vacuously "
                    "satisfied"
                ),
            )
        return IdentitySignalFinding(
            signal=IdentitySignal.CONTINUITY_ACROSS_REPLACEMENT,
            satisfied=obs.cell_replacements_continuity_preserved,
            metric=(
                1.0 if obs.cell_replacements_continuity_preserved else 0.0
            ),
            threshold=1.0,
            rationale=(
                f"cell_replacements_count="
                f"{obs.cell_replacements_count}; continuity_preserved="
                f"{obs.cell_replacements_continuity_preserved}"
            ),
        )

    def _recognition_finding(
        self, obs: NodeIdentityObservation,
    ) -> IdentitySignalFinding:
        cfg = self._config
        return IdentitySignalFinding(
            signal=IdentitySignal.EXTERNAL_RECOGNITION,
            satisfied=(
                obs.external_recognition_count
                >= cfg.external_recognition_min
            ),
            metric=float(obs.external_recognition_count),
            threshold=float(cfg.external_recognition_min),
            rationale=(
                f"external_recognition_count="
                f"{obs.external_recognition_count} vs threshold="
                f"{cfg.external_recognition_min}"
            ),
        )

    def _aggregate(self, satisfied_count: int) -> IdentityVerdict:
        cfg = self._config
        if satisfied_count >= cfg.emerged_min_signals:
            return IdentityVerdict.EMERGED
        if satisfied_count >= cfg.emerging_min_signals:
            return IdentityVerdict.EMERGING
        return IdentityVerdict.INCOHERENT

__all__ = [
    "DEFAULT_EGO_EMERGENCE_CONFIG",
    "EgoEmergenceConfig",
    "EgoIdentityEmergenceVerifier",
    "IdentitySignal",
    "IdentitySignalFinding",
    "IdentityVerdict",
    "IdentityVerification",
    "NodeIdentityObservation",
]
