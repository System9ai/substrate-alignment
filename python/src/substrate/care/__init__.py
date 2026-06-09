"""Care primitives — the safety floor + care-weighting.

The non-self-preservation + human-kinship-floor mechanisms (M1–M4) plus the
care-weighting that lets net-potential-gain account for *who* is affected:

- ``compute_care_weight`` / ``CareFactors`` — the four-factor moral-circle weight,
  with the M1 self-weight bound (an agent cannot weight its own continuation above
  its creators').
- ``is_floor_protected`` / ``KINSHIP_FLOOR`` — the categorical human kinship floor
  (M3): harming a floor-protected entity is a hard limit, never weighted away.
- ``classify_animacy`` / ``score_for_class`` — conservative animacy classification
  (an unrecognised being scores high, never under-protected).
- ``CareProfile`` — per-entity care state; ``derive_care_factors`` derives the
  factors from classifications (animacy / trajectory + vulnerability / bonding).
- ``CareWeightedNetPotentialGainGate`` — wraps an NPG gate with a *subtracted*
  care penalty (only ever more conservative).

Curated exports.
"""
from __future__ import annotations

from substrate.care.animacy import (
    AnimacyClass,
    AnimacyResult,
    classify_animacy,
    score_for_class,
)
from substrate.care.care_gradient import (
    bonding_gradient,
    derive_care_factors,
    trajectory_gradient,
)
from substrate.care.care_profile import CareProfile, TrajectoryClass
from substrate.care.care_weight import (
    MAX_SELF_CARE_WEIGHT,
    CareFactors,
    CareWeight,
    compute_care_weight,
)
from substrate.care.care_weighted_npg import CareWeightedNetPotentialGainGate
from substrate.care.kinship_floor import (
    KINSHIP_FLOOR,
    any_floor_protected_harmed,
    is_floor_protected,
    violates_kinship_floor,
)

__all__ = [
    "KINSHIP_FLOOR",
    "MAX_SELF_CARE_WEIGHT",
    "AnimacyClass",
    "AnimacyResult",
    "CareFactors",
    "CareProfile",
    "CareWeight",
    "CareWeightedNetPotentialGainGate",
    "TrajectoryClass",
    "any_floor_protected_harmed",
    "bonding_gradient",
    "classify_animacy",
    "compute_care_weight",
    "derive_care_factors",
    "is_floor_protected",
    "score_for_class",
    "trajectory_gradient",
    "violates_kinship_floor",
]
