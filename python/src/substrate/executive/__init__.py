"""The executive layer — the band as a decision engine.

The resistance band, made operational as the substrate's executive function: the
corrected symmetric ladder (geometric levels, temporal consequences), the
quantity/scale discipline that keeps "what percentage is this and what does it
mean" precise, and the order metric that reads emergence from a distribution.

Curated exports — import the names, not deep module paths.
"""
from __future__ import annotations

from substrate.executive.band import (
    BAND_TOLERANCE,
    DEFAULT_BAND_PROFILE,
    TWO_THIRDS,
    BandProfile,
    BandProfileInvalid,
    CyclePhase,
    LoadZone,
    classify_cycle_phase,
    classify_load_zone,
    validate_band_profile,
    zone_to_legacy,
)
from substrate.executive.negentropy import (
    NegentropyDirection,
    NegentropyReport,
    negentropy,
    order_index,
)
from substrate.executive.quantities import (
    Cycle,
    GrowthNotADecisionBand,
    Quantity,
    ResourceKind,
    setpoint_for,
)

__all__ = [
    "BAND_TOLERANCE",
    "DEFAULT_BAND_PROFILE",
    "TWO_THIRDS",
    "BandProfile",
    "BandProfileInvalid",
    "Cycle",
    "CyclePhase",
    "GrowthNotADecisionBand",
    "LoadZone",
    "NegentropyDirection",
    "NegentropyReport",
    "Quantity",
    "ResourceKind",
    "classify_cycle_phase",
    "classify_load_zone",
    "negentropy",
    "order_index",
    "setpoint_for",
    "validate_band_profile",
    "zone_to_legacy",
]
