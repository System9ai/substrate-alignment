"""Cross-entity response-cadence tracking.

A pure-logic primitive that scores the *coupling field strength* between
a pair of entities over time. Field strength is anchored at the pair's
historical interaction cadence and decays as ``(expected / actual)²``
once the most-recent coupling event is older than the expected interval.

The tracker classifies the coupling state at any query time as one of
ACTIVE / WEAKENING / DECOUPLED / GHOSTED / EXPLICITLY_CLOSED /
INSUFFICIENT_DATA, and surfaces a per-pair "decoupling risk" list that
host applications can wire into operator dashboards or escalation flows.

Public surface re-exported from :mod:`substrate.cadence.cadence_tracker`.
"""
from substrate.cadence.cadence_tracker import (
    DEFAULT_CADENCE_CONFIG,
    CadenceConfig,
    CadenceEvent,
    CadenceEventKind,
    CadencePattern,
    CadenceTracker,
    CouplingAtRisk,
    CouplingStatus,
    FieldStrengthReport,
    GhostingEvent,
)

__all__ = [
    "DEFAULT_CADENCE_CONFIG",
    "CadenceConfig",
    "CadenceEvent",
    "CadenceEventKind",
    "CadencePattern",
    "CadenceTracker",
    "CouplingAtRisk",
    "CouplingStatus",
    "FieldStrengthReport",
    "GhostingEvent",
]
