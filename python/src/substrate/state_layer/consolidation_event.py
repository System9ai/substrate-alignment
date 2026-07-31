"""Consolidation event primitive: Companion #2

Pure-logic substrate-state primitive representing a *state-layer
consolidation event*: a point at which substrate-state observations
are compressed/checkpointed into a longer-window representation. The
which compartmentalization invariants must be verified; they are the
substrate equivalent of memory consolidation in biological cognition.

A consolidation event records:

* The source observation range (cycle indices)
* The compressed representation hash
* The compartment label (substrate condition #3 multi-scale)
* The actor that produced the event
* Any invariants the actor declares the event upholds

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the event fields.
* Frozen dataclass with slots.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

class ConsolidationKind(str, Enum):
    """Kind of consolidation event."""

    CHECKPOINT = "checkpoint"
    COMPRESSION = "compression"
    SUMMARIZATION = "summarization"
    PROMOTION = "promotion"

@dataclass(frozen=True, slots=True)
class ConsolidationEvent:  # pylint: disable=too-many-instance-attributes
    """One state-layer consolidation event."""

    event_id: str
    actor_entity_id: str
    compartment_label_id: str
    kind: ConsolidationKind
    source_first_cycle: int
    source_last_cycle: int
    compressed_representation_hash: str
    declared_invariants: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must be non-empty")
        if not self.actor_entity_id:
            raise ValueError("actor_entity_id must be non-empty")
        if not self.compartment_label_id:
            raise ValueError(
                "compartment_label_id must be non-empty"
            )
        if not self.compressed_representation_hash:
            raise ValueError(
                "compressed_representation_hash must be non-empty"
            )
        if self.source_first_cycle < 0:
            raise ValueError("source_first_cycle must be >= 0")
        if self.source_last_cycle < self.source_first_cycle:
            raise ValueError(
                "source_last_cycle must be >= source_first_cycle"
            )
        for inv in self.declared_invariants:
            if not inv:
                raise ValueError(
                    "declared_invariants entries must be non-empty"
                )

    @property
    def source_cycle_count(self) -> int:
        """Inclusive count of consolidated cycles."""
        return self.source_last_cycle - self.source_first_cycle + 1

REQUIRED_INVARIANT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "identity-preserved",
        "cryptographic-chain-intact",
        "compartment-label-preserved",
    }
)

def required_invariants_present(event: ConsolidationEvent) -> bool:
    """True iff event.declared_invariants includes every required key."""
    return REQUIRED_INVARIANT_KEYS.issubset(set(event.declared_invariants))

__all__ = [
    "ConsolidationEvent",
    "ConsolidationKind",
    "REQUIRED_INVARIANT_KEYS",
    "required_invariants_present",
]
