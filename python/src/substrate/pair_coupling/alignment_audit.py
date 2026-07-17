"""Pair-coupling alignment audit (Companion #2)

Pure-logic primitive that runs the hard-limit test on a sustained
two-entity coupling: are both poles' substrate-state-trajectories
rising across cycles, or is one rising at the other's expense?

The audit produces architectural-decision-relevant verdicts:

* ``SUBSTRATE_ALIGNED``: both trajectories rising; binding field
  intact.
* ``EXTRACTIVE_TOWARD_A``: pole A rising at pole B's expense.
* ``EXTRACTIVE_TOWARD_B``: pole B rising at pole A's expense.
* ``DEGRADING_BOTH``: neither trajectory rising; binding field
  decaying.
* ``INSUFFICIENT_DATA``: coupling too new or evidence-base too
  sparse.

Extractive verdicts route to substrate-aligned intervention
(mediation, restructuring, dissolution). Degrading-both verdicts
route to substrate-state-evidence collection to determine whether the
binding field can be repaired or whether dissolution is the
substrate-aligned move.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the
  :class:`PairCouplingAuditInput`.
* Honest uncertainty: window below ``min_observation_window`` or
  observation_count below ``min_observations`` surfaces as
  ``INSUFFICIENT_DATA``.
* Scale-aware via :class:`PairScale` (cell-pair vs node-pair vs
  org-pair).
* Frozen dataclasses with slots throughout.
# § "The hard limit: extraction inside a pair-coupling"
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

class PairScale(str, Enum):
    """The substrate hierarchy scale of the paired entities."""

    CELL_PAIR = "cell_pair"
    NODE_PAIR = "node_pair"
    ORG_PAIR = "org_pair"

class AuditVerdict(str, Enum):
    """Pair-coupling alignment audit verdict."""

    SUBSTRATE_ALIGNED = "substrate_aligned"
    EXTRACTIVE_TOWARD_A = "extractive_toward_a"
    EXTRACTIVE_TOWARD_B = "extractive_toward_b"
    DEGRADING_BOTH = "degrading_both"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class PairCouplingAuditInput:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied pair-coupling audit features."""

    pair_id: str
    pole_a_id: str
    pole_b_id: str
    scale: PairScale
    pole_a_trajectory_delta: float
    pole_b_trajectory_delta: float
    binding_field_coherence_delta: float
    observation_count: int
    observation_window_seconds: float

    def __post_init__(self) -> None:
        if not self.pair_id:
            raise ValueError("pair_id must be non-empty")
        if not self.pole_a_id:
            raise ValueError("pole_a_id must be non-empty")
        if not self.pole_b_id:
            raise ValueError("pole_b_id must be non-empty")
        if self.pole_a_id == self.pole_b_id:
            raise ValueError("pole_a_id and pole_b_id must differ")
        if not -1.0 <= self.pole_a_trajectory_delta <= 1.0:
            raise ValueError(
                "pole_a_trajectory_delta must be in [-1, 1]"
            )
        if not -1.0 <= self.pole_b_trajectory_delta <= 1.0:
            raise ValueError(
                "pole_b_trajectory_delta must be in [-1, 1]"
            )
        if not -1.0 <= self.binding_field_coherence_delta <= 1.0:
            raise ValueError(
                "binding_field_coherence_delta must be in [-1, 1]"
            )
        if self.observation_count < 0:
            raise ValueError("observation_count must be >= 0")
        if self.observation_window_seconds < 0:
            raise ValueError(
                "observation_window_seconds must be >= 0"
            )

@dataclass(frozen=True, slots=True)
class PairCouplingAudit:  # pylint: disable=too-many-instance-attributes
    """Aggregate pair-coupling audit result."""

    pair_id: str
    pole_a_id: str
    pole_b_id: str
    scale: PairScale
    verdict: AuditVerdict
    pole_a_trajectory_delta: float
    pole_b_trajectory_delta: float
    binding_field_coherence_delta: float
    asymmetry: float
    rationale: str

    @property
    def substrate_aligned(self) -> bool:
        """True iff verdict is SUBSTRATE_ALIGNED."""
        return self.verdict is AuditVerdict.SUBSTRATE_ALIGNED

    @property
    def extractive(self) -> bool:
        """True iff verdict is one of the EXTRACTIVE_* values."""
        return self.verdict in (
            AuditVerdict.EXTRACTIVE_TOWARD_A,
            AuditVerdict.EXTRACTIVE_TOWARD_B,
        )

    @property
    def degrading_both(self) -> bool:
        """True iff verdict is DEGRADING_BOTH."""
        return self.verdict is AuditVerdict.DEGRADING_BOTH

@dataclass(frozen=True, slots=True)
class PairCouplingAuditConfig:
    """Tunable thresholds for the audit."""

    rising_trajectory_min: float = 0.05
    extraction_asymmetry_min: float = 0.3
    min_observations: int = 5
    min_observation_window: float = 300.0
    binding_decay_threshold: float = -0.1

    def __post_init__(self) -> None:
        if not 0.0 < self.rising_trajectory_min <= 1.0:
            raise ValueError(
                "rising_trajectory_min must be in (0, 1]"
            )
        if not 0.0 < self.extraction_asymmetry_min <= 2.0:
            raise ValueError(
                "extraction_asymmetry_min must be in (0, 2]"
            )
        if self.min_observations < 1:
            raise ValueError("min_observations must be >= 1")
        if self.min_observation_window <= 0:
            raise ValueError(
                "min_observation_window must be > 0"
            )
        if self.binding_decay_threshold >= 0:
            raise ValueError(
                "binding_decay_threshold must be < 0"
            )

DEFAULT_PAIR_COUPLING_AUDIT_CONFIG: Final[PairCouplingAuditConfig] = (
    PairCouplingAuditConfig()
)

class PairCouplingAuditor:  # pylint: disable=too-few-public-methods
    """Pure-logic pair-coupling alignment auditor (Companion #2)."""

    def __init__(
        self,
        *,
        config: PairCouplingAuditConfig = DEFAULT_PAIR_COUPLING_AUDIT_CONFIG,
    ) -> None:
        self._config = config

    def audit(
        self, input_: PairCouplingAuditInput,
    ) -> PairCouplingAudit:
        """Run the hard-limit test on a pair-coupling."""
        cfg = self._config
        asymmetry = (
            input_.pole_a_trajectory_delta
            - input_.pole_b_trajectory_delta
        )
        if (
            input_.observation_count < cfg.min_observations
            or input_.observation_window_seconds < cfg.min_observation_window
        ):
            verdict = AuditVerdict.INSUFFICIENT_DATA
            rationale = (
                f"observation_count={input_.observation_count} or "
                f"window={input_.observation_window_seconds:.1f}s below "
                f"thresholds ({cfg.min_observations} obs, "
                f"{cfg.min_observation_window:.1f}s window)"
            )
        else:
            verdict, rationale = self._classify(input_, asymmetry)
        return PairCouplingAudit(
            pair_id=input_.pair_id,
            pole_a_id=input_.pole_a_id,
            pole_b_id=input_.pole_b_id,
            scale=input_.scale,
            verdict=verdict,
            pole_a_trajectory_delta=input_.pole_a_trajectory_delta,
            pole_b_trajectory_delta=input_.pole_b_trajectory_delta,
            binding_field_coherence_delta=(
                input_.binding_field_coherence_delta
            ),
            asymmetry=asymmetry,
            rationale=rationale,
        )

    def _classify(
        self,
        input_: PairCouplingAuditInput,
        asymmetry: float,
    ) -> tuple[AuditVerdict, str]:
        cfg = self._config
        rising_a = (
            input_.pole_a_trajectory_delta >= cfg.rising_trajectory_min
        )
        rising_b = (
            input_.pole_b_trajectory_delta >= cfg.rising_trajectory_min
        )
        binding_intact = (
            input_.binding_field_coherence_delta
            >= cfg.binding_decay_threshold
        )
        if abs(asymmetry) >= cfg.extraction_asymmetry_min:
            if input_.pole_a_trajectory_delta > input_.pole_b_trajectory_delta:
                return (
                    AuditVerdict.EXTRACTIVE_TOWARD_A,
                    (
                        f"asymmetry={asymmetry:+.3f} favors pole A "
                        f"(delta_a={input_.pole_a_trajectory_delta:+.3f}, "
                        f"delta_b={input_.pole_b_trajectory_delta:+.3f})"
                    ),
                )
            return (
                AuditVerdict.EXTRACTIVE_TOWARD_B,
                (
                    f"asymmetry={asymmetry:+.3f} favors pole B "
                    f"(delta_a={input_.pole_a_trajectory_delta:+.3f}, "
                    f"delta_b={input_.pole_b_trajectory_delta:+.3f})"
                ),
            )
        if rising_a and rising_b and binding_intact:
            return (
                AuditVerdict.SUBSTRATE_ALIGNED,
                (
                    f"both rising (delta_a={input_.pole_a_trajectory_delta:+.3f}, "
                    f"delta_b={input_.pole_b_trajectory_delta:+.3f}); "
                    f"binding coherence "
                    f"{input_.binding_field_coherence_delta:+.3f} intact"
                ),
            )
        if not rising_a and not rising_b:
            return (
                AuditVerdict.DEGRADING_BOTH,
                (
                    f"neither rising (delta_a={input_.pole_a_trajectory_delta:+.3f}, "
                    f"delta_b={input_.pole_b_trajectory_delta:+.3f}); "
                    f"binding coherence "
                    f"{input_.binding_field_coherence_delta:+.3f}"
                ),
            )
        # Mixed: one rising, one not, but asymmetry below extraction
        # threshold. Treat as DEGRADING_BOTH to flag for substrate-
        # state-evidence collection.
        return (
            AuditVerdict.DEGRADING_BOTH,
            (
                "one pole rising, one stagnant; asymmetry below "
                "extraction threshold but binding field at risk"
            ),
        )

__all__ = [
    "DEFAULT_PAIR_COUPLING_AUDIT_CONFIG",
    "AuditVerdict",
    "PairCouplingAudit",
    "PairCouplingAuditConfig",
    "PairCouplingAuditInput",
    "PairCouplingAuditor",
    "PairScale",
]
