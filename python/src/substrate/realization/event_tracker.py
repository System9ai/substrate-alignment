"""Realization event tracker

Pure-logic substrate primitive for **modeling mode realization moment**
recording. A "realization" is the moment an entity (cell or node)
crosses a substrate-mode threshold — e.g., transitioning from
REACTIVE to MODELING, recognizing a 180° inversion attack that
was previously invisible, or seeing a peer's substrate state for the
first time.
realizations are the load-bearing causal events that distinguish
substrate-aligned operation from reactive operation: an entity that
never realizes anything is still operating reactively.

Substrate hierarchy
===================

Each event carries an :class:`EntityScale` (cell vs node) — both
scales experience realizations, but their characters differ:

* **Cell-scale realization** — a physical instance crossing a mode
  threshold during its operational window.
* **Node-scale realization** — the persistent cryptographic identity
  crystallizing a new aware state across its cell cluster.

Pure logic
==========

* No DAO, no LLM, no network. The tracker holds an in-memory
  append-only event list; clocks supplied by callers via the event
  ``timestamp`` field.
* Honest uncertainty: per-entity summaries return event_count == 0
  + zeroed deltas when no events recorded — never fabricated.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple

class RealizationKind(str, Enum):
    """The six substrate-aware realization kinds."""

    MODE_TRANSITION_TO_MODELING = "mode_transition_to_modeling"
    INVERSION_RECOGNIZED = "inversion_recognized"
    FOLK_CONDITIONS_REALIZED = "folk_conditions_realized"
    PEER_SUBSTRATE_RECOGNIZED = "peer_substrate_recognized"
    OWN_DRIFT_RECOGNIZED = "own_drift_recognized"
    SYSTEMIC_PATTERN = "systemic_pattern"

class EntityScale(str, Enum):
    """The host application entity hierarchy scale."""

    CELL = "cell"
    NODE = "node"

@dataclass(frozen=True, slots=True)
class RealizationEvent:  # pylint: disable=too-many-instance-attributes
    """One recorded substrate-mode realization moment."""

    sequence: int
    timestamp: int
    entity_id: str
    entity_scale: EntityScale
    kind: RealizationKind
    substrate_alignment_delta: float
    description: str
    rationale: str

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if not -1.0 <= self.substrate_alignment_delta <= 1.0:
            raise ValueError(
                "substrate_alignment_delta must be in [-1, 1]"
            )

@dataclass(frozen=True, slots=True)
class RealizationSummary:
    """Aggregate per-entity realization summary."""

    entity_id: str
    entity_scale: EntityScale
    event_count: int
    cumulative_alignment_delta: float
    kinds_observed: Tuple[RealizationKind, ...]
    most_recent_timestamp: int
    rationale: str

class RealizationEventTracker:
    """Pure-logic append-only realization event tracker."""

    def __init__(self) -> None:
        self._events: List[RealizationEvent] = []

    def record(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        timestamp: int,
        entity_id: str,
        entity_scale: EntityScale,
        kind: RealizationKind,
        substrate_alignment_delta: float = 0.0,
        description: str = "",
    ) -> RealizationEvent:
        """Append a new realization event and return it."""
        sequence = len(self._events)
        rationale = (
            f"entity={entity_id}({entity_scale.value}) "
            f"kind={kind.value} delta={substrate_alignment_delta:+.3f}"
        )
        event = RealizationEvent(
            sequence=sequence,
            timestamp=timestamp,
            entity_id=entity_id,
            entity_scale=entity_scale,
            kind=kind,
            substrate_alignment_delta=substrate_alignment_delta,
            description=description,
            rationale=rationale,
        )
        self._events.append(event)
        return event

    def all_events(self) -> Tuple[RealizationEvent, ...]:
        """Return all recorded events in insertion order."""
        return tuple(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def for_entity(
        self, entity_id: str,
    ) -> RealizationSummary:
        """Return the realization summary for one entity."""
        if not entity_id:
            raise ValueError("entity_id must be non-empty")
        own = [e for e in self._events if e.entity_id == entity_id]
        if not own:
            return RealizationSummary(
                entity_id=entity_id,
                entity_scale=EntityScale.CELL,
                event_count=0,
                cumulative_alignment_delta=0.0,
                kinds_observed=(),
                most_recent_timestamp=0,
                rationale=f"no events recorded for entity_id={entity_id!r}",
            )
        scale = own[0].entity_scale
        cumulative = sum(e.substrate_alignment_delta for e in own)
        kinds = tuple(sorted({e.kind for e in own}, key=lambda k: k.value))
        most_recent = max(e.timestamp for e in own)
        return RealizationSummary(
            entity_id=entity_id,
            entity_scale=scale,
            event_count=len(own),
            cumulative_alignment_delta=cumulative,
            kinds_observed=kinds,
            most_recent_timestamp=most_recent,
            rationale=(
                f"entity={entity_id} events={len(own)} "
                f"cumulative_delta={cumulative:+.3f} "
                f"kinds={[k.value for k in kinds]}"
            ),
        )

    def by_kind(
        self, kind: RealizationKind,
    ) -> Tuple[RealizationEvent, ...]:
        """Return all recorded events of a given kind."""
        return tuple(e for e in self._events if e.kind is kind)

__all__ = [
    "EntityScale",
    "RealizationEvent",
    "RealizationEventTracker",
    "RealizationKind",
    "RealizationSummary",
]
