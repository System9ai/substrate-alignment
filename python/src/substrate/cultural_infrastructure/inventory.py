"""Cultural-infrastructure inventory — Companion #2

Pure-logic inventory of which condition-#6 cultural-infrastructure
substrate primitives an org or node has wired into its deployment.
The
loophole prevention) is satisfied not by a single primitive but by the
*ensemble* of six mechanisms operating together. The inventory
enumerates which mechanisms are present and which are missing.

Condition #6 mechanisms
=======================

1. **Identity-grounded reputation** — Phase 23 trust scorer + Phase 50
   multi-signal extension.
2. **Symmetric audit** — Phase 16 trace ledger + peer-attestation.
3. **Reciprocal feedback** — Phase 28 tit-for-tat + Phase 120
   reciprocal feedback protocol.
4. **Halt-and-escalate** — Phase 100 halt-and-escalate protocol.
5. **Substrate-aware voting** — Phase 33 awareness precondition +
   Phase 115 position classifier.
6. **Pair-coupled architecture** — Phase 118 pair-coupled agent
   architecture marker.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the per-mechanism
  presence vector.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

class CulturalMechanism(str, Enum):
    """The six condition-#6 cultural-infrastructure mechanisms."""

    IDENTITY_GROUNDED_REPUTATION = "identity_grounded_reputation"
    SYMMETRIC_AUDIT = "symmetric_audit"
    RECIPROCAL_FEEDBACK = "reciprocal_feedback"
    HALT_AND_ESCALATE = "halt_and_escalate"
    SUBSTRATE_AWARE_VOTING = "substrate_aware_voting"
    PAIR_COUPLED_ARCHITECTURE = "pair_coupled_architecture"

ALL_MECHANISMS: Final[frozenset[CulturalMechanism]] = frozenset(
    CulturalMechanism
)

@dataclass(frozen=True, slots=True)
class MechanismPresence:
    """Caller-supplied per-mechanism presence."""

    mechanism: CulturalMechanism
    present: bool
    coverage_ratio: float
    """Fraction of relevant call sites that wire the mechanism,
    in [0, 1]. Aspirational: 1.0 = fully wired."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.coverage_ratio <= 1.0:
            raise ValueError(
                "coverage_ratio must be in [0, 1]"
            )

@dataclass(frozen=True, slots=True)
class InventoryInput:
    """Caller-supplied inventory input."""

    org_or_node_id: str
    mechanisms: tuple[MechanismPresence, ...]

    def __post_init__(self) -> None:
        if not self.org_or_node_id:
            raise ValueError("org_or_node_id must be non-empty")
        seen: set[CulturalMechanism] = set()
        for entry in self.mechanisms:
            if entry.mechanism in seen:
                raise ValueError(
                    f"duplicate mechanism {entry.mechanism.value}"
                )
            seen.add(entry.mechanism)

@dataclass(frozen=True, slots=True)
class InventoryReport:  # pylint: disable=too-many-instance-attributes
    """Inventory report output."""

    org_or_node_id: str
    present_count: int
    missing_count: int
    mean_coverage_ratio: float
    present_mechanisms: tuple[CulturalMechanism, ...]
    missing_mechanisms: tuple[CulturalMechanism, ...]
    coverage_by_mechanism: tuple[tuple[CulturalMechanism, float], ...]

    @property
    def is_complete(self) -> bool:
        """True iff every mechanism is present with non-zero coverage."""
        return self.missing_count == 0 and self.mean_coverage_ratio > 0.0

class CulturalInfrastructureInventory:  # pylint: disable=too-few-public-methods
    """Pure-logic cultural-infrastructure inventory (Companion #2)."""

    @staticmethod
    def compile(input_: InventoryInput) -> InventoryReport:
        """Compile the inventory report."""
        present: list[CulturalMechanism] = []
        missing: list[CulturalMechanism] = []
        coverages: list[tuple[CulturalMechanism, float]] = []
        provided = {entry.mechanism: entry for entry in input_.mechanisms}
        for mechanism in CulturalMechanism:
            entry = provided.get(mechanism)
            if entry is None or not entry.present:
                missing.append(mechanism)
                coverages.append((mechanism, 0.0))
            else:
                present.append(mechanism)
                coverages.append((mechanism, entry.coverage_ratio))
        mean = (
            sum(c for _, c in coverages) / len(coverages)
        )
        return InventoryReport(
            org_or_node_id=input_.org_or_node_id,
            present_count=len(present),
            missing_count=len(missing),
            mean_coverage_ratio=mean,
            present_mechanisms=tuple(present),
            missing_mechanisms=tuple(missing),
            coverage_by_mechanism=tuple(coverages),
        )

__all__ = [
    "ALL_MECHANISMS",
    "CulturalInfrastructureInventory",
    "CulturalMechanism",
    "InventoryInput",
    "InventoryReport",
    "MechanismPresence",
]
