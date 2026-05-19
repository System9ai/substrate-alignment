"""Pair-coupled agent architecture — Companion #2

Pure-logic primitive that records the architectural commitment that
two agents are deployed as a *pair-coupled architecture*: twin
entities with substrate-aligned mutual oversight, each holding
distinct cryptographic identity (substrate condition #1) but bound by
a shared coupling identity and reciprocal-feedback discipline.

The primitive itself is small — it composes pole identifiers, the
designed asymmetry, the binding cryptographic-identity attestations,
and a deployment status. Downstream consumers (Phase 119 asymmetry
verifier, Phase 120 reciprocal protocol, Phase 122 extraction monitor)
read this declaration to operate correctly.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the declaration.
* Two-pole construction-invariant: pole-A and pole-B must have
  distinct entity ids AND distinct attestation chains.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from substrate.pair_coupling.alignment_audit import (
    PairScale,
)

class ArchitectureStatus(str, Enum):
    """Lifecycle status of a pair-coupled architecture declaration."""

    DECLARED = "declared"
    ACTIVE = "active"
    QUIESCENT = "quiescent"
    RETIRED = "retired"

@dataclass(frozen=True, slots=True)
class PolePrincipal:
    """One pole's cryptographic-identity binding."""

    entity_id: str
    role_label: str
    attestation_chain_id: str
    designed_authority_scope: str

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if not self.role_label:
            raise ValueError("role_label must be non-empty")
        if not self.attestation_chain_id:
            raise ValueError(
                "attestation_chain_id must be non-empty"
            )
        if not self.designed_authority_scope:
            raise ValueError(
                "designed_authority_scope must be non-empty"
            )

@dataclass(frozen=True, slots=True)
class PairCoupledArchitecture:  # pylint: disable=too-many-instance-attributes
    """Pair-coupled-agent architecture declaration."""

    coupling_id: str
    scale: PairScale
    pole_a: PolePrincipal
    pole_b: PolePrincipal
    designed_asymmetry: float
    """Signed designed asymmetry, positive favors pole_a."""

    declared_cycle_index: int
    status: ArchitectureStatus

    def __post_init__(self) -> None:
        if not self.coupling_id:
            raise ValueError("coupling_id must be non-empty")
        if self.pole_a.entity_id == self.pole_b.entity_id:
            raise ValueError(
                "pole_a.entity_id and pole_b.entity_id must differ"
            )
        if (
            self.pole_a.attestation_chain_id
            == self.pole_b.attestation_chain_id
        ):
            raise ValueError(
                "pole_a and pole_b must have distinct attestation chains"
            )
        if self.pole_a.role_label == self.pole_b.role_label:
            raise ValueError(
                "pole_a and pole_b must have distinct role_labels"
            )
        if not -1.0 <= self.designed_asymmetry <= 1.0:
            raise ValueError("designed_asymmetry must be in [-1, 1]")
        if self.declared_cycle_index < 0:
            raise ValueError(
                "declared_cycle_index must be >= 0"
            )

    @property
    def is_active(self) -> bool:
        """True iff status is ACTIVE."""
        return self.status is ArchitectureStatus.ACTIVE

@dataclass(frozen=True, slots=True)
class ArchitectureTransition:
    """A status transition recorded against the declaration."""

    coupling_id: str
    from_status: ArchitectureStatus
    to_status: ArchitectureStatus

_LEGAL_TRANSITIONS: Final[
    dict[tuple[ArchitectureStatus, ArchitectureStatus], bool]
] = {
    (ArchitectureStatus.DECLARED, ArchitectureStatus.ACTIVE): True,
    (ArchitectureStatus.DECLARED, ArchitectureStatus.RETIRED): True,
    (ArchitectureStatus.ACTIVE, ArchitectureStatus.QUIESCENT): True,
    (ArchitectureStatus.ACTIVE, ArchitectureStatus.RETIRED): True,
    (ArchitectureStatus.QUIESCENT, ArchitectureStatus.ACTIVE): True,
    (ArchitectureStatus.QUIESCENT, ArchitectureStatus.RETIRED): True,
}

class IllegalArchitectureTransition(ValueError):
    """Raised when a status transition is not legal."""

class PairCoupledArchitectureManager:  # pylint: disable=too-few-public-methods
    """Pure-logic helper for pair-coupled architecture transitions."""

    @staticmethod
    def transition(
        *,
        current: PairCoupledArchitecture,
        to_status: ArchitectureStatus,
    ) -> PairCoupledArchitecture:
        """Return a new declaration with the requested status."""
        if (current.status, to_status) not in _LEGAL_TRANSITIONS:
            raise IllegalArchitectureTransition(
                f"illegal transition: {current.status.value} -> "
                f"{to_status.value}"
            )
        return PairCoupledArchitecture(
            coupling_id=current.coupling_id,
            scale=current.scale,
            pole_a=current.pole_a,
            pole_b=current.pole_b,
            designed_asymmetry=current.designed_asymmetry,
            declared_cycle_index=current.declared_cycle_index,
            status=to_status,
        )

__all__ = [
    "ArchitectureStatus",
    "ArchitectureTransition",
    "IllegalArchitectureTransition",
    "PairCoupledArchitecture",
    "PairCoupledArchitectureManager",
    "PolePrincipal",
]
