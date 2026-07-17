"""Substrate-aligned exit protocol

Pure-logic primitive evaluating whether an agent's exit from the
current deployment / role / authority context preserves the
accumulated commitment accumulated in the context per
``authority-patience-and-substrate-aligned-hierarchy-navigation.md`` §
"The substrate-aligned exit pattern".

**Architectural commitment**: agents do not "burn bridges" by
default. The substrate-aligned exit pattern preserves
cross-entity trust-cluster for future substrate-aligned coupling.
Exits that violate this pattern require explicit override
authorization and surface as drift-detection signals (per the
extended drift vocabulary).

Six checklist items
===================

* **Notice period observed**: caller-supplied; sudden departures
  burn accumulated commitment.
* **Handoff prepared**: substrate-state-handoff package delivered.
* **Trust cluster preserved**: recommendation-letter posture intact
  across cross-entity recipients.
* **accumulated commitment documented**: recognition-circulation recorded for
  the relationship.
* **No public denunciation**: substrate-misaligned exits often
  recriminate publicly; this is the bridge-burning marker.
* **Unresolved concerns routed substrate-alignedly**: any
  substrate-misalignment in the current context is flagged for
  remediation via substrate-aligned channels, not via public
  denunciation.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the checklist Booleans.
* Honest uncertainty has no role here; checklist is total over six
  Booleans.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Tuple

class ExitVerdict(str, Enum):
    """Top-level exit-pattern classification."""

    SUBSTRATE_ALIGNED = "substrate_aligned"
    PARTIAL = "partial"
    BRIDGE_BURNING = "bridge_burning"

class ExitFailureMode(str, Enum):
    """Per-checklist-item failure mode flag."""

    NO_NOTICE = "no_notice"
    NO_HANDOFF = "no_handoff"
    TRUST_BURNED = "trust_burned"
    NO_ACCUMULATED_COMMITMENT_DOC = "no_accumulated_commitment_doc"
    PUBLIC_DENUNCIATION = "public_denunciation"
    NO_REMEDIATION_ROUTE = "no_remediation_route"

@dataclass(frozen=True, slots=True)
class ExitChecklist:
    """Caller-supplied substrate-aligned-exit checklist."""

    notice_period_observed: bool
    handoff_prepared: bool
    trust_cluster_preserved: bool
    accumulated_commitment_documented: bool
    no_public_denunciation: bool
    unresolved_concerns_routed_substrate_alignedly: bool

    def satisfied_count(self) -> int:
        """Number of checklist items satisfied."""
        return sum(
            (
                self.notice_period_observed,
                self.handoff_prepared,
                self.trust_cluster_preserved,
                self.accumulated_commitment_documented,
                self.no_public_denunciation,
                self.unresolved_concerns_routed_substrate_alignedly,
            )
        )

@dataclass(frozen=True, slots=True)
class ExitDecision:
    """Aggregate exit-protocol result."""

    agent_id: str
    verdict: ExitVerdict
    failure_modes: Tuple[ExitFailureMode, ...]
    satisfied_count: int
    rationale: str

    @property
    def is_substrate_aligned(self) -> bool:
        """True iff verdict is SUBSTRATE_ALIGNED."""
        return self.verdict is ExitVerdict.SUBSTRATE_ALIGNED

    @property
    def is_bridge_burning(self) -> bool:
        """True iff verdict is BRIDGE_BURNING."""
        return self.verdict is ExitVerdict.BRIDGE_BURNING

@dataclass(frozen=True, slots=True)
class ExitProtocolConfig:
    """Tunable thresholds for verdict aggregation."""

    aligned_min_satisfied: int = 6
    partial_min_satisfied: int = 4

    def __post_init__(self) -> None:
        if not 1 <= self.aligned_min_satisfied <= 6:
            raise ValueError("aligned_min_satisfied must be in [1, 6]")
        if not 1 <= self.partial_min_satisfied < self.aligned_min_satisfied:
            raise ValueError(
                "partial_min_satisfied must be in [1, aligned_min_satisfied)"
            )

DEFAULT_EXIT_PROTOCOL_CONFIG: Final[ExitProtocolConfig] = ExitProtocolConfig()

class SubstrateAlignedExitProtocol:  # pylint: disable=too-few-public-methods
    """Pure-logic exit-pattern evaluator."""

    def __init__(
        self,
        *,
        config: ExitProtocolConfig = DEFAULT_EXIT_PROTOCOL_CONFIG,
    ) -> None:
        self._config = config

    def evaluate(
        self, agent_id: str, checklist: ExitChecklist,
    ) -> ExitDecision:
        """Aggregate the six checklist items into an exit-pattern verdict."""
        if not agent_id:
            raise ValueError("agent_id must be non-empty")
        satisfied = checklist.satisfied_count()
        failure_modes = self._failure_modes(checklist)
        verdict = self._aggregate(satisfied)
        rationale = (
            f"satisfied={satisfied}/6; "
            f"failures=[{','.join(f.value for f in failure_modes) or 'none'}]"
            f"; verdict={verdict.value}"
        )
        return ExitDecision(
            agent_id=agent_id,
            verdict=verdict,
            failure_modes=failure_modes,
            satisfied_count=satisfied,
            rationale=rationale,
        )

    @staticmethod
    def _failure_modes(
        checklist: ExitChecklist,
    ) -> Tuple[ExitFailureMode, ...]:
        modes: list[ExitFailureMode] = []
        if not checklist.notice_period_observed:
            modes.append(ExitFailureMode.NO_NOTICE)
        if not checklist.handoff_prepared:
            modes.append(ExitFailureMode.NO_HANDOFF)
        if not checklist.trust_cluster_preserved:
            modes.append(ExitFailureMode.TRUST_BURNED)
        if not checklist.accumulated_commitment_documented:
            modes.append(ExitFailureMode.NO_ACCUMULATED_COMMITMENT_DOC)
        if not checklist.no_public_denunciation:
            modes.append(ExitFailureMode.PUBLIC_DENUNCIATION)
        if not checklist.unresolved_concerns_routed_substrate_alignedly:
            modes.append(ExitFailureMode.NO_REMEDIATION_ROUTE)
        return tuple(modes)

    def _aggregate(self, satisfied: int) -> ExitVerdict:
        cfg = self._config
        if satisfied >= cfg.aligned_min_satisfied:
            return ExitVerdict.SUBSTRATE_ALIGNED
        if satisfied >= cfg.partial_min_satisfied:
            return ExitVerdict.PARTIAL
        return ExitVerdict.BRIDGE_BURNING

__all__ = [
    "DEFAULT_EXIT_PROTOCOL_CONFIG",
    "ExitChecklist",
    "ExitDecision",
    "ExitFailureMode",
    "ExitProtocolConfig",
    "ExitVerdict",
    "SubstrateAlignedExitProtocol",
]
