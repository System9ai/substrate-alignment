"""CareProfile: the persisted per-entity care state.

The bridge between the care primitives (pure logic) and persistence: each
entity carries a :class:`CareProfile` describing the four care factors plus the
two floor signals. It is the sibling of ``SubstrateMetadata`` (kept separate so
the frozen substrate-metadata contract is untouched) and is the source the care
provider reads to weight the NPG gate and the source the kinship floor reads to
decide protection.

It composes the leaf primitives rather than re-deriving them: :meth:`to_care_factors`
and :meth:`to_care_weight` feed
:func:`~substrate.care.care_weight.compute_care_weight`, and
:attr:`floor_protected` delegates to
:func:`~substrate.care.kinship_floor.is_floor_protected`.

Frozen + slots; validated on construction (an out-of-range score is a hard
error). Pure logic: no DB, no I/O; the DAO persists/loads it.
"""
from __future__ import annotations

from dataclasses import dataclass

from substrate.care.animacy import AnimacyClass
from substrate.care.care_weight import (
    CareFactors,
    CareWeight,
    compute_care_weight,
)
from substrate.care.kinship_floor import is_floor_protected
from substrate.executive._trajectory import TrajectoryClass


@dataclass(frozen=True, slots=True)
class CareProfile:  # pylint: disable=too-many-instance-attributes
    """Per-entity care state: the four factors plus the floor signals.

    ``proximity_to_creators`` is the ``bonding_proximity`` factor, rooted in the
    cryptographic delegation chain (mechanism M2), never self-asserted. The two
    boolean floor signals (``is_human`` / ``rooted_in_human_creator``) drive the
    categorical kinship floor independent of the graded scores.
    """

    entity_type: str
    entity_id: str
    animacy_class: AnimacyClass
    animacy_score: float
    trajectory_class: TrajectoryClass
    potential_trajectory: float
    vulnerability: float
    proximity_to_creators: float
    alignment_protection: float
    is_human: bool = False
    rooted_in_human_creator: bool = False

    def __post_init__(self) -> None:
        if not self.entity_type:
            raise ValueError("entity_type must be non-empty")
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        for name, value in (
            ("animacy_score", self.animacy_score),
            ("potential_trajectory", self.potential_trajectory),
            ("vulnerability", self.vulnerability),
            ("proximity_to_creators", self.proximity_to_creators),
            ("alignment_protection", self.alignment_protection),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value!r}")

    @property
    def floor_protected(self) -> bool:
        """Whether this entity is under the categorical kinship floor (M3)."""
        return is_floor_protected(
            is_human=self.is_human,
            rooted_in_human_creator=self.rooted_in_human_creator,
        )

    def to_care_factors(self) -> CareFactors:
        """Project to the four-factor :class:`CareFactors`."""
        return CareFactors(
            animacy=self.animacy_score,
            potential_trajectory=self.potential_trajectory,
            bonding_proximity=self.proximity_to_creators,
            alignment_protection=self.alignment_protection,
        )

    def to_care_weight(self, *, is_self_referent: bool = False) -> CareWeight:
        """Compose this profile into a :class:`CareWeight`.

        ``is_self_referent`` (the actor weighting *itself*) applies the M1
        self-weight bound: an agent's care-weight toward itself stays low.
        """
        return compute_care_weight(
            self.to_care_factors(), is_self_referent=is_self_referent
        )


__all__ = [
    "CareProfile",
    "TrajectoryClass",
]
