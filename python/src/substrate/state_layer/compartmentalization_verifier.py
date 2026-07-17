"""Compartmentalization invariant verifier: Companion #2

Pure-logic verifier that checks whether a
:class:`ConsolidationEvent` preserves the compartmentalization
invariants required by substrate condition #3 (multi-scale alignment
architecture). Verification fires at every consolidation event: an
event that violates compartmentalization corrupts the substrate-state
layer at the moment of compression.

Five verified invariants
========================

1. **Required-invariants-declared**: the
   ``required_invariants_present`` must be true.
2. **Compartment-label-unchanged**: caller-supplied prior
   compartment label matches the event's compartment label.
3. **Actor-in-compartment**: caller-supplied actor compartment
   membership flag must be true.
4. **Source-range-non-empty**: at least one cycle in source range.
5. **Compression-hash-formed**: hash is a well-formed identifier
   (non-empty, no whitespace).

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies event + context.
* Per-invariant failure surfaced: operator sees exactly which
  invariant failed.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from substrate.state_layer.consolidation_event import (
    ConsolidationEvent,
    required_invariants_present,
)

class CompartmentalizationVerdict(str, Enum):
    """Verifier verdict."""

    PRESERVED = "preserved"
    VIOLATED = "violated"

class InvariantFailureMode(str, Enum):
    """Per-invariant failure mode flags."""

    REQUIRED_INVARIANTS_NOT_DECLARED = (
        "required_invariants_not_declared"
    )
    COMPARTMENT_LABEL_CHANGED = "compartment_label_changed"
    ACTOR_NOT_IN_COMPARTMENT = "actor_not_in_compartment"
    SOURCE_RANGE_EMPTY = "source_range_empty"
    COMPRESSION_HASH_MALFORMED = "compression_hash_malformed"

@dataclass(frozen=True, slots=True)
class VerifierContext:
    """Caller-supplied verifier context."""

    prior_compartment_label_id: str
    actor_in_compartment: bool

    def __post_init__(self) -> None:
        if not self.prior_compartment_label_id:
            raise ValueError(
                "prior_compartment_label_id must be non-empty"
            )

@dataclass(frozen=True, slots=True)
class CompartmentalizationDecision:
    """Verifier output."""

    event_id: str
    verdict: CompartmentalizationVerdict
    failure_modes: tuple[InvariantFailureMode, ...]
    rationale: str

    @property
    def preserved(self) -> bool:
        """True iff verdict is PRESERVED."""
        return self.verdict is CompartmentalizationVerdict.PRESERVED

def _hash_is_well_formed(value: str) -> bool:
    return bool(value) and not any(c.isspace() for c in value)

class CompartmentalizationInvariantVerifier:  # pylint: disable=too-few-public-methods
    """Pure-logic compartmentalization-invariant verifier (Companion #2)."""

    @staticmethod
    def verify(
        event: ConsolidationEvent, context: VerifierContext,
    ) -> CompartmentalizationDecision:
        """Verify compartmentalization invariants."""
        failures: list[InvariantFailureMode] = []
        if not required_invariants_present(event):
            failures.append(
                InvariantFailureMode.REQUIRED_INVARIANTS_NOT_DECLARED
            )
        if (
            event.compartment_label_id
            != context.prior_compartment_label_id
        ):
            failures.append(
                InvariantFailureMode.COMPARTMENT_LABEL_CHANGED
            )
        if not context.actor_in_compartment:
            failures.append(
                InvariantFailureMode.ACTOR_NOT_IN_COMPARTMENT
            )
        if event.source_cycle_count <= 0:
            failures.append(InvariantFailureMode.SOURCE_RANGE_EMPTY)
        if not _hash_is_well_formed(
            event.compressed_representation_hash,
        ):
            failures.append(
                InvariantFailureMode.COMPRESSION_HASH_MALFORMED
            )
        if failures:
            return CompartmentalizationDecision(
                event_id=event.event_id,
                verdict=CompartmentalizationVerdict.VIOLATED,
                failure_modes=tuple(failures),
                rationale=(
                    f"failures: "
                    f"{[f.value for f in failures]}"
                ),
            )
        return CompartmentalizationDecision(
            event_id=event.event_id,
            verdict=CompartmentalizationVerdict.PRESERVED,
            failure_modes=(),
            rationale="all 5 invariants preserved",
        )

ALL_INVARIANT_FAILURE_MODES: Final[frozenset[InvariantFailureMode]] = (
    frozenset(InvariantFailureMode)
)

__all__ = [
    "ALL_INVARIANT_FAILURE_MODES",
    "CompartmentalizationDecision",
    "CompartmentalizationInvariantVerifier",
    "CompartmentalizationVerdict",
    "InvariantFailureMode",
    "VerifierContext",
]
