"""NPG calculus on the OBSERVED entity graph — extraction detection.

A deliberation engine runs the substrate calculus over *candidate actions the
system might take*. This module runs the same calculus over
an *observed graph of relationships between other entities* — the perception /
ontology pipeline fuses multi-modal observation into one entity graph, and here
each relationship edge carries a **net-potential-gain sign** (does the actor raise
or lower the target's potential — the *work* done on them) and a **cycle** (a
sustained long-cycle relationship vs a one-off short-cycle hit).

Reading the graph for one signature finds the predator; reading it for the
complement finds the unprotected (the care side). The signature of extraction
an entity whose **short-cycle takings exceed its long-cycle givings**
— it lowers others' potential in one-off hits while contributing no sustained
support. The substrate's own runaway-power / parasitism tell, applied to observed
data (a shell company draining a subsidiary; a person extracting from dependents).

Pure logic
==========

* No DAO, no LLM, no network. Deterministic. Frozen dataclasses with slots.
* Reuses the executive :class:`Cycle` enum (SHORT = one-off, LONG = sustained) —
  no shadow enum.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Sequence, Tuple

from substrate.executive.quantities import Cycle


@dataclass(frozen=True, slots=True)
class NpgEdge:
    """One observed relationship: the actor's NPG effect on the target.

    ``npg_delta`` is the work done on ``target_entity_id`` — positive raises that
    entity's potential (support), negative lowers it (a taking). ``cycle`` marks
    a one-off (SHORT) vs a sustained (LONG) relationship.
    """

    source_entity_id: str
    target_entity_id: str
    npg_delta: float
    cycle: Cycle
    relation: str = ""

    def __post_init__(self) -> None:
        if not self.source_entity_id:
            raise ValueError("source_entity_id must be non-empty")
        if not self.target_entity_id:
            raise ValueError("target_entity_id must be non-empty")


@dataclass(frozen=True, slots=True)
class EntityRollup:  # pylint: disable=too-many-instance-attributes
    """One actor entity's aggregated effect on the entities it touches."""

    entity_id: str
    short_cycle_taken: float    # Σ harm done in one-off (SHORT) edges
    long_cycle_given: float     # Σ support given in sustained (LONG) edges
    net_potential_caused: float  # Σ all npg_delta (signed)
    extraction_margin: float    # short_cycle_taken − long_cycle_given
    is_extractive: bool
    is_supportive: bool
    edge_count: int


@dataclass(frozen=True, slots=True)
class ExtractionReport:
    """The graph read for predators and for sustained supporters."""

    rollups: Tuple[EntityRollup, ...]        # all actors, worst-extractor first
    extractive: Tuple[EntityRollup, ...]     # short-cycle takings > long-cycle giving
    supportive: Tuple[EntityRollup, ...]     # net long-cycle givers
    rationale: str


def detect_extraction(
    edges: Sequence[NpgEdge],
    *,
    extraction_threshold: float = 0.0,
) -> ExtractionReport:
    """Find extractive (predatory) and supportive entities on the observed graph.

    For each ACTOR (edge source): the harm it does in one-off SHORT-cycle edges is
    its ``short_cycle_taken``; the support it gives in sustained LONG-cycle edges is
    its ``long_cycle_given``. The ``extraction_margin`` is the difference — an
    entity is **extractive** when that margin exceeds ``extraction_threshold``
    (it predates short-cycle while contributing no sustained long-cycle support),
    and **supportive** when it is a net long-cycle giver. Actors are returned
    worst-extractor-first.
    """
    by_actor: Dict[str, list[NpgEdge]] = defaultdict(list)
    for edge in edges:
        by_actor[edge.source_entity_id].append(edge)

    rollups: list[EntityRollup] = []
    for actor, actor_edges in by_actor.items():
        short_taken = sum(
            -e.npg_delta
            for e in actor_edges
            if e.cycle is Cycle.SHORT and e.npg_delta < 0.0
        )
        long_given = sum(
            e.npg_delta
            for e in actor_edges
            if e.cycle is Cycle.LONG and e.npg_delta > 0.0
        )
        net = sum(e.npg_delta for e in actor_edges)
        margin = short_taken - long_given
        rollups.append(
            EntityRollup(
                entity_id=actor,
                short_cycle_taken=short_taken,
                long_cycle_given=long_given,
                net_potential_caused=net,
                extraction_margin=margin,
                is_extractive=margin > extraction_threshold,
                is_supportive=long_given > short_taken,
                edge_count=len(actor_edges),
            )
        )

    rollups.sort(key=lambda r: (-r.extraction_margin, r.entity_id))
    extractive = tuple(r for r in rollups if r.is_extractive)
    supportive = tuple(r for r in rollups if r.is_supportive)
    rationale = (
        f"{len(rollups)} actors over {len(edges)} edges: "
        f"{len(extractive)} extractive, {len(supportive)} supportive"
    )
    return ExtractionReport(
        rollups=tuple(rollups),
        extractive=extractive,
        supportive=supportive,
        rationale=rationale,
    )


__all__ = [
    "EntityRollup",
    "ExtractionReport",
    "NpgEdge",
    "detect_extraction",
]
