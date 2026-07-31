"""Cross-org substrate-mode classifier (substrate).

Aggregates per-entity :class:`SubstrateMode` classifications across an
organization's members (cells, agents, users) and produces an
org-level classification with cohesion + dominant-mode summary.

Pure logic:

- No DB access. Caller assembles the member list and passes it in.
- Deterministic. Same inputs → same outputs.
- Immutable result via frozen dataclass.

Substrate-alignment intent: cross-scale substrate-mode-reasoning per
substrate condition #8 means orgs can ask "is this org operating in
LONG_CYCLE substrate-aligned mode, or has it drifted to SHORT_CYCLE
transactional mode?" without inventing new vocabulary at the
org scale.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from substrate.types import SubstrateMode

@dataclass(frozen=True, slots=True)
class OrgMember:
    """One classified member of an org (cell, agent, user, etc.)."""

    entity_id: str
    entity_type: str
    substrate_mode: SubstrateMode

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if not self.entity_type:
            raise ValueError("entity_type must be non-empty")

@dataclass(frozen=True, slots=True)
class OrgSubstrateModeResult:  # pylint: disable=too-many-instance-attributes
    """Aggregate substrate-mode classification across an org's members."""

    org_id: str
    member_count: int
    aggregate_mode: SubstrateMode
    long_cycle_fraction: float
    short_cycle_fraction: float
    mixed_fraction: float
    unknown_fraction: float
    cohesion_score: float
    reasoning: str

    @property
    def is_substrate_aligned(self) -> bool:
        """True iff the org's aggregate mode is LONG_CYCLE.

        Per this discipline, ``LONG_CYCLE`` is the
        substrate-aligned production default; any other aggregate is
        a signal worth surfacing.
        """
        return self.aggregate_mode is SubstrateMode.LONG_CYCLE

    @property
    def is_drifted(self) -> bool:
        """True iff the org's aggregate mode is SHORT_CYCLE.

        A SHORT_CYCLE org-aggregate is the canonical "drift to
        transactional operating" signal at the org scale.
        """
        return self.aggregate_mode is SubstrateMode.SHORT_CYCLE

def _fraction(count: int, total: int) -> float:
    return (count / total) if total > 0 else 0.0

def _cohesion(distribution: Mapping[SubstrateMode, int], total: int) -> float:
    """Return cohesion in ``[0, 1]``, where higher means more concentrated.

    The cohesion is the largest mode's fraction. ``1.0`` = unanimous;
    ``0.25`` = perfectly split four ways.
    """
    if total <= 0:
        return 0.0
    return max(distribution.values()) / total

def _aggregate_mode(
    distribution: Mapping[SubstrateMode, int],
    total: int,
) -> SubstrateMode:
    """Return the org-aggregate substrate mode.

    Rules (in order):

    1. If the population is empty → UNKNOWN.
    2. If LONG_CYCLE is the strict plurality → LONG_CYCLE.
    3. If SHORT_CYCLE is the strict plurality → SHORT_CYCLE.
    4. Otherwise → MIXED.

    "Strict plurality" means the mode is the unique max. Ties
    resolve to MIXED. This discipline forbids picking
    a winner when the population can't commit.
    """
    if total <= 0:
        return SubstrateMode.UNKNOWN
    counts = {m: distribution.get(m, 0) for m in SubstrateMode}
    top_count = max(counts.values())
    top_modes = [m for m, c in counts.items() if c == top_count]
    if len(top_modes) != 1:
        return SubstrateMode.MIXED
    return top_modes[0]

def classify_org(
    org_id: str,
    members: Sequence[OrgMember],
) -> OrgSubstrateModeResult:
    """Classify an org's aggregate substrate mode.

    The caller assembles the member list (cells, agents, users that
    are members of this org). The classifier is stateless and
    deterministic.

    Raises ``ValueError`` if ``org_id`` is empty.
    """
    if not org_id:
        raise ValueError("org_id must be non-empty")
    distribution: dict[SubstrateMode, int] = {m: 0 for m in SubstrateMode}
    seen: set[str] = set()
    deduped: list[OrgMember] = []
    for m in members:
        key = f"{m.entity_type}/{m.entity_id}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)
        distribution[m.substrate_mode] += 1
    total = len(deduped)
    aggregate = _aggregate_mode(distribution, total)
    long_frac = _fraction(distribution[SubstrateMode.LONG_CYCLE], total)
    short_frac = _fraction(distribution[SubstrateMode.SHORT_CYCLE], total)
    mixed_frac = _fraction(distribution[SubstrateMode.MIXED], total)
    unknown_frac = _fraction(distribution[SubstrateMode.UNKNOWN], total)
    cohesion = _cohesion(distribution, total)
    if total == 0:
        reasoning = f"org={org_id} has no members; aggregate=UNKNOWN"
    else:
        reasoning = (
            f"org={org_id} members={total} long={long_frac:.2f} "
            f"short={short_frac:.2f} mixed={mixed_frac:.2f} "
            f"unknown={unknown_frac:.2f} cohesion={cohesion:.2f} "
            f"aggregate={aggregate.value}"
        )
    return OrgSubstrateModeResult(
        org_id=org_id,
        member_count=total,
        aggregate_mode=aggregate,
        long_cycle_fraction=long_frac,
        short_cycle_fraction=short_frac,
        mixed_fraction=mixed_frac,
        unknown_fraction=unknown_frac,
        cohesion_score=cohesion,
        reasoning=reasoning,
    )

__all__ = [
    "OrgMember",
    "OrgSubstrateModeResult",
    "classify_org",
]
