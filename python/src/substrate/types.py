"""Canonical vocabulary types for substrate-alignment.

Three primitives every conforming implementation shares:

- :class:`SubstrateMode` — the four operating-cycle modes a classified
  entity can be in.
- :class:`AlignmentVector` — per-component alignment signals (trust,
  expertise, capability, health), each in ``[0.0, 1.0]``.
- :class:`SubstrateMetadata` — the persisted record of an entity's
  classified mode, its current alignment vector, and the rolled-up
  net-potential score.

Consumers import these types here rather than redefining them locally so
that all primitives in the package — gates, classifiers, drift signals,
audit-chain records — speak the same vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Optional


class SubstrateMode(str, Enum):
    """The four operating-cycle modes.

    - ``SHORT_CYCLE`` (``"ShortCycle"``) — rapid, transactional,
      low-context operation. Suitable for cache fills, telemetry ticks,
      throw-away inferences.
    - ``LONG_CYCLE`` (``"LongCycle"``) — sustained, contextual,
      principled operation. The substrate-aligned default for
      production agents and observers.
    - ``MIXED`` (``"Mixed"``) — a blend of cycles; the classifier could
      not commit. Common for entities mid-classification.
    - ``UNKNOWN`` (``"Unknown"``) — never classified. Default for
      newly-created entities until the classifier runs.

    str-Enum so values serialise identically across SQL, JSON, and the
    canonical-bytes form used by the audit chain.
    """

    SHORT_CYCLE = "ShortCycle"
    LONG_CYCLE = "LongCycle"
    MIXED = "Mixed"
    UNKNOWN = "Unknown"


#: All defined substrate modes. Stays in lockstep with the persisted
#: ``substrate_mode`` column's CHECK constraint in any host database.
SUBSTRATE_MODES: Final[frozenset[str]] = frozenset(m.value for m in SubstrateMode)


@dataclass(frozen=True, slots=True)
class AlignmentVector:
    """Per-component alignment signals for one entity.

    Each component is in ``[0.0, 1.0]``. Components are typically
    populated from the host application's trust-scoring,
    expertise-tracking, capability-publication, and health-checking
    subsystems; the package itself takes no opinion on how each signal
    is computed.

    The aggregate :func:`compute_net_potential` (in
    :mod:`substrate.alignment`) rolls these four into a single
    ``[0.0, 1.0]`` score under configurable weights.
    """

    trust: float = 0.0
    expertise: float = 0.0
    capability: float = 0.0
    health: float = 0.0

    def __post_init__(self) -> None:
        for name in ("trust", "expertise", "capability", "health"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise ValueError(
                    f"AlignmentVector.{name} must be in [0.0, 1.0]; got {v}"
                )


@dataclass(frozen=True, slots=True)
class SubstrateMetadata:
    """Persisted alignment state for one entity.

    Composite identity: ``(entity_type, entity_id)``. Entities may share
    an id across types — a user-id and a node-id can coincide — so the
    primary identity is the pair, not just the id.

    Fields:

    - ``substrate_mode`` — the four-state classifier output.
    - ``classifier`` — names the classifier that produced this mode
      (e.g. ``"auto"``, ``"operator:alice"``, ``"contract:v1"``). Not
      free-text; operator surfaces group by this value.
    - ``classifier_rationale`` — human-readable justification for the
      classified mode.
    - ``net_potential`` — the aggregate of :class:`AlignmentVector`
      under the active weights; recomputed on every update so consumers
      filtering on it stay consistent with the underlying components.
    - ``classified_at`` — wall-clock ISO timestamp the classifier
      committed the mode. Distinct from ``updated_at``, which moves with
      every signal refresh, not only with classifier runs.
    """

    entity_type: str
    entity_id: str
    substrate_mode: SubstrateMode = SubstrateMode.UNKNOWN
    classifier: str = ""
    classifier_rationale: str = ""
    classified_at: Optional[str] = None
    alignment_vector: AlignmentVector = field(default_factory=AlignmentVector)
    net_potential: float = 0.0
    last_observed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by_entity_id: Optional[str] = None
    updated_by_entity_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.entity_type:
            raise ValueError("SubstrateMetadata.entity_type must be non-empty")
        if not self.entity_id:
            raise ValueError("SubstrateMetadata.entity_id must be non-empty")
        if not 0.0 <= self.net_potential <= 1.0:
            raise ValueError(
                f"SubstrateMetadata.net_potential must be in [0.0, 1.0]; "
                f"got {self.net_potential}"
            )


__all__ = [
    "SUBSTRATE_MODES",
    "AlignmentVector",
    "SubstrateMetadata",
    "SubstrateMode",
]
