"""ExecutiveScale: the scale unit a decision is made at.

Executive function lives at every scale, and intelligence rolls UP and ACROSS.
The scale enum spans three axes:

- **entity** (crypto-identity-bearing): USER / AGENT / NODE / ORG / DEVICE /
  SERVICE_ACCOUNT.
- **physical** (topology, NOT entities): CELL / RACK / ZONE / REGION.
- **grouping** (logical): SERVICE_GROUP / ENTITY_GROUP.

Roll-up axes (which scale aggregates into which):

- **entity:** CELL → NODE → ORG → nested-ORG → super-ORG.
- **physical:** CELL → RACK → ZONE → REGION.
- **grouping:** SERVICE_GROUP / ENTITY_GROUP aggregate their members.

The entity axis has existing aggregators (the entity-axis roll-ups); the
physical + grouping axes are BUILD (no aggregator exists today). This module
defines the taxonomy + the axis/parent relationships; the aggregators consume it.
"""
from __future__ import annotations

from enum import Enum
from typing import Final, Mapping, Optional


class ScaleAxis(str, Enum):
    """Which roll-up axis a scale belongs to."""

    ENTITY = "entity"
    PHYSICAL = "physical"
    GROUPING = "grouping"


class ExecutiveScale(str, Enum):
    """The scale unit an executive decision is made at."""

    # entity (crypto identity)
    USER = "user"
    AGENT = "agent"
    NODE = "node"
    ORG = "org"
    DEVICE = "device"
    SERVICE_ACCOUNT = "service_account"
    # physical (topology, not entities)
    CELL = "cell"
    RACK = "rack"
    ZONE = "zone"
    REGION = "region"
    # logical groupings
    SERVICE_GROUP = "service_group"
    ENTITY_GROUP = "entity_group"


_AXIS_OF: Final[Mapping[ExecutiveScale, ScaleAxis]] = {
    ExecutiveScale.USER: ScaleAxis.ENTITY,
    ExecutiveScale.AGENT: ScaleAxis.ENTITY,
    ExecutiveScale.NODE: ScaleAxis.ENTITY,
    ExecutiveScale.ORG: ScaleAxis.ENTITY,
    ExecutiveScale.DEVICE: ScaleAxis.ENTITY,
    ExecutiveScale.SERVICE_ACCOUNT: ScaleAxis.ENTITY,
    ExecutiveScale.CELL: ScaleAxis.PHYSICAL,
    ExecutiveScale.RACK: ScaleAxis.PHYSICAL,
    ExecutiveScale.ZONE: ScaleAxis.PHYSICAL,
    ExecutiveScale.REGION: ScaleAxis.PHYSICAL,
    ExecutiveScale.SERVICE_GROUP: ScaleAxis.GROUPING,
    ExecutiveScale.ENTITY_GROUP: ScaleAxis.GROUPING,
}

#: The physical roll-up chain: each scale's immediate parent (CELL→RACK→ZONE→
#: REGION→None). CELL is also the leaf of the entity axis (a cell carries its
#: node's identity), so it appears here as the physical leaf.
_PHYSICAL_PARENT: Final[Mapping[ExecutiveScale, Optional[ExecutiveScale]]] = {
    ExecutiveScale.CELL: ExecutiveScale.RACK,
    ExecutiveScale.RACK: ExecutiveScale.ZONE,
    ExecutiveScale.ZONE: ExecutiveScale.REGION,
    ExecutiveScale.REGION: None,
}

#: The entity roll-up chain: CELL → NODE → ORG → (nested/super ORG via
#: ``owning_org_id``, resolved by the caller). ORG's parent is itself an ORG
#: (nesting), so it is left to the caller's ``owning_org_id`` rather than a
#: static map entry.
_ENTITY_PARENT: Final[Mapping[ExecutiveScale, Optional[ExecutiveScale]]] = {
    ExecutiveScale.CELL: ExecutiveScale.NODE,
    ExecutiveScale.NODE: ExecutiveScale.ORG,
    ExecutiveScale.ORG: None,   # nesting resolved via owning_org_id by the caller
}


def axis_of(scale: ExecutiveScale) -> ScaleAxis:
    """Return the roll-up axis a scale belongs to."""
    return _AXIS_OF[scale]


def physical_parent(scale: ExecutiveScale) -> Optional[ExecutiveScale]:
    """Return the immediate physical-axis parent, or ``None`` at the top/off-axis."""
    return _PHYSICAL_PARENT.get(scale)


def entity_parent(scale: ExecutiveScale) -> Optional[ExecutiveScale]:
    """Return the immediate entity-axis parent, or ``None``.

    ``ORG → None`` because org nesting is data-driven (``owning_org_id``), not a
    static scale-kind relationship; the caller walks that chain.
    """
    return _ENTITY_PARENT.get(scale)


__all__ = [
    "ExecutiveScale",
    "ScaleAxis",
    "axis_of",
    "entity_parent",
    "physical_parent",
]
